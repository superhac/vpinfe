"""A fixture extension that uses the whole contract, and does nothing real with it.

Committed rather than written into a temporary directory by the test that loads it, so
the worked example of an extension is something an author can read - the same reason
`apps/generic` is a file rather than a stub. It reaches VPinFE only through the context
it is handed.
"""

from __future__ import annotations

from fastapi import APIRouter

# The core event it listens to. A name, not an import: the event vocabulary is part of
# the platform ABI the manifest names, and an extension holds no reference into core.
GAME_SELECTED = "game.selected"


def register(ctx) -> None:
    ctx.logger.info("Registering")
    seen: list[dict] = []
    router = APIRouter()

    @router.get("/hello")
    def hello() -> dict:
        return {"name": ctx.name, "greeting": ctx.config.get("greeting", "hello")}

    @router.get("/seen")
    def how_many() -> dict:
        return {"seen": len(seen)}

    @router.get("/boom")
    def boom() -> dict:
        raise RuntimeError("the fixture was asked to fail")

    def on_selected(**payload) -> None:
        if payload.get("game_id") == "fail":
            raise RuntimeError("the fixture was asked to fail")
        seen.append(payload)
        ctx.events.publish("noticed", game_id=payload.get("game_id"))

    ctx.events.subscribe(GAME_SELECTED, on_selected)
    ctx.add_router(router, scope=ctx.scope("read"))
