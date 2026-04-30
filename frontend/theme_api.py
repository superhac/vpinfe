from __future__ import annotations

import json
import logging
from urllib.parse import quote

from common.config_access import NetworkConfig, SettingsConfig
from common.paths import THEMES_DIR


logger = logging.getLogger("vpinfe.frontend.theme_api")


def get_theme_name(config) -> str:
    return SettingsConfig.from_config(config).theme


def resolve_theme_dir(theme_name: str):
    theme_dir = THEMES_DIR / theme_name
    return theme_dir if theme_dir.is_dir() else None


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
    theme_dir = resolve_theme_dir(get_theme_name(config))
    if not theme_dir:
        return None

    theme_schema_path = theme_dir / "theme.json"
    if theme_schema_path.exists():
        try:
            schema = json.loads(theme_schema_path.read_text(encoding="utf-8"))
            if isinstance(schema, dict):
                built = _build_theme_config_from_schema(schema)
                if built is not None:
                    return built
        except json.JSONDecodeError:
            logger.warning("Theme schema is invalid JSON: %s", theme_schema_path, exc_info=True)
        except OSError:
            logger.warning("Could not read theme schema: %s", theme_schema_path, exc_info=True)

    config_path = theme_dir / "config.json"
    if not config_path.exists():
        logger.debug("Theme config not found: %s or %s", theme_schema_path, config_path)
        return None
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Theme config is invalid JSON: %s", config_path, exc_info=True)
        return None
    except OSError:
        logger.warning("Could not read theme config: %s", config_path, exc_info=True)
        return None


def get_audio_muted(config) -> bool:
    return SettingsConfig.from_config(config).mute_audio


def get_theme_index_page(config, window_name: str) -> str:
    port = NetworkConfig.from_config(config).theme_assets_port
    theme_name = quote(get_theme_name(config), safe="")
    return f"http://127.0.0.1:{port}/themes/{theme_name}/index_{window_name}.html?window={window_name}"
