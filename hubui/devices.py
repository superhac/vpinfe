"""Devices: what each one is, and what it can be asked to do."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from common.labels import humanize

from . import panel

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
          library: Any = None, rerender: Callable[[], None] | None = None) -> None:
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
            library, rerender), once=True)


async def _fill_detail(body, device: dict[str, Any], device_capabilities: list[str],
                       local_device_id: str | None, local_capabilities: set[str],
                       library: Any, rerender: Callable[[], None] | None) -> None:
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
    rows.append((panel.HEADING, "Capabilities"))
    for capability in device_capabilities:
        state = capability_state(device, capability, local_device_id,
                                 local_capabilities)
        text, level = _CHIP[state]
        rows.append((humanize(capability), panel.state(text, level)))
    with body:
        panel.facts(ui, rows)


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
