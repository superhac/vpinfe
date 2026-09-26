"""A notice with one action on it. Every reversible act says what it did through here,
with Undo; a notice that leads somewhere carries its link the same way."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from common.failures import why
from common.i18n import t

logger = logging.getLogger("vpinfe.console.undo")

STANDS_S = 8.0


def act(said: str, label: str, run: Callable[[], Awaitable[Any]], *, warn: bool = False,
        icon: str | None = None) -> ui.notification:
    """Say `said`, green or amber where `warn`, with `label` on it running `run` the first
    time it is pressed."""
    client = ui.context.client
    spent = {"pressed": False}
    # Under the page: in the caller's slot, a dialog closing or a panel redrawing deletes
    # the element its button calls.
    with client:
        note = ui.notification(said, type="warning" if warn else "positive",
                               icon=icon, timeout=STANDS_S)

    async def pressed() -> None:
        if spent["pressed"]:
            return
        spent["pressed"] = True
        with client:
            await run()

    note.on("act", pressed)
    # Quasar runs an action's handler in the browser; this one hands the click to the
    # element, whose listener brings it here. The color is the text's on that ground.
    note._props["options"]["actions"] = [{
        "label": label, "noCaps": True,
        "color": "dark" if warn else "white",
        ":handler": f"() => getElement({note.id}).$emit('act')"}]
    return note


def offer(said: str, reverse: Callable[[], Awaitable[Any]], *, warn: bool = False,
          icon: str | None = None, label: str = "", done: str = "") -> ui.notification:
    """Say what was done, with Undo running `reverse` once: green, or amber where `warn`,
    with `icon` in place of the kind's own. `label` names the action where Undo is not
    the word for it, and `done` is said once it has run."""
    return act(said, label or t("word.undo"), lambda: _undo(reverse, done), warn=warn,
               icon=icon)


async def _undo(reverse: Callable[[], Awaitable[Any]], done: str = "") -> None:
    try:
        await reverse()
    except Exception as exc:  # noqa: BLE001 - the reason belongs on screen
        logger.warning("console: an undo failed", exc_info=True)
        ui.notify(t("console.undo.could_not"), caption=why(exc), type="negative")
        return
    ui.notify(done or t("console.undo.undone"), type="positive")
