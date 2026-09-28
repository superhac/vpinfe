"""A player's VPinPlay account: a user id, chosen free and claimed deliberately, and the
key VPinPlay ties it to once it is.

An account is unclaimed while it holds a user id and no key - free to change or drop,
never sent. **Claiming** checks the id is still free, mints the key and registers the pair
with an empty send; nothing before that reaches VPinPlay. Core draws the account on each
player and asks the routes below with the player's id; the values live in this extension's
own file for a kept player, and in memory for a guest.
"""

from __future__ import annotations

import logging
import secrets
import string
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import requests
from fastapi import APIRouter, HTTPException

from . import client, sync

if TYPE_CHECKING:
    from collections.abc import Callable

    from .sending import Sender

logger = logging.getLogger("vpinfe.ext.vpinplay.accounts")


def _on_a_thread(work: Callable[[], object]) -> None:
    threading.Thread(target=work, name="vpinplay-resolve", daemon=True).start()

USER_ID = "user_id"
KEY = "key"
CLAIMED = "claimed"
CONSENTED = "consented"
# What the account has been sent and what is waiting to go, as comma-separated game ids,
# and when a send last went. About the user id they were sent under.
SENT = "sent"
WAITING = "waiting"
LAST_SENT = "last_sent"
BOOKS = (SENT, WAITING, LAST_SENT)

# The card 2.x's Download QR Code saved. Cards are on people's phones, so this is read for
# good and never changes shape.
CARD_TYPE = "vpinplay_identity"
CARD_VERSION = 1
CARD_INITIALS_AT_MOST = 3

SEND_NOW = "send_now"
CLAIM = "claim"
CONSENT = "consent"
DISCONNECT = "disconnect"

PLAYERS_CHANGED = "players.changed"

# The settings the owner's account is made from, and the mark that it has been.
SETTINGS_USER_ID = "user_id"
SETTINGS_MACHINE_ID = "machine_id"
OWNER_ACCOUNT_MADE = "owner_account_made"


def listed(held: Any) -> list[str]:
    """Game ids as the books keep them."""
    return [one for one in str(held or "").split(",") if one.strip()]


def new_key(length: int = 64) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def page_for(site: str, user_id: str) -> str:
    return f"{site}/players.html?userid={quote(user_id)}"


def routers(ctx: Any, site: str, sender: Sender,
           endpoint: Callable[[], str]) -> tuple[APIRouter, APIRouter]:
    """Reading and writing, the way settings are split.

    An act answers what came of it: Send Now a `message`; Claim, Consent and Disconnect
    the account, as `GET {base}/{player_id}` does.
    """
    reading = APIRouter()
    writing = APIRouter()
    # Per extension load: a guest's in-memory account resolves again after a restart
    # the way a kept one does.
    resolved: dict[str, bool] = {}
    asking: set[str] = set()
    resolve_lock = threading.Lock()

    def ensure_resolved(user_id: str) -> None:
        with resolve_lock:
            if user_id in resolved or user_id in asking:
                return
            asking.add(user_id)

        def work() -> None:
            where = sync.endpoint_for(endpoint())
            try:
                available = client.check_available(where, user_id)
            except Exception:
                available = False
            with resolve_lock:
                resolved[user_id] = available
                asking.discard(user_id)

        _on_a_thread(work)

    def initials_of(player_id: str) -> str:
        return str((ctx.players.get(player_id) or {}).get("initials") or "").strip().upper()

    def card_for(player_id: str, held: dict[str, str]) -> dict | None:
        user_id, key = held.get(USER_ID, ""), held.get(KEY, "")
        initials = initials_of(player_id)
        if not (user_id and key and initials):
            return None
        return {"card": {"type": CARD_TYPE, "version": CARD_VERSION, "userId": user_id,
                         "initials": initials, "machineId": key},
                "filename": f"vpinplay-{user_id}"}

    def acts(claimed: bool, waiting: int) -> list[dict]:
        if claimed and waiting:
            return [{"key": SEND_NOW, "label": ctx.t("account.act.send_now.label")}]
        return []

    def status(claimed: bool, held: dict[str, str], waiting: int) -> str:
        if not claimed:
            return ""
        if waiting:
            return ctx.t("account.status.waiting", count=waiting)
        return sent_ago(ctx, held.get(LAST_SENT, ""))

    def claimed_of(user_id: str, key: str, held: dict[str, str]) -> bool:
        if not (user_id and key):
            return False
        if held.get(CLAIMED):
            return True
        known = resolved.get(user_id)
        if known is None:
            ensure_resolved(user_id)
            return True
        return not known

    def answer(player_id: str) -> dict:
        held = ctx.players.account(player_id)
        user_id, key = held.get(USER_ID, ""), held.get(KEY, "")
        claimed = claimed_of(user_id, key, held)
        waiting = len(listed(held.get(WAITING)))
        return {
            "fields": [],
            "user_id": user_id,
            "claimed": claimed,
            "needs_consent": not bool(held.get(CONSENTED)),
            "page": page_for(site, user_id) if claimed else "",
            "status": status(claimed, held, waiting),
            "waiting": bool(waiting),
            "waiting_count": waiting,
            "acts": acts(claimed, waiting),
            "card": card_for(player_id, held) is not None,
        }

    def card_or_404(player_id: str) -> dict:
        made = card_for(player_id, ctx.players.account(player_id))
        if made is None:
            raise HTTPException(404, detail=ctx.t("error.no_card"))
        return made

    def reached(url: str, user_id: str) -> bool:
        """Whether `user_id` is free, asked fresh. Raises where VPinPlay could not be."""
        try:
            return client.check_available(url, user_id)
        except requests.RequestException as exc:
            logger.warning("Could not reach VPinPlay to check %r: %s", user_id, exc)
            raise HTTPException(503, detail=ctx.t("error.unreachable")) from exc

    def claim(player_id: str) -> dict:
        held = dict(ctx.players.account(player_id))
        user_id = held.get(USER_ID, "").strip()
        if not user_id:
            raise HTTPException(400, detail=ctx.t("error.no_user_id"))
        if held.get(KEY):
            raise HTTPException(400, detail=ctx.t("error.already_claimed"))
        initials = initials_of(player_id)
        if not initials:
            raise HTTPException(400, detail=ctx.t("error.no_initials"))
        where = sync.endpoint_for(endpoint())
        if not reached(where, user_id):
            raise HTTPException(400, detail=ctx.t("error.taken"))
        key = new_key()
        try:
            result = client.register(where, user_id, initials, key, ctx.host_version)
        except requests.RequestException as exc:
            logger.warning("Could not reach VPinPlay to claim %r: %s", user_id, exc)
            raise HTTPException(503, detail=ctx.t("error.unreachable")) from exc
        if not result.get("ok"):
            raise HTTPException(503, detail=ctx.t("error.claim_failed"))
        with sender.books():
            ctx.players.set_account(player_id, {USER_ID: user_id, KEY: key,
                                                CLAIMED: "true", CONSENTED: "true"})
        return answer(player_id)

    def consent(player_id: str) -> dict:
        """Marks Share's consent seen, with no send - safe to call whether or not the
        account is already claimed."""
        with sender.books():
            held = dict(ctx.players.account(player_id))
            held[CONSENTED] = "true"
            ctx.players.set_account(player_id, {k: v for k, v in held.items() if v})
        return answer(player_id)

    def disconnect(player_id: str) -> dict:
        with sender.books():
            ctx.players.set_account(player_id, {})
        return answer(player_id)

    # A path of its own, one segment away from `/accounts/{player_id}` below: this must
    # never be read as that route with `player_id="available"`.
    @reading.get("/available")
    def check_available(candidate: str) -> dict:
        where = sync.endpoint_for(endpoint())
        return {"available": reached(where, candidate.strip().lower())}

    @reading.get("/accounts/{player_id}")
    def read_account(player_id: str) -> dict:
        return answer(player_id)

    @writing.put("/accounts/{player_id}")
    def write_account(player_id: str, payload: dict) -> dict:
        """Saves what is chosen; claiming is its own act, never a side effect of a write."""
        offered = dict((payload or {}).get("values") or {})
        with sender.books():
            held = dict(ctx.players.account(player_id))
            was = held.get(USER_ID, "")
            if USER_ID in offered:
                held[USER_ID] = str(offered[USER_ID] or "").strip().lower()
            # No write clears a key, an empty one included. A card writes both at once.
            written_key = str(offered.get(KEY) or "").strip()
            if written_key:
                held[KEY] = written_key
            elif held.get(USER_ID) and held.get(USER_ID) != was:
                held.pop(CLAIMED, None)
            kept = (USER_ID, KEY, CLAIMED, CONSENTED,
                   *(BOOKS if held.get(USER_ID) == was else ()))
            ctx.players.set_account(player_id, {key: value for key, value in held.items()
                                                if key in kept and value})
        written = ctx.players.account(player_id)
        if written.get(USER_ID) and written.get(KEY) and not written.get(CLAIMED):
            ensure_resolved(written[USER_ID])
        return answer(player_id)

    @writing.post("/accounts/{player_id}/acts/{act}")
    def run_act(player_id: str, act: str) -> dict:
        if act == CLAIM:
            return claim(player_id)
        if act == CONSENT:
            return consent(player_id)
        if act == DISCONNECT:
            return disconnect(player_id)
        if act != SEND_NOW:
            raise HTTPException(404, detail=ctx.t("error.no_act", act=act))
        held = ctx.players.account(player_id)
        if not (held.get(USER_ID) and held.get(KEY)):
            raise HTTPException(404, detail=ctx.t("error.no_user_id"))
        if not sender.waiting(player_id):
            return {"message": ctx.t("account.nothing_waiting")}
        went, waiting = sender.send_now(player_id)
        if waiting:
            return {"message": ctx.t("account.status.waiting", count=waiting)}
        return {"message": ctx.t("account.sent", count=went)}

    @reading.get("/accounts/{player_id}/card")
    def read_card_of(player_id: str) -> dict:
        return card_or_404(player_id)

    @writing.post("/accounts/cards")
    def read_card(payload: dict) -> dict:
        card = checked(ctx, (payload or {}).get("card"))
        return {"name": card["userId"], "initials": card["initials"],
                "values": {USER_ID: card["userId"], KEY: card["machineId"]}}

    resolve_unmarked(ctx, ensure_resolved)

    return reading, writing


def resolve_unmarked(ctx: Any, ensure_resolved: Callable[[str], None]) -> None:
    """Every held account with a key and no `claimed` marker gets the same one-time
    resolve a fresh write does."""
    for player in ctx.players.roster():
        held = ctx.players.account(str(player.get("id") or ""))
        user_id, key = held.get(USER_ID, ""), held.get(KEY, "")
        if user_id and key and not held.get(CLAIMED):
            ensure_resolved(user_id)


def sent_ago(ctx: Any, when: str) -> str:
    """When the last send went, in words; nothing where none has."""
    try:
        then = datetime.fromisoformat(str(when or "").replace("Z", "+00:00"))
    except ValueError:
        return ""
    seconds = max(0, int((datetime.now(UTC) - then).total_seconds()))
    if seconds < 60:
        return ctx.t("account.status.sent_just_now")
    if seconds < 3600:
        return ctx.t("account.status.sent_minutes_ago", count=seconds // 60)
    if seconds < 86400:
        return ctx.t("account.status.sent_hours_ago", count=seconds // 3600)
    return ctx.t("account.status.sent_days_ago", count=seconds // 86400)


def checked(ctx: Any, card: Any) -> dict[str, Any]:
    """A card as 2.x read one: the same checks, in the same order, in 2.x's words."""
    def refused(said: str) -> HTTPException:
        return HTTPException(400, detail=said)

    if not isinstance(card, dict):
        raise refused(ctx.t("error.card.not_an_object"))
    kind = str(card.get("type", "") or "").strip()
    user_id = str(card.get("userId", "") or "").strip()
    initials = str(card.get("initials", "") or "").strip().upper()
    machine_id = str(card.get("machineId", "") or "").strip()
    try:
        version = int(card.get("version", 0))
    except (TypeError, ValueError):
        raise refused(ctx.t("error.card.version_invalid")) from None
    if kind != CARD_TYPE:
        raise refused(ctx.t("error.card.type", kind=kind) if kind
                      else ctx.t("error.card.type_missing"))
    if version != CARD_VERSION:
        raise refused(ctx.t("error.card.version", version=version))
    if not user_id:
        raise refused(ctx.t("error.card.no_user_id"))
    if not initials:
        raise refused(ctx.t("error.card.no_initials"))
    if len(initials) > CARD_INITIALS_AT_MOST:
        raise refused(ctx.t("error.card.initials_length"))
    if not machine_id:
        raise refused(ctx.t("error.card.no_machine_id"))
    return {"type": kind, "version": version, "userId": user_id, "initials": initials,
            "machineId": machine_id}


def move_owner_account(ctx: Any) -> None:
    """Make the owner's account from this extension's own settings, once there is an
    owner, and only once."""
    lock = threading.Lock()
    settled = False

    def make(owner_id: str) -> None:
        user_id = str(ctx.config.get(SETTINGS_USER_ID, "") or "").strip()
        if not user_id:
            return
        if not ctx.players.account(owner_id):
            key = str(ctx.config.get(SETTINGS_MACHINE_ID, "") or "").strip()
            ctx.players.set_account(owner_id, {USER_ID: user_id, KEY: key or new_key()})
            ctx.logger.info("Made the owner's VPinPlay account from its settings")
        ctx.config.set(OWNER_ACCOUNT_MADE, "true")

    def move(**_payload: Any) -> None:
        nonlocal settled
        with lock:
            if settled:
                return
            try:
                if str(ctx.config.get(OWNER_ACCOUNT_MADE, "") or "").strip():
                    settled = True
                    return
                owner = next((one for one in ctx.players.roster() if one.get("owner")),
                             None)
                if owner is None:
                    return
                settled = True
                make(str(owner["id"]))
            except Exception:
                settled = True
                ctx.logger.exception("Could not make the owner's VPinPlay account; "
                                     "trying again at the next start")

    move()
    ctx.events.subscribe(PLAYERS_CHANGED, move)
