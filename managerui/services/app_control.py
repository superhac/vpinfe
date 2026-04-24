from __future__ import annotations

import os
import subprocess
import sys

from nicegui import ui

from managerui.paths import CONFIG_DIR


def system_command_env() -> dict[str, str]:
    """Return a clean env for OS tools that must not inherit bundled runtime libs."""
    env = os.environ.copy()
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH", "_MEIPASS2"):
        env.pop(key, None)
    return env


def _terminate_frontend_browser() -> None:
    main_module = sys.modules.get("__main__")
    frontend_browser = getattr(main_module, "frontend_browser", None) if main_module else None
    if frontend_browser:
        frontend_browser.terminate_all()


def restart_app() -> None:
    """Restart the VPinFE application by signaling main.py to re-exec itself."""
    ui.notify("Restarting VPinFE...", type="info")
    restart_flag = CONFIG_DIR / ".restart"
    restart_flag.touch()
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

    if sys.platform == "win32":
        subprocess.Popen(["shutdown", "/s", "/t", "1"], shell=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
    else:
        subprocess.Popen(["systemctl", "poweroff", "-i"], env=system_command_env())

    _terminate_frontend_browser()


def reboot_system() -> None:
    """Reboot the system."""
    ui.notify("Rebooting system...", type="warning")

    if sys.platform == "win32":
        subprocess.Popen(["shutdown", "/r", "/t", "1"], shell=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to restart'])
    else:
        subprocess.Popen(["systemctl", "reboot"], env=system_command_env())

    _terminate_frontend_browser()
