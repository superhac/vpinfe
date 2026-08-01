from __future__ import annotations

import os
from pathlib import Path

from common.paths import COLLECTIONS_PATH, CONFIG_DIR, THEMES_DIR, VPINFE_INI_PATH, get_ini_config


CONFIG_DIR.mkdir(parents=True, exist_ok=True)

MANAGER_STATIC_DIR = Path(__file__).resolve().parent / "static"


def get_games_path(default: str = "~/tables") -> str:
    """Resolve Settings.gamerootdir with a stable fallback."""
    try:
        config = get_ini_config()
        game_root = config.config.get("Settings", "gamerootdir", fallback="").strip()
        if game_root:
            return os.path.expanduser(game_root)
    except Exception:
        pass
    return os.path.expanduser(default)
