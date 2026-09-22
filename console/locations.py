
"""Locations: where this install looks for games.

A grid rather than a rail, for the reason Devices is one: the value of a location is
mostly its state, and the question somebody brings to this page is a comparison across
rows - which share is down, which is read-only, which one new games land in. A rail makes
that a click each.

What the disk says is read on every draw and never stored. A stored answer is wrong the
moment a mount drops, and a mount dropping is the case plural locations exist to report.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common.games import locations as model
from common.games import tables
from common.i18n import t
from console import offload, verbs, views
from console.data import Library

from . import confirm, grid, panel

logger = logging.getLogger("vpinfe.console.locations")

SCOPE = "locations"

# What a person would call each kind, rather than what the record calls it.
KIND_LABELS = {"root": "console.locations.game_folders",
               "game": "console.locations.one_game"}


_KIND_CHOICES = [{"value": key, "label": t(label)} for key, label in KIND_LABELS.items()]

COLUMNS = [
    # The folder leads and is pinned. It is what a person recognizes a location by, and
    # every other column is a fact about it.
    grid.identifier("name", t("word.folder"), 260, pinned="left",
                help=t("console.locations.folder_location_last_two.help")),
    grid.column("contains", t("word.contains"), 140,
            **grid.choice_filter(_KIND_CHOICES),
                help=t("console.locations.game_folders_children_games.help")),
    grid.column("state", t("word.state"), 140,
                help=t("console.locations.what_disk_says_right.help")),
    grid.column("new_games", t("console.locations.new_games"), 120,
                help=t("console.locations.where_game_add_import.help")),
    # Priority as a number rather than as position alone: the grid can be sorted by
    # any column, so the order you are looking at is not always the order that decides.
    grid.column("priority", t("word.priority"), 110, type="numericColumn",
                help=t("console.locations.location_wins_two_them.help")),
    grid.column("shadowed", t("console.locations.shadowed"), 120, type="numericColumn",
                help=t("console.locations.game_folders_whose_id.help")),
    grid.column("path", t("console.locations.full_path"), 420,
                help=t("console.locations.whole_path_telling_two.help")),
]

LOCATION_VIEWS: dict[str, list[str] | views.Preset] = {
    t("console.view.overview"): views.Preset(
        columns=("name", "contains", "state", "new_games", "shadowed", "path"),
        help=t("console.view.locations.help")),
    # Its own view rather than more columns on Overview: this one is read when
    # something is wrong, and the question is which location beats which.
    t("word.priority"): views.Preset(
        columns=("name", "priority", "shadowed", "state", "path"),
        help=t("console.view.priority.help")),
}


def state_of(row: dict[str, Any]) -> str:
    """The fewest true words. Why is in the column's help and in the panel."""
    if not row.get("reachable"):
        return t("word.unreachable")
    return t("word.ready") if row.get("writable") \
        else t("word.read_only")


def rows(locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per location, with the wire's flags turned into words a column shows."""
    return [{
        "id": one["location_id"],
        "name": one["name"],
        "path": one["path"],
        "contains": t(KIND_LABELS.get(one["kind"], one["kind"])),
        "state": state_of(one),
        # Blank on every other row rather than "No": a column that says the same thing
        # everywhere but once is a column about the exception.
        "new_games": t("word.created_here") if one.get("write_to") else "",
        # From the list order, which is what the install reads it from. 1 is highest,
        # because a person counts places from one and this is a rank, not an index.
        "priority": place + 1,
        # None rather than 0, so the ordinary answer is an empty cell. A column of
        # zeroes reads as a thing to look at.
        "shadowed": int(one.get("shadowed") or 0) or None,
    } for place, one in enumerate(locations)]


def build(library: Library, state: dict[str, Any],
          on_select: Callable[[dict | None], Any],
          rerender: Callable[[], None] | None = None) -> None:
    """The grid. Read on every draw, because what the disk says changes without anybody
    editing anything."""
    body = ui.column().classes("w-full grow min-h-0 gap-0")
    # On a timer, because reading goes over HTTP and the draw it is part of runs on the
    # event loop, where the client refuses a call.
    ui.timer(0.01, lambda: _fill(library, state, on_select, rerender, body), once=True)


async def _fill(library: Library, state: dict[str, Any], on_select: Callable[[dict | None], Any],
                rerender: Callable[[], None] | None, body: Any) -> None:
    try:
        found = await offload.io(library.locations)
    except Exception as exc:  # noqa: BLE001 - this page says why, never 500s
        with body:
            panel.facts(ui, [panel.intro(t("console.locations.could_not_read_locations",
                    exc=(exc)))])
        return

    # Imported here: `workbench` imports this module, and `games` imports `workbench`,
    # so reaching for it at the top would close the loop.
    from console.games import view_control

    held = list(found.get("locations") or [])
    built = rows(held)
    fields = [definition["field"] for definition in COLUMNS]

    with body:
        with ui.row().classes(
                "w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 console-panel console-grid-bar"):
            bar = panel.grid_bar()
            wire_views, _picker, showing, describe = view_control(
                library, SCOPE, LOCATION_VIEWS, fields, COLUMNS, bar=bar)
            describe()
            with bar.top, panel.bar_end():
                search = panel.search(t("console.locations.search_locations"))
            picked: list[dict[str, Any]] = []
            with bar.bottom, panel.bar_end():
                count = ui.label(t("console.locations.location", len=(len(built)),
                        value=('' if len(built) == 1 else 's'))) \
                    .classes("text-xs console-label")
                bulk = ui.button(icon=verbs.MORE).props("flat round dense") \
                    .tooltip(t("console.locations.actions_selected_locations"))
                with bulk, ui.menu():
                    ui.menu_item(t("console.locations.remove_selected"),
                                 lambda: _remove_many(picked, library, rerender)) \
                        .classes("console-menu-item console-menu-danger")
                bulk.set_visibility(False)
                panel.add_action(
                    [(t("console.locations.add_location"),
                      (lambda: _ask_new(library, state, rerender)))],
                    empty=not built)

        if not built:
            panel.facts(ui, [panel.intro(
                t("console.locations.no_locations_yet_add"))])
            return

        by_id = {row["id"]: row for row in built}
        grid.on_row_focus(SCOPE,
                          lambda event: on_select(by_id.get(grid.focused_row(event))))
        def on_selected(rows_selected: list[dict[str, Any]]) -> None:
            picked[:] = rows_selected
            bulk.set_visibility(bool(rows_selected))
            count.text = (t("console.locations.selected",
                            len=(len(rows_selected)), len2=(len(built)))
                          if rows_selected
                          else t("console.locations.location", len=(len(built)),
                                 value=('' if len(built) == 1 else 's')))

        with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
            table = grid.build(COLUMNS, built, SCOPE, on_select_rows=on_selected,
                               view_of=showing)
        search.on_value_change(
            lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                          search.value or ""))
        # After the grid exists: the widgets sit above it and the behavior needs it.
        wire_views(table)


async def _remove_many(picked: list[dict[str, Any]], library: Library,
                       rerender: Callable[[], None] | None) -> None:
    """Several at once, asked once. One selected is named rather than counted - the
    name is on the row, and "1 locations" is not a sentence."""
    if not picked:
        return
    names = [str(row.get("name") or "") for row in picked]
    one = len(names) == 1
    shown = [] if one else names[:8] + ([t("said.and_more", value=(len(names) - 8))]
            if len(names) > 8 else [])
    if not await confirm.ask(
            t("console.locations.stop_looking", value=(names[0])) if one
            else t("console.locations.stop_looking_in", len=(len(names))),
            detail=t("console.locations.games_leave_library_nothing") if one
            else t("console.locations.games_leave_library_folders"),
            lines=shown, confirm=t("word.remove"), icon=verbs.REMOVE):
        return
    for row in picked:
        try:
            await offload.io(library.delete_location, str(row.get("id") or ""))
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("said.could_not_remove_it", exc=(exc)), type="negative")
            return
    if rerender is not None:
        rerender()


def _sort_it(found: dict[str, Any], state_now: str, said: str) -> str:
    """Which kind the typed folder is, decided, and the line that says so.

    Only for a folder that is there: the answer is what is inside it, and a path that
    does not resolve has nothing inside to read.
    """
    game = state_now == "ok" and tables.is_game_folder(said)
    found["kind"] = model.KIND_GAME if game else model.KIND_ROOT
    if state_now != "ok":
        return ""
    return t("console.locations.one_game_folder" if game
             else "console.locations.folder_of_games")


def _ask_new(library: Library, state: dict[str, Any],
             rerender: Callable[[], None] | None) -> None:
    """The folder, asked before the row exists.

    Not a placeholder row to edit afterwards, which is how Launchers adds one: a
    launcher with no program set reads as unconfigured, but a location with no folder
    reads as *unreachable* - the same words a share that has dropped uses. A row that
    looks broken the moment it is made is worse than one more dialog.

    `found` carries what `_sort_it` decided; the workbench's select is where a miss is
    corrected.
    """
    with ui.dialog() as dialog, ui.card():
        ui.label(t("console.locations.add_location")).classes("console-card-title")
        found: dict[str, Any] = {"kind": model.KIND_ROOT}
        folder = panel.path_field(placeholder="/path/to/your/games", wants="dir",
                                  on_checked=lambda state_now, said:
                                      _sort_it(found, state_now, said))

        async def keep() -> None:
            wanted = (folder.value or "").strip()
            if not wanted:
                folder.props('error error-message="Name a folder"')
                return
            dialog.close()
            await _create(library, state, rerender, found["kind"], wanted)

        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button(t("word.cancel"),
                icon=verbs.CANCEL, on_click=dialog.close).props("flat no-caps")
            ui.button(t("word.add"), icon=verbs.ADD, on_click=keep).props("no-caps")
    dialog.on("show", lambda: ui.run_javascript(
        f"document.getElementById('c{folder.id}').focus()"))
    dialog.open()


async def _create(library: Library, state: dict[str, Any], rerender: Callable[[], None] | None,
                  kind: str, path: str) -> None:
    made = model.mint_location_id()
    try:
        await run.io_bound(library.put_location, made, {"path": path, "kind": kind})
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("said.could_not_add_it", exc=(exc)), type="negative")
        return
    state["location"] = made
    if rerender is not None:
        rerender()


async def remove(library: Library, row: dict[str, Any]) -> bool:
    """Asked about first. The games in it leave the library, and their records go with
    them - which is where they live, so they are there again if it comes back."""
    if not await confirm.ask(
            t("console.locations.stop_looking", value=row["name"]) if row.get("name")
            else t("console.locations.stop_looking_here"),
            detail=t("console.locations.games_leave_library_nothing"),
            confirm=t("word.remove"), icon=verbs.REMOVE):
        return False
    try:
        await run.io_bound(library.delete_location, row["location_id"])
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("said.could_not_remove_it", exc=(exc)), type="negative")
        return False
    return True
