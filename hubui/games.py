"""The games grid: one row per game, with lenses over the same rows."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from hubui import grid
from hubui.api import HubClient
from hubui.data import TIER_LEGEND

SCOPE = "hubui.games.columns"

COLUMNS = [
    grid.column("name", "Name", 280, pinned="left"),  # default; toggled from the toolbar
    grid.column("manufacturer", "Manufacturer", 150),
    grid.column("year", "Year", 80),
    grid.column("game_type", "Type", 80),
    grid.column("themes", "Themes", 200),
    grid.column("rom", "ROM", 150),
    grid.column("version", "Version", 90),
    grid.column("coverage", "Assets", 90, type="numericColumn"),
    grid.column("rating", "Rating", 90, type="numericColumn"),
]

# Presets, not a replacement for the column picker: a lens sets which columns are
# shown, and anything the user changes afterwards is theirs and is what persists.
LENSES: dict[str, list[str]] = {
    "Metadata": ["name", "manufacturer", "year", "game_type", "themes", "rating"],
    "Coverage": ["name", "coverage", "rating"],
    "Files": ["name", "rom", "version"],
    # Media is built from the library's own kinds, so it is added at render time.
    "Media": [],
}

_ALL = [definition["field"] for definition in COLUMNS]


def _two_line(header: str) -> str:
    """Break the last word onto its own line, so a long kind stays narrow."""
    words = header.split()
    return header if len(words) < 2 else " ".join(words[:-1]) + "\n" + words[-1]


# A renderer is a way of drawing a field, chosen per column. Two here, hardcoded, to
# see whether the idea earns a registry: the same media field as a mark or as a picture.
RENDERERS = ("Ticks", "Thumbnails")

# What one row is. A section owns a subject and a view is a preset of columns over it -
# which is why this is a separate control from the view toggle rather than four more
# entries in it. Only `game` is built; the rest declare themselves so the shape of the
# idea is visible before the work is done.
SUBJECTS = {
    "game": "Games",
    "table": "Tables",
    "media_file": "Media files",
    "vps": "VPS entries",
}

SUBJECT_STUBS = {
    "table": "One row per .vpx file. The 15 games here that carry more than one table "
             "collapse to a single row in Games and cannot be told apart there.",
    "media_file": "One row per file on disk, with the game it resolved to and the tier "
                  "it resolved at. This is where an orphaned file becomes visible.",
    "vps": "One row per Virtual Pinball Spreadsheet entry, joined against this library, "
           "so the footer can say how many are installed and how many are unmatched.",
}


def media_columns(kinds: list[str]) -> list[dict[str, Any]]:
    """One width for every kind, set by the widest line any of them needs.

    A ragged set of widths reads as noise in a matrix whose cells are all one glyph -
    the columns should scan as a grid, so they are sized together rather than each to
    its own header.
    """
    headers = {kind: _two_line(kind.replace("_", " ")) for kind in kinds}
    width = max((grid.header_width(header) for header in headers.values()), default=92)
    return [grid.column(f"media_{kind}", header, width,
                        cellStyle={"textAlign": "center"})
            for kind, header in headers.items()]


async def _rate(games: list[dict[str, Any]]) -> None:
    """Set a rating on every game passed in.

    The API rates one game at a time (`PUT /games/{id}/rating`), so this loops here
    rather than calling a bulk endpoint that does not exist.
    """
    from nicegui import run
    if not games:
        return

    async def apply(value: int) -> None:
        client = HubClient()
        for game in games:
            await run.io_bound(client.rate, game["id"], value)
        dialog.close()
        ui.notify(f"Rated {len(games)} game(s) {value}", type="positive")

    with ui.dialog() as dialog, ui.card():
        ui.label(f"Rate {len(games)} game(s)").classes("text-sm")
        with ui.row():
            for value in range(6):
                ui.button(str(value), on_click=lambda v=value: apply(v)).props("flat dense")
    dialog.open()


async def _launch(games: list[dict[str, Any]]) -> None:
    """Launch one game. Deliberately refuses a multi-row selection.

    Launching is device-resident and starts something on a machine; doing it for
    several rows at once has no sensible meaning, so it is refused rather than looped.
    """
    from nicegui import run
    if len(games) != 1:
        ui.notify("Select a single game to launch", type="warning")
        return
    await run.io_bound(HubClient().launch, games[0]["id"])
    ui.notify(f"Launching {games[0].get('name')}", type="positive")


def build(rows: list[dict[str, Any]], kinds: list[str],
          on_select: Callable[[dict | None], None],
          state: dict[str, Any] | None = None,
          rerender: Callable[[], None] | None = None) -> None:
    state = state if state is not None else {}
    subject = state.get("subject", "game")
    if subject != "game":
        # Stop before the grid, not after it. A toolbar of controls acting on a table
        # that is not there is worse than an empty page.
        with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                              "hub-panel"):
            _subject_select(state, rerender, subject)
        _subject_stub(subject)
        return
    columns = COLUMNS + media_columns(kinds)
    all_fields = [definition["field"] for definition in columns]
    selected: list[dict[str, Any]] = []
    context_row: list[dict[str, Any]] = []

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 hub-panel"):
        _subject_select(state, rerender, subject)
        search = ui.input(placeholder="Search games") \
            .props("dense outlined clearable").classes("w-64")
        lens = ui.toggle(list(LENSES), value="Metadata").props("dense no-caps unelevated")
        cells = ui.toggle(list(RENDERERS), value="Ticks").props("dense no-caps unelevated")
        cells.bind_visibility_from(lens, "value", lambda value: value == "Media")
        columns_btn = ui.button(icon="view_column").props("flat round dense") \
            .tooltip("Choose columns")
        columns_menu = ui.menu()
        ui.space()
        legend = ui.label(TIER_LEGEND).classes("text-xs opacity-60")
        legend.bind_visibility_from(lens, "value", lambda value: value == "Media")
        # The selection count sits with the total: it is the same fact - how much am I
        # looking at - and it costs no vertical space of its own.
        count = ui.label(f"{len(rows)} games").classes("text-xs hub-label")
        actions = ui.button(icon="more_vert").props("flat round dense") \
            .tooltip("Actions for the selected games")
        with actions:
            with ui.menu():
                ui.menu_item("Rate selected", lambda: _rate(selected))
                ui.separator()
                ui.menu_item("Clear selection",
                             lambda: table.run_grid_method("deselectAll"))
        actions.set_visibility(False)

    def on_select_rows(rows_selected: list[dict[str, Any]]):
        selected[:] = rows_selected
        actions.set_visibility(bool(rows_selected))
        count.text = (f"{len(rows_selected)} of {len(rows)} selected"
                      if rows_selected else f"{len(rows)} games")

    by_id = {row["id"]: row for row in rows}

    def focused(event) -> Any:
        """The row the keyboard or a click landed on, which is what is being looked at."""
        return on_select(by_id.get(str(event.args)))

    ui.on("hub_row_focus", focused)

    def on_context(row: dict | None) -> None:
        # The row menu acts on the row under the cursor, which is not necessarily the
        # selection. Conflating the two is how people act on the wrong thing.
        context_row[:] = [row] if row else []
        _fill_menu(row=row)

    async def on_header_context(col_id: str | None) -> None:
        # Asked of the grid rather than tracked here: the column can also be dragged in
        # and out of the pinned area, and a local flag would then be wrong.
        current = await table.run_grid_method("getColumnState")
        entry = next((c for c in current if c.get("colId") == col_id), {})
        _fill_menu(col_id=col_id, pinned=bool(entry.get("pinned")))

    async def set_pinned(col_id: str, pinned: str | None) -> None:
        table.run_grid_method("applyColumnState",
                              {"state": [{"colId": col_id, "pinned": pinned}]})

    async def hide_column(col_id: str) -> None:
        table.run_grid_method("setColumnsVisible", [col_id], False)

    def _fill_menu(row: dict | None = None, col_id: str | None = None,
                   pinned: bool = False) -> None:
        """One menu, filled for whatever was right-clicked.

        Two menus cannot both hang off the grid wrapper, and the wrapper sees every
        right-click - which is why the row menu used to appear over a header offering to
        launch a column.
        """
        context_menu.clear()
        with context_menu:
            if col_id and not col_id.startswith("ag-Grid-"):
                header = next((definition.get("headerName") for definition in columns
                               if definition.get("field") == col_id), col_id)
                ui.item_label(str(header).replace("\n", " ")) \
                    .props("header").classes("hub-menu-header")
                ui.separator()
                # One entry that says what it will do, rather than two where one is
                # always a no-op.
                if pinned:
                    ui.menu_item("Unpin", lambda: set_pinned(col_id, None)) \
                        .classes("hub-menu-item")
                else:
                    ui.menu_item("Pin left", lambda: set_pinned(col_id, "left")) \
                        .classes("hub-menu-item")
                ui.menu_item("Hide column", lambda: hide_column(col_id)) \
                    .classes("hub-menu-item")
            elif row:
                ui.item_label(row.get("name") or "").props("header") \
                    .classes("hub-menu-header")
                ui.separator()
                ui.menu_item("Rate", lambda: _rate(context_row)).classes("hub-menu-item")
                ui.menu_item("Launch", lambda: _launch(context_row)).classes("hub-menu-item")

    # The menu hangs off a wrapper, not off the grid: ui.aggrid's Vue template is a bare
    # <div> with no slot, so a child of it is never rendered and the menu silently does
    # not exist. Anchoring to an element that does render its children is the fix.
    # The wrapper has to carry the flex chain too, not just anchor the menu: as a plain
    # block it collapsed to its content height and the grid inside it never filled.
    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        table = grid.build(columns, rows, SCOPE, on_select_rows, on_context,
                           on_header_context,
                           html_fields=[f"media_{k}" for k in kinds])
        context_menu = ui.context_menu()

    def apply_lens() -> None:
        if lens.value == "Media":
            wanted = ["name", *[f"media_{kind}" for kind in kinds]]
        else:
            wanted = LENSES.get(lens.value or "", all_fields)
        table.run_grid_method("setColumnsVisible", wanted, True)
        table.run_grid_method("setColumnsVisible",
                              [name for name in all_fields if name not in wanted], False)

    async def open_columns() -> None:
        """Every column with a checkbox, so a hidden one can be brought back.

        Hiding from the header menu with no counterpart here would be a one-way door -
        the lens presets happen to restore visibility, but relying on that is not a way
        back anyone would find.
        """
        current = await table.run_grid_method("getColumnState")
        hidden = {c.get("colId") for c in current if c.get("hide")}
        columns_menu.clear()
        with columns_menu:
            ui.item_label("Columns").props("header").classes("hub-menu-header")
            ui.separator()
            # An explicit column: the menu lays its children out inline otherwise, so
            # twenty checkboxes wrap into a paragraph rather than a list.
            with ui.column().classes("gap-0 w-full py-1"):
                for definition in columns:
                    field = definition["field"]
                    label = str(definition.get("headerName") or field).replace("\n", " ")
                    ui.checkbox(label, value=field not in hidden,
                                on_change=lambda event, f=field: table.run_grid_method(
                                    "setColumnsVisible", [f], event.value)) \
                        .props("dense").classes("hub-menu-item w-full")

    columns_btn.on_click(open_columns)

    def apply_renderer() -> None:
        """Redraw the media cells as marks or as pictures.

        The field is the same either way; only its presentation changes. Rows carry
        both, so this is a redraw - no refetch, and filters and sort survive it.
        """
        thumbs = cells.value == "Thumbnails"
        for row, source in zip(table.options["rowData"], rows, strict=True):
            for kind in kinds:
                row[f"media_{kind}"] = source[f"thumb_{kind}" if thumbs else f"media_{kind}"]
        table.run_grid_method("setGridOption", "rowHeight", 60 if thumbs else 42)
        table.update()
        table.run_grid_method("redrawRows")

    cells.on_value_change(apply_renderer)
    lens.on_value_change(apply_lens)
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText", search.value or ""))


def _subject_stub(subject: str) -> None:
    with ui.column().classes("w-full items-start gap-2 p-6"):
        ui.label(SUBJECTS.get(subject, subject)).classes("hub-card-title")
        ui.label(SUBJECT_STUBS.get(subject, "")).classes("hub-help")
        ui.label("Not built. The grid, the views and the details pane are the same "
                 "machinery - what a new subject needs is a field registry entry and a "
                 "reader, not a new page.").classes("hub-help mt-2 opacity-70")


def _subject_select(state: dict[str, Any], rerender: Callable[[], None] | None,
                    subject: str) -> None:
    def pick(value: str) -> None:
        state["subject"] = value
        if rerender is not None:
            rerender()

    ui.select(SUBJECTS, value=subject, label="Show",
              on_change=lambda e: pick(e.value)) \
        .props("dense outlined").classes("w-40")
