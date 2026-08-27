"""Devices: what each one is, and what it can be asked to do."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

# What a kind of device can do when nobody can ask it. A vpx_mobile device runs VPX and
# not VPinFE, so it declares nothing, ever - the hub knows its abilities from the kind.
IMPLIED_BY_KIND: dict[str, set[str]] = {
    "vpx_mobile": {"launch"},
}

PRESENT, ABSENT, UNKNOWN = "present", "absent", "unknown"

_BADGE = {
    PRESENT: ("positive", "check_circle", "Available"),
    ABSENT: ("grey", "remove_circle_outline", "Not offered"),
    UNKNOWN: ("warning", "help_outline", "Cannot be determined"),
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


def build_detail(device: dict[str, Any], device_capabilities: list[str],
          local_device_id: str | None, local_capabilities: set[str]) -> None:
    with ui.column().classes("w-full p-4 gap-3"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("sports_esports", size="28px").classes("text-primary")
            with ui.column().classes("gap-0"):
                ui.label(device.get("display_name") or "Device").classes("text-lg")
                ui.label(f"{device.get('kind', 'vpinfe')} · {device.get('address') or '-'}") \
                    .classes("text-xs opacity-70")

        ui.separator()
        ui.label("Capabilities").classes("text-sm opacity-70")
        with ui.column().classes("w-full gap-1"):
            for capability in device_capabilities:
                state = capability_state(device, capability, local_device_id,
                                         local_capabilities)
                color, icon, label = _BADGE[state]
                with ui.row().classes("items-center gap-2 w-full"):
                    ui.icon(icon).classes(f"text-{color}")
                    ui.label(capability.replace("_", " ")).classes("w-40")
                    ui.badge(label, color=color).props("outline")


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
                        ui.label(device.get("display_name") or "device").classes("text-sm")
                        ui.label(f"{device.get('kind', 'vpinfe')} \u00b7 "
                                 f"{device.get('address') or '-'}").classes("text-xs opacity-60")
                    ui.space()
                    ui.icon("chevron_right").classes("opacity-40")
