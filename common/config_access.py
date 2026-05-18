from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.table_metadata import is_truthy


def _parser(source):
    return getattr(source, "config", source)


def cfg_get(source, section: str, key: str, fallback: str = "") -> str:
    parser = _parser(source)
    try:
        return str(parser.get(section, key, fallback=fallback))
    except Exception:
        try:
            return str(parser[section].get(key, fallback))
        except Exception:
            return fallback


def cfg_bool(source, section: str, key: str, fallback: bool = False) -> bool:
    parser = _parser(source)
    try:
        return bool(parser.getboolean(section, key, fallback=fallback))
    except Exception:
        return is_truthy(cfg_get(parser, section, key, "true" if fallback else "false"), default=fallback)


def cfg_int(source, section: str, key: str, fallback: int = 0) -> int:
    raw = cfg_get(source, section, key, str(fallback)).strip()
    if raw == "":
        return fallback
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return fallback


@dataclass(frozen=True)
class SettingsConfig:
    table_root_dir: str = ""
    vpx_bin_path: str = ""
    vpx_ini_path: str = ""
    vpx_log_delete_on_start: bool = False
    theme: str = "Revolution"
    startup_collection: str = ""
    auto_update_media_on_startup: bool = False
    global_ini_override: str = ""
    global_table_ini_override_enabled: bool = False
    global_table_ini_override_mask: str = ""
    vpx_launch_env: str = ""
    mute_audio: bool = False
    splashscreen: bool = False
    chrome_options: str = ""
    disable_default_chrome_options: bool = False
    cab_mode: bool = False
    hide_quit_button: bool = False

    @classmethod
    def from_config(cls, source: Any) -> "SettingsConfig":
        theme = cfg_get(source, "Settings", "theme", "Revolution").strip() or "Revolution"
        return cls(
            table_root_dir=cfg_get(source, "Settings", "tablerootdir", "").strip(),
            vpx_bin_path=cfg_get(source, "Settings", "vpxbinpath", "").strip(),
            vpx_ini_path=cfg_get(source, "Settings", "vpxinipath", "").strip(),
            vpx_log_delete_on_start=cfg_bool(source, "Settings", "vpxlogdeleteonstart", False),
            theme=theme,
            startup_collection=cfg_get(source, "Settings", "startup_collection", "").strip(),
            auto_update_media_on_startup=cfg_bool(source, "Settings", "autoupdatemediaonstartup", False),
            global_ini_override=cfg_get(source, "Settings", "globalinioverride", "").strip(),
            global_table_ini_override_enabled=cfg_bool(source, "Settings", "globaltableinioverrideenabled", False),
            global_table_ini_override_mask=cfg_get(source, "Settings", "globaltableinioverridemask", ""),
            vpx_launch_env=cfg_get(source, "Settings", "vpxlaunchenv", ""),
            mute_audio=cfg_bool(source, "Settings", "muteaudio", False),
            splashscreen=cfg_bool(source, "Settings", "splashscreen", False),
            chrome_options=cfg_get(source, "Settings", "chromeoptions", ""),
            disable_default_chrome_options=cfg_bool(source, "Settings", "disabledefaultchromeoptions", False),
            cab_mode=cfg_bool(source, "Settings", "cabmode", False),
            hide_quit_button=cfg_bool(source, "Settings", "MMhideQuitButton", False),
        )


@dataclass(frozen=True)
class MediaConfig:
    table_type: str = "table"
    table_resolution: str = "4k"
    table_video_resolution: str = "1k"
    table_media_priority: str = "video"
    bg_media_priority: str = "video"
    dmd_media_priority: str = "video"
    realdmd_media_priority: str = "color"

    @classmethod
    def from_config(cls, source: Any) -> "MediaConfig":
        return cls(
            table_type=cfg_get(source, "Media", "tabletype", "table").strip().lower() or "table",
            table_resolution=cfg_get(source, "Media", "tableresolution", "4k").strip().lower() or "4k",
            table_video_resolution=cfg_get(source, "Media", "tablevideoresolution", "1k").strip().lower() or "1k",
            table_media_priority=_media_priority(source, "tablemediapriority", ("image", "video"), "video"),
            bg_media_priority=_media_priority(source, "bgmediapriority", ("image", "video"), "video"),
            dmd_media_priority=_media_priority(source, "dmdmediapriority", ("image", "video"), "video"),
            realdmd_media_priority=_media_priority(source, "realdmdmediapriority", ("standard", "color"), "color"),
        )

    def priority_payload(self) -> dict[str, str]:
        return {
            "table": self.table_media_priority,
            "bg": self.bg_media_priority,
            "dmd": self.dmd_media_priority,
            "realdmd": self.realdmd_media_priority,
        }


def _media_priority(source: Any, key: str, allowed: tuple[str, ...], fallback: str) -> str:
    value = cfg_get(source, "Media", key, fallback).strip().lower()
    aliases = {
        "png": "image",
        "mp4": "video",
        "realdmd": "standard",
        "realdmd.png": "standard",
        "realdmd-color": "color",
        "realdmd-color.png": "color",
        "colour": "color",
        "colorized": "color",
    }
    normalized = aliases.get(value, value)
    return normalized if normalized in allowed else fallback


@dataclass(frozen=True)
class NetworkConfig:
    ws_port: int = 8002
    manager_ui_port: int = 8001
    theme_assets_port: int = 8000

    @classmethod
    def from_config(cls, source: Any) -> "NetworkConfig":
        return cls(
            ws_port=cfg_int(source, "Network", "wsport", 8002),
            manager_ui_port=cfg_int(source, "Network", "manageruiport", 8001),
            theme_assets_port=cfg_int(source, "Network", "themeassetsport", 8000),
        )


@dataclass(frozen=True)
class DisplayConfig:
    table_screen_id: int = 0
    table_screen_id_raw: str = "0"
    bg_screen_id: str = ""
    dmd_screen_id: str = ""
    table_orientation: str = "landscape"
    table_rotation: int = 0
    cab_mode: bool = False

    @classmethod
    def from_config(cls, source: Any) -> "DisplayConfig":
        table_screen_id_raw = cfg_get(source, "Displays", "tablescreenid", "0").strip()
        return cls(
            table_screen_id=cfg_int(source, "Displays", "tablescreenid", 0),
            table_screen_id_raw=table_screen_id_raw,
            bg_screen_id=cfg_get(source, "Displays", "bgscreenid", "").strip(),
            dmd_screen_id=cfg_get(source, "Displays", "dmdscreenid", "").strip(),
            table_orientation=cfg_get(source, "Displays", "tableorientation", "landscape"),
            table_rotation=cfg_int(source, "Displays", "tablerotation", 0),
            cab_mode=cfg_bool(source, "Displays", "cabmode", SettingsConfig.from_config(source).cab_mode),
        )

    def window_screen_id(self, config_key: str) -> str:
        if config_key == "bgscreenid":
            return self.bg_screen_id
        if config_key == "dmdscreenid":
            return self.dmd_screen_id
        if config_key == "tablescreenid":
            return self.table_screen_id_raw
        return ""


@dataclass(frozen=True)
class VPinPlayConfig:
    api_endpoint: str = ""
    user_id: str = ""
    initials: str = ""
    machine_id: str = ""
    sync_on_exit: bool = False

    @classmethod
    def from_config(cls, source: Any) -> "VPinPlayConfig":
        return cls(
            api_endpoint=cfg_get(source, "vpinplay", "apiendpoint", "").strip(),
            user_id=cfg_get(source, "vpinplay", "userid", "").strip(),
            initials=cfg_get(source, "vpinplay", "initials", "").strip(),
            machine_id=cfg_get(source, "vpinplay", "machineid", "").strip(),
            sync_on_exit=cfg_bool(source, "vpinplay", "synconexit", False),
        )
