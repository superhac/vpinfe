
"""Ask before something cannot be undone.

One dialog: two had already been written to the same shape with different spellings, and
a third would have been the one that taught users the buttons are not in a fixed place.
Awaited rather than callback, so the caller keeps its own flow.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from nicegui import ui

from common.i18n import t
from console import dialog as frame
from console import verbs


async def ask(question: str, *, detail: str | Sequence[str] = "",
              lines: Iterable[str] = (),
              confirm: str = t("word.delete"), icon: str = verbs.DELETE,
              danger: bool = True,
              also: tuple[str, Callable[[], Any], str] | None = None) -> bool:
    """Put the question, and wait for an answer.

    `question` is the whole ask - "Delete the extracted script?", never "Are you sure?",
    which asks nothing. `detail` is the consequence, a line to each sentence where
    there are two. `lines` names files where a count would hide which ones. The
    `confirm` button is the verb that does the thing, so it reads without the question,
    and `icon` is that verb's drawing - pass both or neither. `also` is one act to offer
    before answering, as its label, what it does and its drawing; it leaves the question
    open.
    """
    with frame.opened(question, classes="console-confirm") as box:
        for said in [detail] if isinstance(detail, str) else detail:
            if said:
                ui.label(said).classes("console-help px-3")
        for line in lines:
            ui.label(line).classes("console-confirm-line")
        with frame.footer():
            if also is not None:
                label, act, drawing = also
                frame.aside(label, act, icon=drawing)
            # Cancel first and quiet: the destructive verb is the one to be aimed at.
            frame.cancel(lambda: box.submit(False))
            frame.answer(confirm, lambda: box.submit(True), icon=icon, danger=danger)
    return bool(await box)


async def replace(label: str, going: list[str]) -> bool:
    """Name what a write would replace in a slot, and wait for a yes.

    The files are listed rather than counted because the surprising case is the one a
    count hides: a whole family goes at this tier, so a .mp4 arriving over a .png takes
    the .png with it and the user never named that file.
    """
    return await ask(t("console.mediasource.replace", kind=label),
                     detail=t("console.mediasource.replaced_files_deleted_not"),
                     lines=going, confirm=t("word.replace"), icon=verbs.REPLACE)
