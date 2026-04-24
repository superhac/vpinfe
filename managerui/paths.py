from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir

from common.iniconfig import IniConfig


CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

VPINFE_INI_PATH = CONFIG_DIR / "vpinfe.ini"
COLLECTIONS_PATH = CONFIG_DIR / "collections.ini"
THEMES_DIR = CONFIG_DIR / "themes"
MANAGER_STATIC_DIR = Path(__file__).resolve().parent / "static"


def get_ini_config() -> IniConfig:
    """Return a fresh VPinFE config reader."""
    return IniConfig(str(VPINFE_INI_PATH))


def get_tables_path(default: str = "~/tables") -> str:
    """Resolve Settings.tablerootdir with a stable fallback."""
    try:
        config = get_ini_config()
        table_root = config.config.get("Settings", "tablerootdir", fallback="").strip()
        if table_root:
            return os.path.expanduser(table_root)
    except Exception:
        pass
    return os.path.expanduser(default)
