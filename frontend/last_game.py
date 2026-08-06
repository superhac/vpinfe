from __future__ import annotations

import logging

from common.config_access import SettingsConfig, cfg_get

logger = logging.getLogger("vpinfe.frontend.last_game")

# Internal state, not a user-facing setting. Kept in its own section so the
# Manager UI (which renders every key in a shown section) never surfaces it.
STATE_SECTION = "state"
# The canonical spelling; config_schema keeps "lastgame" resolving for a file
# written before schema 2.
STATE_KEY = "last_game"


def game_identity(game) -> str:
    """Stable id for a game, preferring its absolute path over its dir name.

    Used both to save the last-launched game and to resolve it back to an
    index, so it must be computed the same way in both directions.
    """
    return str(getattr(game, "fullPathGame", "") or getattr(game, "gameDirName", "") or "")


def save_last_game(iniConfig, game) -> None:
    """Persist `game` as the last-launched game when the feature is enabled."""
    if not SettingsConfig.from_config(iniConfig).restore_last_game:
        return
    identity = game_identity(game)
    if not identity:
        return
    parser = iniConfig.config
    if not parser.has_section(STATE_SECTION):
        parser.add_section(STATE_SECTION)
    if parser.get(STATE_SECTION, STATE_KEY, fallback="") == identity:
        return  # unchanged; skip the disk write
    parser.set(STATE_SECTION, STATE_KEY, identity)
    try:
        iniConfig.save()
    except Exception:
        logger.exception("Could not persist last game selection")


def resolve_last_game_index(iniConfig, games) -> int:
    """Return the index of the saved last game within `games`, else 0.

    Returns 0 when the feature is off, nothing is saved, or the saved game
    isn't in the current view (e.g. filtered out by a startup collection).
    """
    if not SettingsConfig.from_config(iniConfig).restore_last_game:
        return 0
    saved = cfg_get(iniConfig, STATE_SECTION, STATE_KEY, "").strip()
    if not saved:
        return 0
    for index, game in enumerate(games):
        if game_identity(game) == saved:
            return index
    return 0
