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
