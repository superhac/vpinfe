from __future__ import annotations

import subprocess
import sys
import re
from pathlib import Path

from screeninfo import get_monitors


def get_detected_displays() -> dict:
    detected = {
        "screeninfo": [],
        "nsscreen": [],
        "error": "",
    }

    try:
        monitors = get_monitors()
        detected["screeninfo"] = [{
            "id": f"Monitor {i}",
            "output": monitor.name,
            "x": monitor.x,
            "y": monitor.y,
            "width": monitor.width,
            "height": monitor.height,
        } for i, monitor in enumerate(monitors)]
    except Exception as exc:
        detected["error"] = str(exc)
        return detected

    if sys.platform == "darwin":
        try:
            from frontend.chromium_manager import get_mac_screens
            detected["nsscreen"] = [{
                "id": f"Screen {i}",
                "x": screen.x,
                "y": screen.y,
                "width": screen.width,
                "height": screen.height,
            } for i, screen in enumerate(get_mac_screens())]
        except Exception:
            pass

    return detected


def get_display_id_options(detected_displays, current_value: str = "") -> list[str]:
    options = [""]
    count = len(detected_displays.get("screeninfo", []))
    options.extend(str(i) for i in range(count))

    current = (current_value or "").strip()
    if current and current not in options:
        options.append(current)
    return options


def get_uniform_field_width_ch(values: list[str], minimum: int = 30, padding: int = 2) -> int:
    longest = max((len(str(value or "").strip()) for value in values), default=0)
    return max(minimum, longest + padding)


def split_logger_level_value(raw_value: str | None) -> tuple[str, bool, bool]:
    raw = str(raw_value or "").strip()
    if not raw:
        return "info", False, False

    parts = [part.strip().lower() for part in re.split(r"[|,]", raw) if part.strip()]
    level = parts[0] if parts else "info"
    flags = {part.lower() for part in parts[1:]}
    return level, "thirdparty" in flags, "windows" in flags


def get_logger_level_options(current_value: str = "") -> list[str]:
    options = ["debug", "info", "warning", "error", "critical"]
    current, _, _ = split_logger_level_value(current_value)
    if current and current not in options:
        options.append(current)
    return options


def get_ledcontrol_command(script_path: Path, api_key: str, force: bool) -> list[str]:
    command = [sys.executable, str(script_path), "--api-key", api_key]
    if force:
        command.append("--force")
    return command


def run_ledcontrol_pull(script_path: Path, api_key: str, force: bool) -> tuple[int, str, list[str]]:
    command = get_ledcontrol_command(script_path, api_key, force)
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    output = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
    return proc.returncode, output, command
