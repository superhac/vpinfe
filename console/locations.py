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

from . import confirm, grid, panel

logger = logging.getLogger("vpinfe.console.locations")

SCOPE = "locations"

# What a person would call each kind, rather than what the record calls it.
KIND_LABELS = {"root": "Game folders", "game": "One game"}

# The verb, for the buttons that make one. Not the same words as the column: adding is
# an act and reads as one.
ADD_LABELS = {"root": "Add a folder of games", "game": "Add a single game"}

_KIND_CHOICES = [{"value": key, "label": label} for key, label in KIND_LABELS.items()]

COLUMNS = [
    # The folder leads and is pinned. It is what a person recognizes a location by, and
    # every other column is a fact about it.
    grid.column("name", "Folder", 260, pinned="left",
                help="The folder this location is.\n"
                     "The last two parts of the path, because a library is very often\n"
                     "called `tables` and two of those would read the same."),
    grid.column("contains", "Contains", 140, **grid.choice_filter(_KIND_CHOICES),
                help="Game folders - its children are games.\n"
                     "One game - the location is itself a single game folder."),
    grid.column("state", "State", 140,
                help="What the disk says right now.\n\n"
                     "Ready - reachable and can be written to.\n"
                     "Read-only - reachable, but nothing can be added.\n"
                     "Unreachable - not there. Usually a share that has not mounted."),
    grid.column("new_games", "New Games", 120,
                help="Where a game you add or import is created.\n"
                     "One location holds this, and it is your choice."),
    grid.column("path", "Full Path", 420,
                help="The whole path, for telling two similar folders apart."),
]

LOCATION_VIEWS: dict[str, list[str]] = {
    "Overview": ["name", "contains", "state", "new_games", "path"],
}


def state_of(row: dict[str, Any]) -> str:
    """The fewest true words. Why is in the column's help and in the panel."""
    if not row.get("reachable"):
        return "Unreachable"
    return "Ready" if row.get("writable") else "Read-only"


def rows(locations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per location, with the wire's flags turned into words a column shows."""
    return [{
        "id": one["location_id"],
        "name": one["name"],
        "path": one["path"],
        "contains": KIND_LABELS.get(one["kind"], one["kind"]),
        "state": state_of(one),
        # Blank on every other row rather than "No": a column that says the same thing
        # everywhere but once is a column about the exception.
        "new_games": "Created here" if one.get("write_to") else "",
    } for one in locations]


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
            panel.facts(ui, [panel.intro(f"Could not read the locations: {exc}")])
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
                ui.button(label, icon="add",
                          on_click=lambda k=kind: _ask_new(library, state, rerender, k)) \
                    .props("flat dense no-caps size=sm").classes("shrink-0 console-action")
            search = panel.search("Search locations")
            wire_views, _picker, showing = view_control(library, SCOPE,
                                                        LOCATION_VIEWS, fields, COLUMNS)
            ui.space()
            ui.label(f"{len(built)} location{'' if len(built) == 1 else 's'}") \
                .classes("text-xs console-label")

        if not built:
            panel.facts(ui, [panel.intro(
                "No locations yet. Add the folder your games are in.")])
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
        ui.label(ADD_LABELS[kind]).classes("console-card-title")
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
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
            ui.button("Add", on_click=keep).props("no-caps")
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
        ui.notify(f"Could not add it: {exc}", type="negative")
        return
    state["location"] = made
    if rerender is not None:
        rerender()


async def remove(library, row: dict[str, Any]) -> bool:
    """Asked about first. The games in it leave the library, and their records go with
    them - which is where they live, so they are there again if it comes back."""
    if not await confirm.ask(
            f"Stop looking in {row.get('name') or 'this location'}?",
            detail="The games in it leave the library. Nothing on disk is touched, and "
                   "adding the folder again brings them back with their media and "
                   "their history.",
            confirm="Remove"):
        return False
    try:
        await run.io_bound(library.delete_location, row["location_id"])
    except Exception as exc:  # noqa: BLE001
        ui.notify(f"Could not remove it: {exc}", type="negative")
        return False
    return True
