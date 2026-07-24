from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_dir

from common.iniconfig import IniConfig


def _resolve_config_dir() -> Path:
    # VPINFE_CONFIG_DIR lets you point the whole config directory (vpinfe.ini,
    # themes/, caches, logs, .nicegui storage) somewhere other than the OS
    # default. Read at import time so it also applies to frozen PyInstaller
    # builds. Falls back to the platformdirs location when unset.
    override = os.environ.get("VPINFE_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(user_config_dir("vpinfe", "vpinfe"))


CONFIG_DIR = _resolve_config_dir()
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
