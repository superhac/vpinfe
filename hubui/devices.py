"""Devices: what each one is, and what it can be asked to do."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

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
          update: dict[str, Any] | None = None) -> None:
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
            library, rerender, update), once=True)


async def _fill_detail(body, device: dict[str, Any], device_capabilities: list[str],
                       local_device_id: str | None, local_capabilities: set[str],
                       library: Any, rerender: Callable[[], None] | None,
                       update: dict[str, Any] | None = None) -> None:
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

    rows: list[tuple[Any, Any]] = [
        ("Name", panel.field(stored, rename,
                             placeholder=_hostname_placeholder(device, is_local),
                             disabled=not editable)),
    ]
    if not is_local:
        rows.append(panel.note(REMOTE_NAME_NOTE))
    rows.extend(_software_rows(device, is_local, library, update))
    rows.append((panel.HEADING, "Capabilities"))
    for capability in device_capabilities:
        state = capability_state(device, capability, local_device_id,
                                 local_capabilities)
        text, level = _CHIP[state]
        rows.append((humanize(capability), panel.state(text, level)))
    with body:
        panel.facts(ui, rows)


def _software_rows(device: dict[str, Any], is_local: bool, library: Any,
                   update: dict[str, Any] | None) -> list[tuple[Any, Any]]:
    """What this device is running, and whether it can take what is published.

    A device that is not this one gets the heading and an unknown: the hub holds what it
    reported, and nothing has asked it what it is running. Saying "up to date" there
    would be a guess wearing a fact.
    """
    rows: list[tuple[Any, Any]] = [(panel.HEADING, "Software")]
    if not is_local or not update:
        rows.append(("Version", panel.state("Not known", "unknown")))
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
    rows.append((
        "",
        panel.action(f"Update to {latest}", lambda: _confirm_update(library, update),
                     icon="system_update_alt", inline=True),
    ))
    return rows


async def _confirm_update(library: Any, update: dict[str, Any]) -> None:
    """Ask before replacing the running application, naming which install it is.

    The name is the point of the question. The hub can be open on one machine while it
    drives another, and "Update to v3.1" does not say which one goes down - an update
    replaces the install the hub is running on, whichever screen was used to ask.
    """
    latest = str(update.get("latest_version") or "the published build")
    try:
        where = await run.io_bound(library.discovery)
        playing = await run.io_bound(library.play_state)
    except Exception as exc:  # noqa: BLE001 - a dialog that cannot say what it will do
        ui.notify(f"Could not check what that install is doing: {exc}", type="negative")
        return

    name = str((where or {}).get("display_name") or "this install")
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
    await _start_update(library, bool(running))


async def _start_update(library: Any, stop_table: bool) -> None:
    try:
        await run.io_bound(lambda: library.perform_update(stop_table=stop_table))
    except Exception as exc:  # noqa: BLE001 - the reason belongs on the page
        ui.notify(f"Could not start the update: {exc}", type="negative")
        return
    # Nothing to redraw towards: the install answering this page is the one going down,
    # so the next thing this client does is fail until it comes back.
    ui.notify("Update staged. VPinFE is restarting to apply it.", type="positive")


def _hostname_placeholder(device: dict[str, Any], is_local: bool) -> str:
    """What it will be called if the field is left empty.

    The name it reports with nothing set is its hostname, so showing that is more use
    than the word "hostname" - it is the actual answer rather than a description of one.
    """
    if not is_local:
        return str(device.get("display_name") or "")
    return str(device.get("display_name") or "").strip() or "This machine's hostname"


def build_registry(registry: list[dict[str, Any]],
                 on_open: Callable[[dict[str, Any]], None]) -> None:
    """The devices this hub knows, as a page rather than as nav entries.

    One entry per device in the nav read fine with one device and would not with ten -
    and a registry accumulates entries for installs that never come back, so its length
    is not something the nav can be sized for.
    """
    with ui.column().classes("w-full p-4 gap-2"):
        ui.label(f"{len(registry)} device(s)").classes("text-xs opacity-60")
        for device in registry:
            with ui.card().classes("w-full cursor-pointer").on("click",
                                                               lambda p=device: on_open(p)):
                with ui.row().classes("items-center gap-3 w-full"):
                    ui.icon("sports_esports" if device.get("kind") == "vpinfe"
                            else "tablet_android", size="22px").classes("text-primary")
                    with ui.column().classes("gap-0"):
                        ui.label(device_label(device)).classes("text-sm")
                        ui.label(f"{device.get('kind', 'vpinfe')} \u00b7 "
                                 f"{device.get('address') or '-'}").classes("text-xs opacity-60")
                    ui.space()
                    ui.icon("chevron_right").classes("opacity-40")
