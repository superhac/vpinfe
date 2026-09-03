"""Devices: what each one is, and what it can be asked to do."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common import device_client
from common.labels import humanize

from . import confirm, grid, panel, views
from . import settings as settings_page

logger = logging.getLogger("vpinfe.hubui.devices")

# What a kind of device can do when nobody can ask it. A vpx_mobile device runs VPX and
# not VPinFE, so it declares nothing, ever - the hub knows its abilities from the kind.
IMPLIED_BY_KIND: dict[str, set[str]] = {
    "vpx_mobile": {"launch"},
}

PRESENT, ABSENT, UNKNOWN = "present", "absent", "unknown"

# What the absence costs, which is what the chip's color means everywhere else in the
# hub: an unoffered capability is ordinary, one nothing has asked about is not.
_CHIP = {
    PRESENT: ("Available", "on"),
    ABSENT: ("Not offered", "off"),
    UNKNOWN: ("Cannot be determined", "unknown"),
}

# Why the name of a device that is not this one cannot be edited here. The install owns
# its own name, and the hub holds a copy of what it last reported.
REMOTE_NAME_NOTE = "This name belongs to that install, and only it can change it."

# A device the hub has no way to call back. Not the same as one that is down, and it says
# which: an install announces the port it answers on, and this one never did.
UNREACHABLE_NOTE = ("This device has not said which port it answers on, so it cannot be "
                    "asked. It will once it has announced itself again.")

# Why an install cannot replace itself, in the words a person reads. The API answers with
# the reason's name; the sentence for it belongs to whatever is showing it.
WHY_NOT = {
    "source_build": "This build runs from source, so it updates with a git pull "
                    "rather than from here.",
    "non_release_build": "This build was not published as a release, so there is "
                         "nothing to replace it with.",
    "unsupported_architecture": "No published build matches this machine's "
                                "architecture.",
    "macos_not_supported_yet": "Updating in place is not built for macOS yet.",
    "unsupported_platform": "Updating in place is not built for this platform.",
}
CANNOT_UPDATE = "This install cannot update itself."

# What forgetting a device does, said before it is done. The registry is a record of what
# the hub has met, not a permission list, so this removes a row and nothing else.
FORGET_NOTE = ("Forgetting a device removes the hub's entry for it. Nothing on that "
               "machine changes, and it comes back the next time it announces itself.")

# What a probe found, as the mark on a rail row and the chip on the page. Green for
# answering, because that is the one a person scans the rail for.
_REACH = {
    device_client.ANSWERING: ("Answering", "on", "positive"),
    device_client.UNREACHABLE: ("Not answering", "bad", "negative"),
    device_client.UNASKABLE: ("Cannot be asked", "unknown", "grey"),
}


def capability_state(device: dict[str, Any], capability: str,
                     local_device_id: str | None,
                     local_capabilities: set[str]) -> str:
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
    # A remote VPinFE device declares its own capabilities, and the hub has no route to
    # ask it: httpapi/devices.py records what a device said about itself and nothing more.
    return UNKNOWN


def device_label(device: dict[str, Any]) -> str:
    """What to call a device on screen.

    The name it reported, then the address it answered from - an unnamed install is
    still the one at a particular address, and "device" tells nobody which. The install
    itself falls back to its hostname, so a blank name here means it never reported one.
    """
    return (str(device.get("display_name") or "").strip()
            or str(device.get("address") or "").strip()
            or "Device")


def _connection_rows(device: dict[str, Any],
                     reach: dict[str, Any] | None) -> list[tuple[Any, Any]]:
    """Whether it is there, what answered, and when it last was.

    The timestamp is shown beside the state rather than instead of it: "not answering"
    is the fact, and how long that has been true is what decides whether it is worth
    doing something about.
    """
    rows: list[tuple[Any, Any]] = [
        ("Address", str(device.get("address") or "") or "Not known")]

    found = _REACH.get(str((reach or {}).get("state") or ""))
    if found is None:
        rows.append(("State", panel.state("Checking", "unknown")))
    else:
        label, level, _color = found
        what = str((reach or {}).get("what") or "")
        rows.append(("State", panel.state(label, level, beside=what)))
        reason = str((reach or {}).get("reason") or "")
        if level != "on" and reason:
            rows.append(panel.note(reason))

    rows.append(("Last seen",
                 _when(str(device.get("last_reachable") or "")) or "Never"))
    return rows


async def _confirm_forget(library: Any, device: dict[str, Any],
                          rerender: Callable[[], None] | None) -> None:
    """Drop the entry, having said what that does and does not do."""
    name = device_label(device)
    if not await confirm.ask(
            f"Forget {name}?",
            detail="This removes the hub's entry for it. Nothing on that machine "
                   "changes, and it comes back the next time it announces itself.",
            confirm="Forget"):
        return
    try:
        await run.io_bound(library.forget_device, str(device.get("device_id") or ""))
    except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
        ui.notify(f"Could not forget that device: {exc}", type="negative")
        return
    ui.notify(f"Forgot {name}", type="positive")
    if rerender is not None:
        rerender()


def _software_rows(device: dict[str, Any], is_local: bool, client: Any,
                   update: dict[str, Any] | None) -> list[tuple[Any, Any]]:
    """What this device is running, and whether it can take what is published.

    A device with no answer gets the heading and an unknown - one that announced itself
    before ports were recorded cannot be reached, and one that is not answering has not
    said. Either way "up to date" would be a guess wearing a fact.
    """
    rows: list[tuple[Any, Any]] = [(panel.HEADING, "Software")]
    if not update:
        rows.append(("Version", panel.state("Not known", "unknown")))
        if not is_local and client is None:
            rows.append(panel.note(UNREACHABLE_NOTE))
        return rows

    current = str(update.get("current_version") or "unknown")
    if not update.get("update_available"):
        rows.append(("Version", panel.state(current, "on")))
        return rows

    latest = str(update.get("latest_version") or "a newer build")
    if not update.get("update_supported"):
        reason = WHY_NOT.get(str(update.get("support_reason") or ""), CANNOT_UPDATE)
        rows.append(("Version", panel.state(f"{latest} available", "warn",
                                            beside=current)))
        rows.append(panel.note(reason))
        return rows

    rows.append(("Version", panel.state(f"{latest} available", "warn", beside=current)))
    def update_action() -> None:
        with ui.element("div").classes("hub-fact-edit"):
            panel.action(f"Update to {latest}",
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
    latest = str(update.get("latest_version") or "the published build")
    try:
        playing = await run.io_bound(client.play_state)
    except Exception as exc:  # noqa: BLE001 - a dialog that cannot say what it will do
        ui.notify(f"Could not check what {name} is doing: {exc}", type="negative")
        return

    running = str((playing or {}).get("game_name") or "") if (
        playing or {}).get("launching") else ""

    # Named, because "a table is running" is a fact the person asking may not have: the
    # hub is not necessarily open on the machine the table is on.
    lines = [f"{running} is being played there and will be closed."] if running else []
    if not await confirm.ask(
            f"Update {name} to {latest}?",
            detail="The package is downloaded first, then VPinFE closes, the install "
                   "is replaced and it starts again.",
            lines=lines,
            confirm="Stop the table and update" if running else "Update",
            danger=bool(running)):
        return
    await _start_update(client, name, bool(running))


async def _start_update(client: Any, name: str, stop_table: bool) -> None:
    try:
        await run.io_bound(lambda: client.perform_update(stop_table=stop_table))
    except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
        ui.notify(f"Could not start the update: {exc}", type="negative")
        return
    # Nothing to redraw towards. Updating this install takes the page's own server down;
    # updating another leaves it up but knowing nothing new until that device is back.
    ui.notify(f"Update staged. {name} is restarting to apply it.", type="positive")


def _hostname_placeholder(device: dict[str, Any], is_local: bool) -> str:
    """What it will be called if the field is left empty.

    The name it reports with nothing set is its hostname, so showing that is more use
    than the word "hostname" - it is the actual answer rather than a description of one.
    """
    if not is_local:
        return str(device.get("display_name") or "")
    return str(device.get("display_name") or "").strip() or "This machine's hostname"




# --- The grid ---------------------------------------------------------------

SCOPE = "hubui.devices.columns"

KIND_LABELS = {"vpinfe": "VPinFE", "vpx_mobile": "VPX Mobile"}

_KIND_CHOICES = [{"value": label, "label": label} for label in KIND_LABELS.values()]
_STATE_CHOICES = [{"value": text, "label": text} for text, _l, _c in _REACH.values()]

COLUMNS: list[dict[str, Any]] = [
    grid.column("name", "Name", 200, pinned="left",
                help="What this device calls itself, or the address it answered from\n"
                     "where it has never reported a name."),
    grid.column("kind", "Kind", 120, **grid.choice_filter(_KIND_CHOICES),
                help="A VPinFE install answers for itself. A VPX Mobile device runs\n"
                     "VPX and not VPinFE, so the hub holds everything known about it."),
    grid.column("state", "State", 140, **grid.choice_filter(_STATE_CHOICES),
                help="Whether it answered when the hub last asked.\n\n"
                     "Answering - it is there.\n"
                     "Not answering - the hub asked and got nothing.\n"
                     "Cannot be asked - it has never said which port it answers on,\n"
                     "which switching the machine on does not fix."),
    grid.column("what", "Running", 160,
                help="What answered. A VPinFE install reports its version; a phone\n"
                     "reports nothing beyond being there."),
    grid.column("address", "Address", 150,
                help="Where the hub reaches it. Read off the socket it announced from,\n"
                     "never claimed in the announcement."),
    grid.column("last_seen", "Last seen", 170,
                help="When it was last known to be there - it announced, or the hub\n"
                     "asked and got an answer. Not the same as when it last started."),
    grid.column("roles", "Roles", 130,
                help="What that install serves: the shared library half (hub), the\n"
                     "machine games launch on (device), or both."),
]

_ALL = [definition["field"] for definition in COLUMNS]

VIEWS: dict[str, list[str] | views.Preset] = {
    "All devices": views.Preset(
        columns=("name", "kind", "state", "what", "last_seen"),
        sort=({"colId": "state", "sort": "asc", "sortIndex": 0},
              {"colId": "name", "sort": "asc", "sortIndex": 1}),
        help="Every device this hub has met. Sorted so that anything not answering "
             "is at the top, because that is what you opened this page to find out."),
    "Answering": views.Preset(
        columns=("name", "kind", "what", "address", "roles"),
        sort=({"colId": "name", "sort": "asc", "sortIndex": 0},),
        filters={"state": {"values": [_REACH[device_client.ANSWERING][0]]}},
        help="What is switched on and reachable right now."),
    "Not answering": views.Preset(
        columns=("name", "kind", "state", "address", "last_seen"),
        sort=({"colId": "last_seen", "sort": "asc", "sortIndex": 0},),
        filters={"state": {"values": [_REACH[device_client.UNREACHABLE][0],
                                      _REACH[device_client.UNASKABLE][0]]}},
        help="Devices the hub could not reach, oldest first - so the ones that have "
             "been gone longest, and are most likely worth forgetting, lead."),
    "Everything": views.Preset(
        columns=tuple(_ALL),
        help="Every row and every column. The way out of any other view, and where "
             "you build a filter of your own worth saving."),
}


def rows(devices: list[dict[str, Any]],
         reach: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
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
            "name": device_label(device),
            "kind": KIND_LABELS.get(str(device.get("kind") or "vpinfe"), "VPinFE"),
            # Blank until the probes land, rather than a word meaning "not yet": a
            # grid filter over "Checking" is a filter over how fast the page loaded.
            "state": state[0] if state else "",
            "what": str(probe.get("what") or ""),
            "address": str(device.get("address") or ""),
            "last_seen": _when(str(device.get("last_reachable") or "")),
            "roles": ", ".join(str(r) for r in (device.get("roles") or [])),
        })
    return out


def _when(stamp: str) -> str:
    """A timestamp as a person reads one. Sortable as text because it stays ISO order -
    the grid sorts the string, and the string is still year-first."""
    return stamp.replace("T", " ").replace("Z", "") if stamp else ""


def build(found: list[dict[str, Any]], library: Any, state: dict[str, Any],
          on_select: Callable[[dict | None], None],
          probe: Callable[[], Any] | None = None) -> None:
    """Devices as a grid, so the selected row is what the workbench answers for.

    The same shape every other subject uses. Kind and reachability are columns rather
    than groups, which is what lets one question - "which of these is not answering" -
    be a sort, a filter and a saved view instead of a fixed arrangement.
    """
    # Deferred: `games` imports `workbench`, and `workbench` imports this module for
    # the device sections - so taking the view control at import time closes the loop.
    # Only `build` needs it, and by then every module is loaded.
    from .games import view_control

    built = rows(found, state.get("device_reach"))
    away = sum(1 for row in built if row["state"]
               and row["state"] != _REACH[device_client.ANSWERING][0])
    on_screen = {"rows": len(built)}

    def said() -> str:
        if on_screen["rows"] != len(built):
            return f"{on_screen['rows']} of {len(built)} devices"
        return f"{len(built)} devices, {away} not answering" if away \
            else f"{len(built)} devices"

    with ui.row().classes("w-full items-center gap-2 px-3 py-2 mb-2 shrink-0 hub-panel"):
        search = ui.input(placeholder="Search devices") \
            .props("dense outlined clearable").classes("w-64")
        _wire_views, _picker, showing = view_control(library, SCOPE, VIEWS,
                                                    _ALL, COLUMNS)
        ui.space()
        count = ui.label(said()).classes("text-xs hub-label")
        if probe is not None:
            ui.button(icon="refresh", on_click=probe) \
                .props("flat dense round size=sm").classes("shrink-0") \
                .tooltip("Ask every device whether it is there")

    by_id = {row["id"]: row for row in built}
    ui.on("hub_row_focus",
          lambda event: on_select(by_id.get(grid.focused_row(event))))

    async def on_header_context(col_id: str | None) -> None:
        state_now = await table.run_grid_method("getColumnState") or []
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

def _client_for(context: dict[str, Any]):
    return device_client.for_device(_of(context), context.get("local_device_id"))


def _of(context: dict[str, Any]) -> dict[str, Any]:
    return context.get("device") or {}


def _is_local(context: dict[str, Any]) -> bool:
    return _of(context).get("device_id") == context.get("local_device_id")


async def detail_groups(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """Everything about a device, as one list of groups.

    One section rather than five, because four of the five held three rows or fewer and
    a rail entry that opens one row is a click charged for nothing. The groups are
    headings inside it, which is what the panel already does everywhere else.
    """
    rows_out: list[tuple[Any, Any]] = [(panel.HEADING, "Identity")]
    rows_out += await _identity_rows(context)
    rows_out.append((panel.HEADING, "Connection"))
    rows_out += _connection_rows(_of(context), context.get("reach"))
    rows_out += await software_rows(context)
    caps = capability_rows(context)
    if caps:
        rows_out.append((panel.HEADING, "Capabilities"))
        rows_out += caps
    rows_out.append((panel.HEADING, "This entry"))
    rows_out += entry_rows(context)
    return rows_out


async def _identity_rows(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """What it is called, and what kind of thing it is."""
    device = _of(context)
    library = context.get("library")
    editable = _is_local(context) and library is not None

    # What the install has been told to call itself, which is not what it reports: the
    # reported name already fell back to the hostname, so showing that as the value
    # leaves nothing to tell a chosen name from a defaulted one.
    stored = ""
    if editable:
        try:
            values = await run.io_bound(library.config_values)
            stored = str(((values or {}).get("install") or {}).get("display_name") or "")
        except Exception:  # noqa: BLE001 - an unreadable name is an empty field, not a 500
            editable = False

    async def rename(value: str) -> None:
        try:
            await run.io_bound(library.put_config,
                               {"install": {"display_name": value.strip()}})
        except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
            ui.notify(f"Could not save that: {exc}", type="negative")
            return
        rebuild = context.get("rebuild")
        if rebuild is not None:
            await rebuild()

    rows_out: list[tuple[Any, Any]] = [
        ("Name", panel.field(stored, rename,
                             placeholder=_hostname_placeholder(device,
                                                               _is_local(context)),
                             disabled=not editable)),
    ]
    if not _is_local(context):
        rows_out.append(panel.note(REMOTE_NAME_NOTE))
    rows_out.append(("Kind", KIND_LABELS.get(str(device.get("kind") or "vpinfe"),
                                             "VPinFE")))
    rows_out.append(("Roles", ", ".join(str(r) for r in (device.get("roles") or []))
                     or "Not reported"))
    return rows_out


def connection_rows(device: dict[str, Any],
                    reach: dict[str, Any] | None) -> list[tuple[Any, Any]]:
    return _connection_rows(device, reach)


async def software_rows(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """What it is running. Asked of the device rather than read from the registry,
    which holds no version at all."""
    device = _of(context)
    client = _client_for(context)
    update = context.get("update")
    if update is None and client is not None:
        try:
            update = await run.io_bound(client.update_check)
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
                                 context.get("local_capabilities") or set())
        text, level = _CHIP[state]
        out.append((humanize(capability), panel.state(text, level)))
    return out or [panel.intro("This device declares nothing.")]


def entry_rows(context: dict[str, Any]) -> list[tuple[Any, Any]]:
    """What this hub holds about the device, which is the only part a hub owns."""
    device = _of(context)
    library = context.get("library")
    out: list[tuple[Any, Any]] = [
        ("First seen", _when(str(device.get("first_seen") or "")) or "Not known"),
        ("Announced", _when(str(device.get("last_seen") or "")) or "Never"),
    ]
    if _is_local(context) or library is None:
        out.append(panel.note(
            "This is the install you are reading the hub from, so its entry is not "
            "something to forget."))
        return out

    def forget_action() -> None:
        # In the fact rhythm's own wrapper, or the button takes the whole value column -
        # a destructive verb drawn as a full-width bar reads as a banner.
        with ui.element("div").classes("hub-fact-edit"):
            panel.action("Forget this device",
                         lambda: _confirm_forget(library, device,
                                                 context.get("rebuild")),
                         icon="delete_outline", inline=True, danger=True)()

    out.append(panel.note(FORGET_NOTE))
    out.append(("", forget_action))
    return out


async def settings_page_block(context: dict[str, Any],
                              sections: tuple[str, ...]) -> None:
    """One page of a device's settings, drawn from the schema that device serves.

    Whoever holds the settings answers for them: this install through the hub's own
    client, another machine through the client that reaches it. Both expose the same
    three calls, so a page here and the same page under Settings are one page.

    A device that cannot be reached says so rather than drawing an empty form - a
    settings page with nothing in it reads as a device with no settings.
    """
    device = _of(context)
    source = context.get("library") if _is_local(context) else _client_for(context)
    if source is None:
        panel.facts(ui, [panel.intro(UNREACHABLE_NOTE)])
        return

    # Read once per panel build rather than per page: every page wants the same two
    # answers, and asking a machine across the network per rail click is a page that
    # gets slower the more you look at it.
    if "device_config" not in context:
        try:
            context["device_config"] = (
                await run.io_bound(source.config_schema),
                await run.io_bound(source.config_values))
        except Exception as exc:  # noqa: BLE001 - a settings page says why, never 500s
            context["device_config"] = None
            logger.info("Could not read settings on %s", device_label(device),
                        exc_info=True)
            panel.facts(ui, [panel.intro(
                f"Could not read the settings on {device_label(device)}: {exc}")])
            return
    if context["device_config"] is None:
        panel.facts(ui, [panel.intro(
            f"Could not read the settings on {device_label(device)}.")])
        return

    schema, values = context["device_config"]
    settings_page.build_device_page(source, context, schema, values, sections)
