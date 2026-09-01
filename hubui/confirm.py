"""Ask before something cannot be undone.

One dialog: two had already been written to the same shape with different spellings, and
a third would have been the one that taught users the buttons are not in a fixed place.
Awaited rather than callback, so the caller keeps its own flow.
"""

from __future__ import annotations

from collections.abc import Iterable

from nicegui import ui


async def ask(question: str, *, detail: str = "", lines: Iterable[str] = (),
              confirm: str = "Delete", danger: bool = True) -> bool:
    """Put the question, and wait for an answer.

    `question` is the whole ask - "Delete the extracted script?", never "Are you sure?",
    which asks nothing. `lines` names files where a count would hide which ones. The
    `confirm` button is the verb that does the thing, so it reads without the question.
    """
    with ui.dialog() as dialog, ui.card().classes("hub-confirm"):
        ui.label(question).classes("hub-confirm-title")
        if detail:
            ui.label(detail).classes("hub-help")
        for line in lines:
            ui.label(line).classes("hub-confirm-line")
        with ui.row().classes("justify-end gap-2 w-full"):
            # Cancel first and quiet: the destructive verb is the one to be aimed at.
            ui.button("Cancel", on_click=lambda: dialog.submit(False)) \
                .props("flat no-caps")
            ui.button(confirm, on_click=lambda: dialog.submit(True)) \
                .props("no-caps" + (" color=negative" if danger else ""))
    return bool(await dialog)
