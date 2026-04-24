from __future__ import annotations

import json
import logging
from urllib.parse import quote

from common.paths import THEMES_DIR
from common.table_metadata import is_truthy


logger = logging.getLogger("vpinfe.frontend.theme_api")


def get_theme_name(config) -> str:
    theme_name = str(config["Settings"].get("theme", "Revolution")).strip()
    return theme_name or "Revolution"


def resolve_theme_dir(theme_name: str):
    theme_dir = THEMES_DIR / theme_name
    return theme_dir if theme_dir.is_dir() else None


def get_theme_config(config):
    theme_dir = resolve_theme_dir(get_theme_name(config))
    if not theme_dir:
        return None
    try:
        return json.loads((theme_dir / "config.json").read_text(encoding="utf-8"))
    except Exception:
        logger.debug("Could not read theme config for %s", theme_dir, exc_info=True)
        return None


def get_audio_muted(config) -> bool:
    return is_truthy(config["Settings"].get("muteaudio", "false"))


def get_theme_index_page(config, window_name: str) -> str:
    port = int(config["Network"].get("themeassetsport", "8000"))
    theme_name = quote(get_theme_name(config), safe="")
    return f"http://127.0.0.1:{port}/themes/{theme_name}/index_{window_name}.html?window={window_name}"
