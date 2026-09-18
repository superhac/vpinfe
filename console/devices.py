"""Devices: what each one is, and what it can be asked to do."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common import device_client, device_registry
from common.i18n import t
from common.labels import humanize
from console import offload

from . import confirm, grid, panel, views
from . import settings as settings_page
from .api import ApiClient

logger = logging.getLogger("vpinfe.console.devices")

# What a kind of device can do when nobody can ask it. A vpx_mobile device runs VPX and
# not VPinFE, so it declares nothing, ever - its abilities are known from the kind.
IMPLIED_BY_KIND: dict[str, set[str]] = {
    "vpx_mobile": {"launch"},
}

PRESENT, ABSENT, UNKNOWN = "present", "absent", "unknown"

# What the absence costs, which is what the chip's color means everywhere else in the
# here: an unoffered capability is ordinary, one nothing has asked about is not.
_CHIP = {
    PRESENT: ("console.devices.available_2", "on"),
    ABSENT: ("console.devices.not_offered", "off"),
    UNKNOWN: ("console.devices.cannot_determined", "unknown"),
}

# Why the name of a device that is not this one cannot be edited here. The install owns
# its own name, and the registry holds a copy of what it last reported.

# A device there is no way to call back. Not the same as one that is down, and it says
# which: an install announces the port it answers on, and this one never did.
UNREACHABLE_NOTE = "console.devices.device_not_said_port"

# Why an install cannot replace itself, in the words a person reads. The API answers with
# the reason's name; the sentence for it belongs to whatever is showing it.
WHY_NOT = {
    "source_build": "console.devices.why_not.build_runs_source_updates",
    "non_release_build": "console.devices.why_not.build_not_published_release",
    "unsupported_architecture": "console.devices.why_not.no_published_build_matches",
    "macos_not_supported_yet": "console.devices.why_not.updating_place_not_built",
    "unsupported_platform": "console.devices.why_not.updating_place_not_built"
}

# What forgetting a device does, said before it is done. The registry is a record of what
# this install has met, not a permission list, so this removes a row and nothing else.
# How many records to ask for. Enough to see what led to something without handing over
# a 2MB file to a panel; the path is on the page for anyone who wants the rest.
LOG_LIMIT = 200

# What each level is worth noticing. Only the two that mean something went wrong are
# colored - a column where every row is lit says nothing about any of them.
# Read by the Logs page too, so one install's log and another's are colored the same.
LOG_LEVELS = {
    "ERROR": "console-log-bad",
    "CRITICAL": "console-log-bad",
    "WARNING": "console-log-warn",
}

# What an icon says about a verb, where the verb alone reads as either direction.
_ACTION_ICONS = {
    ("table", "stop"): "stop_circle",
    ("frontend", "start"): "launch",
    ("frontend", "stop"): "close",
    ("frontend", "restart"): "refresh",
    ("vpinfe", "stop"): "power_settings_new",
    ("vpinfe", "restart"): "restart_alt",
    ("system", "stop"): "power_settings_new",
    ("system", "restart"): "restart_alt",
}

# Said once over the list rather than under each. Which machine this happens on is the
# thing a fleet surface has to be clear about.


# What a probe found, as the mark on a rail row and the chip on the page. Green for
# answering, because that is the one a person scans the rail for.
_REACH = {
    device_client.ANSWERING: ("console.devices.answering", "on", "positive"),
    device_client.UNREACHABLE: ("console.devices.not_answering", "bad", "negative"),
    device_client.UNASKABLE: ("console.devices.cannot_asked", "unknown", "grey"),
}


def capability_state(device: dict[str, Any], capability: str,
                     local_device_id: str | None,
                     local_capabilities: set[str],
                     probed: dict[str, Any] | None = None) -> str:
    """One of three answers, never two.

    "Cannot be determined" is its own state on purpose. Collapsing it into "not offered"
    tells someone their hardware lacks a feature when the truth is that nothing has
    asked it - which is a worse error than saying nothing.
    """
    kind = device.get("kind", "vpinfe")
    if kind in IMPLIED_BY_KIND:
        return PRESENT if capability in IMPLIED_BY_KIND[kind] else ABSENT
    if device.get("device_id") == local_device_id:
        return PRESENT if capability in local_capabilities else ABSENT
    # What the probe already heard. A remote install declares its capabilities in the
    # same response the probe reads for its name and version, so this costs nothing -
    # and it used to be thrown away, which left every remote install answering
    # "cannot be determined" for all of them.
    if probed and probed.get("state") == device_client.ANSWERING:
        said = probed.get("capabilities")
        # None is a build that did not say, which is not the same as a build that
        # answered and offers nothing. Reading it as the latter put "Not offered" on
        # every row of a machine that offers all of them.
        if said is None:
            return UNKNOWN
        return PRESENT if capability in set(said) else ABSENT
    # Nothing has asked it, or it did not answer. Not the same as "does not offer it".
    return UNKNOWN


def device_label(device: dict[str, Any]) -> str:
    """What to call a device on screen.

    The name it reported, then the address it answered from - an unnamed install is
    still the one at a particular address, and "device" tells nobody which. The install
    itself falls back to its hostname, so a blank name here means it never reported one.
    """
    return (str(device.get("display_name") or "").strip()
            or str(device.get("address") or "").strip()
            or t("console.devices.device"))


def _connection_rows(device: dict[str, Any],
                     reach: dict[str, Any] | None) -> list[tuple[Any, Any]]:
    """Whether it is there, what answered, and when it last was.

    The timestamp is shown beside the state rather than instead of it: "not answering"
    is the fact, and how long that has been true is what decides whether it is worth
    doing something about.
    """
    rows: list[tuple[Any, Any]] = [
        (t("console.devices.address"),
         str(device.get("address") or "") or t("console.devices.not_known"))]

    found = _REACH.get(str((reach or {}).get("state") or ""))
    if found is None:
        rows.append((t("word.state"),
                     panel.state(t("console.devices.checking"), "unknown")))
    else:
        label, level, _color = found
        what = str((reach or {}).get("what") or "")
        rows.append((t("word.state"),
                     panel.state(t(label), level, beside=what)))
        reason = str((reach or {}).get("reason") or "")
        if level != "on" and reason:
            rows.append(panel.note(reason))

    rows.append((t("word.last_seen"),
                 _when(str(device.get("last_reachable") or "")) or t("word.never")))
    return rows


async def _confirm_forget(library: Any, device: dict[str, Any],
                          rerender: Callable[[], None] | None) -> None:
    """Drop the entry, having said what that does and does not do."""
    name = device_label(device)
    if not await confirm.ask(
            t("console.devices.forget", name=(name)),
            detail=t("console.devices.removes_install_s_entry"),
            confirm=t("word.forget")):
        return
    try:
        await run.io_bound(library.forget_device, str(device.get("device_id") or ""))
    except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
        ui.notify(t("console.devices.could_not_forget_device", exc=(exc)), type="negative")
        return
    ui.notify(t("console.devices.forgot", name=(name)), type="positive")
    if rerender is not None:
        rerender()


def _software_rows(device: dict[str, Any], is_local: bool, client: Any,
                   update: dict[str, Any] | None) -> list[tuple[Any, Any]]:
    """What this device is running, and whether it can take what is published.

    A device with no answer gets the heading and an unknown - one that announced itself
    before ports were recorded cannot be reached, and one that is not answering has not
    said. Either way "up to date" would be a guess wearing a fact.
    """
    rows: list[tuple[Any, Any]] = [(panel.HEADING, t("word.software"))]
    if not update:
        rows.append((t("word.version"), panel.state(t("console.devices.not_known"),
                "unknown")))
        if not is_local and client is None:
            rows.append(panel.note(t(UNREACHABLE_NOTE)))
        return rows

    current = str(update.get("current_version") or "unknown")
    if not update.get("update_available"):
        rows.append((t("word.version"), panel.state(current, "on")))
        return rows

    latest = str(update.get("latest_version") or t("console.devices.newer_build"))
    if not update.get("update_supported"):
        reason = t(WHY_NOT.get(str(update.get("support_reason") or ""),
                               "console.devices.install_cannot_update_itself"))
        rows.append((t("word.version"), panel.state(t("console.devices.available",
                latest=(latest)), "warn",
                                            beside=current)))
        rows.append(panel.note(reason))
        return rows

    rows.append((t("word.version"),
            panel.state(t("console.devices.available", latest=(latest)), "warn", beside=current)))
    def update_action() -> None:
        with ui.element("div").classes("console-fact-edit"):
            panel.action(t("console.devices.update_3", latest=(latest)),
                         lambda: _confirm_update(client, device_label(device), update),
                         icon="system_update_alt", inline=True)()

    rows.append(("", update_action))
    return rows


async def _confirm_update(client: Any, name: str, update: dict[str, Any]) -> None:
    """Ask before replacing an install, naming which one it is.

    The name is the point of the question. An update replaces the machine it runs on,
    which may not be the one this page is open on - "Update to v3.1" does not say which
    one goes down, and by the time it has, saying so is too late.
    """
    latest = str(update.get("latest_version") or t("console.devices.published_build"))
    try:
        playing = await offload.io(client.play_state)
    except Exception as exc:  # noqa: BLE001 - a dialog that cannot say what it will do
        ui.notify(t("console.devices.could_not_check_what", name=(name), exc=(exc)),
                type="negative")
        return

    running = str((playing or {}).get("game_name") or "") if (
        playing or {}).get("launching") else ""

    # Named, because "a table is running" is a fact the person asking may not have: the
    # Console is not necessarily open on the machine the table is on.
    lines = [t("console.devices.being_played_closed", running=(running))] if running else []
    if not await confirm.ask(
            t("console.devices.update_2", name=(name), latest=(latest)),
            detail=t("console.devices.package_downloaded_first_vpinfe"),
            lines=lines,
            confirm=t("console.devices.stop_table_update") if running
            else t("console.devices.update"),
            danger=bool(running)):
        return
    await _start_update(client, name, bool(running))


async def _start_update(client: Any, name: str, stop_table: bool) -> None:
    try:
        await run.io_bound(lambda: client.perform_update(stop_table=stop_table))
    except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
        ui.notify(t("console.devices.could_not_start_update", exc=(exc)), type="negative")
        return
    # Nothing to redraw towards. Updating this install takes the page's own server down;
    # updating another leaves it up but knowing nothing new until that device is back.
    ui.notify(t("console.devices.update_staged_restarting_apply", name=(name)), type="positive")


def _hostname_placeholder(device: dict[str, Any], is_local: bool) -> str:
    """What it will be called if the field is left empty.

    The name it reports with nothing set is its hostname, so showing that is more use
    than the word "hostname" - it is the actual answer rather than a description of one.
    """
    if not is_local:
        return str(device.get("display_name") or "")
    return str(device.get("display_name") or "") \
        .strip() or t("console.devices.machine_s_hostname")




# --- The grid ---------------------------------------------------------------

SCOPE = "console.devices.columns"

KIND_LABELS = {"vpinfe": "VPinFE", "vpx_mobile": "VPX Mobile"}

_KIND_CHOICES = [{"value": label, "label": label} for label in KIND_LABELS.values()]
_STATE_CHOICES = [{"value": text, "label": t(text)} for text, _l, _c in _REACH.values()]

COLUMNS: list[dict[str, Any]] = [
    # Never shown - it exists so every built-in view can sort this device to the top.
    # A column has to be declared to be sorted on, and this one is a fact about the row
    # rather than anything to read.
    grid.column("self", t("console.devices.device_2"), hide=True,
                help=t("console.devices.whether_install_reading_console.help")),
    grid.identifier("name", t("word.name"), 200, pinned="left",
                help=t("console.devices.what_device_calls_itself.help")),
    grid.column("kind", t("word.kind"), 120, **grid.choice_filter(_KIND_CHOICES),
                help=t("console.devices.vpinfe_install_answers_itself.help")),
    grid.column("state", t("word.state"), 140, **grid.choice_filter(_STATE_CHOICES),
                help=t("console.devices.whether_answered_install_last.help")),
    grid.column("what", t("word.running"), 160,
                help=t("console.devices.what_answered_vpinfe_install.help")),
    grid.column("address", t("console.devices.address"), 150,
                help=t("console.devices.where_reached_read_off.help")),
    grid.column("last_seen", t("word.last_seen"), 170,
                help=t("console.devices.last_known_announced_install.help")),
    grid.column("features", t("console.devices.features"), 150,
                help=t("console.devices.what_install_curating_library.help")),
]

# `self` is out: it is a sort key, not a column somebody picks.
_ALL = [definition["field"] for definition in COLUMNS if definition["field"] != "self"]

# Every view leads with it, so the device you are on is the first row whatever else the
# view orders by - which is what "pinned" means here, and it survives re-sorting because
# a user's sort is added to this rather than replacing it.
_SELF_FIRST = {"colId": "self", "sort": "desc", "sortIndex": 0}

VIEWS: dict[str, list[str] | views.Preset] = {
    t("console.devices.all_devices"): views.Preset(
        columns=("name", "kind", "state", "what", "last_seen"),
        sort=(_SELF_FIRST,
              {"colId": "state", "sort": "asc", "sortIndex": 1},
              {"colId": "name", "sort": "asc", "sortIndex": 2}),
        help=t("console.devices.every_device_install_met.help")),
    t("console.view.answering"): views.Preset(
        columns=("name", "kind", "what", "address", "features"),
        sort=(_SELF_FIRST, {"colId": "name", "sort": "asc", "sortIndex": 1}),
        filters={"state": {"values": [_REACH[device_client.ANSWERING][0]]}},
        help=t("console.devices.what_switched_reachable_right.help")),
    t("console.devices.not_answering"): views.Preset(
        columns=("name", "kind", "state", "address", "last_seen"),
        sort=(_SELF_FIRST, {"colId": "last_seen", "sort": "asc", "sortIndex": 1}),
        filters={"state": {"values": [_REACH[device_client.UNREACHABLE][0],
                                      _REACH[device_client.UNASKABLE][0]]}},
        help=t("console.devices.devices_could_not_reached.help")),
    t("console.view.everything"): views.Preset(
        columns=tuple(_ALL),
        help=t("console.devices.every_row_every_column.help")),
}


def rows(devices: list[dict[str, Any]],
         reach: dict[str, dict[str, Any]] | None = None,
         local_device_id: str | None = None) -> list[dict[str, Any]]:
    """One row per device, flattened for a grid.

    The probe's answer is folded in rather than fetched per row: it arrives once for
    the whole registry, and a column that asked per row would dial every machine again
    each time the grid redrew.
    """
    found = reach or {}
    out = []
    for device in devices:
        device_id = str(device.get("device_id") or "")
        probe = found.get(device_id) or {}
        state = _REACH.get(str(probe.get("state") or ""))
        out.append({
            "id": device_id,
            "self": device_id == (local_device_id or ""),
            "name": device_label(device),
            "kind": KIND_LABELS.get(str(device.get("kind") or "vpinfe"), "VPinFE"),
            # Blank until the probes land, rather than a word meaning "not yet": a
            # grid filter over "Checking" is a filter over how fast the page loaded.
            "state": state[0] if state else "",
            "what": str(probe.get("what") or ""),
            "address": str(device.get("address") or ""),
            "last_seen": _when(str(device.get("last_reachable") or "")),
            "features": settings_page.features_said(device.get("features")),
        })
    return out


def _when(stamp: str) -> str:
    """A timestamp as a person reads one. Sortable as text because it stays ISO order -
    the grid sorts the string, and the string is still year-first."""
    return stamp.replace("T", " ").replace("Z", "") if stamp else ""


def build(found: list[dict[str, Any]], library: Any, state: dict[str, Any],
          on_select: Callable[[dict | None], Any],
          probe: Callable[[], Any] | None = None,
          local_device_id: str | None = None) -> None:
    """Devices as a grid, so the selected row is what the workbench answers for.

    The same shape every other subject uses. Kind and reachability are columns rather
    than groups, which is what lets one question - "which of these is not answering" -
    be a sort, a filter and a saved view instead of a fixed arrangement.
    """
    # Deferred: `games` imports `workbench`, and `workbench` imports this module for
    # the device sections - so taking the view control at import time closes the loop.
    # Only `build` needs it, and by then every module is loaded.
    from .games import view_control

    built = rows(found, state.get("device_reach"), local_device_id)
    away = sum(1 for row in built if row["state"]
               and row["state"] != _REACH[device_client.ANSWERING][0])
    on_screen = {"rows": len(built)}

    def said() -> str:
        if on_screen["rows"] != len(built):
            return t("console.devices.devices_2", shown=(on_screen["rows"]),
                     count=(len(built)))
        return t("console.devices.devices_not_answering", count=(len(built)), away=(away)) if away \
            else t("console.devices.devices", count=(len(built)))

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 "
                                  "console-panel console-grid-bar"):
        bar = panel.grid_bar()
        _wire_views, _picker, showing, describe = view_control(library, SCOPE, VIEWS,
                                                    _ALL, COLUMNS, bar=bar)
        describe()
        with bar.top, panel.bar_end():
            search = panel.search(t("console.devices.search_devices"))
        with bar.bottom, panel.bar_end():
            count = ui.label(said()).classes("text-xs console-label")
            if probe is not None:
                ui.button(icon="refresh", on_click=probe) \
                    .props("flat dense round size=sm").classes("shrink-0") \
                    .tooltip(t("console.devices.ask_every_device_whether"))

    by_id = {row["id"]: row for row in built}
    ui.on("hub_row_focus",
          lambda event: on_select(by_id.get(grid.focused_row(event))))

    async def on_header_context(col_id: str | None) -> None:
        state_now: list[dict[str, Any]] = \
            await table.run_grid_method("getColumnState") or []
        entry = next((c for c in state_now if c.get("colId") == col_id), {})
        menu.clear()
        with menu:
            grid.column_menu(menu, table, COLUMNS, col_id, bool(entry.get("pinned")))

    with ui.element("div").classes("w-full grow min-h-0 flex flex-col"):
        table = grid.build(COLUMNS, built, SCOPE,
                           on_header_context=on_header_context, view_of=showing)
        menu = ui.context_menu()
    search.on_value_change(
        lambda: table.run_grid_method("setGridOption", "quickFilterText",
                                      search.value or ""))

    async def counted() -> None:
        on_screen["rows"] = await table.run_grid_method("getDisplayedRowCount") or 0
        count.text = said()

    table.on("rowDataUpdated", counted)
    table.on("filterChanged", counted)


# --- Panel sections ---------------------------------------------------------
#
# One function per section of the workbench rail. They take the panel's context and
# hand back fact rows, because what a device is and what may be asked of it belongs
# with the device rather than with the panel that draws it.

def _client_for(context: dict[str, Any]) -> Any:
    """Who answers for this device. This install's own client for itself, the client
    that reaches it for anything else - both expose the same calls, which is what lets
    one page draw either."""
    if _is_local(context):
        return context.get("library")
    return device_client.for_device(_of(context), context.get("local_device_id"))


def _of(context: dict[str, Any]) -> dict[str, Any]:
    return context.get("device") or {}


def _is_local(context: dict[str, Any]) -> bool:
    return _of(context).get("device_id") == context.get("local_device_id")


async def detail_groups(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """What a device is, whether it is there, where its settings are, and what this
    install holds about it.

    Descriptive, then operational, then what this install holds about it: what a thing
    is comes before what can be done to it, and the record we keep of it is nobody's
    first question. They are headings inside one section rather than rail entries of
    their own, because four of them hold three rows or fewer and a rail entry that opens
    one row is a click charged for nothing.
    """
    rows_out: list[tuple[Any, Any]] = [(panel.HEADING, t("word.identity"))]
    rows_out += await _identity_rows(context)
    rows_out.append((panel.HEADING, t("console.devices.connection")))
    rows_out += _connection_rows(_of(context), context.get("reach"))
    if _of(context).get("kind") == device_registry.KIND_VPX_MOBILE:
        # A phone is not an install: no software, no lifecycle, no settings of ours to
        # open. What it has instead is the one thing this end can act on - the games it
        # is carrying - so that heading takes the place of Settings rather than being
        # added beside it.
        rows_out.append((panel.HEADING, t("console.devices.carrying")))
        rows_out += await _carrying_rows(context)
    else:
        rows_out.append((panel.HEADING, t("console.devices.settings")))
        rows_out += settings_door(context)
    rows_out.append((panel.HEADING, t("console.devices.entry")))
    rows_out += entry_rows(context)
    return rows_out


async def _carrying_rows(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """What the device holds, asked of the device.

    Never remembered between visits: a phone is filled up and emptied by hand and taken
    out of the house, so anything recorded here would be a claim about a machine that
    has not been asked. That it takes a moment is the honest cost of the answer being
    true.
    """
    device = _of(context)
    library = context.get("library")
    try:
        held = await offload.io(ApiClient().device_games,
                                  str(device.get("device_id") or ""))
    except Exception as exc:
        # The words the API used. A device that is switched off is the ordinary case
        # here, and it is not a failure of this panel.
        return [panel.note(str(exc))]

    async def forget(name: str) -> None:
        if not await confirm.ask(
                t("console.devices.remove", name=(name),
                        device_label=(device_label(device))),
                detail=t("console.devices.comes_off_device_own"),
                confirm=t("word.remove"), danger=True):
            return
        try:
            await run.io_bound(ApiClient().remove_from_device,
                               str(device.get("device_id") or ""), name)
        except Exception as exc:
            ui.notify(str(exc), type="negative")
            return
        if library is not None:
            context["rerender"]()

    if not held:
        return [panel.note(t("console.devices.nothing_yet_send_games"))]

    def row(name: str) -> Callable[[], None]:
        def draw() -> None:
            with ui.element("div").classes("console-slot-actions"):
                ui.button(t("word.remove"), on_click=lambda _e=None: forget(name)) \
                    .props("flat dense no-caps size=sm") \
                    .classes("console-action console-action--inline")

        return draw

    return [(name, row(name)) for name in held]


# Why a device's settings are somewhere else. Said where somebody is looking for them,
# because "not here" without a reason reads as something missing.
SETTINGS_NOTE = "console.devices.machine_s_settings_belong"

# What is wrong when the door will not open. Both halves matter: one is a machine to go
# and switch on, the other is an entry with nothing to dial.
NO_DOOR = {
    device_client.UNREACHABLE: "console.devices.not_answering_nothing_open",
    device_client.UNASKABLE: UNREACHABLE_NOTE,
}


# Where this install's own settings are, which is a place in the Console already open.
SYSTEM_PATH = "/console?view=system"


def settings_url(device: dict[str, Any]) -> str:
    """That install's own Console, landing on System. Empty when there is nothing to
    dial - an entry written before ports were recorded has no port."""
    address = str(device.get("address") or "").strip()
    port = int(device.get("port") or 0)
    return f"http://{address}:{port}{SYSTEM_PATH}" if address and port else ""


def door_reason(device: dict[str, Any], reach: dict[str, Any] | None,
                is_local: bool) -> str:
    """Why the door will not open, or "" when it will.

    A machine that is not answering must not be offered as a live link: the tab opens on
    a connection error, which is a worse answer than being told here.
    """
    if is_local:
        return ""
    found = NO_DOOR.get(str((reach or {}).get("state") or ""))
    if found:
        return found
    return "" if settings_url(device) else UNREACHABLE_NOTE


def settings_door(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """The way into that install's own Console, or the reason there is not one.

    A door rather than a section. Drawing that install's settings here, from a schema
    fetched over HTTP, would mean this build deciding how another build's settings look -
    which is exactly where version skew bites.
    """
    device = _of(context)
    here = _is_local(context)
    stopped = door_reason(device, context.get("reach"), here)

    def open_it() -> None:
        # In place for this install, a new tab for anything else: one is a place in the
        # Console you are already reading, and the other is a different machine's.
        ui.navigate.to(SYSTEM_PATH if here else settings_url(device),
                       new_tab=not here)

    def door() -> None:
        with ui.element("div").classes("console-fact-edit"):
            panel.action(t("console.devices.open_system") if here
                    else t("console.devices.open_settings"),
                         open_it, icon="open_in_new", inline=True,
                         enabled=not stopped)()

    return [("", door), panel.note(t(stopped) if stopped else t(SETTINGS_NOTE))]


async def _identity_rows(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """What it is called, and what kind of thing it is."""
    device = _of(context)
    # The library this name can be written through, which only the install serving the
    # page has. Its absence is what makes the field read-only, so the two cannot drift.
    library = context.get("library") if _is_local(context) else None

    # What the install has been told to call itself, which is not what it reports: the
    # reported name already fell back to the hostname, so showing that as the value
    # leaves nothing to tell a chosen name from a defaulted one.
    stored = ""
    if library is not None:
        try:
            values = await offload.io(library.config_values)
            stored = str(((values or {}).get("install") or {}).get("display_name") or "")
        except Exception:  # noqa: BLE001 - an unreadable name is an empty field, not a 500
            library = None

    async def rename(value: str) -> None:
        if library is None:
            return
        try:
            await run.io_bound(library.put_config,
                               {"install": {"display_name": value.strip()}})
        except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
            ui.notify(t("console.devices.could_not_save", exc=(exc)), type="negative")
            return
        rebuild = context.get("rebuild")
        if rebuild is not None:
            await rebuild()

    rows_out: list[tuple[Any, Any]] = [
        (t("word.name"), panel.field(stored, rename,
                             placeholder=_hostname_placeholder(device,
                                                               _is_local(context)),
                             disabled=library is None)),
    ]
    if not _is_local(context):
        rows_out.append(panel.note(t("console.devices.name_belongs_install_can")))
    rows_out.append((t("word.kind"),
            KIND_LABELS.get(str(device.get("kind") or "vpinfe"),
                                             "VPinFE")))
    rows_out.append((t("console.devices.features"),
                     settings_page.features_said(device.get("features"))
                     or t("console.devices.not_reported")))
    return rows_out


def connection_rows(device: dict[str, Any],
                    reach: dict[str, Any] | None) -> list[tuple[Any, Any]]:
    return _connection_rows(device, reach)


def update_checker(is_local: bool, client: Any) -> Any:
    """Whichever client can answer *this* device's update check.

    The local client is this process, and asking it to reach the network for a version
    it already knows would be this install phoning itself - so it does not offer the
    call at all. The Console does have a way to ask: its own API, which serves `/update`
    for exactly this. Without this the local device raised, the caller logged that a
    device could not be asked, and the one install that never learned it had an update
    was the one in front of you.
    """
    if is_local:
        from console.api import ApiClient

        return ApiClient().update_check
    return getattr(client, "update_check", None)


async def software_rows(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """What it is running. Asked of the device rather than read from the registry,
    which holds no version at all."""
    device = _of(context)
    client = _client_for(context)
    update = context.get("update")
    ask = update_checker(_is_local(context), client)
    if update is None and ask is not None:
        try:
            update = await offload.io(ask)
        except Exception:  # noqa: BLE001 - unreachable is a state, not a 500
            logger.info("Could not ask %s what it is running",
                        device_label(device), exc_info=True)
            update = None
        context["update"] = update
    return _software_rows(device, _is_local(context), client, update)


def capability_rows(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    device = _of(context)
    out: list[tuple[Any, Any]] = []
    for capability in context.get("device_capabilities") or []:
        state = capability_state(device, capability,
                                 context.get("local_device_id"),
                                 context.get("local_capabilities") or set(),
                                 context.get("reach"))
        text, level = _CHIP[state]
        text = t(text)
        out.append((humanize(capability), panel.state(text, level)))
    return out or [panel.intro(t("console.devices.device_declares_nothing"))]


# What a lifecycle action costs, which is what decides whether it is asked about twice.
# Closing a table loses a game in progress; the rest lose the whole machine for a while.
_HEAVY = {"vpinfe", "system"}


async def action_rows(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """What this device can be told to do, and what it will not answer for.

    Every pair the build has, greyed where nothing over there performs it - two installs
    showing different buttons look like different products, and the reason is the answer
    to somebody asking why.
    """
    client = _client_for(context)
    if client is None:
        return [panel.intro(t(UNREACHABLE_NOTE))]
    try:
        offered = await offload.io(client.actions)
    except device_client.TooOldError as exc:
        return [panel.intro(str(exc))]
    except Exception as exc:  # noqa: BLE001 - unreachable is a state, not a 500
        logger.info("Could not ask %s what it does", device_label(_of(context)),
                    exc_info=True)
        return [panel.intro(t("console.devices.could_not_ask",
                device_label=(device_label(_of(context))), exc=(exc)))]
    if not offered:
        return [panel.intro(t("console.devices.device_offers_nothing"))]

    rows_out: list[tuple[Any, Any]] = [panel.intro(t("console.devices.happen_device_not_install"))]
    for entry in offered:
        rows_out.append(("", _action_control(context, entry)))
        if not entry.get("available") and entry.get("reason"):
            rows_out.append(panel.note(str(entry["reason"])))
    return rows_out


def _action_control(context: dict[str, Any],
                    entry: dict[str, Any]) -> Callable[[], None]:
    """One verb, asked about first where it costs the machine."""
    scope = str(entry.get("scope") or "")
    action = str(entry.get("action") or "")
    label = str(entry.get("label") or f"{action} the {scope}")

    async def go() -> None:
        if scope in _HEAVY and not await confirm.ask(
                f"{label}?",
                detail=t("console.devices.happens_now",
                        device_label=(device_label(_of(context)))),
                confirm=label):
            return
        client = _client_for(context)
        try:
            done = await offload.io(client.perform_action, scope, action)
        except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
            ui.notify(t("said.could_not_do_that", exc=(exc)), type="negative")
            return
        # A machine on its way down answers before it goes, so "performed" here means
        # the work was handed over rather than finished.
        ui.notify(f"{label}" if done.get("performed") else t("console.devices.not_happen",
                label=(label)),
                  type="positive" if done.get("performed") else "warning")

    def draw() -> None:
        with ui.element("div").classes("console-fact-edit"):
            panel.action(label, go, icon=_ACTION_ICONS.get((scope, action), "play_arrow"),
                         inline=True, danger=scope in _HEAVY,
                         enabled=bool(entry.get("available")))()

    return draw


async def log_rows(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """The tail of that install's own log.

    Read from the machine that holds it, which is the only party that has it. Records
    rather than lines, so a traceback arrives under the message that caused it instead
    of as a dozen rows carrying no level of their own.
    """
    client = _client_for(context)
    if client is None:
        return [panel.intro(t(UNREACHABLE_NOTE))]
    try:
        found = await offload.io(client.logs, LOG_LIMIT)
    except device_client.TooOldError as exc:
        return [panel.intro(str(exc))]
    except Exception as exc:  # noqa: BLE001 - unreachable is a state, not a 500
        logger.info("Could not read the log on %s", device_label(_of(context)),
                    exc_info=True)
        return [panel.intro(t("console.devices.could_not_read_log", exc=(exc)))]

    records = list(found.get("records") or [])
    if not records:
        return [panel.intro(t("console.devices.nothing_written_log_device"))]
    return [(panel.FULL, lambda: _log_lines(records, str(found.get("path") or "")))]


def _log_lines(records: list[dict[str, Any]], path: str) -> None:
    """Newest last, the way a log reads and the way `tail` shows one."""
    with ui.column().classes("w-full gap-0 console-log"):
        for record in records:
            with ui.row().classes("items-baseline gap-2 w-full no-wrap console-log-row"):
                ui.label(str(record.get("when") or "")).classes("console-log-when")
                level = str(record.get("level") or "")
                ui.label(level).classes(
                    "console-log-level " + LOG_LEVELS.get(level, "console-log-plain"))
                ui.label(str(record.get("logger") or "")).classes("console-log-source")
            ui.label(str(record.get("message") or "")).classes("console-log-message")
    if path:
        ui.label(path).classes("console-log-path")


def entry_rows(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """What this install holds about the device, which is the only part it owns."""
    device = _of(context)
    library = context.get("library")
    out: list[tuple[Any, Any]] = [
        (t("console.devices.first_seen"),
                _when(str(device.get("first_seen") or "")) or t("console.devices.not_known")),
        (t("console.devices.announced"),
                _when(str(device.get("last_seen") or "")) or t("word.never")),
    ]
    if _is_local(context) or library is None:
        out.append(panel.note(
            t("console.devices.install_reading_console_entry")))
        return out

    def forget_action() -> None:
        # In the fact rhythm's own wrapper, or the button takes the whole value column -
        # a destructive verb drawn as a full-width bar reads as a banner.
        with ui.element("div").classes("console-fact-edit"):
            panel.action(t("console.devices.forget_device"),
                         lambda: _confirm_forget(library, device,
                                                 context.get("rebuild")),
                         icon="delete_outline", inline=True, danger=True)()

    out.append(panel.note(t("console.devices.forgetting_device_removes_install")))
    out.append(("", forget_action))
    return out
