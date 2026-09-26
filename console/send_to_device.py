"""Putting games on a device that plays them but does not run VPinFE.

The same operation seen from two subjects, which is what this surface runs on. From the
library you start with the games you want and choose where they go; from a device you
start with the phone and manage what it is carrying. Neither covers the other - picking
twelve tables to push is a library job, and noticing a phone is carrying something stale
is a device job - so both are offered and both come through here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nicegui import run, ui

from common import device_registry
from common.i18n import t
from console import confirm, offload, panel, verbs
from console import dialog as frame
from console.api import ApiClient

logger = logging.getLogger("vpinfe.console.send_to_device")

_POLL_S = 1.0
_POLLS = 3600


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


async def ask_where(games: list[dict[str, Any]],
                    state: dict[str, Any] | None = None) -> None:
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
    await send(games, picked, state)


async def send(games: list[dict[str, Any]], device: dict[str, Any],
               state: dict[str, Any] | None = None) -> None:
    """Start the transfer, and say so if it fails. The drawer's job line says how it is
    going while it runs."""
    client = ApiClient()
    try:
        job = await run.io_bound(client.send_to_device, str(device["device_id"]),
                                 [str(one["id"]) for one in games])
    except Exception as exc:
        ui.notify(str(exc), type="negative")
        return
    ui.notify(t("console.send_to_device.sending", len=(len(games)), name_of=(name_of(device))),
            type="positive")
    watch = (state or {}).get("watch_jobs")
    if callable(watch):
        watch()
    for _ in range(_POLLS):
        await asyncio.sleep(_POLL_S)
        try:
            found = await offload.io(client.job, str((job or {}).get("id") or ""))
        except Exception:  # noqa: BLE001 - the footer line still reports it
            return
        if found.get("state") == "running":
            continue
        if found.get("state") == "failed":
            ui.notify(t("console.send_to_device.failed", name_of=name_of(device),
                        error=found.get("error") or ""), type="negative")
        return


async def _which(found: list[dict[str, Any]]) -> dict[str, Any]:
    """Which device, when there is more than one."""
    with frame.opened(t("console.send_to_device.send_device")) as box:
        with ui.column().classes("gap-2 px-3"):
            for device in found:
                panel.action(name_of(device), lambda _e=None, d=device: box.submit(d),
                             icon=verbs.SEND)()
        with frame.footer():
            frame.cancel(lambda: box.submit(None))
    return await box or {}
