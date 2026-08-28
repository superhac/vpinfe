"""The collections grid: one row per collection, with the workbench beside it.

A collection is a subject like any other here, so this is a grid and not a pair of
cards. What one *is* - a name, how it is ordered, how many games - is what the columns
carry; what it *holds* is the workbench's answer, because membership is a list and a
list does not fit in a cell.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common.games.collection_store import DIRECTION_LABELS, SORT_LABELS
from hubui import grid, views
from hubui.games import view_control

logger = logging.getLogger("vpinfe.hubui.collections")

SCOPE = "hubui.collections"

# What a collection is called in the UI. The API's `type` is derived for display
# (COLLECTIONS section 2.11), so this is the only place the word is chosen.
KIND_LABELS = {"manual": "Manual", "filter": "Filter"}

COLUMNS = [
    grid.column("name", "Name", 260, pinned="left"),
    grid.column("kind", "Kind", 110),
    # Right-aligned with the other number rather than left with the words: a count is
    # read against the counts above and below it.
    grid.column("games", "Games", 100, type="numericColumn"),
    grid.column("order", "Order", 200),
    grid.column("limit", "Limit", 90, type="numericColumn"),
]

# One built-in, and the control stays: a view is how you save your own, and a grid with
# nothing to start from is a grid nobody saves a view of.
COLLECTION_VIEWS: dict[str, list[str]] = {
    "Overview": ["name", "kind", "games", "order", "limit"],
}


def rows(collections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per collection, in the words the grid shows.

    `games` is blank for a filter collection rather than 0: its membership is not a
    stored list, so there is no number to report until it is resolved, and 0 would read
    as "empty" when the truth is "ask".
    """
    built = []
    for row in collections:
        count = row.get("game_count")
        built.append({
            "id": row.get("name") or "",
            "name": row.get("name") or "",
            "kind": KIND_LABELS.get(row.get("type") or "", row.get("type") or ""),
            # None, not "": a numeric column renders an empty string as
            # "Invalid Number", and blank is what "there is no number here" looks like.
            "games": count,
            "order": _order_line(row),
            "limit": row.get("limit") or None,
            # Kept whole on the row so the workbench does not refetch what the grid
            # already read.
            "_raw": row,
        })
    return built


def _order_line(row: dict[str, Any]) -> str:
    """How this collection is ordered, in one phrase.

    `manual` is the stored member array and says so - it is not one of the fields a
    collection can be sorted by, which is why SORT_LABELS does not carry it.
    """
    by = row.get("order_by") or ""
    if by == "manual":
        return "As arranged"
    if not by:
        return ""
    direction = DIRECTION_LABELS.get(row.get("direction") or "", "")
    return f"{SORT_LABELS.get(by, by)}, {direction.lower()}" if direction \
        else SORT_LABELS.get(by, by)


def build(collections: list[dict[str, Any]], library: Any,
          on_select: Callable[[dict | None], None],
          state: dict[str, Any] | None = None,
          rerender: Callable[[], None] | None = None) -> None:
    state = state if state is not None else {}
    built = rows(collections)
    fields = [definition["field"] for definition in COLUMNS]

    async def act(what: Callable, *args: Any, said: str = "") -> None:
        try:
            await run.io_bound(what, *args)
        except Exception as exc:
            ui.notify(f"Could not do that: {exc}", type="negative")
            return
        ui.notify(said, type="positive")
        if rerender is not None:
            rerender()

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 hub-panel"):
        ui.button("New collection", icon="add",
                  on_click=lambda: _ask_new(library, act)) \
            .props("flat dense no-caps size=sm").classes("shrink-0 hub-action")
        search = ui.input(placeholder="Search collections") \
            .props("dense outlined clearable").classes("w-64")
        wire_views, _ = view_control(library, SCOPE, COLLECTION_VIEWS, fields, COLUMNS)
        ui.space()
        ui.label(f"{len(built)} collections").classes("text-xs hub-label")

    by_id = {row["id"]: row for row in built}
    ui.on("hub_row_focus", lambda event: on_select(by_id.get(str(event.args))))

    def on_context(row: dict | None) -> None:
        # The menu acts on the row under the cursor, not on the selection.
        _fill(row)

    async def on_header_context(col_id: str | None) -> None:
        state_now = await table.run_grid_method("getColumnState") or []
        entry = next((c for c in state_now if c.get("colId") == col_id), {})
        _fill(None, col_id=col_id, pinned=bool(entry.get("pinned")))

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        table = grid.build(COLUMNS, built, SCOPE, None, on_context, on_header_context)
        menu = ui.context_menu()

    def _fill(row: dict | None, col_id: str | None = None,
              pinned: bool = False) -> None:
        """One menu, filled for whatever was right-clicked."""
        menu.clear()
        with menu:
            if col_id and not col_id.startswith("ag-Grid-"):
                header = next((d.get("headerName") for d in COLUMNS
                               if d.get("field") == col_id), col_id)
                ui.item_label(str(header)).props("header").classes("hub-menu-header")
                ui.separator()
                ui.menu_item(
                    "Unpin" if pinned else "Pin left",
                    lambda c=col_id, p=pinned: table.run_grid_method(
                        "applyColumnState",
                        {"state": [{"colId": c, "pinned": None if p else "left"}]})) \
                    .classes("hub-menu-item")
                ui.menu_item("Hide column",
                             lambda c=col_id: table.run_grid_method(
                                 "setColumnsVisible", [c], False)) \
                    .classes("hub-menu-item")
            elif row:
                name = row["name"]
                ui.item_label(name).props("header").classes("hub-menu-header")
                ui.separator()
                ui.menu_item("Rename", lambda n=name: _ask_rename(n, act)) \
                    .classes("hub-menu-item")
                ui.menu_item("Delete", lambda n=name: _ask_delete(n, library, act)) \
                    .classes("hub-menu-item")

    wire_views(table)
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                      search.value or ""))


def _ask_new(library: Any, act: Callable) -> None:
    """A name, and which kind it is.

    The kind is asked here because it cannot be changed later without discarding
    something: turning a manual collection into a filter one throws away the list
    somebody picked by hand, which the API only ever does when asked explicitly.
    """
    with ui.dialog() as dialog, ui.card():
        ui.label("New collection").classes("hub-card-title")
        name = ui.input(placeholder="Name it") \
            .props("outlined dense debounce=0").classes("w-72")
        kind = ui.toggle({"manual": "I pick the games", "filter": "It follows a rule"},
                         value="manual").props("dense no-caps unelevated")
        ui.label("A rule collection is built from the library, never from another "
                 "collection.").classes("hub-help")

        async def keep() -> None:
            if not (name.value or "").strip():
                name.props('error error-message="Give it a name"')
                return
            dialog.close()
            # An empty filter block is every game, which is the honest starting point
            # for a rule nobody has written yet - and the Rule section is where it
            # gets written.
            await act(library.create_collection, name.value.strip(),
                      {} if kind.value == "filter" else None,
                      said=f"Created “{name.value.strip()}”")

        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=keep).props("no-caps")
    dialog.on("show", lambda: ui.run_javascript(
        f"document.getElementById('c{name.id}').focus()"))
    dialog.open()


def _ask_rename(name: str, act: Callable) -> None:
    with ui.dialog() as dialog, ui.card():
        ui.label(f"Rename “{name}”").classes("hub-card-title")
        field = ui.input(value=name).props("outlined dense debounce=0").classes("w-72")

        async def keep() -> None:
            wanted = (field.value or "").strip()
            if not wanted:
                field.props('error error-message="Give it a name"')
                return
            dialog.close()
            if wanted != name:
                await act(_rename, name, wanted, said=f"Now “{wanted}”")

        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Rename", on_click=keep).props("no-caps")
    dialog.open()


def _rename(old: str, new: str) -> None:
    from hubui.api import HubClient
    HubClient().patch_collection(old, {"name": new})


def _ask_delete(name: str, library: Any, act: Callable) -> None:
    """Asked, because a manual collection is somebody's hand-picked list and there is
    no undo behind this."""
    with ui.dialog() as dialog, ui.card():
        ui.label(f"Delete “{name}”?").classes("hub-card-title")
        ui.label("The games stay in the library. Only the list goes.") \
            .classes("hub-help")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")

            async def go() -> None:
                dialog.close()
                await act(library.delete_collection, name, said=f"Deleted {name}")

            ui.button("Delete", on_click=go).props("no-caps color=negative")
    dialog.open()


def stored_views(library: Any) -> tuple[list[views.View], str]:
    """Exposed for tests: which views this grid has saved."""
    return views.stored(library, SCOPE)
