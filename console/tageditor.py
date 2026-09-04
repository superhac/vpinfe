"""The tag editor: one row per tag, and the way to fix two spellings of one word.

Entry does not fold case - Chris, 2026-09-01: surface close matches and let the user
decide - so `sci-fi` and `Sci-Fi` can both exist. This is where that gets cleaned up,
which is why merge is the headline here and rename is the same operation with one
source.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from console import confirm, grid

SUBJECT = "tag"
LABEL = "Tags"

COLUMNS = [
    grid.column("tag", "Tag", 260, pinned="left"),
    grid.column("games", "Games", type="numericColumn"),
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
            changed = await run.io_bound(call, *args)
        except Exception as exc:
            ui.notify(f"Could not do that: {exc}", type="negative")
            return
        ui.notify(f"{said} - {changed} game{'' if changed == 1 else 's'} changed",
                  type="positive")
        if rerender is not None:
            rerender()

    async def merge(group: list[dict[str, Any]]) -> None:
        into = str(group[0].get("tag") or "")
        others = [str(r.get("tag")) for r in group[1:]]
        if not await confirm.ask(
                f"Merge into “{into}”?",
                detail="Every game carrying one of the others is retagged. This cannot "
                       "be undone.",
                lines=[f"{r['tag']} - {r['games']} game"
                       f"{'' if r['games'] == 1 else 's'}" for r in group[1:]],
                confirm="Merge"):
            return
        await sweep(library.merge_tags, others + [into], into, said=f"Merged into {into}")

    async def rename(row: dict[str, Any]) -> None:
        said = await _ask_for_a_name(str(row.get("tag") or ""))
        if not said or said == row.get("tag"):
            return
        await sweep(library.merge_tags, [str(row.get("tag"))], said,
                    said=f"Renamed to {said}")

    async def drop(row: dict[str, Any]) -> None:
        tag = str(row.get("tag") or "")
        count = int(row.get("games") or 0)
        if not await confirm.ask(
                f"Remove “{tag}” from every game?",
                detail=f"{count} game{'' if count == 1 else 's'} carry it. A tag no game "
                       "carries does not exist, so there is nothing to restore it from.",
                confirm="Remove"):
            return
        await sweep(library.delete_tag, tag, said=f"Removed {tag}")

    duplicates = rows_by_key(rows)
    if duplicates:
        with ui.element("div").classes("hub-card w-full mb-2"):
            ui.label("These look like the same tag").classes("hub-card-title")
            ui.label("Entry keeps what you typed, so two spellings of one word both "
                     "exist. Merging folds them into the most-used one.") \
                .classes("hub-help")
            for group in duplicates:
                with ui.row().classes("items-center gap-2 w-full no-wrap "
                                      "hub-member-row"):
                    ui.label(" · ".join(f"{r['tag']} ({r['games']})" for r in group)) \
                        .classes("hub-member-name grow min-w-0 truncate")
                    ui.button("Merge", on_click=lambda _, g=group: merge(g)) \
                        .props("flat dense no-caps size=sm") \
                        .classes("hub-action hub-action--inline")

    if not rows:
        ui.label("No tags yet. Tag a game from its Play section and it appears here.") \
            .classes("hub-help p-4")
        return

    menu_row: dict[str, Any] = {}

    def fill(row: dict | None) -> None:
        menu.clear()
        if not row:
            return
        with menu:
            ui.item_label(str(row.get("tag") or "")).props("header") \
                .classes("hub-menu-header")
            ui.separator()
            ui.menu_item("Rename…", lambda r=row: rename(r)).classes("hub-menu-item")
            ui.menu_item("Remove from every game", lambda r=row: drop(r)) \
                .classes("hub-menu-item hub-menu-danger")

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        grid.build(COLUMNS, rows, "console.tags", lambda _row: None,
                   lambda row: (menu_row.__setitem__("row", row), fill(row)))
        menu = ui.context_menu()


async def _ask_for_a_name(current: str) -> str:
    """A dialog that collects a value keeps its own shape - `docs/conventions.md` says
    the confirm treatment is for a question, not for a field."""
    with ui.dialog() as dialog, ui.card().classes("hub-confirm"):
        ui.label("Rename this tag").classes("hub-confirm-title")
        ui.label("Every game carrying it is retagged.").classes("hub-help")
        field = ui.input(value=current).props("dense autofocus") \
            .classes("hub-edit-field w-full")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Cancel", on_click=lambda: dialog.submit("")).props("flat no-caps")
            ui.button("Rename", on_click=lambda: dialog.submit(field.value or "")) \
                .props("no-caps")
    return str(await dialog or "")
