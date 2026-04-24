from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from common.iniconfig import IniConfig

from managerui.paths import CONFIG_DIR, VPINFE_INI_PATH


VPX_BACKUP_DIR = CONFIG_DIR / "backups" / "vpx_ini"


def load_vpx_ini_path() -> Path | None:
    config = IniConfig(str(VPINFE_INI_PATH))
    raw_path = config.config.get("Settings", "vpxinipath", fallback="").strip()
    if not raw_path:
        return None
    return Path(os.path.expanduser(raw_path))


def backup_filename(ini_path: Path, reason: str = "manual") -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{ini_path.stem}-{reason}-{timestamp}{ini_path.suffix}"


def sanitize_backup_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(label or "").strip())
    cleaned = cleaned.strip("-.")
    return cleaned[:64]


def create_backup(ini_path: Path, reason: str = "manual", label: str = "") -> Path:
    VPX_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    filename = backup_filename(ini_path, reason=reason)
    safe_label = sanitize_backup_label(label)
    if safe_label:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{ini_path.stem}-{reason}-{safe_label}-{timestamp}{ini_path.suffix}"
    backup_path = VPX_BACKUP_DIR / filename
    shutil.copy2(ini_path, backup_path)
    return backup_path


def list_backups() -> list[Path]:
    if not VPX_BACKUP_DIR.exists():
        return []
    return sorted(
        (path for path in VPX_BACKUP_DIR.iterdir() if path.is_file() and path.suffix.lower() == ".ini"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
