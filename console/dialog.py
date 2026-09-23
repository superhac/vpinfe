from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui


@contextmanager
def opened(title: str, *, wide: bool = False, persistent: bool = False,
           classes: str = "") -> Iterator[ui.dialog]:
    """Draw the dialog's contents inside; the caller awaits the dialog it yields."""
    with ui.dialog().props("persistent" if persistent else "") as dialog, \
            ui.card().classes(" ".join(("console-dialog", "console-dialog--wide" if wide else "",
                                        classes)).strip()):
        ui.label(title).classes("console-dialog-title")
        yield dialog


def footer() -> ui.row:
    return ui.row().classes("console-dialog-footer")
