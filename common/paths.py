from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir

from common.iniconfig import IniConfig


CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
VPINFE_INI_PATH = CONFIG_DIR / "vpinfe.ini"
COLLECTIONS_PATH = CONFIG_DIR / "collections.ini"
THEMES_DIR = CONFIG_DIR / "themes"
PLUGIN_PROFILES_DIR = CONFIG_DIR / "plugin_profiles"
USER_CONFIG_PATH = VPINFE_INI_PATH
USER_ROMS_PATH = CONFIG_DIR / "roms.json"


def ensure_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def configure_nicegui_storage() -> str:
    nicegui_storage_dir = ensure_config_dir() / ".nicegui"
    nicegui_storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = str(nicegui_storage_dir)
    os.environ["NICEGUI_STORAGE_PATH"] = storage_path
    return storage_path


def get_ini_config() -> IniConfig:
    ensure_config_dir()
    return IniConfig(str(VPINFE_INI_PATH))


def get_tables_path(default: str = "~/tables") -> str:
    try:
        config = get_ini_config()
        table_root = config.config.get("Settings", "tablerootdir", fallback="").strip()
        if table_root:
            return os.path.expanduser(table_root)
    except Exception:
        pass
    return os.path.expanduser(default)


def get_themes_dir() -> Path:
    return ensure_config_dir() / "themes"
