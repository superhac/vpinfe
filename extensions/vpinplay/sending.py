"""Who is sent which game, and when.

An account's books - what it was sent, what waits, when a send last went - are values of
the account itself, so they are kept and forgotten wherever the account is.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any

from . import sync
from .accounts import KEY, LAST_SENT, SENT, USER_ID, WAITING, listed

PLAY_RECORDED = "table.play_recorded"
GAME_RATED = "game.rated"


def _on_a_thread(work: Callable[[], object]) -> None:
    threading.Thread(target=work, name="vpinplay-send", daemon=True).start()


@dataclass(frozen=True)
class Holder:
    """One player's account, as it stood when something was to be sent."""

    player_id: str
    owner: bool
    initials: str
    user_id: str
    key: str


@dataclass(frozen=True)
class Played:
    """What one game's end said about it, for one player."""

    game_id: str
    reading: dict | None
    credited: bool
    record: dict | None


class Sender:
    def __init__(self, ctx: Any, endpoint_of: Callable[[], str]) -> None:
        self._ctx = ctx
        self._endpoint_of = endpoint_of
        # Held across a whole run, network included, so two runs for one account never
        # send the same waiting game twice.
        self._sending = threading.Lock()
        # Held only to read and write an account's books, so an edit in the Console never
        # waits on the network.
        self._books = threading.Lock()

    # -- what core says ------------------------------------------------------

    def played(self, **payload: Any) -> None:
        """`table.play_recorded`. What a run needs is read here, on the launch thread, so
        a guest who signs out before it starts is still sent as they were."""
        game_id = str(payload.get("game_id") or "").strip()
        if payload.get("private") or not game_id:
            return
        up = [str(one.get("id") or "") for one in payload.get("up") or []]
        credited = {str((one.get("player") or {}).get("id") or "")
                    for one in payload.get("new_entries") or []}
        runs = []
        for player_id in dict.fromkeys([*up, *credited]):
            holder = self._holder(player_id)
            if holder is None or not self._ctx.players.sharing(player_id):
                continue
            record = None if holder.owner else self._ctx.players.record(player_id, game_id)
            runs.append((holder, Played(game_id, payload.get("reading"),
                                        player_id in credited, record)))
        if runs:
            _on_a_thread(lambda: [self._run(holder, played) for holder, played in runs])

    def rated(self, **payload: Any) -> None:
        """`game.rated`, for a sharing account whose books hold the game."""
        game_id = str(payload.get("game_id") or "").strip()
        player_id = str((payload.get("player") or {}).get("id") or "")
        holder = self._holder(player_id)
        if (holder is None or not game_id or not self._ctx.players.sharing(player_id)
                or game_id not in self._sent(player_id)):
            return
        _on_a_thread(partial(self._run, holder, Played(game_id, None, False, None)))

    # -- what a person asks for ------------------------------------------------

    def books(self) -> threading.Lock:
        """Held while an account's values are read and written back, by a send and by an
        edit alike."""
        return self._books

    def send_now(self, player_id: str) -> tuple[int, int]:
        """Try every game waiting for this account again, now. Answers how many went and
        how many are still waiting."""
        holder = self._holder(player_id)
        if holder is None:
            return 0, len(self.waiting(player_id))
        return self._run(holder, None)

    def waiting(self, player_id: str) -> list[str]:
        return listed(self._ctx.players.account(player_id).get(WAITING))

    # -- a run -----------------------------------------------------------------

    def _run(self, holder: Holder, played: Played | None) -> tuple[int, int]:
        """Send `played`, if any, and whatever is waiting for this account, in one
        request. Never raises."""
        with self._sending:
            try:
                return self._send(holder, played)
            except Exception:
                self._ctx.logger.exception("Could not send to VPinPlay for %s",
                                           holder.initials or holder.player_id)
                if played is not None:
                    self._book(holder, waiting=[played.game_id])
                return 0, len(self.waiting(holder.player_id))

    def _send(self, holder: Holder, played: Played | None) -> tuple[int, int]:
        where = sync.endpoint_for(self._endpoint_of())
        games = list(dict.fromkeys([*([played.game_id] if played else []),
                                    *self.waiting(holder.player_id)]))
        built: dict[str, dict] = {}
        unsent: list[str] = []
        for game_id in games:
            now_played = played if played and played.game_id == game_id else None
            try:
                one = self._payload(where, holder, game_id, now_played)
            except CannotReadTheirsError:
                unsent.append(game_id)
                continue
            if one is not None:
                built[game_id] = one
        if not built:
            return 0, self._book(holder, waiting=unsent, settled=games)

        payload = sync.envelope(holder.user_id, holder.initials, holder.key,
                                list(built.values()), self._ctx.host_version, sync.now())
        try:
            result = sync.send(where, payload, sync.GAME_TIMEOUT)
        except Exception as exc:
            result = {"ok": False, "status_code": None,
                      "response_body": self._ctx.why(exc, at=where)}
        if not result["ok"]:
            self._ctx.logger.warning("VPinPlay did not take %s game(s) for %s (%s): %s",
                                     len(built), holder.initials, result["status_code"],
                                     result["response_body"])
            return 0, self._book(holder, waiting=[*built, *unsent], settled=games)
        self._ctx.logger.info("Sent %s game(s) to VPinPlay for %s", len(built),
                              holder.initials)
        return len(built), self._book(holder, sent=list(built), waiting=unsent,
                                      settled=games)

    def _payload(self, where: str, holder: Holder, game_id: str,
                 played: Played | None) -> dict | None:
        """One game for this account, or None where there is nothing to send: a Private
        game, a game no catalog matched, a game no longer here. Raises
        `CannotReadTheirsError` where what VPinPlay holds for a player other than the owner
        could not be read, which leaves the game waiting."""
        try:
            game = self._ctx.games.get_game(game_id)
        except Exception:
            self._ctx.logger.info("Not sending %s: it is no longer here", game_id)
            return None
        vps_id = str(game.get("vps_id") or "").strip()
        if game.get("private") or not vps_id:
            return None
        tables = self._ctx.games.game_tables(game_id)["tables"]
        table = next((one for one in tables if one.get("default")),
                     tables[0] if tables else None)
        library = sync.from_library(game)
        reading = played.reading if played and played.reading else library["user"]["score"]
        if holder.owner:
            return sync.payload_for({**library, "user": {**library["user"],
                                                         "score": reading}}, table)
        held = sync.their_record(where, holder.user_id, vps_id, sync.GAME_TIMEOUT)
        if held is None:
            self._ctx.logger.warning("Not sending %s for %s yet: VPinPlay could not say "
                                     "what it already holds", game.get("name"),
                                     holder.initials)
            raise CannotReadTheirsError
        mine = (played.record if played and played.record is not None
                else self._ctx.players.record(holder.player_id, game_id)) or {}
        return sync.payload_for_player(game, table, mine, held, reading, holder.initials,
                                       credited=bool(played and played.credited))

    # -- the books -------------------------------------------------------------

    def _holder(self, player_id: str) -> Holder | None:
        """The account a send would go under, or None where it cannot: no user id, no
        key, or a player with no initials to send."""
        player = self._ctx.players.get(player_id) if player_id else None
        if player is None:
            return None
        held = self._ctx.players.account(player_id)
        user_id, key = held.get(USER_ID, ""), held.get(KEY, "")
        initials = str(player.get("initials") or "").strip().upper()
        if not (user_id and key and initials):
            return None
        return Holder(player_id, bool(player.get("owner")), initials, user_id, key)

    def _sent(self, player_id: str) -> set[str]:
        return set(listed(self._ctx.players.account(player_id).get(SENT)))

    def _book(self, holder: Holder, *, sent: Iterable[str] = (),
              waiting: Iterable[str] = (), settled: Iterable[str] = ()) -> int:
        """Write what a run came to: `settled` leaves the waiting list, then `waiting`
        joins it and `sent` joins what has been sent. Answers how many are waiting. An
        account whose user id changed meanwhile, or a player who has left, is not
        written."""
        sent, waiting, settled = list(sent), list(waiting), set(settled)
        with self._books:
            held = dict(self._ctx.players.account(holder.player_id))
            if held.get(USER_ID) != holder.user_id:
                return 0
            left = [one for one in listed(held.get(WAITING)) if one not in settled]
            now_waiting = list(dict.fromkeys([*left, *waiting]))
            held[WAITING] = ",".join(now_waiting)
            if sent:
                held[SENT] = ",".join(dict.fromkeys([*listed(held.get(SENT)), *sent]))
                held[LAST_SENT] = datetime.now(UTC).isoformat(timespec="seconds")
            try:
                self._ctx.players.set_account(holder.player_id,
                                              {k: v for k, v in held.items() if v})
            except Exception:
                self._ctx.logger.info("Not keeping what was sent for %s, who has left",
                                      holder.initials)
            return len(now_waiting)


class CannotReadTheirsError(Exception):
    """VPinPlay could not say what it holds for a player, so nothing is sent for them."""
