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
from common.games.meta_config import VPINFE_SECTION
from common.games.tables import (
    DEFAULT_TABLE_KEY,
    TABLE_ID_KEY,
    TABLES_KEY,
    entry_filename,
    entry_for_filename,
    rekey_by_id,
    table_id,
)

logger = logging.getLogger("vpinfe.common.games.table_identity")


def table_ids(game) -> dict[str, str]:
    """{filename: id} for a game's tables, skipping entries with no id yet."""
    entries = getattr(game, "metaConfig", None) or {}
    entries = entries.get(TABLES_KEY) if isinstance(entries, dict) else None
    return {entry_filename(e): i for i, e in rekey_by_id(entries).items()
            if entry_filename(e)}


def ensure_unique_table_ids(games: Iterable[Any]) -> dict[str, tuple[Any, str]]:
    """Bring a library's table identity up to date, in one pass over every game.

    Mints missing ids, re-mints collisions, converts the filename-keyed map, and
    rewrites a recorded default that still names a file. Returns {id: (game, filename)}.

    Writes a .info only when that game changed: this runs at startup over the whole
    library, and on a share a needless write is a round trip each.

    A collision is not chance at this length - it means a game folder was copied.
    """
    by_id: dict[str, tuple[Any, str]] = {}
    minted = remixed = rekeyed = defaults = 0

    for game in games:
        stored = (getattr(game, "metaConfig", None) or {}).get(TABLES_KEY)
        if not isinstance(stored, dict):
            continue

        entries = rekey_by_id(stored)
        # Same object back means there was nothing to convert.
        changed = entries is not stored
        rekeyed += changed

        resolved: dict[str, dict] = {}
        for entry in entries.values():
            filename = entry_filename(entry)
            # The entry's own id, never the map key: an id-less entry is keyed by its
            # filename, which is truthy and is not an id.
            current = table_id(entry)
            if current and current not in by_id:
                resolved[current] = entry
                by_id[current] = (game, filename)
                continue

            if current:
                other_game, other_file = by_id[current]
                logger.warning(
                    "Table id %s is used by both %s/%s and %s/%s; assigning a new id "
                    "to the latter",
                    current, getattr(other_game, "gameDirName", "?"), other_file,
                    getattr(game, "gameDirName", "?"), filename)
                remixed += 1
            else:
                minted += 1

            fresh = new_id()
            while fresh in by_id:
                fresh = new_id()
            resolved[fresh] = {**entry, TABLE_ID_KEY: fresh}
            by_id[fresh] = (game, filename)
            changed = True

        # The recorded default is a table id. The 2.x migration seeds it with the
        # filename 2.x described, so convert it here rather than teaching every reader
        # to accept both. A name matching no table is left alone: `default_table`
        # already falls through to one that exists.
        vpinfe = (getattr(game, "metaConfig", None) or {}).get(VPINFE_SECTION)
        new_default = ""
        if isinstance(vpinfe, dict):
            recorded = str(vpinfe.get(DEFAULT_TABLE_KEY, "") or "").strip()
            if recorded and recorded not in resolved:
                new_default = entry_for_filename(resolved, recorded)[0]
                if new_default:
                    vpinfe[DEFAULT_TABLE_KEY] = new_default
                    defaults += 1
                    changed = True

        if not changed:
            continue

        game.metaConfig[TABLES_KEY] = resolved
        # Re-read so unrelated sections come from disk, but replace tables outright:
        # re-deriving here would mint different ids than the ones just handed out.
        config = load_game_meta(game)
        config[TABLES_KEY] = resolved
        if new_default:
            config.setdefault(VPINFE_SECTION, {})[DEFAULT_TABLE_KEY] = new_default
        persist_game_meta(game, config)

    if minted or remixed or rekeyed or defaults:
        logger.info("Assigned ids to %s tables, re-minted %s collisions, re-keyed %s "
                    "games, converted %s recorded defaults",
                    minted, remixed, rekeyed, defaults)
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
