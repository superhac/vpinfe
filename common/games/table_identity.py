"""Stable local identity for tables: an opaque id on each entry in the `tables` map.

Unique across the library, not just within a game, so an id alone identifies a table.
The game-level counterpart is `game_identity`; the reasoning is in COLLECTIONS.local.md.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from common.games.game_metadata import load_game_meta, persist_game_meta
from common.games.ids import new_id
from common.games.tables import TABLE_ID_KEY, TABLES_KEY, table_id

logger = logging.getLogger("vpinfe.common.games.table_identity")


def table_ids(game) -> dict[str, str]:
    """{filename: id} for a game's tables, skipping entries with no id yet."""
    entries = getattr(game, "metaConfig", None) or {}
    entries = entries.get(TABLES_KEY) if isinstance(entries, dict) else None
    if not isinstance(entries, dict):
        return {}
    return {name: table_id(entry) for name, entry in entries.items() if table_id(entry)}


def ensure_unique_table_ids(games: Iterable[Any]) -> dict[str, tuple[Any, str]]:
    """Give every table an id, re-minting collisions. Returns {id: (game, filename)}.

    Writes a .info only when that game changed: this runs at startup over the whole
    library, and on a share a needless write is a round trip each.

    A collision is not chance at this length - it means a game folder was copied.
    """
    by_id: dict[str, tuple[Any, str]] = {}
    minted = 0
    remixed = 0

    for game in games:
        config = None
        entries = (getattr(game, "metaConfig", None) or {}).get(TABLES_KEY)
        if not isinstance(entries, dict):
            continue

        for filename, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            current = table_id(entry)
            collided = current in by_id
            if current and not collided:
                by_id[current] = (game, filename)
                continue

            if collided:
                other_game, other_file = by_id[current]
                logger.warning(
                    "Table id %s is used by both %s/%s and %s/%s; assigning a new id "
                    "to the latter",
                    current, getattr(other_game, "gameDirName", "?"), other_file,
                    getattr(game, "gameDirName", "?"), filename)
                remixed += 1
            else:
                minted += 1

            # Load lazily so a game that needs no change is never read back off disk.
            if config is None:
                config = load_game_meta(game)
            stored = config.setdefault(TABLES_KEY, {}).setdefault(filename, {})
            fresh = new_id()
            while fresh in by_id:
                fresh = new_id()
            stored[TABLE_ID_KEY] = fresh
            entry[TABLE_ID_KEY] = fresh
            by_id[fresh] = (game, filename)

        if config is not None:
            persist_game_meta(game, config)

    if minted or remixed:
        logger.info("Assigned ids to %s tables and re-minted %s collisions",
                    minted, remixed)
    return by_id


def find_table_by_id(games: Iterable[Any], wanted: str) -> tuple[Any, str] | None:
    """(game, filename) for this table id, or None."""
    wanted = (wanted or "").strip()
    if not wanted:
        return None
    for game in games:
        for filename, found in table_ids(game).items():
            if found == wanted:
                return game, filename
    return None
