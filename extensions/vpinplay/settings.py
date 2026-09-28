"""What VPinPlay is configured with, offered in the shape core renders.

The fields are declared and core draws them, so an extension's settings look like every
other setting in the Console. Values live in this extension's own store, which is the
only place a change reaches: core does not read its `[vpinplay]` section, and a write
there is lost without saying so. A player's user id and key are their account
(`accounts.py`), not a setting.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

ENDPOINT_KEY = "endpoint"


def fields(ctx: Any, default_endpoint: str) -> list[dict]:
    """Every setting, with what it is set to now."""
    held = ctx.config.all() if hasattr(ctx.config, "all") else {}
    return [
        {"key": ENDPOINT_KEY, "label": ctx.t("settings.endpoint.label"), "type": "string",
         "value": str(held.get(ENDPOINT_KEY) or ""), "placeholder": default_endpoint,
         "help": ctx.t("settings.endpoint.help", default=default_endpoint)},
    ]


def routers(ctx: Any, default_endpoint: str) -> tuple[APIRouter, APIRouter]:
    """Reading and writing, so seeing a setting and changing it are separate
    permissions."""
    reading = APIRouter()
    writing = APIRouter()

    @reading.get("/settings")
    def read_settings() -> dict:
        return {"fields": fields(ctx, default_endpoint)}

    @writing.put("/settings")
    def write_settings(payload: dict) -> dict:
        offered = dict((payload or {}).get("values") or {})
        known = {one["key"] for one in fields(ctx, default_endpoint)}
        for key, value in offered.items():
            if key not in known:
                continue
            ctx.config.set(key, str(value or ""))
        return {"fields": fields(ctx, default_endpoint)}

    return reading, writing
