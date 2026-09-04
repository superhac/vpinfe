"""What the Manager UI does about starting, stopping and restarting.

All of it goes through common.lifecycle, so quitting from here runs the same clean
shutdown a signal does. Reaching for the browser directly is what used to skip it.
"""

from __future__ import annotations

import logging

from nicegui import Client, context, ui

from common import device_client, events, lifecycle
from common.host import system_actions

logger = logging.getLogger("vpinfe.managerui.app_control")


def system_command_env() -> dict[str, str]:
    """Return a clean env for OS tools that must not inherit bundled runtime libs."""
    return system_actions.system_command_env()


def _origin() -> lifecycle.Origin:
    """This browser tab is the address a confirmation goes back to. Outside a client
    there is no tab, which is an origin nothing can ask."""
    try:
        return lifecycle.Origin(lifecycle.SURFACE_MANAGER_UI, context.client.id)
    except Exception:
        return lifecycle.Origin(lifecycle.SURFACE_MANAGER_UI, "")


def _notice(*, surface, address, description, **_payload) -> None:
    """Tell every open Manager UI tab, except the one that asked.

    A tab with no live socket is skipped: NiceGUI would queue the notification for a
    reload that may never come.
    """
    for client in list(Client.instances.values()):
        if client.id == address and surface == lifecycle.SURFACE_MANAGER_UI:
            continue
        if not client.has_socket_connection:
            continue
        try:
            with client:
                ui.notify(description, type="warning")
        except Exception:
            logger.exception("Could not tell a Manager UI client about %s", description)


_notices_installed = False


def install_notices() -> None:
    """Subscribe the Manager UI to lifecycle announcements. Idempotent - subscribing
    twice would show every notice twice."""
    global _notices_installed
    if _notices_installed:
        return
    events.subscribe(events.LIFECYCLE_ACTING, _notice)
    _notices_installed = True


async def _confirmed(scope: str, action: str) -> bool:
    """Put the question to this tab, if the user asked to be asked.

    Asked here rather than through a registered confirmer: a NiceGUI dialog is awaited
    and lifecycle.confirm is not, so the surface asks and reports the answer.
    """
    if not device_client.local().wants_confirmation(scope):
        return True

    question = lifecycle.Request(scope, action, _origin()).describe().capitalize()
    with ui.dialog() as dialog, ui.card().classes('bg-gray-800 p-6'):
        with ui.column().classes('items-center gap-4'):
            ui.icon('warning', size='48px').classes('text-orange-400')
            ui.label(f'{question}?').classes('text-xl font-bold text-white')
            with ui.row().classes('gap-4 mt-4'):
                ui.button('Cancel', on_click=lambda: dialog.submit(False)).props('flat').classes(
                    'bg-gray-600 text-white px-6 py-2 rounded hover:bg-gray-500'
                )
                ui.button('Confirm', on_click=lambda: dialog.submit(True)).props('flat').classes(
                    'bg-orange-600 text-white px-6 py-2 rounded hover:bg-orange-500'
                )
    return bool(await dialog)


async def _request(scope: str, action: str, notice: str, notice_type: str = "info") -> bool:
    if not await _confirmed(scope, action):
        return False
    if not device_client.local().request(scope, action, origin=_origin(),
                                        already_confirmed=True):
        return False
    ui.notify(notice, type=notice_type)
    return True


async def restart_app() -> bool:
    """Restart VPinFE by signaling main.py to re-exec itself."""
    return await _request(lifecycle.APP, lifecycle.RESTART, "Restarting VPinFE...")


async def quit_app() -> bool:
    """Quit VPinFE, closing the frontend windows if any are open."""
    return await _request(lifecycle.APP, lifecycle.STOP, "Quitting VPinFE...")


async def shutdown_system() -> bool:
    """Power off the machine."""
    return await _request(lifecycle.SYSTEM, lifecycle.STOP, "Shutting down system...", "warning")


async def reboot_system() -> bool:
    """Restart the machine."""
    return await _request(lifecycle.SYSTEM, lifecycle.RESTART, "Rebooting system...", "warning")


async def start_frontend() -> bool:
    """Open the frontend windows on an instance that was started headless."""
    return await _request(lifecycle.FRONTEND, lifecycle.START, "Starting the frontend...")


async def stop_frontend() -> bool:
    """Close the frontend windows and leave VPinFE running."""
    return await _request(lifecycle.FRONTEND, lifecycle.STOP, "Closing the frontend...")
