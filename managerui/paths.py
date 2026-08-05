from __future__ import annotations

import os
from pathlib import Path

from common.paths import COLLECTIONS_PATH, CONFIG_DIR, THEMES_DIR, VPINFE_INI_PATH, get_ini_config


CONFIG_DIR.mkdir(parents=True, exist_ok=True)

MANAGER_STATIC_DIR = Path(__file__).resolve().parent / "static"


def get_games_path(default: str = "~/tables") -> str:
    """Resolve Settings.game_root_dir with a stable fallback."""
    try:
        from common.config_access import cfg_get
        game_root = cfg_get(get_ini_config(), "Settings", "game_root_dir").strip()
        if game_root:
            return os.path.expanduser(game_root)
    except Exception:
        pass
    return os.path.expanduser(default)
