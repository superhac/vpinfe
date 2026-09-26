"""Launchers: which ways this install runs a table, and one of them open beside it.

A grid with a workbench, the shape Devices uses, and for the reason Devices uses it: one
launcher is deep. Its own seven fields are the least of it - an app declares its whole
settings surface, which for Visual Pinball is around twelve hundred keys in named groups,
and that is more inside one object than anything else in the Console holds. A section rail
is how the Console shows what is inside one thing, and without one the seven fields
somebody actually came to change sit at the top of a thousand-row scroll.

The grid answers how many tables each launcher plays, and says a state only on the ones
that cannot play them. It knows because each row carries what the disk made of the
program it names.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import run, ui

from common import install_identity, path_checks
from common.failures import why
from common.i18n import t
from console import confirm, grid, offload, panel, verbs, views
from console import dialog as frame
from console.data import Library

logger = logging.getLogger("vpinfe.console.launchers")

SCOPE = "console.launchers.columns"

STATE_READY = ""
STATE_OFF = "console.launchers.switched_off"
STATE_MISSING = "console.launchers.program_missing"
STATE_NO_PROGRAM = "console.launchers.no_program"

_STATE_CHOICES = [{"value": one, "label": one}
                  for one in (t(STATE_NO_PROGRAM), t(STATE_MISSING), t(STATE_OFF))]

_NUMERIC: dict[str, Any] = {"type": "numericColumn", "filter": "agNumberColumnFilter"}

COLUMNS: list[dict[str, Any]] = [
    grid.identifier("name", t("word.name"), 240, pinned="left", subtitle="app"),
    grid.column("tables", t("console.launchers.tables"),
                help=t("console.launchers.tables.help"), **_NUMERIC),
    grid.column("state", t("word.state"), 150, **grid.choice_filter(_STATE_CHOICES),
                help=t("console.launchers.ready_switched_program_cannot.help")),
    grid.column("default", t("word.default"), 110,
                help=t("console.launchers.tables_name_no_launcher.help")),
    grid.column("app", t("word.runs"), 180),
    grid.column("program", t("word.program"), 420,
                help=t("console.launchers.executable_launcher_runs.help")),
]

LAUNCHER_VIEWS: dict[str, list[str] | views.Preset] = {
    "console.view.overview": views.Preset(
        columns=("name", "tables", "state", "default"),
        help=t("console.view.launchers.help")),
}


def _program_check(one: dict) -> str:
    """What the disk made of the program it names, or "" where its app names none."""
    checks = one.get("checks") or {}
    return next((str((checks.get(field["key"]) or {}).get("state") or "")
                 for field in one.get("fields") or [] if field.get("path") == "exe"), "")


def state_of(one: dict) -> str:
    """The worse fact wins. Switched off is a choice somebody made; a launcher with no
    program to run is the one to say when a row is both."""
    program = _program_check(one)
    if program == path_checks.UNSET:
        return STATE_NO_PROGRAM
    if program not in ("", path_checks.OK):
        return STATE_MISSING
    return STATE_READY if one.get("enabled") else STATE_OFF


def rows(held: list[dict], defaults: dict,
         plays: dict[str, int] | None = None) -> list[dict[str, Any]]:
    return [{
        "id": one["launcher_id"],
        "name": one["display_name"],
        "tables": int((plays or {}).get(one["launcher_id"]) or 0),
        "app": one["app_name"],
        "state": t(found) if (found := state_of(one)) else "",
        # Blank on every other row rather than "No": a column that says the same thing
        # everywhere but once is a column about the exception.
        "default": t("word.default") if defaults.get(one["app"]) ==
                one["launcher_id"] else "",
        "program": str((one.get("settings") or {}).get("bin_path") or ""),
    } for one in held]


def launcher_offer(held: list[dict], app: str, named: str = "") -> list[dict[str, Any]]:
    """What a table of `app` may be pointed at, in order: that app's launchers, then
    every other program's. A switched-off one is left out unless the table names it,
    since picking it would change nothing that happens."""
    shown = [one for one in held if one.get("enabled") or one["launcher_id"] == named]
    ordered = ([one for one in shown if one.get("app") == app]
               + [one for one in shown if one.get("app") != app])
    return [{"id": one["launcher_id"], "name": one["display_name"],
             "other": one.get("app") != app,
             "mark": (t(STATE_OFF) if not one.get("enabled")
                      else t("word.default") if one.get("app") == app and one.get("is_default")
                      else "")}
            for one in ordered]


def build(library: Library, state: dict[str, Any],
          on_select: Callable[[dict | None], Any],
          redraw: Callable[[], None]) -> None:
    """The grid. Read on every draw, because this page edits it and what the disk says
    can change without anybody editing anything."""
    body = ui.column().classes("w-full grow min-h-0 gap-0")
    # On a timer, because reading goes over HTTP and the draw it is part of runs on the
    # event loop, where the client refuses a call.
    ui.timer(0.01, lambda: _fill(library, state, on_select, redraw, body), once=True)


async def _fill(library: Library, state: dict[str, Any], on_select: Callable[[dict | None], Any],
                redraw: Callable[[], None], body: Any) -> None:
    state["show_launcher"] = on_select
    try:
        found = await offload.io(library.launchers)
    except Exception as exc:  # noqa: BLE001 - this page says why, never 500s
        with body:
            panel.facts(ui, [panel.intro(t("console.launchers.could_not_read_launchers"),
                                         hint=why(exc))])
        return

    # Imported here: `workbench` imports this module, and `games` imports `workbench`,
    # so reaching for it at the top would close the loop.
    from console.games import view_control

    held = list(found.get("launchers") or [])
    apps_known = list(found.get("apps") or [])
    built = rows(held, dict(found.get("defaults") or {}), dict(found.get("tables") or {}))
    fields = [definition["field"] for definition in COLUMNS]

    with body:
        with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                              "console-panel console-grid-bar"):
            bar = panel.grid_bar()
            wire_views, _picker, showing, describe = view_control(
                library, SCOPE, LAUNCHER_VIEWS, fields, COLUMNS, bar=bar)
            describe()
            with bar.top, panel.bar_end():
                search = panel.search(t("console.launchers.search_launchers"))
            with bar.bottom, panel.bar_end():
                ui.label(t("console.launchers.launcher", count=len(built))) \
                    .classes("text-xs console-label")
                panel.add_action(
                    [(t("console.launchers.add", app=one["name"]),
                      (lambda a=one: _add(library, state, redraw, a)))
                     for one in apps_known],
                    empty=not built, heading=t("console.launchers.new_launcher"))

        if not built:
            panel.facts(ui, [panel.intro(
                t("console.launchers.no_launchers_yet_add"))])
            return

        by_id = {row["id"]: row for row in built}
        by_launcher = {one["launcher_id"]: one for one in held}
        grid.on_row_focus(SCOPE,
                          lambda event: on_select(by_id.get(grid.focused_row(event))))

        def fill(row: dict | None) -> None:
            launcher = by_launcher.get(str((row or {}).get("id") or ""))
            if launcher is None:
                menu.clear()
                return
            panel.verb_menu(menu, str(launcher["display_name"]),
                            acts(library, state, launcher, len(held), redraw))

        with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
            table = grid.build(COLUMNS, built, SCOPE, on_context=fill, view_of=showing)
            menu = ui.context_menu()
        search.on_value_change(
            lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                          search.value or ""))
        # After the grid exists: the widgets sit above it and the behavior needs it.
        wire_views(table)

        async def refresh_launchers() -> None:
            again = await offload.io(library.launchers)
            fresh_held = list(again.get("launchers") or [])
            by_launcher.clear()
            by_launcher.update({one["launcher_id"]: one for one in fresh_held})
            grid.replace_rows(table, built, by_id,
                              rows(fresh_held, dict(again.get("defaults") or {}),
                                   dict(again.get("tables") or {})),
                              lambda _row: True)

        state["refresh_launchers"] = refresh_launchers


async def _add(library: Library, state: dict[str, Any], redraw: Callable[[], None],
               app: dict) -> None:
    """A new launcher for an app: its name, and the paths the app declares.

    Nothing copied from an existing one: Add is for a second program, and Duplicate is
    the action for a second way of running the same one.
    """
    from common.games import launchers as model

    names = await _names(library)
    asked = [one for one in app.get("fields") or [] if one.get("path")]
    made = model.mint_launcher_id()

    async def write(name: str, settings: dict[str, str]) -> None:
        await run.io_bound(library.put_launcher, made, {
            "app": app["id"], "enabled": True, "settings": settings,
            "display_name": name or model.free_name(app["name"], names)})

    if await ask_name(t("console.launchers.new_title", app=app["name"]), t("word.add"),
                      names, write, asked=asked,
                      placeholder=t("console.launchers.name_example", app=app["name"])):
        await _open(state, redraw, made)


async def duplicate(library: Library, state: dict[str, Any], redraw: Callable[[], None],
                     launcher: dict) -> None:
    """A copy, which is the case this feature exists for: change one thing - usually the
    Settings File - and you have a second way of running the same program.

    The copy does not claim to own an ini. It points at whatever the original did, and
    only a file VPinFE made is one VPinFE offers to delete.
    """
    from common.games import launchers as model

    names = await _names(library)
    made = model.mint_launcher_id()
    offered = model.free_name(t("console.launchers.copy_of", name=launcher["display_name"]),
                              names)

    async def write(name: str, _settings: dict[str, str]) -> None:
        await run.io_bound(library.put_launcher, made,
                           {**launcher, "launcher_id": made, "owns_ini": False,
                            "display_name": name or offered})

    if await ask_name(t("console.launchers.duplicate_title", name=launcher["display_name"]),
                      t("console.workbench.duplicate"), names, write, named=offered,
                      icon=verbs.DUPLICATE):
        await _open(state, redraw, made)


async def _open(state: dict[str, Any], redraw: Callable[[], None], made: str) -> None:
    """The grid drawn again with it, and it in the workbench."""
    state["launcher"] = made
    grid.land_on(SCOPE, {"id": made})
    redraw()
    show = state.get("show_launcher")
    if callable(show):
        await show({"id": made})


async def ask_name(title: str, answer: str, names: list[str],
                   write: Callable[[str, dict[str, str]], Awaitable[None]], *,
                   named: str = "", asked: list[dict] | None = None,
                   placeholder: str = "", icon: str = verbs.CREATE) -> bool:
    """Name a launcher, and fill the path fields `asked` lists, before it exists.

    True once `write` took it. A name already in use, or any refusal from `write`, is
    said on the Name field and the dialog stays open.
    """
    from common.games import launchers as model

    fields: dict[str, Any] = {}

    def draw(key: str, value: str = "", hint: str = "") -> Callable[[], None]:
        def drawn() -> None:
            fields[key] = frame.field(value, placeholder=hint)
        return drawn

    def refused(why: str) -> None:
        fields["name"].props["error"] = bool(why)
        fields["name"].props["error-message"] = why

    async def keep() -> None:
        name = " ".join(str(fields["name"].value or "").split())
        if any(model.same_name(name, one) for one in names):
            refused(t("error.launchers.name_taken", name=name))
            return
        try:
            await write(name, {one["key"]: str(fields[one["key"]].value or "").strip()
                               for one in asked or ()})
        except Exception as exc:  # noqa: BLE001 - said where it can be put right
            refused(why(exc))
            return
        box.submit(True)

    with frame.opened(title) as box:
        panel.facts(ui, [(t("word.name"), draw("name", named, placeholder))]
                    + [(one["label"], draw(one["key"], hint=str(one.get("blank") or "")))
                       for one in asked or ()])
        with frame.footer():
            frame.cancel(lambda: box.submit(False))
            go = frame.answer(answer, keep, icon=icon)
    fields["name"].on_value_change(lambda: refused(""))
    frame.focus(box, fields["name"], select=bool(named))
    frame.enter_presses(go)
    return bool(await box)


async def _names(library: Library) -> list[str]:
    found = await offload.io(library.launchers)
    return [str(one.get("display_name") or "") for one in found.get("launchers") or []]


def copy_targets(known: list[dict], install_id: str) -> list[dict]:
    return [one for one in known
            if str(one.get("kind") or "vpinfe") == "vpinfe"
            and install_identity.FRONTEND in (one.get("features") or ())
            and str(one.get("device_id") or "") != install_id]


async def copy_dialog(library: Library, state: dict[str, Any], launcher: dict) -> None:
    """Pick the devices, see what it will do, then do it.

    A copy with no ongoing link, which the dialog says rather than leaving somebody to
    find out: edit a cabinet's launcher afterwards and the two diverge.
    """
    try:
        known = await offload.io(library.devices)
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("console.launchers.could_not_read_devices"), caption=why(exc),
                  type="negative")
        return
    reachable = copy_targets(known, str(state.get("install_id") or ""))
    if not reachable:
        ui.notify(t("console.launchers.no_other_frontend"), type="warning")
        return

    picked: set[str] = set()
    with frame.opened(t("console.launchers.copy_to_devices",
                        value=launcher["display_name"])) as box:
        ui.label(t("console.launchers.arrives_same_name_same")).classes("console-help px-3")
        with ui.column().classes("gap-1 px-3"):
            for one in reachable:
                name = str(one.get("display_name") or one.get("device_id"))
                ui.checkbox(name, on_change=lambda e, d=one: (
                    picked.add(str(d.get("device_id"))) if e.value
                    else picked.discard(str(d.get("device_id"))))) \
                    .props("dense")
            also = ui.checkbox(t("console.launchers.also_copy_tables_use")).props("dense")
        ui.label(t("console.launchers.one_way_copy_change")).classes("console-help px-3")
        with frame.footer():
            frame.cancel(lambda: box.submit(None))
            frame.answer(t("word.copy"), lambda: box.submit(True), icon=verbs.COPY)

    if not await box:
        return
    if not picked:
        ui.notify(t("console.launchers.no_devices_picked"), type="warning")
        return
    await _do_copy(library, launcher, [one for one in reachable
                                       if str(one.get("device_id")) in picked],
                   bool(also.value))


async def _do_copy(library: Library, launcher: dict, devices: list[dict],
                   with_mappings: bool) -> None:
    from common.games import launcher_copy

    mappings = {}
    if with_mappings:
        try:
            found = await offload.io(library.launchers)
            mappings = {table: to for table, to in (found.get("mappings") or {}).items()
                        if to == launcher["launcher_id"]}
        except Exception as exc:  # noqa: BLE001
            ui.notify(t("console.launchers.could_not_read_assignments"), caption=why(exc),
                      type="negative")
            return

    def client_for(device: Any) -> Any:
        from common import device_client

        return device_client.for_device(device)

    outcomes = await offload.io(launcher_copy.copy_to, devices, [launcher],
                                  mappings, client_for=client_for)
    ui.notify(launcher_copy.said(outcomes), caption=launcher_copy.trouble(outcomes),
              type="positive" if all(one.ok for one in outcomes) else "warning")


def acts(library: Library, state: dict[str, Any], launcher: dict, count: int,
         redraw: Callable[[], None]) -> list[panel.Verb]:
    """What can be done to one launcher."""
    offered = [panel.Verb(t("console.workbench.duplicate"),
                          lambda: duplicate(library, state, redraw, launcher))]
    if state.get("can_manage_devices"):
        offered.append(panel.Verb(t("console.workbench.copy_devices"),
                                  lambda: copy_dialog(library, state, launcher)))
    offered.append(panel.Verb(
        t("word.remove"),
        None if count <= 1 else (lambda: remove(library, state, redraw, launcher)),
        danger=True, hint=t("console.workbench.only_launcher")))
    return offered


def removal_words(found: dict[str, Any]) -> tuple[str, list[str]]:
    """The confirm's detail and lines, from what switching the launcher off would do,
    which is what removing it does to its tables."""
    kept = t("console.launchers.remove_keeps_files")
    count = int(found.get("tables") or 0)
    goes = list(found.get("fallbacks") or [])
    if not count:
        return kept, []
    if len(goes) == 1:
        name = goes[0].get("display_name")
        said = (t("console.launchers.remove_moves_to", count=count, fallback=name) if name
                else t("console.launchers.remove_strands", count=count))
        return f"{said} {kept}", []
    return (f"{kept} {t('console.launchers.remove_split', count=count)}",
            [t("console.workbench.count_launch_with", count=int(one["tables"]),
               name=one["display_name"]) if one.get("display_name")
             else t("console.launchers.count_no_launcher", count=int(one["tables"]))
             for one in goes])


async def remove(library: Library, state: dict[str, Any], redraw: Callable[[], None],
                  launcher: dict) -> None:
    """Asked about first, because it is the destructive one and it takes assignments
    with it - a table pointing here goes back to the default."""
    try:
        found = await offload.io(library.launcher_fallback, launcher["launcher_id"])
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("console.workbench.could_not_work"), caption=why(exc), type="negative")
        return
    detail, lines = removal_words(found)
    if not await confirm.ask(
            t("console.launchers.remove", value=(launcher['display_name'])),
            detail=detail, lines=lines, confirm=t("word.remove"), icon=verbs.REMOVE):
        return
    try:
        await run.io_bound(library.delete_launcher, launcher["launcher_id"])
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("said.could_not_remove_it"), caption=why(exc), type="negative")
        return
    state["launcher"] = ""
    redraw()
