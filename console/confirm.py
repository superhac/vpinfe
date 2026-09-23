
"""Ask before something cannot be undone.

One dialog: two had already been written to the same shape with different spellings, and
a third would have been the one that taught users the buttons are not in a fixed place.
Awaited rather than callback, so the caller keeps its own flow.
"""

from __future__ import annotations

from collections.abc import Iterable

from nicegui import ui

from common.i18n import t
from console import dialog as frame
from console import verbs


async def ask(question: str, *, detail: str = "", lines: Iterable[str] = (),
              confirm: str = t("word.delete"), icon: str = verbs.DELETE,
              danger: bool = True) -> bool:
    """Put the question, and wait for an answer.

    `question` is the whole ask - "Delete the extracted script?", never "Are you sure?",
    which asks nothing. `lines` names files where a count would hide which ones. The
    `confirm` button is the verb that does the thing, so it reads without the question,
    and `icon` is that verb's drawing - pass both or neither.
    """
    with frame.opened(question, classes="console-confirm") as box:
        if detail:
            ui.label(detail).classes("console-help px-3")
        for line in lines:
            ui.label(line).classes("console-confirm-line")
        with frame.footer():
            # Cancel first and quiet: the destructive verb is the one to be aimed at.
            frame.cancel(lambda: box.submit(False))
            frame.answer(confirm, lambda: box.submit(True), icon=icon, danger=danger)
    return bool(await box)
