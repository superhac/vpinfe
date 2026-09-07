"""Launchers: which ways this install runs a table, and one of them open beside it.

A grid with a workbench, the shape Devices uses, and for the reason Devices uses it: one
launcher is deep. Its own seven fields are the least of it - an app declares its whole
settings surface, which for Visual Pinball is around twelve hundred keys in named groups,
and that is more inside one object than anything else in the Console holds. A section rail
is how the Console shows what is inside one thing, and without one the seven fields
somebody actually came to change sit at the top of a thousand-row scroll.

The grid answers the one question a list of launchers has: which of these can actually
run a table. It knows because each row carries what the disk made of the program it
names.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common import path_checks
from console import confirm, grid, panel

logger = logging.getLogger("vpinfe.console.launchers")

SCOPE = "console.launchers.columns"

# Said once over the list rather than under each row. What a launcher is for, in the
# words somebody would use before they know the word.
INTRO = ("Each one is a way of running a table: which program, and how it is configured. "
         "Tables use the first one that is switched on unless they name another.")

# Why a row is the default, where that is not obvious. Only on the one it applies to -
# a note on every row would say nothing.
DEFAULT_HINT = "Tables that name no launcher use this one."

STATE_READY = "Ready"
STATE_OFF = "Switched off"
STATE_BROKEN = "Cannot run"

_STATE_CHOICES = [{"value": one, "label": one}
                  for one in (STATE_READY, STATE_OFF, STATE_BROKEN)]

COLUMNS: list[dict[str, Any]] = [
    grid.column("name", "Name", 240, pinned="left",
                help="What you called this way of running a table."),
    grid.column("app", "Runs", 180,
                help="The program behind it. It only says something the name does not\n"
                     "where the two differ."),
    grid.column("state", "State", 150, **grid.choice_filter(_STATE_CHOICES),
                help="Ready - it is switched on and its program is there.\n"
                     "Cannot run - a path it names is not on this machine.\n"
                     "Switched off - configured, keeping its tables, not in use."),
    grid.column("default", "Default", 110,
                help="Tables that name no launcher use this one."),
    grid.column("program", "Program", 420,
                help="The executable this launcher runs."),
]

LAUNCHER_VIEWS: dict[str, list[str]] = {
    "Overview": ["name", "app", "state", "default", "program"],
}


def _broken(one: dict):
    """Every path this launcher names that the disk cannot answer for."""
    checks = one.get("checks") or {}
    labels = {field["key"]: field["label"] for field in one.get("fields") or []}
    for key, found in checks.items():
        state = str(found.get("state") or "")
        if state in ("", path_checks.OK, path_checks.UNSET):
            continue
        yield f"{labels.get(key, key)}: {found.get('reason') or state}"


def state_of(one: dict) -> str:
    """The worse fact wins. Switched off is a choice somebody made; a program that is
    not there is a launcher that cannot run, and it is the one to say when a row is
    both."""
    if next(iter(_broken(one)), ""):
        return STATE_BROKEN
    return STATE_READY if one.get("enabled") else STATE_OFF


def rows(held: list[dict], defaults: dict) -> list[dict[str, Any]]:
    return [{
        "id": one["launcher_id"],
        "name": one["display_name"],
        "app": one["app_name"],
        "state": state_of(one),
        # Blank on every other row rather than "No": a column that says the same thing
        # everywhere but once is a column about the exception.
        "default": "Default" if defaults.get(one["app"]) == one["launcher_id"] else "",
        "program": str((one.get("settings") or {}).get("bin_path") or ""),
    } for one in held]


def build(library, state: dict[str, Any],
          on_select: Callable[[dict | None], Any],
          redraw: Callable[[], None]) -> None:
    """The grid. Read on every draw, because this page edits it and what the disk says
    can change without anybody editing anything."""
    body = ui.column().classes("w-full grow min-h-0 gap-0")
    # On a timer, because reading goes over HTTP and the draw it is part of runs on the
    # event loop, where the client refuses a call.
    ui.timer(0.01, lambda: _fill(library, state, on_select, redraw, body), once=True)


async def _fill(library, state: dict[str, Any], on_select: Callable[[dict | None], Any],
                redraw: Callable[[], None], body) -> None:
    try:
        found = await run.io_bound(library.launchers)
    except Exception as exc:  # noqa: BLE001 - this page says why, never 500s
        with body:
            panel.facts(ui, [panel.intro(f"Could not read the launchers: {exc}")])
        return

    # Imported here: `workbench` imports this module, and `games` imports `workbench`,
    # so reaching for it at the top would close the loop.
    from console.games import view_control

    held = list(found.get("launchers") or [])
    apps_known = list(found.get("apps") or [])
    built = rows(held, dict(found.get("defaults") or {}))
    fields = [definition["field"] for definition in COLUMNS]

    with body:
        with ui.column().classes("w-full gap-1 px-3 pt-2 pb-1"):
            ui.label(INTRO).classes("console-help")
            with ui.row().classes("items-center gap-2 w-full no-wrap"):
                for app in apps_known:
                    ui.button(f"Add {app['name']}", icon="add",
                              on_click=lambda a=app: _add(library, state, redraw, a)) \
                        .props("flat dense no-caps size=sm").classes("console-action")
                search = panel.search("Search launchers")
                wire_views, _picker, showing = view_control(library, SCOPE,
                                                            LAUNCHER_VIEWS, fields,
                                                            COLUMNS)
                ui.space()
                ui.label(f"{len(built)} launcher{'' if len(built) == 1 else 's'}") \
                    .classes("text-xs console-label")

        if not built:
            panel.facts(ui, [panel.intro(
                "No launchers yet. Add one and point it at the program that plays your "
                "tables.")])
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


async def _add(library, state: dict[str, Any], redraw: Callable[[], None],
               app: dict) -> None:
    """A new launcher for an app, with nothing filled in.

    Nothing copied from an existing one: Add is for a second program, and Duplicate is
    the action for a second way of running the same one.
    """
    from common.games import launchers as model

    made = model.mint_launcher_id()
    try:
        await run.io_bound(library.put_launcher, made,
                           {"app": app["id"], "display_name": app["name"],
                            "enabled": True, "settings": {}})
    except Exception as exc:  # noqa: BLE001
        ui.notify(f"Could not add it: {exc}", type="negative")
        return
    state["launcher"] = made
    redraw()


async def duplicate(library, state: dict[str, Any], redraw: Callable[[], None],
                     launcher: dict) -> None:
    """A copy, which is the case this feature exists for: change one thing - usually the
    configuration file - and you have a second way of running the same program.

    The copy does not claim to own an ini. It points at whatever the original did, and
    only a file VPinFE made is one VPinFE offers to delete.
    """
    from common.games import launchers as model

    made = model.mint_launcher_id()
    try:
        await run.io_bound(library.put_launcher, made,
                           {**launcher, "launcher_id": made, "owns_ini": False,
                            "display_name": f"{launcher['display_name']} copy"})
    except Exception as exc:  # noqa: BLE001
        ui.notify(f"Could not duplicate it: {exc}", type="negative")
        return
    state["launcher"] = made
    redraw()


async def copy_dialog(library, state: dict[str, Any], launcher: dict) -> None:
    """Pick the machines, see what it will do, then do it.

    A copy with no ongoing link, which the dialog says rather than leaving somebody to
    find out: edit a cabinet's launcher afterwards and the two diverge.
    """
    try:
        known = await run.io_bound(library.devices)
    except Exception as exc:  # noqa: BLE001
        ui.notify(f"Could not read the devices: {exc}", type="negative")
        return
    # Only other VPinFE installs. A phone runs no launcher, and this install already has
    # the launcher being copied.
    mine = str(state.get("install_id") or "")
    reachable = [one for one in known
                 if str(one.get("kind") or "vpinfe") == "vpinfe"
                 and str(one.get("device_id") or "") != mine]
    if not reachable:
        ui.notify("No other VPinFE installs are known to this one.", type="warning")
        return

    picked: set[str] = set()
    with ui.dialog() as dialog, ui.card().classes("console-confirm"):
        ui.label(f"Copy {launcher['display_name']} to which machines?") \
            .classes("console-confirm-title")
        ui.label("It arrives with the same name and the same id, so a table that names "
                 "it there means this launcher. A program path that does not exist on "
                 "that machine is reported by it, not here.") \
            .classes("console-help")
        for one in reachable:
            name = str(one.get("display_name") or one.get("device_id"))
            ui.checkbox(name, on_change=lambda e, d=one: (
                picked.add(str(d.get("device_id"))) if e.value
                else picked.discard(str(d.get("device_id"))))) \
                .props("dense")
        also = ui.checkbox("Also copy which tables use it").props("dense")
        ui.label("A one-way copy. Change it on a machine afterwards and the two differ "
                 "from then on - nothing keeps them in step.").classes("console-help")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Cancel", on_click=lambda: dialog.submit(None)).props("flat no-caps")
            ui.button("Copy", on_click=lambda: dialog.submit(True)).props("no-caps")

    if not await dialog:
        return
    if not picked:
        ui.notify("No machines picked.", type="warning")
        return
    await _do_copy(library, launcher, [one for one in reachable
                                       if str(one.get("device_id")) in picked],
                   bool(also.value))


async def _do_copy(library, launcher: dict, devices: list[dict],
                   with_mappings: bool) -> None:
    from common.games import launcher_copy

    mappings = {}
    if with_mappings:
        try:
            found = await run.io_bound(library.launchers)
            mappings = {table: to for table, to in (found.get("mappings") or {}).items()
                        if to == launcher["launcher_id"]}
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"Could not read the assignments: {exc}", type="negative")
            return

    def client_for(device):
        from common import device_client

        return device_client.for_device(device)

    outcomes = await run.io_bound(launcher_copy.copy_to, devices, [launcher],
                                  mappings, client_for=client_for)
    said = launcher_copy.said(outcomes)
    ui.notify(said, type="positive" if all(one.ok for one in outcomes) else "warning")


async def remove(library, state: dict[str, Any], redraw: Callable[[], None],
                  launcher: dict) -> None:
    """Asked about first, because it is the destructive one and it takes assignments
    with it - a table pointing here goes back to the default."""
    if not await confirm.ask(
            f"Remove {launcher['display_name']}?",
            detail="Tables that name it go back to the default launcher. Its settings "
                   "are gone; the program and any file it points at are left alone.",
            confirm="Remove"):
        return
    try:
        await run.io_bound(library.delete_launcher, launcher["launcher_id"])
    except Exception as exc:  # noqa: BLE001
        ui.notify(f"Could not remove it: {exc}", type="negative")
        return
    state["launcher"] = ""
    redraw()
