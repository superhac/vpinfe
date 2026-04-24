from __future__ import annotations

from common.iniconfig import IniConfig
from common.themes import ThemeRegistry

from managerui.paths import VPINFE_INI_PATH


def get_active_theme() -> str:
    try:
        config = IniConfig(str(VPINFE_INI_PATH))
        theme_name = config.config.get("Settings", "theme", fallback="Revolution").strip()
        return theme_name or "Revolution"
    except Exception:
        return "Revolution"


def set_active_theme(theme_key: str) -> None:
    config = IniConfig(str(VPINFE_INI_PATH))
    config.config.set("Settings", "theme", theme_key)
    with open(VPINFE_INI_PATH, "w") as handle:
        config.config.write(handle)


def load_registry() -> ThemeRegistry:
    registry = ThemeRegistry()
    registry.load_registry()
    registry.load_theme_manifests()
    return registry


def install_theme(registry: ThemeRegistry, theme_key: str) -> None:
    registry.install_theme(theme_key, force=True)


def delete_theme(registry: ThemeRegistry, theme_key: str) -> None:
    registry.delete_theme(theme_key)
