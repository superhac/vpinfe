
"""The tag editor: one row per tag, and the way to fix two spellings of one word.

Entry does not fold case - the picker surfaces close matches and the user decides -
so `sci-fi` and `Sci-Fi` can both exist. This is where that gets cleaned up,
which is why merge is the headline here and rename is the same operation with one
source.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from common.i18n import t
from console import confirm, grid, offload, verbs

SUBJECT = "tag"
LABEL = t("console.tageditor.tags")

COLUMNS = [
    grid.identifier("tag", t("console.tageditor.tag"), 260, pinned="left",
                    help=t("console.tageditor.tag.help")),
    grid.column("games", t("console.tageditor.games"), type="numericColumn",
                help=t("console.tageditor.games.help")),
]


def rows_by_key(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """The spellings that share a word, most-used first inside each group.

    Only groups with more than one member: a tag nobody has spelled twice is not
    something to act on, and listing it would bury the ones that are.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get("same") or ""), []).append(row)
    return [sorted(group, key=lambda r: (-int(r.get("games") or 0), str(r.get("tag"))))
            for group in groups.values() if len(group) > 1]


def build(rows: list[dict[str, Any]], library: Any,
          rerender: Callable[[], None] | None = None) -> None:
    """The editor. The duplicates lead, because they are what somebody came here for."""
    async def sweep(call: Callable[..., Any], *args: Any, said: str = "") -> None:
        try:
            changed = await offload.io(call, *args)
        except Exception as exc:
            ui.notify(t("said.could_not_do_that", exc=(exc)), type="negative")
            return
        ui.notify(t("console.tageditor.game_changed", said=(said), changed=(changed),
                value=('' if changed == 1 else 's')),
                  type="positive")
        if rerender is not None:
            rerender()

    async def merge(group: list[dict[str, Any]]) -> None:
        into = str(group[0].get("tag") or "")
        others = [str(r.get("tag")) for r in group[1:]]
        if not await confirm.ask(
                t("console.tageditor.merge", into=(into)),
                detail=t("console.tageditor.every_game_carrying_one"),
                lines=[t("console.tageditor.tag_game" if r["games"] == 1
                         else "console.tageditor.tag_games",
                         tag=r["tag"], count=r["games"]) for r in group[1:]],
                confirm=t("word.merge"), icon=verbs.MERGE):
            return
        await sweep(library.merge_tags, others + [into], into,
                said=t("console.tageditor.merged", into=(into)))

    async def rename(row: dict[str, Any]) -> None:
        said = await _ask_for_a_name(str(row.get("tag") or ""))
        if not said or said == row.get("tag"):
            return
        await sweep(library.merge_tags, [str(row.get("tag"))], said,
                    said=t("console.tageditor.renamed", said=(said)))

    async def drop(row: dict[str, Any]) -> None:
        tag = str(row.get("tag") or "")
        count = int(row.get("games") or 0)
        if not await confirm.ask(
                t("console.tageditor.remove_every_game", tag=(tag)),
                detail=t("console.tageditor.game_carry_tag_no", the_count=(count),
                        value=('' if count == 1 else 's')),
                confirm=t("word.remove"), icon=verbs.REMOVE):
            return
        await sweep(library.delete_tag, tag, said=t("console.tageditor.removed", tag=(tag)))

    duplicates = rows_by_key(rows)
    if duplicates:
        with ui.element("div").classes("console-card w-full mb-2"):
            ui.label(t("console.tageditor.look_like_same_tag")).classes("console-card-title")
            ui.label(t("console.tageditor.entry_keeps_what_typed")) \
                .classes("console-help")
            for group in duplicates:
                with ui.row().classes("items-center gap-2 w-full no-wrap "
                                      "console-member-row"):
                    ui.label(" · ".join(f"{r['tag']} ({r['games']})" for r in group)) \
                        .classes("console-member-name grow min-w-0 truncate")
                    ui.button(t("word.merge"),
                        icon=verbs.MERGE, on_click=lambda _, g=group: merge(g)) \
                        .props("flat dense no-caps size=sm") \
                        .classes("console-action console-action--inline")

    if not rows:
        ui.label(t("console.tageditor.no_tags_yet_tag")) \
            .classes("console-help p-4")
        return

    menu_row: dict[str, Any] = {}

    def fill(row: dict | None) -> None:
        menu.clear()
        if not row:
            return
        with menu:
            ui.item_label(str(row.get("tag") or "")).props("header") \
                .classes("console-menu-header")
            ui.separator()
            ui.menu_item(t("console.tageditor.rename"),
                    lambda r=row: rename(r)).classes("console-menu-item")
            ui.menu_item(t("console.tageditor.remove_every_game_2"), lambda r=row: drop(r)) \
                .classes("console-menu-item console-menu-danger")

    def on_context(row: dict | None) -> None:
        menu_row["row"] = row
        fill(row)

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        grid.build(COLUMNS, rows, "console.tags", on_context=on_context)
        menu = ui.context_menu()


async def _ask_for_a_name(current: str) -> str:
    """A dialog that collects a value keeps its own shape - `docs/conventions.md` says
    the confirm treatment is for a question, not for a field."""
    with ui.dialog() as dialog, ui.card().classes("console-confirm"):
        ui.label(t("console.tageditor.rename_tag")).classes("console-confirm-title")
        ui.label(t("console.tageditor.every_game_carrying_retagged")).classes("console-help")
        field = ui.input(value=current).props("dense autofocus") \
            .classes("console-edit-field w-full")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button(t("word.cancel"), icon=verbs.CANCEL,
                    on_click=lambda: dialog.submit("")).props("flat no-caps")
            ui.button(t("console.tageditor.rename_2"), icon=verbs.RENAME,
                    on_click=lambda: dialog.submit(field.value or "")) \
                .props("no-caps")
    return str(await dialog or "")
