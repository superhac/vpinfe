from __future__ import annotations

import sys

from nicegui import ui

from managerui.paths import CONFIG_DIR
from common import system_actions


def system_command_env() -> dict[str, str]:
    """Return a clean env for OS tools that must not inherit bundled runtime libs."""
    return system_actions.system_command_env()


def _terminate_frontend_browser() -> None:
    main_module = sys.modules.get("__main__")
    frontend_browser = getattr(main_module, "frontend_browser", None) if main_module else None
    if frontend_browser:
        frontend_browser.terminate_all()


def restart_app() -> None:
    """Restart the VPinFE application by signaling main.py to re-exec itself."""
    ui.notify("Restarting VPinFE...", type="info")
    system_actions.request_app_restart(CONFIG_DIR)
    _terminate_frontend_browser()


def quit_app() -> None:
    """Quit VPinFE by closing all Chromium windows or signaling shutdown in headless mode."""
    from managerui.managerui import _shutdown_event

    ui.notify("Quitting VPinFE...", type="info")
    _shutdown_event.set()
    _terminate_frontend_browser()


def shutdown_system() -> None:
    """Shutdown the system."""
    ui.notify("Shutting down system...", type="warning")
    system_actions.shutdown_system()
    _terminate_frontend_browser()


def reboot_system() -> None:
    """Reboot the system."""
    ui.notify("Rebooting system...", type="warning")
    system_actions.reboot_system()
    _terminate_frontend_browser()
