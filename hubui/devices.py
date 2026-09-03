"""Devices: what each one is, and what it can be asked to do."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common import device_client
from common.labels import humanize

from . import confirm, panel

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

# The rail's groups. By kind always, because the two are different things that answer
# different questions - a flat list would mix what can be asked with what can only be
# sent to. Ordered, so the groups do not move about as devices come and go.
KIND_GROUPS: tuple[tuple[str, str], ...] = (
    ("vpinfe", "VPinFE Installs"),
    ("vpx_mobile", "VPX Mobile"),
)

# How the rail is ordered, within every group at once. Last seen leads because the
# question a registry raises is which of these is still out there.
SORTS: tuple[tuple[str, str], ...] = (
    ("last_seen", "Last seen"),
    ("name", "Name"),
)
DEFAULT_SORT = "last_seen"

# Wider than the pane's rail, for the same reason Settings is: these are names people
# chose, and a hostname is longer than a section heading.
RAIL_PX = 210

# What a probe found, as the mark on a rail row and the chip on the page. Green for
# answering, because that is the one a person scans the rail for.
_REACH = {
    device_client.ANSWERING: ("Answering", "on", "positive"),
    device_client.UNREACHABLE: ("Not answering", "bad", "negative"),
    device_client.UNASKABLE: ("Cannot be asked", "unknown", "grey"),
}


def sorted_devices(devices: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    """The rail's order, applied inside every group rather than across them.

    Newest first under last seen, because the interesting end of that list is what is
    still out there; A-Z under name, because that is what alphabetical means. A device
    that has never been reached sorts last either way rather than first - an empty
    timestamp is the smallest string there is, and it would otherwise lead.
    """
    if sort == "name":
        return sorted(devices, key=lambda d: device_label(d).lower())
    return sorted(devices, key=lambda d: (not d.get("last_reachable"),
                                          _reverse(str(d.get("last_reachable") or "")),
                                          device_label(d).lower()))


def _reverse(stamp: str) -> tuple:
    """Newest first out of an ascending sort, without a reverse flag - the other keys in
    the tuple want ascending, and one flag cannot say two things."""
    return tuple(-ord(ch) for ch in stamp)


def grouped_devices(devices: list[dict[str, Any]], sort: str) -> list[tuple[str, str, list]]:
    """(kind, heading, devices) for each group that has anything in it.

    An empty group is left out: a heading over nothing tells a reader the hub is missing
    something rather than that they have not added one.
    """
    out = []
    for kind, heading in KIND_GROUPS:
        held = [d for d in devices if str(d.get("kind") or "vpinfe") == kind]
        if held:
            out.append((kind, heading, sorted_devices(held, sort)))
    return out


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


def build_detail(device: dict[str, Any], device_capabilities: list[str],
          local_device_id: str | None, local_capabilities: set[str],
          library: Any = None, rerender: Callable[[], None] | None = None,
          update: dict[str, Any] | None = None,
          reach: dict[str, Any] | None = None) -> None:
    with ui.column().classes("w-full p-4 gap-3"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("sports_esports", size="28px").classes("text-primary")
            with ui.column().classes("gap-0"):
                ui.label(device_label(device)).classes("text-lg")
                ui.label(f"{device.get('kind', 'vpinfe')} · {device.get('address') or '-'}") \
                    .classes("text-xs opacity-70")

        ui.separator()
        body = ui.column().classes("w-full gap-0")
        # The stored name is read over HTTP, and this runs on the event loop that would
        # answer it. Same reason the settings pages fill themselves on a timer.
        ui.timer(0.01, lambda: _fill_detail(
            body, device, device_capabilities, local_device_id, local_capabilities,
            library, rerender, update, reach), once=True)


async def _fill_detail(body, device: dict[str, Any], device_capabilities: list[str],
                       local_device_id: str | None, local_capabilities: set[str],
                       library: Any, rerender: Callable[[], None] | None,
                       update: dict[str, Any] | None = None,
                       reach: dict[str, Any] | None = None) -> None:
    is_local = device.get("device_id") == local_device_id
    editable = is_local and library is not None

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
        # Read back rather than assumed: an emptied field falls back to the hostname,
        # and only the install knows what that is. Mutated in place because this dict is
        # what the page is holding - rebinding it here would redraw the old one.
        try:
            fresh = await run.io_bound(library.devices)
            for entry in fresh:
                if entry.get("device_id") == device.get("device_id"):
                    device.update(entry)
                    break
        except Exception:  # noqa: BLE001 - the write landed; the heading catches up later
            logger.warning("Could not re-read the device after renaming it",
                           exc_info=True)
        # The name is the heading of the page it was typed on.
        if rerender is not None:
            rerender()

    # Local or remote, one interface. None means there is nothing to dial - a device that
    # announced itself before ports were recorded, which is not the same as one that is
    # down and must not read like it.
    client = device_client.for_device(device, local_device_id)
    if update is None and client is not None:
        try:
            update = await run.io_bound(client.update_check)
        except Exception:  # noqa: BLE001 - unreachable is a state on the page, not a 500
            logger.info("Could not ask %s what it is running",
                        device_label(device), exc_info=True)
            update = None

    rows: list[tuple[Any, Any]] = [
        ("Name", panel.field(stored, rename,
                             placeholder=_hostname_placeholder(device, is_local),
                             disabled=not editable)),
    ]
    if not is_local:
        rows.append(panel.note(REMOTE_NAME_NOTE))
    rows.extend(_connection_rows(device, reach))
    rows.extend(_software_rows(device, is_local, client, update))
    rows.append((panel.HEADING, "Capabilities"))
    for capability in device_capabilities:
        state = capability_state(device, capability, local_device_id,
                                 local_capabilities)
        text, level = _CHIP[state]
        rows.append((humanize(capability), panel.state(text, level)))
    if not is_local and library is not None:
        rows.append((panel.HEADING, "This entry"))
        rows.append(panel.note(FORGET_NOTE))
        def forget_action() -> None:
            # In the fact rhythm's own wrapper, or the button takes the whole value
            # column - a destructive verb drawn as a full-width bar reads as a banner.
            with ui.element("div").classes("hub-fact-edit"):
                panel.action("Forget this device",
                             lambda: _confirm_forget(library, device, rerender),
                             icon="delete_outline", inline=True, danger=True)()

        rows.append(("", forget_action))
    with body:
        panel.facts(ui, rows)


def _connection_rows(device: dict[str, Any],
                     reach: dict[str, Any] | None) -> list[tuple[Any, Any]]:
    """Whether it is there, what answered, and when it last was.

    The timestamp is shown beside the state rather than instead of it: "not answering"
    is the fact, and how long that has been true is what decides whether it is worth
    doing something about.
    """
    rows: list[tuple[Any, Any]] = [(panel.HEADING, "Connection")]
    rows.append(("Address", str(device.get("address") or "") or "Not known"))

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

    when = str(device.get("last_reachable") or "")
    rows.append(("Last seen", when or "Never"))
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


def _reach_mark(state: str) -> Callable[[], None]:
    """The dot on a rail row that says a device is there.

    Before the name rather than after it, because it is a fact about the device and the
    rail is scanned down its left edge. Nothing at all where the state is not known yet:
    the probes land after the first draw, and a grey dot on every row while they run
    reads as an answer.
    """
    def draw() -> None:
        found = _REACH.get(state)
        if found is None:
            return
        label, _level, color = found
        ui.icon("circle", size="9px") \
            .classes(f"text-{color} shrink-0 hub-reach-dot").tooltip(label)

    return draw


def build(state: dict[str, Any], devices: list[dict[str, Any]],
          device_capabilities: list[str], local_device_id: str | None,
          local_capabilities: set[str], library: Any,
          rerender: Callable[[], None]) -> None:
    """Devices as a rail and one open page, which is the shape Settings already uses.

    A rail rather than a list-then-detail: every device stays visible while you look at
    one, so comparing two is reading rather than navigating - and there is no back
    button to charge for arriving.
    """
    sort = str(state.get("device_sort") or DEFAULT_SORT)
    groups = grouped_devices(devices, sort)
    known = [d for _kind, _heading, held in groups for d in held]
    if not known:
        with ui.column().classes("w-full p-4 gap-2"):
            panel.facts(ui, [panel.intro(
                "No devices yet. An install announces itself to the hub it reads its "
                "library from, and this one is the hub.")])
        return

    current = str(state.get("device_id") or "")
    if current not in {str(d.get("device_id")) for d in known}:
        current = str(known[0].get("device_id") or "")
        state["device_id"] = current

    def pick(device_id: str) -> None:
        state["device_id"] = device_id
        rerender()

    def set_sort(value: str) -> None:
        state["device_sort"] = value
        rerender()

    with ui.row().classes("items-center gap-2 w-full no-wrap hub-devices-bar"):
        ui.label("Sort").classes("text-xs opacity-70")
        picker = ui.select({key: label for key, label in SORTS}, value=sort) \
            .props("dense borderless options-dense").classes("hub-devices-sort")
        picker.on_value_change(lambda: set_sort(str(picker.value or DEFAULT_SORT)))

    entries: list[tuple[Any, ...]] = []
    for _kind, heading, held in groups:
        entries.append((panel.GROUP, heading))
        for device in held:
            found = (state.get("device_reach") or {}).get(str(device.get("device_id")))
            entries.append((str(device.get("device_id")), device_label(device),
                            _reach_hint(device, found),
                            _reach_mark(str((found or {}).get("state") or ""))))

    work = panel.sections(entries, current, pick, rail_px=RAIL_PX)
    chosen = next((d for d in known if str(d.get("device_id")) == current), known[0])
    with work:
        build_detail(chosen, device_capabilities, local_device_id, local_capabilities,
                     library, rerender,
                     reach=(state.get("device_reach") or {}).get(current))


def _reach_hint(device: dict[str, Any], found: dict[str, Any] | None) -> str:
    """The rail row's tooltip: what answered, or when it was last there."""
    if found and found.get("state") == device_client.ANSWERING:
        return str(found.get("what") or "Answering")
    when = str(device.get("last_reachable") or "")
    return f"Last seen {when}" if when else "Never seen"
