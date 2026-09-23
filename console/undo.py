"""The message a reversible act leaves behind, and the Undo on it. Every reversible act
says what it did through here."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from common.i18n import t

logger = logging.getLogger("vpinfe.console.undo")

STANDS_S = 8.0


def offer(said: str, reverse: Callable[[], Awaitable[Any]], *, warn: bool = False,
          icon: str | None = None) -> ui.notification:
    """Say what was done, with Undo running `reverse` once: green, or amber where `warn`,
    with `icon` in place of the kind's own."""
    client = ui.context.client
    spent = {"undone": False}
    note = ui.notification(said, type="warning" if warn else "positive",
                           icon=icon, timeout=STANDS_S)
    note.on("undo", lambda: _undo(client, spent, reverse))
    # Quasar runs an action's handler in the browser; this one hands the click to the
    # element, whose listener brings it here. The color is the text's on that ground.
    note._props["options"]["actions"] = [{
        "label": t("word.undo"), "noCaps": True,
        "color": "dark" if warn else "white",
        ":handler": f"() => getElement({note.id}).$emit('undo')"}]
    return note


async def _undo(client: Any, spent: dict[str, bool],
                reverse: Callable[[], Awaitable[Any]]) -> None:
    if spent["undone"]:
        return
    spent["undone"] = True
    with client:
        try:
            await reverse()
        except Exception as exc:  # noqa: BLE001 - the reason belongs on screen
            logger.warning("console: an undo failed", exc_info=True)
            ui.notify(t("console.undo.could_not", exc=exc), type="negative")
            return
        ui.notify(t("console.undo.undone"), type="positive")
