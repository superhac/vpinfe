from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from common.iniconfig import IniConfig

from managerui.paths import VPINFE_INI_PATH


def gpu_monitoring_supported() -> bool:
    return platform.system() in {"Linux", "Darwin"}


def resolve_usage_path() -> Path:
    candidate = Path.home()
    try:
        config = IniConfig(str(VPINFE_INI_PATH))
        tableroot = config.config.get("Settings", "tablerootdir", fallback="").strip()
        if tableroot:
            candidate = Path(tableroot).expanduser()
    except Exception:
        pass

    current = candidate
    while not current.exists() and current != current.parent:
        current = current.parent

    return current if current.exists() else Path.home()


def format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return "0 B"


def disk_usage(path: Path):
    return shutil.disk_usage(path)


def windowing_system() -> str:
    if platform.system() == "Windows":
        return "Windows"
    if platform.system() == "Darwin":
        return "macOS"

    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "").strip()
    display = os.environ.get("DISPLAY", "").strip()

    if wayland_display or session_type == "wayland":
        return "Wayland"
    if display or session_type == "x11":
        return "X11"
    return "Unknown"


def metric_color(value: float, warn: float, critical: float) -> str:
    if value >= critical:
        return "text-red-400"
    if value >= warn:
        return "text-amber-400"
    return "text-emerald-400"


def metric_tone(value: float, warn: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value >= warn:
        return "warn"
    return "ok"
