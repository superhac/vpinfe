"""What a command may stand for, said beside the field somebody types it into.

The names are declared, so this is generated from that declaration rather than written
out twice. Beside the field and not in a manual: a name you have to already know to go
looking for is a name nobody uses.

Eleven of them is a wall between two settings, so the long list opens rather than sits
there. The label is always in the same place, which is what makes it findable - the
short one has nothing to gain by hiding, so it does not.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from common import tokens
from console import panel

# Below this many, a list is shorter than the control that would fold it away.
SHOW_ALL_UP_TO = 3


def offered(context: str) -> tuple[Any, Callable[[], None]]:
    """The names a command in this context may use, under the fields it applies to."""
    available = tokens.offered(context, after=True)
    later = {one.name for one in available if one.name in tokens.AFTER_ONLY}

    def rows() -> None:
        with ui.element("div").classes("console-token-list"):
            for one in available:
                ui.label("{" + one.name + "}").classes("console-token")
                says = one.says
                if one.name in later:
                    says += " - only after it has finished"
                ui.label(says).classes("console-help")

    def draw() -> None:
        if len(available) <= SHOW_ALL_UP_TO:
            with ui.column().classes("gap-1"):
                ui.label(_LEAD).classes("console-help")
                rows()
            return
        with ui.expansion(f"Names you can use ({len(available)})") \
                .props("dense dense-toggle").classes("console-tokens"):
            with ui.column().classes("gap-1 pt-1"):
                ui.label(_LEAD).classes("console-help")
                rows()

    return (panel.ASIDE, draw)


_LEAD = ("Each stands for something when the command runs. A name that is not on this "
         "list is refused rather than left blank.")
