"""A fixture extension that uses the whole contract, and does nothing real with it.

Committed rather than written into a temporary directory by the test that loads it, so
the worked example of an extension is something an author can read - the same reason
`apps/generic` is a file rather than a stub. It reaches VPinFE only through the context
it is handed.

Its secrets are answered with their values on purpose: core takes them out on the way to
a client, and the tests hold it to that.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

# The core event it listens to. A name, not an import: the event vocabulary is part of
# the platform ABI the manifest names, and an extension holds no reference into core.
GAME_SELECTED = "game.selected"

# The one kind of card it reads, and the version of it it writes.
CARD = "sample_card"
CARD_VERSION = 1


def register(ctx) -> None:
    ctx.logger.info("Registering")
    seen: list[dict] = []
    router = APIRouter()
    writing = APIRouter()

    @router.get("/hello")
    def hello() -> dict:
        return {"name": ctx.name, "greeting": ctx.config.get("greeting", "hello")}

    @router.get("/seen")
    def how_many() -> dict:
        return {"seen": len(seen)}

    @router.get("/boom")
    def boom() -> dict:
        raise RuntimeError("the fixture was asked to fail")

    def settings() -> dict:
        return {"fields": [
            {"key": "greeting", "label": "Greeting", "type": "string",
             "value": ctx.config.get("greeting", "")},
            {"key": "token", "label": "Token", "type": "secret",
             "value": ctx.config.get("token", "")}]}

    @router.get("/settings")
    def read_settings() -> dict:
        return settings()

    @writing.put("/settings")
    def write_settings(payload: dict) -> dict:
        for key, value in dict(payload.get("values") or {}).items():
            ctx.config.set(key, str(value))
        return settings()

    def account(player_id: str) -> dict:
        held = ctx.players.account(player_id)
        return {"fields": [
                    {"key": "handle", "label": "Handle", "type": "string",
                     "value": held.get("handle", "")},
                    {"key": "token", "label": "Token", "type": "secret",
                     "value": held.get("token", "")}],
                "status": "Ready" if held.get("handle") else "No handle",
                "acts": [{"key": "ping", "label": "Ping"}],
                "card": bool(held.get("handle") and held.get("token"))}

    @router.get("/accounts/{player_id}")
    def read_account(player_id: str) -> dict:
        return account(player_id)

    @writing.put("/accounts/{player_id}")
    def write_account(player_id: str, payload: dict) -> dict:
        held = ctx.players.account(player_id)
        ctx.players.set_account(player_id, {**held, **dict(payload.get("values") or {})})
        return account(player_id)

    @writing.post("/accounts/{player_id}/acts/{act}")
    def act(player_id: str, act: str) -> dict:
        if act != "ping":
            raise HTTPException(404, detail="No such act")
        return {"message": f"Pinged {ctx.players.account(player_id).get('handle', '')}"}

    @router.get("/accounts/{player_id}/card")
    def card(player_id: str) -> dict:
        held = ctx.players.account(player_id)
        player = ctx.players.get(player_id) or {}
        if not (held.get("handle") and held.get("token")):
            raise HTTPException(404, detail="No card yet")
        return {"card": {"type": CARD, "version": CARD_VERSION, "handle": held["handle"],
                         "token": held["token"], "initials": player.get("initials", "")},
                "filename": f"sample-{held['handle']}"}

    @writing.post("/accounts/cards")
    def read_card(payload: dict) -> dict:
        found = dict(payload.get("card") or {})
        if found.get("version") != CARD_VERSION:
            raise HTTPException(400, detail="Not a card this reads")
        return {"name": "", "initials": str(found.get("initials") or ""),
                "values": {"handle": str(found.get("handle") or ""),
                           "token": str(found.get("token") or "")}}

    def on_selected(**payload) -> None:
        if payload.get("game_id") == "fail":
            raise RuntimeError("the fixture was asked to fail")
        seen.append(payload)
        ctx.events.publish("noticed", game_id=payload.get("game_id"))

    ctx.events.subscribe(GAME_SELECTED, on_selected)
    ctx.add_router(router, scope=ctx.scope("read"))
    ctx.add_router(writing, scope=ctx.scope("write"))
    ctx.ui.settings("/settings")
    ctx.ui.account("/accounts", label="Sample", cards=(CARD,))
