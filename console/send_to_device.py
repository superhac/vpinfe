"""Putting games on a device that plays them but does not run VPinFE.

The same operation seen from two subjects, which is what this surface runs on. From the
library you start with the games you want and choose where they go; from a device you
start with the phone and manage what it is carrying. Neither covers the other - picking
twelve tables to push is a library job, and noticing a phone is carrying something stale
is a device job - so both are offered and both come through here.
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import run, ui

from common import device_registry
from common.i18n import t
from console import confirm, offload, verbs
from console.api import ApiClient

logger = logging.getLogger("vpinfe.console.send_to_device")


def phones(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The devices games can be sent to, which is the ones that are not installs.

    An install is sent to by putting files in its library, which is a different
    operation with a different answer to where they go.
    """
    return [one for one in devices
            if str(one.get("kind") or "") == device_registry.KIND_VPX_MOBILE
            and one.get("address") and one.get("port")]


def name_of(device: dict[str, Any]) -> str:
    return str(device.get("display_name") or "").strip() or t("console.send_to_device.device")


async def ask_where(games: list[dict[str, Any]]) -> None:
    """Choose a device, say what will happen, and start it.

    A confirm rather than a straight send: this copies whole tables over somebody's
    wifi, and the count and the destination are the two things they would want to have
    seen first.
    """
    if not games:
        return
    try:
        found = phones(await offload.io(ApiClient().devices))
    except Exception as exc:
        ui.notify(str(exc), type="negative")
        return
    if not found:
        # Said rather than hidden: the answer is "not yet", and somebody who has just
        # added a phone in Devices needs to know this is where it turns up.
        ui.notify(t("console.send_to_device.no_devices_send_add"),
                  type="warning")
        return

    picked = found[0] if len(found) == 1 else await _which(found)
    if not picked:
        return
    if not await confirm.ask(
            t("console.send_to_device.send_game_s", len=(len(games)),
                    name_of=(name_of(picked))),
            detail=t("console.send_to_device.table_backglass_settings_rom"),
            confirm=t("console.send_to_device.send"), icon=verbs.SEND, danger=False):
        return
    await send(games, picked)


async def send(games: list[dict[str, Any]], device: dict[str, Any]) -> None:
    """Start the transfer. It runs as a job, so this returns as soon as it is under
    way and the drawer's job line says how it is going."""
    try:
        await run.io_bound(ApiClient().send_to_device, str(device["device_id"]),
                           [str(one["id"]) for one in games])
    except Exception as exc:
        ui.notify(str(exc), type="negative")
        return
    ui.notify(t("console.send_to_device.sending", len=(len(games)), name_of=(name_of(device))),
            type="positive")


async def _which(found: list[dict[str, Any]]) -> dict[str, Any]:
    """Which device, when there is more than one."""
    with ui.dialog() as dialog, ui.card().classes("console-confirm"):
        ui.label(t("console.send_to_device.send_device")).classes("console-confirm-title")
        for device in found:
            ui.button(name_of(device),
                      on_click=lambda _e=None, d=device: dialog.submit(d)) \
                .props("flat no-caps align=left").classes("console-action w-full")
        ui.button(t("word.cancel"), icon=verbs.CANCEL, on_click=lambda: dialog.submit(None)) \
            .props("flat no-caps").classes("console-action")
    return await dialog or {}
