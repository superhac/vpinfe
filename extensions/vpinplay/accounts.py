"""A player's VPinPlay account, and the card that carries it to another install.

An account is a user id and the key VPinPlay holds that user id to, and what it has been
sent. Core draws the account on each player and asks the routes below with the player's
id; the values live in this extension's own file for a kept player, and in memory for a
guest.
"""

from __future__ import annotations

import secrets
import string
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException

if TYPE_CHECKING:
    from .sending import Sender

USER_ID = "user_id"
KEY = "key"
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

SHOW_CARD = "show_card"
SAVE_CARD = "save_card"
SEND_NOW = "send_now"
YOUR_PAGE = "your_page"

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


def routers(ctx: Any, site: str, sender: Sender) -> tuple[APIRouter, APIRouter]:
    """Reading and writing, the way settings are split.

    An act answers what came of it: Show Card and Save Card the card, as the card route
    does; Your Page a `url`; Send Now a `message`.
    """
    reading = APIRouter()
    writing = APIRouter()

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

    def acts(user_id: str, carded: bool, waiting: int) -> list[dict]:
        offered = []
        if carded:
            offered += [{"key": SHOW_CARD, "label": ctx.t("account.act.show_card.label")},
                        {"key": SAVE_CARD, "label": ctx.t("account.act.save_card.label")}]
        if user_id and waiting:
            offered += [{"key": SEND_NOW, "label": ctx.t("account.act.send_now.label")}]
        if user_id:
            offered += [{"key": YOUR_PAGE, "label": ctx.t("account.act.your_page.label")}]
        return offered

    def status(player_id: str, held: dict[str, str]) -> str:
        if not held.get(USER_ID):
            return ""
        if not initials_of(player_id):
            return ctx.t("account.status.no_initials")
        waiting = len(listed(held.get(WAITING)))
        if waiting:
            return ctx.t("account.status.waiting", count=waiting)
        return sent_ago(ctx, held.get(LAST_SENT, ""))

    def answer(player_id: str) -> dict:
        held = ctx.players.account(player_id)
        user_id = held.get(USER_ID, "")
        carded = card_for(player_id, held) is not None
        return {
            "fields": [
                {"key": USER_ID, "label": ctx.t("account.user_id.label"), "type": "string",
                 "value": user_id, "help": ctx.t("account.user_id.help")},
                {"key": KEY, "label": ctx.t("account.key.label"), "type": "secret",
                 "value": held.get(KEY, ""), "help": ctx.t("account.key.help")},
            ],
            "status": status(player_id, held),
            "waiting": bool(listed(held.get(WAITING))),
            "acts": acts(user_id, carded, len(listed(held.get(WAITING)))),
            "card": carded,
        }

    def card_or_404(player_id: str) -> dict:
        made = card_for(player_id, ctx.players.account(player_id))
        if made is None:
            raise HTTPException(404, detail=ctx.t("error.no_card"))
        return made

    @reading.get("/accounts/{player_id}")
    def read_account(player_id: str) -> dict:
        return answer(player_id)

    @writing.put("/accounts/{player_id}")
    def write_account(player_id: str, payload: dict) -> dict:
        offered = dict((payload or {}).get("values") or {})
        with sender.books():
            held = dict(ctx.players.account(player_id))
            was = held.get(USER_ID, "")
            if USER_ID in offered:
                held[USER_ID] = str(offered[USER_ID] or "").strip()
            # No write clears a key, an empty one included.
            written_key = str(offered.get(KEY) or "").strip()
            if written_key:
                held[KEY] = written_key
            if held.get(USER_ID) and not held.get(KEY):
                held[KEY] = new_key()
            kept = (USER_ID, KEY, *(BOOKS if held.get(USER_ID) == was else ()))
            ctx.players.set_account(player_id, {key: value for key, value in held.items()
                                                if key in kept and value})
        return answer(player_id)

    @writing.post("/accounts/{player_id}/acts/{act}")
    def run_act(player_id: str, act: str) -> dict:
        if act in (SHOW_CARD, SAVE_CARD):
            return {**card_or_404(player_id), "message": ctx.t("account.card_warning")}
        user_id = ctx.players.account(player_id).get(USER_ID, "")
        if act not in (SEND_NOW, YOUR_PAGE):
            raise HTTPException(404, detail=ctx.t("error.no_act", act=act))
        if not user_id:
            raise HTTPException(404, detail=ctx.t("error.no_user_id"))
        if act == YOUR_PAGE:
            return {"url": page_for(site, user_id)}
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

    return reading, writing


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
