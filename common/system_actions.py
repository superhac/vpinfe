from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def system_command_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH", "_MEIPASS2"):
        env.pop(key, None)
    return env


def request_app_restart(config_dir: Path) -> None:
    (config_dir / ".restart").touch()


def restart_if_requested(config_dir: Path, logger, main_script: Path | None = None, sleep_func=None) -> None:
    restart_flag = config_dir / ".restart"
    if not restart_flag.exists():
        logger.info("No restart requested, exiting.")
        return

    restart_flag.unlink()
    logger.info("Restart requested, re-launching...")
    if sleep_func is None:
        import time

        sleep_func = time.sleep
    sleep_func(1)
    if getattr(sys, "frozen", False):
        os.execvp(sys.executable, [sys.executable])
    script = os.path.abspath(main_script or Path(__file__).resolve().parent.parent / "main.py")
    os.execvp(sys.executable, [sys.executable, script])


def shutdown_system() -> None:
    if sys.platform == "win32":
        subprocess.Popen(["shutdown", "/s", "/t", "1"], shell=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
    else:
        subprocess.Popen(["systemctl", "poweroff", "-i"], env=system_command_env())


def reboot_system() -> None:
    if sys.platform == "win32":
        subprocess.Popen(["shutdown", "/r", "/t", "1"], shell=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["osascript", "-e", 'tell app "System Events" to restart'])
    else:
        subprocess.Popen(["systemctl", "reboot"], env=system_command_env())
