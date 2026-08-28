"""The games grid: one row per game, with views over the same rows."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from hubui import grid, views
from hubui.api import HubClient
from hubui.data import TIER_LEGEND

logger = logging.getLogger("vpinfe.hubui.games")

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

# Presets, not a replacement for choosing columns: a view sets which columns are
# shown, and anything the user changes afterwards is theirs and is what persists.
# Only fields that belong to a game. `rom` and `version` do not: game_repository reads
# them from the default table, so at this grain they report one table's and call them
# the game's. Tables is where that question is answered.
GAME_VIEWS: dict[str, list[str]] = {
    "Metadata": ["name", "manufacturer", "year", "game_type", "themes", "rating"],
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

# What one row is: three grains of the library the user owns - the folder, the
# launchable file inside it, and the asset that resolved for it. Everything here has to
# be something the workbench can answer for, which is what keeps a catalog out.
SUBJECTS = {
    "game": "Games",
    "table": "Tables",
    "media_file": "Media files",
}

SUBJECT_STUBS = {
    "media_file": "One row per file on disk, with the game it resolved to and the tier "
                  "it resolved at. This is where an orphaned file becomes visible.",
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


def build(rows: list[dict[str, Any]], kinds: list[str], library: Any,
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
        # The media preset is the library's own kinds, so it is only knowable here.
        presets = {**GAME_VIEWS, "Media": ["name", *[f"media_{kind}" for kind in kinds]]}
        wire_views, view_picker = view_control(library, SCOPE, presets, all_fields,
                                              columns)
        cells = ui.toggle(list(RENDERERS), value="Ticks").props("dense no-caps unelevated")
        cells.bind_visibility_from(view_picker, "value",
                                   lambda value: value == "builtin:Media")
        ui.space()
        legend = ui.label(TIER_LEGEND).classes("text-xs opacity-60")
        legend.bind_visibility_from(view_picker, "value",
                                    lambda value: value == "builtin:Media")
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
    wire_views(table)
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText", search.value or ""))


# A tick where it is true and nothing where it is not, so a column of them is scanned
# rather than read. The value stays boolean underneath, which is what lets the column
# sort and filter - a column of "Yes"/"" strings would sort alphabetically and filter
# as text.
_TICK = {
    ":valueFormatter": "params => params.value ? '\u2713' : ''",
    "cellClass": "hub-tick",
    # No filter override: the set filter is an AG Grid Enterprise module and this
    # project is MIT-only. The community text filter reads a boolean fine.
    ":cellRenderer": None,
}


# One row per launchable file. The game's name leads, because a filename alone does not
# say what the thing is - and it is pinned, because scrolling right to see which game a
# row belongs to is the failure this subject exists to fix.
TABLE_COLUMNS = [
    grid.column("game", "Game", 240, pinned="left"),
    grid.column("version", "Version", 100),
    grid.column("author", "Author", 160),
    grid.column("rom", "ROM", 140),
    grid.column("app", "App", 90),
    # One column per fact rather than one word folding three together. "Status" cannot
    # stay one column anyway - has an update, missing its rom and the rest are all
    # status - and folded, a table that is both the default and hidden reads as only
    # one of them. Each of these sorts and filters on its own, which is what a list is
    # for. A summary column can be built later, deliberately, from these.
    grid.column("default", "Default", 100, **_TICK),
    grid.column("hidden", "Hidden", 95, **_TICK),
    grid.column("missing", "Missing", 100, **_TICK),
    # Last and widest: it is the identifier of record, and the part that tells two
    # tables of one game apart sits at its end.
    grid.column("filename", "File", 420),
]

TABLE_VIEWS: dict[str, list[str]] = {
    # Default and Hidden ride in every preset: which table a game offers and whether it
    # is offered at all are the questions this view exists to answer, and a preset that
    # hides them is a list of files.
    "Identity": ["game", "version", "author", "default", "hidden", "filename"],
    "Files": ["game", "filename", "app", "default", "hidden", "missing"],
    "Play": ["game", "rom", "app", "default", "hidden"],
}


def _table_label(row: dict[str, Any]) -> str:
    """What to call one table: version and author, never the filename - two tables of
    one game differ in two characters out of forty."""
    parts = [part for part in (row.get("author"), row.get("version")) if part]
    return " \u00b7 ".join([row.get("game") or ""] + parts) if parts \
        else (row.get("game") or row.get("filename") or "")


def table_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The API's tables, flattened for a grid.

    `missing` rather than the API's `available`, so all three flags read the same way:
    true is the notable state and the tick means "this row is one of those". Sorting or
    filtering on a column where true means nothing is wrong is a trap.
    """
    return [{**row,
             "missing": not row.get("available", True),
             "author": ", ".join(row.get("authors") or [])}
            for row in rows]


def build_tables(rows: list[dict[str, Any]], library: Any,
                 on_select: Callable[[dict | None], None],
                 state: dict[str, Any] | None = None,
                 rerender: Callable[[], None] | None = None) -> None:
    """The library seen by launchable file rather than by folder.

    Its own builder rather than a branch inside the games grid: the columns, the views
    and the row identity are all different, and the two sharing one function would be a
    long argument about which subject each line is for.
    """
    state = state if state is not None else {}
    built = table_rows(rows)
    fields = [definition["field"] for definition in TABLE_COLUMNS]

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 hub-panel"):
        _subject_select(state, rerender, state.get("subject", "table"))
        search = ui.input(placeholder="Search tables") \
            .props("dense outlined clearable").classes("w-64")
        wire_views, _ = view_control(library, f"{SCOPE}.tables",
                                     TABLE_VIEWS, fields, TABLE_COLUMNS)
        ui.space()
        ui.label(f"{len(built)} tables in {len({r['game_id'] for r in built})} games") \
            .classes("text-xs hub-label")

    # The workbench follows the focused row, the same way it does under Games - focus
    # rather than selection, so arrowing down the list is a sweep and the checkboxes
    # stay whatever a bulk action left them.
    by_id = {row["id"]: row for row in built}
    ui.on("hub_row_focus", lambda event: on_select(by_id.get(str(event.args))))

    row_menu: dict[str, Any] = {}

    def on_context(row: dict | None) -> None:
        # The menu acts on the row under the cursor, not on the selection. Conflating
        # the two is how people act on the wrong thing.
        row_menu["row"] = row
        _fill(row)

    async def on_header_context(col_id: str | None) -> None:
        # Asked of the grid rather than tracked here: the column can also be dragged in
        # and out of the pinned area, and a local flag would then be wrong.
        state_now = await table.run_grid_method("getColumnState") or []
        entry = next((c for c in state_now if c.get("colId") == col_id), {})
        _fill(None, col_id=col_id, pinned=bool(entry.get("pinned")))

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        table = grid.build(TABLE_COLUMNS, built, f"{SCOPE}.tables", on_select,
                           on_context, on_header_context)
        menu = ui.context_menu()

    async def act(what: Callable, *args: Any, said: str = "") -> None:
        try:
            await run.io_bound(what, *args)
        except Exception as exc:
            ui.notify(f"Could not do that: {exc}", type="negative")
            return
        ui.notify(said, type="positive")
        # Both subjects read tables, so the list is rebuilt rather than patched.
        if rerender is not None:
            rerender()

    def _fill(row: dict | None, col_id: str | None = None,
              pinned: bool = False) -> None:
        """One menu, filled for whatever was right-clicked.

        Two menus cannot both hang off the grid wrapper, and the wrapper sees every
        right-click - so the header's entries and the row's share this one.
        """
        menu.clear()
        with menu:
            if col_id and not col_id.startswith("ag-Grid-"):
                header = next((definition.get("headerName")
                               for definition in TABLE_COLUMNS
                               if definition.get("field") == col_id), col_id)
                ui.item_label(str(header).replace("\n", " ")).props("header") \
                    .classes("hub-menu-header")
                ui.separator()
                # One entry that says what it will do, rather than two where one is
                # always a no-op.
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
                ui.item_label(_table_label(row)).props("header") \
                    .classes("hub-menu-header")
                ui.separator()
                if not row.get("default"):
                    ui.menu_item(
                        "Make this the game's default",
                        lambda r=row: act(library.set_default_table, r["game_id"],
                                          r["id"], said="Now this game's default")) \
                        .classes("hub-menu-item")
                hidden = bool(row.get("hidden"))
                ui.menu_item(
                    "Offer this in the frontend" if hidden else "Hide from the frontend",
                    lambda r=row, h=hidden: act(library.set_table_hidden, r["game_id"],
                                                r["id"], not h,
                                                said="Now offered" if h else "Hidden")) \
                    .classes("hub-menu-item")
                # Only for a table whose file is gone. While it is on disk the record
                # describes something the user owns, and hiding is what takes it out of
                # play without losing its stats.
                if not row.get("available"):
                    ui.menu_item(
                        "Forget this table",
                        lambda r=row: act(library.forget_table, r["game_id"], r["id"],
                                          said="Record dropped")) \
                        .classes("hub-menu-item")

    wire_views(table)
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                      search.value or ""))


def view_control(library: Any, scope: str, presets: dict[str, list[str]],
                 all_fields: list[str], columns: list[dict[str, Any]]):
    """One control for how the rows are presented: which view, and what is in it.

    Built here in the toolbar and wired once the grid exists, because the widgets have
    to sit above the grid and the behavior needs the grid to talk to.

    Returns `(wire, picker)`. Call `wire(table)` once the grid exists; the picker is
    handed back so a caller can hang a binding off which view is showing.
    """
    custom, active = views.stored(library, scope)
    known = views.builtins(presets) + custom
    if active not in {view.id for view in known}:
        active = known[0].id
    held: dict[str, Any] = {"views": known, "active": active, "custom": custom,
                            "modified": False}

    picker = ui.select({view.id: _view_name(view) for view in known}, value=active,
                       label="View").props("dense outlined") \
        .classes("w-52 hub-view-picker")
    # Inside the button, not beside it: a q-menu anchors to its parent, and as a
    # sibling this one anchored to the toolbar row and opened 726px away.
    menu_button = ui.button(icon="more_vert").props("flat dense round size=sm") \
        .tooltip("Columns, and saving this view")
    with menu_button:
        menu = ui.menu()

    def current() -> Any:
        return next(v for v in held["views"] if v.id == held["active"])

    def wire(table: ui.aggrid) -> None:
        async def apply(view: Any) -> None:
            """Put a view on the grid: which columns, sorted how, filtered to what."""
            wanted = [f for f in view.columns if f in all_fields] or all_fields
            table.run_grid_method("setColumnsVisible", wanted, True)
            table.run_grid_method("setColumnsVisible",
                                  [f for f in all_fields if f not in wanted], False)
            # defaultState clears the sort on every column this view does not name,
            # or an old sort would survive a switch and the view would be a lie.
            table.run_grid_method("applyColumnState",
                                  {"state": list(view.sort),
                                   "defaultState": {"sort": None}})
            # Always set, even to nothing: a built-in carries no filters, and clearing
            # them is what makes going back to one a way out rather than a hope.
            table.run_grid_method("setFilterModel", view.filters or None)
            await _refresh()

        async def _seen() -> tuple:
            """What the grid is actually showing, in the terms a view is written in.

            AG Grid's own generated columns - the checkbox, chiefly - are in the state
            and are nobody's view, so they are dropped. Left in, every view reads as
            modified the moment it is applied.
            """
            state = [entry for entry in
                     (await table.run_grid_method("getColumnState") or [])
                     if not str(entry.get("colId", "")).startswith("ag-Grid-")]
            model = await table.run_grid_method("getFilterModel") or {}
            shown = tuple(entry["colId"] for entry in state if not entry.get("hide"))
            return shown, tuple(state), model

        async def _refresh() -> None:
            shown, sort, model = await _seen()
            view = current()
            changed = views.differs(view, shown, sort, model)
            # On the picker rather than beside it: the drift is a fact about the view
            # that is selected, so it belongs to the control that names it.
            picker.props(add="suffix=modified") if changed \
                else picker.props(remove="suffix")
            # Recorded, not pushed at controls. The menu is built when it opens, so it
            # reads this - which is one fewer thing to keep in step than a set of
            # buttons that show and hide themselves.
            held["modified"] = changed

        async def keep_views(active: str) -> None:
            """Write the user's views. Off the loop - this is an HTTP call, and the
            client refuses one made from a page's own handler."""
            await run.io_bound(views.remember, library, scope, held["custom"], active)

        async def pick(view_id: str) -> None:
            held["active"] = view_id
            await keep_views(view_id)
            await apply(current())

        async def save(name: str) -> None:
            shown, sort, model = await _seen()
            view = views.View(id=f"view:{name.strip().lower()}", name=name.strip(),
                              builtin=False, columns=shown,
                              sort=tuple(e for e in sort if e.get("sort")),
                              filters=model)
            held["custom"] = [v for v in held["custom"] if v.id != view.id] + [view]
            held["views"] = views.builtins(presets) + held["custom"]
            held["active"] = view.id
            await keep_views(view.id)
            picker.set_options({v.id: _view_name(v) for v in held["views"]},
                               value=view.id)
            await _refresh()
            ui.notify(f"Saved the view \u201c{view.name}\u201d", type="positive")

        async def delete() -> None:
            view = current()
            if view.builtin:
                return
            held["custom"] = [v for v in held["custom"] if v.id != view.id]
            held["views"] = views.builtins(presets) + held["custom"]
            held["active"] = held["views"][0].id
            await keep_views(held["active"])
            picker.set_options({v.id: _view_name(v) for v in held["views"]},
                               value=held["active"])
            await apply(current())

        async def fill_menu() -> None:
            """Everything about how this view looks, in one menu.

            Built when it opens rather than kept in step: which columns are showing is
            the grid's to answer, and a checklist rebuilt from it cannot go stale.
            """
            column_state = await table.run_grid_method("getColumnState") or []
            hidden = {entry.get("colId") for entry in column_state if entry.get("hide")}
            view = current()
            menu.clear()
            with menu:
                ui.menu_item("Save as\u2026", lambda: _ask_name(save)) \
                    .classes("hub-menu-item")
                # Only where they mean something: there is nothing to revert to until
                # the screen has drifted, and nothing to delete unless it is the
                # user's own view.
                if held["modified"]:
                    ui.menu_item("Revert", lambda: apply(current())) \
                        .classes("hub-menu-item")
                if not view.builtin and not held["modified"]:
                    ui.menu_item("Delete view", delete).classes("hub-menu-item")
                ui.separator()
                ui.item_label("Columns").props("header").classes("hub-menu-header")
                # An explicit column: the menu lays its children out inline otherwise,
                # so twenty checkboxes wrap into a paragraph rather than a list.
                with ui.column().classes("gap-0 w-full py-1"):
                    for definition in columns:
                        field = definition["field"]
                        label = str(definition.get("headerName") or field) \
                            .replace("\n", " ")
                        ui.checkbox(label, value=field not in hidden,
                                    on_change=lambda event, f=field:
                                    table.run_grid_method("setColumnsVisible",
                                                          [f], event.value)) \
                            .props("dense").classes("hub-menu-item w-full")

        menu_button.on_click(fill_menu)
        picker.on_value_change(lambda event: pick(event.value))
        # The grid reports its own changes; the marker follows them rather than being
        # recomputed on a timer that would outlive the grid.
        for event in ("columnVisible", "sortChanged", "filterChanged"):
            table.on(event, lambda: _refresh(), args=[])
        ui.timer(0, lambda: apply(current()), once=True)

    return wire, picker


def _view_name(view: Any) -> str:
    """Whatever it is called. A name somebody typed is shown as they typed it - the
    built-ins come first in the list and only a view of theirs offers to be deleted,
    which is enough to tell them apart without editing anybody's words."""
    return view.name


def _ask_name(save) -> None:
    with ui.dialog() as dialog, ui.card():
        ui.label("Save this view as").classes("hub-card-title")
        # debounce=0 so the model is current the moment Save is pressed. Focus is put
        # here by the script below - Quasar's autofocus does not land in this dialog.
        name = ui.input(placeholder="Name this view") \
            .props("outlined dense debounce=0").classes("w-72")

        async def keep() -> None:
            if not (name.value or "").strip():
                # Said rather than ignored. A dialog that does nothing when you press
                # the button reads as broken, and this one did.
                name.props('error error-message="Give it a name"')
                return
            dialog.close()
            await save(name.value)

        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            save_button = ui.button("Save", on_click=keep).props("no-caps")
    # Focused when Quasar says the dialog has finished opening. Anything earlier is
    # overridden by its own focus handling, whatever the delay.
    dialog.on("show", lambda: ui.run_javascript(
        f"document.getElementById('c{name.id}').focus()"))
    dialog.open()
    # Enter is bound in the browser rather than through an event handler: nicegui does
    # not forward a keyup from a Quasar input inside a dialog, so nothing arrives to
    # handle. Clicking the button is the same path the mouse takes, which is the point.
    ui.run_javascript(f"""
        (() => {{
          // The dialog mounts after this runs, so the elements are waited for rather
          // than assumed. Bounded, because a dialog that never appears must not leave
          // a timer running behind it.
          let tries = 0;
          const wire = () => {{
            const field = document.getElementById('c{name.id}');
            const button = document.getElementById('c{save_button.id}');
            if (!field || !button) {{
              if (++tries < 40) setTimeout(wire, 25);
              return;
            }}
            // On the dialog, not the field: Quasar's autofocus does not land, so
            // focus can be on the dialog itself when the first key arrives and a
            // listener on the input would never hear it.
            const dialog = button.closest('.q-dialog') || field;
            dialog.addEventListener('keyup', (event) => {{
              if (event.key === 'Enter') button.click();
            }});

          }};
          wire();
        }})()
    """)


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

    # "Rows" rather than "Show", which was a synonym of the View control beside it.
    ui.select(SUBJECTS, value=subject, label="Rows",
              on_change=lambda e: pick(e.value)) \
        .props("dense outlined").classes("w-40")
