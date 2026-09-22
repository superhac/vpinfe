"""What a command may stand for, said beside the field somebody types it into.

The names are declared, so this is generated from that declaration rather than written
out twice. Beside the field and not in a manual: a name you have to already know to go
looking for is a name nobody uses.

Behind a disclosure whatever the count, with the count in the label. A context
offering no names draws nothing at all.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from common import tokens
from common.i18n import t
from console import panel


def add_to(entries: list[Any], context: str) -> None:
    """Put the names a command in this context may use under the fields they apply to."""
    available = tokens.offered(context, after=True)
    if not available:
        return

    def rows() -> None:
        with ui.element("div").classes("console-token-list"):
            for one in available:
                ui.label("{" + one.name + "}").classes("console-token")
                says = one.says
                if one.after_only:
                    says += t("console.commands.after_finished")
                ui.label(says).classes("console-help")

    def draw() -> None:
        with ui.expansion(t("console.commands.names_can_use", len=(len(available)))) \
                .props("dense dense-toggle").classes("console-disclosure console-tokens"):
            with ui.column().classes("gap-1 pt-1"):
                ui.label(t("console.commands.each_stands_something_command")).classes("console-help")
                rows()

    entries.append((panel.ASIDE, draw))
