"""Launchers: the list, and the one that is open beside it.

The shape Collections and Devices already use - a short list of user objects with an
action per row, and the selected one edited in the work area. Not a settings page: add,
remove and duplicate are acts on a collection of objects, and a page of label-and-value
pairs has nowhere to put them.

The editor is generated from what the install says a launcher of that app holds, through
the same control grammar every settings page uses. Nothing here knows that a Visual
Pinball launcher has a binary and an ini.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common import path_checks
from console import confirm, panel
from console import settings as settings_page

logger = logging.getLogger("vpinfe.console.launchers")

RAIL_PX = 230

# Said once over the list rather than under each row. What a launcher is for, in the words
# somebody would use before they know the word.
INTRO = ("Each one is a way of running a table: which program, and how it is configured. "
         "Tables use the first one that is switched on unless they name another.")

# Why a row is the default, where that is not obvious. Only on the one it applies to -
# a note on every row would say nothing.
DEFAULT_HINT = "Tables that name no launcher use this one."


def build(library, state: dict[str, Any], redraw: Callable[[], None]) -> None:
    """The list and the open launcher. Read on every draw, because this page edits it."""
    body = ui.column().classes("w-full grow min-h-0 gap-0")
    # On a timer, because reading goes over HTTP and the draw it is part of runs on the
    # event loop, where the client refuses a call.
    ui.timer(0.01, lambda: _fill(library, state, redraw, body), once=True)


async def _fill(library, state: dict[str, Any], redraw: Callable[[], None],
                body) -> None:
    try:
        found = await run.io_bound(library.launchers)
    except Exception as exc:  # noqa: BLE001 - this page says why, never 500s
        with body:
            panel.facts(ui, [panel.intro(f"Could not read the launchers: {exc}")])
        return

    held = list(found.get("launchers") or [])
    apps_known = list(found.get("apps") or [])
    defaults = dict(found.get("defaults") or {})
    chosen = str(state.get("launcher") or "")
    if chosen not in {one["launcher_id"] for one in held}:
        chosen = held[0]["launcher_id"] if held else ""
    state["launcher"] = chosen

    with body:
        _toolbar(library, state, redraw, apps_known)
        if not held:
            panel.facts(ui, [panel.intro(
                "No launchers yet. Add one and point it at the program that plays your "
                "tables.")])
            return
        _list_and_editor(library, state, redraw, held, defaults, chosen)


def _toolbar(library, state: dict[str, Any], redraw: Callable[[], None],
             apps_known: list[dict]) -> None:
    """Add, above the list rather than inside it. Adding is not a row."""
    # Two rows, not one. Sharing a line put the button against the middle of a paragraph
    # that wraps, which reads as though it belongs to the second sentence.
    with ui.column().classes("w-full gap-1 px-3 pt-2 pb-1"):
        ui.label(INTRO).classes("console-help")
        with ui.row().classes("items-center gap-2 w-full no-wrap"):
            for app in apps_known:
                ui.button(f"Add {app['name']}",
                          on_click=lambda a=app: _add(library, state, redraw, a)) \
                    .props("flat dense no-caps size=sm")


def _mark(one: dict) -> Callable[[], None] | None:
    """The exceptions only, and the worse one wins.

    Switched off is a choice somebody made; a program that is not there is a launcher
    that cannot run, and it is the one to say when a row is both.
    """
    broken = next((said for said in _broken(one)), "")
    if broken:
        return panel.trouble_mark(broken)
    if not one["enabled"]:
        return panel.trouble_mark("Switched off. Tables that name it fall back.")
    return None


def _broken(one: dict):
    """Every path this launcher names that the disk cannot answer for, worst first."""
    checks = one.get("checks") or {}
    labels = {field["key"]: field["label"] for field in one.get("fields") or []}
    for key, found in checks.items():
        state = str(found.get("state") or "")
        if state in ("", path_checks.OK, path_checks.UNSET):
            continue
        yield f"{labels.get(key, key)}: {found.get('reason') or state}"


def _list_and_editor(library, state: dict[str, Any], redraw: Callable[[], None],
                     held: list[dict], defaults: dict, chosen: str) -> None:
    entries: list[tuple[Any, ...]] = []
    for one in held:
        is_default = defaults.get(one["app"]) == one["launcher_id"]
        # The name a person gave it, and what it runs underneath. The app is not a second
        # column: it only says something the name does not when they differ.
        hint = DEFAULT_HINT if is_default else ""
        entries.append((one["launcher_id"], one["display_name"], hint, _mark(one)))

    def pick(key: str) -> None:
        state["launcher"] = key
        redraw()

    work = panel.sections(entries, chosen, pick, rail_px=RAIL_PX)
    open_now = next((one for one in held if one["launcher_id"] == chosen), None)
    if open_now is None:
        return
    with work:
        with ui.column().classes("min-w-0 overflow-auto gap-0 console-workbench-body"):
            _editor(library, state, redraw, open_now,
                    is_default=defaults.get(open_now["app"]) == open_now["launcher_id"],
                    only_one=len(held) == 1)


def _editor(library, state: dict[str, Any], redraw: Callable[[], None],
            launcher: dict, *, is_default: bool, only_one: bool) -> None:
    """One launcher, drawn from the fields its app declares."""
    launcher_id = launcher["launcher_id"]

    async def write(**changes: Any) -> bool:
        body = {**launcher, **changes}
        try:
            await run.io_bound(library.put_launcher, launcher_id, body)
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"Could not save: {exc}", type="negative")
            return False
        return True

    async def rename(text: str) -> None:
        await write(display_name=text.strip() or launcher["app_name"])

    async def flip(on: bool) -> None:
        if await write(enabled=on):
            redraw()

    def save_field(key: str) -> Callable[[Any], Any]:
        async def save(value: Any) -> bool:
            return await write(settings={**launcher["settings"], key: value})
        return save

    entries: list[tuple[Any, Any]] = [
        ("Name", panel.field(launcher["display_name"], rename,
                             placeholder=launcher["app_name"])),
        panel.note("What you call this way of running a table. Nothing is addressed by "
                   "it, so renaming is safe."),
    ]
    if is_default:
        entries.append(panel.note(DEFAULT_HINT))
    entries.append(("Runs", launcher["app_name"]))
    entries.append(("Enabled", panel.switch(
        launcher["enabled"], lambda e: flip(bool(e.value)),
        disabled=only_one,
        hint="The only launcher this install has." if only_one else "")))
    entries.append(panel.note(
        "Switched off it stays configured and keeps its tables, and they fall back to "
        "the default until it is switched on again."))

    entries.append((panel.HEADING, "How it runs"))
    for field in launcher.get("fields") or []:
        entries.append((field["label"],
                        settings_page.control_for(
                            field, launcher["settings"].get(field["key"]),
                            save_field(field["key"]), rerender=redraw,
                            check=(launcher.get("checks") or {}).get(field["key"]))))
        if field.get("description"):
            entries.append(panel.note(field["description"]))

    entries.append(("", _actions(library, state, redraw, launcher, only_one)))
    panel.facts(ui, entries)


def _actions(library, state: dict[str, Any], redraw: Callable[[], None],
             launcher: dict, only_one: bool) -> Callable[[], None]:
    def draw() -> None:
        with ui.row().classes("items-center gap-2 no-wrap"):
            ui.button("Duplicate",
                      on_click=lambda: _duplicate(library, state, redraw, launcher)) \
                .props("flat dense no-caps size=sm")
            if state.get("can_manage_devices"):
                ui.button("Copy to devices",
                          on_click=lambda: _copy_dialog(library, state, launcher)) \
                    .props("flat dense no-caps size=sm")
            remove = ui.button(
                "Remove",
                on_click=lambda: _remove(library, state, redraw, launcher)) \
                .props("flat dense no-caps size=sm color=negative")
            if only_one:
                remove.disable()
                remove.tooltip("The only launcher this install has.")
    return draw


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


async def _duplicate(library, state: dict[str, Any], redraw: Callable[[], None],
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


async def _copy_dialog(library, state: dict[str, Any], launcher: dict) -> None:
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


async def _remove(library, state: dict[str, Any], redraw: Callable[[], None],
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
