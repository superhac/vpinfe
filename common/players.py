"""Who plays on this install, and who the next game counts for.

Kept players are in `players.json`, written whole and atomically like
`common/device_registry.py`. Guests and who is up are held in memory and never written.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from common import events, service_errors
from common.atomic_write import write_atomic
from common.config_access import ConfigSource, cfg_get
from common.i18n import t
from common.install_identity import mint_id
from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.common.players")

PLAYERS_PATH = CONFIG_DIR / "players.json"
SCHEMA = 2
SCHEMA_KEY = "schema"
PLAYERS_KEY = "players"
MIGRATIONS_KEY = "migrations"

INITIALS_LENGTH = 3

OWNER_MIGRATION = "owner_from_2x_initials"
LEGACY_SECTION = "vpinplay"
LEGACY_INITIALS_KEY = "initials"


def normalize_initials(raw: Any) -> str:
    """Initials as they are held: trimmed, upper case."""
    return str(raw or "").strip().upper()


def same_initials(one: Any, other: Any) -> bool:
    """Whether two sets of initials name the same player. Blank names nobody."""
    mine = str(one or "").strip().casefold()
    return bool(mine) and mine == str(other or "").strip().casefold()


def _clean_name(raw: Any) -> str:
    return str(raw or "").strip()


@dataclass(frozen=True)
class Player:
    player_id: str
    name: str = ""
    initials: str = ""
    owner: bool = False
    guest: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        """What `players.json` holds for a kept player. A guest has no record."""
        return {"id": self.player_id, "name": self.name, "initials": self.initials,
                "owner": self.owner, **self.extra}

    @classmethod
    def from_record(cls, raw: dict[str, Any]) -> Player | None:
        player_id = str(raw.get("id", "") or "").strip()
        if not player_id:
            return None
        known = {"id", "name", "initials", "owner"}
        return cls(
            player_id=player_id,
            name=_clean_name(raw.get("name")),
            initials=normalize_initials(raw.get("initials")),
            owner=raw.get("owner") is True,
            # Carried through, so a downgrade does not strip what a newer build filed.
            extra={k: v for k, v in raw.items() if k not in known},
        )


def _schema_of(payload: dict[str, Any]) -> int:
    try:
        return int(payload.get(SCHEMA_KEY) or 0)
    except (TypeError, ValueError):
        return 0


class Roster:
    """Every player on this install, and who is up. One per process - see get_roster()."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else PLAYERS_PATH
        self._lock = threading.RLock()
        self._guests: list[Player] = []
        # Empty means the owner. Ids of players since removed are ignored on read, so a
        # set whose players have all gone falls back to the owner too.
        self._up: tuple[str, ...] = ()

    # -- reading -------------------------------------------------------------

    def players(self) -> list[Player]:
        """The kept players as filed, owner first, then the guests as they joined."""
        with self._lock:
            return self._kept() + list(self._guests)

    def get(self, player_id: str) -> Player | None:
        wanted = (player_id or "").strip()
        return next((p for p in self.players() if p.player_id == wanted), None)

    def owner(self) -> Player | None:
        return next((p for p in self.players() if p.owner), None)

    def up(self) -> list[Player]:
        """Who the next game counts for."""
        with self._lock:
            return self._up_among(self.players())

    def one_up(self) -> Player | None:
        """The player up, when exactly one is. With several up this is nobody."""
        up = self.up()
        return up[0] if len(up) == 1 else None

    def whose(self, initials: str) -> Player | None:
        """The one player these initials name. None when nobody has them or several do."""
        found = [p for p in self.players() if same_initials(p.initials, initials)]
        return found[0] if len(found) == 1 else None

    def state(self) -> dict[str, Any]:
        """The whole roster, as `players.changed` carries it."""
        with self._lock:
            everyone = self.players()
            up = {p.player_id for p in self._up_among(everyone)}
        return {"players": [
            {"id": p.player_id, "name": p.name, "initials": p.initials,
             "owner": p.owner, "guest": p.guest, "up": p.player_id in up,
             "shares_initials_with": [other.player_id for other in everyone
                                      if other.player_id != p.player_id
                                      and same_initials(other.initials, p.initials)]}
            for p in everyone]}

    def player_state(self, player_id: str) -> dict[str, Any]:
        """One player as `state()` lists them."""
        wanted = (player_id or "").strip()
        found = next((one for one in self.state()["players"] if one["id"] == wanted), None)
        if found is None:
            raise _no_player(wanted)
        return found

    # -- writing -------------------------------------------------------------

    def ensure_owner(self, config: ConfigSource) -> Player | None:
        """Make the owner when the roster has none. Returns the one made."""
        with self._changing():
            kept = self._kept()
            if any(p.owner for p in kept):
                return None
            migrations = self._migrations()
            initials = ("" if OWNER_MIGRATION in migrations else normalize_initials(
                cfg_get(config, LEGACY_SECTION, LEGACY_INITIALS_KEY, "")))
            owner = Player(mint_id(), initials=initials, owner=True)
            self._save([owner] + kept, migrations=[
                *migrations, *([] if OWNER_MIGRATION in migrations else [OWNER_MIGRATION])])
            logger.info("Players: made the owner%s",
                        f" with initials {initials}" if initials else ", with no initials")
            return owner

    def add_player(self, name: str = "", initials: str = "") -> Player:
        """A kept player. Refuses initials that are not three characters or that another
        kept player already has."""
        with self._changing():
            kept = self._kept()
            player = Player(mint_id(), name=_clean_name(name),
                            initials=_kept_initials(initials, kept))
            self._save(kept + [player])
            return player

    def add_guest(self, initials: str, name: str = "") -> Player:
        """A guest joins, and is up alone."""
        with self._changing():
            guest = Player(mint_id(), name=_clean_name(name),
                           initials=_guest_initials(initials), guest=True)
            self._guests.append(guest)
            self._up = (guest.player_id,)
            return guest

    def update_player(self, player_id: str, *, name: str | None = None,
                      initials: str | None = None) -> Player:
        """Change a name or initials; None leaves one as it is."""
        wanted = (player_id or "").strip()
        with self._changing():
            kept = self._kept()
            for index, current in enumerate(kept):
                if current.player_id == wanted:
                    others = kept[:index] + kept[index + 1:]
                    changed = replace(
                        current,
                        name=current.name if name is None else _clean_name(name),
                        initials=(current.initials if initials is None else
                                  _kept_initials(initials, others, held=current.initials)))
                    if changed != current:
                        kept[index] = changed
                        self._save(kept)
                    return changed
            for index, current in enumerate(self._guests):
                if current.player_id == wanted:
                    changed = replace(
                        current,
                        name=current.name if name is None else _clean_name(name),
                        initials=(current.initials if initials is None else
                                  _guest_initials(initials, held=current.initials)))
                    self._guests[index] = changed
                    return changed
        raise _no_player(wanted)

    def remove(self, player_id: str) -> Player:
        """Remove a kept player, or sign a guest out. The owner cannot be removed."""
        wanted = (player_id or "").strip()
        with self._changing():
            kept = self._kept()
            found = next((p for p in kept if p.player_id == wanted), None)
            if found is not None:
                if found.owner:
                    raise service_errors.RefusedError(t("error.players.owner_not_removable"))
                self._save([p for p in kept if p.player_id != wanted])
            else:
                found = next((p for p in self._guests if p.player_id == wanted), None)
                if found is None:
                    raise _no_player(wanted)
                self._guests.remove(found)
            self._up = tuple(one for one in self._up if one != wanted)
            return found

    def set_up(self, player_id: str, up: bool = True) -> list[Player]:
        """Put one player up, or take them down. Returns who is up afterwards."""
        wanted = (player_id or "").strip()
        with self._changing():
            everyone = self.players()
            if not any(p.player_id == wanted for p in everyone):
                raise _no_player(wanted)
            current = [p.player_id for p in self._up_among(everyone)]
            if up:
                self._up = tuple(current + ([] if wanted in current else [wanted]))
            else:
                self._up = tuple(one for one in current if one != wanted)
            return self._up_among(everyone)

    def set_who_is_up(self, player_ids: list[str]) -> list[Player]:
        """Put exactly these players up. An id nobody has refuses the whole set; an empty
        set leaves the owner up. Returns who is up afterwards."""
        wanted = [(one or "").strip() for one in player_ids]
        with self._changing():
            everyone = self.players()
            known = {p.player_id for p in everyone}
            missing = next((one for one in wanted if one not in known), None)
            if missing is not None:
                raise _no_player(missing)
            self._up = tuple(dict.fromkeys(wanted))
            return self._up_among(everyone)

    # -- internals -----------------------------------------------------------

    @contextmanager
    def _changing(self) -> Iterator[None]:
        """Hold the lock for a change, then announce it if the roster moved.

        The event goes out after the lock is released: a subscriber is arbitrary code
        and may read the roster back from another thread.
        """
        with self._lock:
            before = self.state()
            yield
            after = self.state()
        if after != before:
            events.emit(events.PLAYERS_CHANGED, state=after)

    def _up_among(self, everyone: list[Player]) -> list[Player]:
        up = [p for p in everyone if p.player_id in self._up]
        if up:
            return up
        return [p for p in everyone if p.owner][:1]

    def _read(self) -> dict[str, Any]:
        """The file's contents when it is the roster, else nothing."""
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Players at %s is unreadable; treating it as empty", self.path)
            return {}
        if not isinstance(payload, dict) or _schema_of(payload) < SCHEMA:
            return {}
        return payload

    def _kept(self) -> list[Player]:
        raw = self._read().get(PLAYERS_KEY)
        if not isinstance(raw, list):
            return []
        kept = [player for player in (Player.from_record(entry) for entry in raw
                                      if isinstance(entry, dict)) if player is not None]
        # One owner, whatever a hand edit says: a second could never be removed.
        first = next((p.player_id for p in kept if p.owner), None)
        return sorted((p if p.player_id == first or not p.owner else replace(p, owner=False)
                       for p in kept), key=lambda p: not p.owner)

    def _migrations(self) -> list[str]:
        raw = self._read().get(MIGRATIONS_KEY)
        return [str(name) for name in raw or [] if str(name).strip()]

    def _save(self, kept: list[Player], migrations: list[str] | None = None) -> None:
        # Whatever else a newer build put in the file is kept, and so is its number.
        held = self._read()
        payload = {**held,
                   SCHEMA_KEY: max(SCHEMA, _schema_of(held)),
                   MIGRATIONS_KEY: self._migrations() if migrations is None else migrations,
                   PLAYERS_KEY: [player.as_record() for player in kept]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(self.path,
                     lambda handle: json.dump(payload, handle, indent=2, ensure_ascii=False))


def _no_player(player_id: str) -> service_errors.NotFoundError:
    return service_errors.NotFoundError(t("error.players.no_player", player_id=player_id))


def _new_initials(raw: Any, held: str) -> str:
    wanted = normalize_initials(raw)
    if same_initials(wanted, held):
        return held
    if wanted and len(wanted) != INITIALS_LENGTH:
        raise service_errors.RefusedError(t("error.players.initials_length"))
    return wanted


def _kept_initials(raw: Any, others: list[Player], held: str = "") -> str:
    wanted = _new_initials(raw, held)
    if wanted == held:
        return held
    clash = next((p for p in others if same_initials(p.initials, wanted)), None)
    if clash is not None:
        raise service_errors.RefusedError(
            t("error.players.initials_taken", player=clash.name or clash.initials))
    return wanted


def _guest_initials(raw: Any, held: str = "") -> str:
    wanted = _new_initials(raw, held)
    if not wanted:
        raise service_errors.RefusedError(t("error.players.guest_needs_initials"))
    return wanted


_roster: Roster | None = None
_roster_lock = threading.Lock()


def get_roster() -> Roster:
    """This install's roster. One per process, because the guests and who is up live in
    it and a second would hold different ones."""
    global _roster
    with _roster_lock:
        if _roster is None:
            _roster = Roster()
        return _roster


def reset_for_tests(path: Path | None = None) -> None:
    global _roster
    with _roster_lock:
        _roster = Roster(path) if path is not None else None
