"""Remembering which game the player was on, by identity rather than by position."""

from __future__ import annotations

import logging

from common.config_access import SettingsConfig, cfg_get
from common.games.game_identity import game_id

logger = logging.getLogger("vpinfe.frontend.last_game")

# Internal state, not a user-facing setting. Kept in its own section so the
# Manager UI (which renders every key in a shown section) never surfaces it.
STATE_SECTION = "state"
# The canonical spelling; config_schema keeps "lasttable" resolving for a file
# written before schema 2.
STATE_KEY = "last_table"


def entry_identity(entry) -> str:
    """Stable id for one row of the wheel: the table's, falling back to its game's.

    A game offers several tables and a collection may name a particular one, so saving
    the game comes back to whichever table the list happens to hold. Ids rather than a
    path, because a device reading its library off a hub never sees the hub's filesystem.
    """
    table_id = str(getattr(entry, "table_id", "") or "").strip()
    if table_id:
        return table_id
    return str(game_id(getattr(entry, "game", entry)) or "").strip()


def save_last_launched(iniConfig, game, table_id: str = "") -> None:
    """Persist what just launched. Takes the two ids rather than an entry: no entry
    exists on the path a Remote or API launch takes."""
    if not SettingsConfig.from_config(iniConfig).restore_last_table:
        return
    identity = (str(table_id or "").strip()
                or str(game_id(game) or "").strip())
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


def resolve_last_table_index(iniConfig, entries) -> int:
    """Return the index of the saved last row within `entries`, else 0.

    Returns 0 when the feature is off, nothing is saved, or the saved row
    isn't in the current view (e.g. filtered out by a startup collection).
    """
    if not SettingsConfig.from_config(iniConfig).restore_last_table:
        return 0
    saved = cfg_get(iniConfig, STATE_SECTION, STATE_KEY, "").strip()
    if not saved:
        return 0
    for index, entry in enumerate(entries):
        if entry_identity(entry) == saved:
            return index
    return 0
