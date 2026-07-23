from __future__ import annotations

import logging

from common.config_access import SettingsConfig, cfg_get


logger = logging.getLogger("vpinfe.frontend.last_table")

# Internal state, not a user-facing setting. Kept in its own section so the
# Manager UI (which renders every key in a shown section) never surfaces it.
STATE_SECTION = "State"
STATE_KEY = "lasttable"


def table_identity(table) -> str:
    """Stable id for a table, preferring its absolute path over its dir name.

    Used both to save the last-launched table and to resolve it back to an
    index, so it must be computed the same way in both directions.
    """
    return str(getattr(table, "fullPathTable", "") or getattr(table, "tableDirName", "") or "")


def save_last_table(iniConfig, table) -> None:
    """Persist `table` as the last-launched table when the feature is enabled."""
    if not SettingsConfig.from_config(iniConfig).restore_last_table:
        return
    identity = table_identity(table)
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
        logger.exception("Could not persist last table selection")


def resolve_last_table_index(iniConfig, tables) -> int:
    """Return the index of the saved last table within `tables`, else 0.

    Returns 0 when the feature is off, nothing is saved, or the saved table
    isn't in the current view (e.g. filtered out by a startup collection).
    """
    if not SettingsConfig.from_config(iniConfig).restore_last_table:
        return 0
    saved = cfg_get(iniConfig, STATE_SECTION, STATE_KEY, "").strip()
    if not saved:
        return 0
    for index, table in enumerate(tables):
        if table_identity(table) == saved:
            return index
    return 0
