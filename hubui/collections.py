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
from urllib.parse import quote

from nicegui import run, ui

from common.games.collection_store import DIRECTION_LABELS, SORT_LABELS
from hubui import confirm, grid, views
from hubui.games import view_control

logger = logging.getLogger("vpinfe.hubui.collections")

SCOPE = "hubui.collections"

# What a collection is called on screen. The wire says `filter`; a reader says
# **Dynamic** - it is the word for a list that changes under you, and "filter" names the
# mechanism rather than the thing.
KIND_LABELS = {"manual": "Manual", "filter": "Dynamic"}

# A number filters as a number: greater-than, less-than, between. AG Grid's default
# filter is the text one, which offers "contains" over a count - and `agNumberColumnFilter`
# is community, unlike the set filter this project cannot use.
_NUMERIC = {"type": "numericColumn", "filter": "agNumberColumnFilter"}

COLUMNS = [
    # The icon leads. A collection is recognised by its picture in the wheel long
    # before its name is read, and a list of collections that showed none of them was
    # asking the reader to work from the least distinctive thing about each.
    grid.column("icon", "", 56, pinned="left", sortable=False, filter=False),
    grid.column("name", "Name", 240, pinned="left"),
    grid.column("kind", "Kind"),
    # Right-aligned with the other number rather than left with the words: a count is
    # read against the counts above and below it.
    # "Table Count", the same as the games grid: a count of tables, not the tables
    # themselves. What it counts is what the collection hands out - one row per entry,
    # and an entry is a table. The stored membership is a different number.
    grid.column("count", "Table Count", **_NUMERIC),
    grid.column("order", "Order", 200),
    # "Table Limit", paired with Table Count: a column header stands alone, so `Limit`
    # invites "limit of what?". The panel keeps plain `Limit` - it sits under
    # Presentation beside Ordered by and Paging, which supply the context a header has
    # to carry for itself.
    grid.column("limit", "Table Limit", **_NUMERIC),
]

# One built-in, and the control stays: a view is how you save your own, and a grid with
# nothing to start from is a grid nobody saves a view of.
COLLECTION_VIEWS: dict[str, list[str]] = {
    "Overview": ["icon", "name", "kind", "count", "order", "limit"],
}


def rows(collections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per collection, in the words the grid shows.

    `count` is what the collection resolves to, which is its size. The stored
    membership is a different number and lives in the panel.
    """
    built = []
    for row in collections:
        built.append({
            "id": row.get("name") or "",
            "name": row.get("name") or "",
            "kind": KIND_LABELS.get(row.get("type") or "", row.get("type") or ""),
            "icon": _icon_cell(row),
            # Zero is an answer here, not an absence: this is what the collection
            # resolves to, and an empty collection resolves to none.
            "count": int(row.get("count") or 0),
            "order": _order_line(row),
            "limit": row.get("limit") or None,
            # Kept whole on the row so the workbench does not refetch what the grid
            # already read.
            "_raw": row,
        })
    return built


def _icon_cell(row: dict[str, Any]) -> str:
    """The collection's picture, or nothing. No placeholder: an icon column of grey
    squares is louder than the few real pictures in it."""
    if not row.get("image"):
        return ""
    name = quote(str(row.get("name") or ""), safe="")
    return (f'<img src="/api/v1/collections/{name}/image" loading="lazy" '
            f'class="hub-collection-cell">')


def _order_line(row: dict[str, Any]) -> str:
    """How this collection is ordered, in one phrase.

    `manual` is the stored member array and says so - it is not one of the fields a
    collection can be sorted by, which is why SORT_LABELS does not carry it.
    """
    by = row.get("order_by") or ""
    if by == "manual":
        return "Manual"
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
        wire_views, _picker, showing = view_control(library, SCOPE, COLLECTION_VIEWS,
                                                    fields, COLUMNS)
        ui.space()
        count = ui.label(f"{len(built)} collections").classes("text-xs hub-label")
        bulk = ui.button(icon="more_vert").props("flat round dense") \
            .tooltip("Actions for the selected collections")
        with bulk, ui.menu():
            ui.menu_item("Delete selected",
                         lambda: _ask_delete_many(picked, library, act)) \
                .classes("hub-menu-item hub-menu-danger")
        bulk.set_visibility(False)

    by_id = {row["id"]: row for row in built}
    ui.on("hub_row_focus",
          lambda event: on_select(by_id.get(grid.focused_row(event))))
    picked: list[dict[str, Any]] = []

    def on_selected(rows_selected: list[dict[str, Any]]) -> None:
        picked[:] = rows_selected
        bulk.set_visibility(bool(rows_selected))
        count.text = (f"{len(rows_selected)} of {len(built)} selected"
                      if rows_selected else f"{len(built)} collections")

    def on_context(row: dict | None) -> None:
        # The menu acts on the row under the cursor, not on the selection.
        _fill(row)

    async def on_header_context(col_id: str | None) -> None:
        state_now = await table.run_grid_method("getColumnState") or []
        entry = next((c for c in state_now if c.get("colId") == col_id), {})
        _fill(None, col_id=col_id, pinned=bool(entry.get("pinned")))

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        table = grid.build(COLUMNS, built, SCOPE, on_selected, on_context,
                           on_header_context, html_fields=["icon"], view_of=showing)
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
                # Renaming lives in the panel's Details, with the description it sits
                # beside. One home per field: a name editable in two places is two
                # answers, and this one is the collection's identity.
                ui.menu_item("Delete", lambda n=name: _ask_delete(n, library, act)) \
                    .classes("hub-menu-item hub-menu-danger")

    wire_views(table)
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                      search.value or ""))


def _ask_new(library: Any, act: Callable) -> None:
    """A name. Nothing else.

    The kind used to be asked here and is not a question at creation: it is decided by
    what the collection ends up holding, and changed in the panel where the games and
    the rule both are. Asking up front made it a mode, which is what COLLECTIONS 2.11
    removed.
    """
    with ui.dialog() as dialog, ui.card():
        ui.label("New collection").classes("hub-card-title")
        name = ui.input(placeholder="Name it") \
            .props("outlined dense debounce=0").classes("w-72")

        async def keep() -> None:
            if not (name.value or "").strip():
                name.props('error error-message="Give it a name"')
                return
            dialog.close()
            await act(library.create_collection, name.value.strip(), None,
                      said=f"Created “{name.value.strip()}”")

        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Create", on_click=keep).props("no-caps")
    dialog.on("show", lambda: ui.run_javascript(
        f"document.getElementById('c{name.id}').focus()"))
    dialog.open()


async def _ask_delete_many(picked: list[dict], library: Any, act: Callable) -> None:
    """Several at once, asked once. The games stay in the library either way."""
    names = [row["name"] for row in picked]
    if not names:
        return
    # Eight, then a count: the list is here to say which ones, and a hundred names is
    # a dialog nobody reads to the end of.
    shown = names[:8] + ([f"...and {len(names) - 8} more"] if len(names) > 8 else [])
    if await confirm.ask(f"Delete {len(names)} collections?",
                         detail="The games stay in the library. Only the lists go.",
                         lines=shown):
        for name in names:
            await act(library.delete_collection, name, said=f"Deleted {name}")


async def _ask_delete(name: str, library: Any, act: Callable) -> None:
    """Asked, because a manual collection is somebody's hand-picked list and there is
    no undo behind this."""
    if await confirm.ask(f"Delete “{name}”?",
                         detail="The games stay in the library. Only the list goes."):
        await act(library.delete_collection, name, said=f"Deleted {name}")


def stored_views(library: Any) -> tuple[list[views.View], str]:
    """Exposed for tests: which views this grid has saved."""
    return views.stored(library, SCOPE)
