from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import quote

from common import theme_options
from common.config_access import NetworkConfig, SettingsConfig
from common.paths import THEMES_DIR

logger = logging.getLogger("vpinfe.frontend.theme_api")


def get_theme_name(config) -> str:
    return SettingsConfig.from_config(config).theme


def resolve_theme_dir(theme_name: str):
    theme_dir = THEMES_DIR / theme_name
    return theme_dir if theme_dir.is_dir() else None


def read_manifest(theme_dir) -> dict | None:
    """A theme's manifest.json, or None when it has none or it is unreadable."""
    return _read_json_object(Path(theme_dir) / "manifest.json")


def _read_json_object(path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Theme config is invalid JSON: %s", path, exc_info=True)
        return None
    except OSError:
        logger.warning("Could not read theme config: %s", path, exc_info=True)
        return None
    return data if isinstance(data, dict) else None


def _deep_merge(base: dict, overlay: dict) -> dict:
    merged = dict(base)
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _deep_set(config: dict, dotted_key: str, value) -> None:
    current = config
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def _build_theme_config_from_schema(schema: dict) -> dict | None:
    raw_options = schema.get("options")
    if not isinstance(raw_options, list):
        return None

    config: dict = {}
    found_option = False
    for raw_option in raw_options:
        if not isinstance(raw_option, dict):
            continue
        key = str(raw_option.get("key") or raw_option.get("id") or "").strip()
        if not key:
            continue
        value = raw_option.get("value")
        if value is None and "default" in raw_option:
            value = raw_option.get("default")
        _deep_set(config, key, value)
        found_option = True
    return config if found_option else None


def get_theme_config(config):
    """The theme's config: what the author set, with the user's option values over it.

    Three sources, narrowing: config.json is the author's fixed settings, theme.json
    declares the options and their defaults, and the user's own file says what they
    picked. Returning theme.json alone dropped every author value the moment a theme
    had one option.
    """
    theme_dir = resolve_theme_dir(get_theme_name(config))
    if not theme_dir:
        return None

    authored = _read_json_object(theme_dir / "config.json")
    schema = _read_json_object(theme_dir / "theme.json")
    options = _build_theme_config_from_schema(schema) if schema is not None else None
    # What the user actually chose lives outside the theme, so an update cannot take it.
    # It goes over the schema's defaults and under nothing.
    chosen = theme_options.load(Path(theme_dir).name)
    if chosen:
        options = {**(options or {}), **chosen}

    if authored is None and options is None:
        logger.debug("Theme config not found: %s/{config,theme}.json", theme_dir)
        return None
    return _deep_merge(authored or {}, options or {})


def get_audio_muted(config) -> bool:
    return SettingsConfig.from_config(config).mute_audio


def get_theme_index_page(config, window_name: str) -> str:
    port = NetworkConfig.from_config(config).theme_assets_port
    theme_name = quote(get_theme_name(config), safe="")
    return f"http://127.0.0.1:{port}/themes/{theme_name}/index_{window_name}.html?window={window_name}"
