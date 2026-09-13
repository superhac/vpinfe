
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

from common.i18n import t

from . import confirm, grid, panel

logger = logging.getLogger("vpinfe.console.locations")

SCOPE = "locations"

# What a person would call each kind, rather than what the record calls it.
KIND_LABELS = {"root": "console.locations.game_folders",
               "game": "console.locations.one_game"}

# The verb, for the buttons that make one. Not the same words as the column: adding is
# an act and reads as one.
ADD_LABELS = {
    "root": "console.locations.add.add_folder_games",
    "game": "console.locations.add.add_single_game"
}

_KIND_CHOICES = [{"value": key, "label": t(label)} for key, label in KIND_LABELS.items()]

COLUMNS = [
    # The folder leads and is pinned. It is what a person recognizes a location by, and
    # every other column is a fact about it.
    grid.column("name", t("word.folder"), 260, pinned="left",
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

LOCATION_VIEWS: dict[str, list[str]] = {
    t("console.view.overview"): ["name", "contains", "state", "new_games", "shadowed", "path"],
    # Its own view rather than more columns on Overview: this one is read when
    # something is wrong, and the question is which location beats which.
    t("word.priority"): ["name", "priority", "shadowed", "state", "path"],
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


def build(library, state: dict[str, Any],
          on_select: Callable[[dict | None], Any],
          rerender: Callable[[], None] | None = None) -> None:
    """The grid. Read on every draw, because what the disk says changes without anybody
    editing anything."""
    body = ui.column().classes("w-full grow min-h-0 gap-0")
    # On a timer, because reading goes over HTTP and the draw it is part of runs on the
    # event loop, where the client refuses a call.
    ui.timer(0.01, lambda: _fill(library, state, on_select, rerender, body), once=True)


async def _fill(library, state: dict[str, Any], on_select: Callable[[dict | None], Any],
                rerender: Callable[[], None] | None, body) -> None:
    try:
        found = await run.io_bound(library.locations)
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
                "w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 console-panel"):
            for kind, label in ADD_LABELS.items():
                ui.button(t(label), icon="add",
                          on_click=lambda k=kind: _ask_new(library, state, rerender, k)) \
                    .props("flat dense no-caps size=sm").classes("shrink-0 console-action")
            search = panel.search(t("console.locations.search_locations"))
            wire_views, _picker, showing = view_control(library, SCOPE,
                                                        LOCATION_VIEWS, fields, COLUMNS)
            ui.space()
            ui.label(t("console.locations.location", len=(len(built)),
                    value=('' if len(built) == 1 else 's'))) \
                .classes("text-xs console-label")

        if not built:
            panel.facts(ui, [panel.intro(
                t("console.locations.no_locations_yet_add"))])
            return

        by_id = {row["id"]: row for row in built}
        ui.on("hub_row_focus",
              lambda event: on_select(by_id.get(grid.focused_row(event))))
        with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
            table = grid.build(COLUMNS, built, SCOPE, view_of=showing)
        search.on_value_change(
            lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                          search.value or ""))
        # After the grid exists: the widgets sit above it and the behavior needs it.
        wire_views(table)


def _ask_new(library, state: dict[str, Any], rerender: Callable[[], None] | None,
             kind: str) -> None:
    """The folder, asked before the row exists.

    Not a placeholder row to edit afterwards, which is how Launchers adds one: a
    launcher with no program set reads as unconfigured, but a location with no folder
    reads as *unreachable* - the same words a share that has dropped uses. A row that
    looks broken the moment it is made is worse than one more dialog.
    """
    with ui.dialog() as dialog, ui.card():
        ui.label(t(ADD_LABELS[kind])).classes("console-card-title")
        folder = ui.input(placeholder="/path/to/your/games") \
            .props("outlined dense debounce=0").classes("w-96")

        async def keep() -> None:
            wanted = (folder.value or "").strip()
            if not wanted:
                folder.props('error error-message="Name a folder"')
                return
            dialog.close()
            await _create(library, state, rerender, kind, wanted)

        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button(t("word.cancel"), on_click=dialog.close).props("flat no-caps")
            ui.button(t("word.add"), on_click=keep).props("no-caps")
    dialog.on("show", lambda: ui.run_javascript(
        f"document.getElementById('c{folder.id}').focus()"))
    dialog.open()


async def _create(library, state: dict[str, Any], rerender: Callable[[], None] | None,
                  kind: str, path: str) -> None:
    from common.games import locations as model

    made = model.mint_location_id()
    try:
        await run.io_bound(library.put_location, made, {"path": path, "kind": kind})
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("said.could_not_add_it", exc=(exc)), type="negative")
        return
    state["location"] = made
    if rerender is not None:
        rerender()


async def remove(library, row: dict[str, Any]) -> bool:
    """Asked about first. The games in it leave the library, and their records go with
    them - which is where they live, so they are there again if it comes back."""
    if not await confirm.ask(
            t("console.locations.stop_looking",
                    value=(row.get('name') or t("console.locations.location_2"))),
            detail=t("console.locations.games_leave_library_nothing"),
            confirm=t("word.remove")):
        return False
    try:
        await run.io_bound(library.delete_location, row["location_id"])
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("said.could_not_remove_it", exc=(exc)), type="negative")
        return False
    return True
