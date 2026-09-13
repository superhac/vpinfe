"""What the library holds, reconciled against what the .info files say.

Discovery is not enrichment. Listing a folder's .vpx and giving each one an entry costs
a directory read the scan has already done; parsing them for a rom and an author costs an
OLE read each. Fusing the two is why only the table that launches ever had an id, and why
a folder's other builds could not be addressed at all.

An entry added here carries a filename and nothing else. It claims no parsed facts, so it
is not the half-filled record `entry_from_parsed` warns about - the minting pass gives it
an id, and enrichment fills the rest in later.

**Nothing is ever removed.** A table's entry carries the user's `hidden`, its play stats
and its match records, and a library on a network share reads as entirely absent for as
long as the mount is late. A file that is not there is recorded with the time it was first
missed and left for a person to act on.
"""

from __future__ import annotations

import logging
from typing import Any

from common.games.game_metadata import load_game_meta, persist_game_meta
from common.games.tables import (
    ABSENT_SINCE_KEY,
    TABLE_FILENAME_KEY,
    TABLES_KEY,
    entry_filename,
    table_entries,
)
from common.timestamps import utc_now_iso

logger = logging.getLogger("vpinfe.common.games.library_discovery")

def _reconcile(game, on_disk: list[str]) -> tuple[dict, int, int, int]:
    """The tables map this game should hold, and what changed to get there."""
    config = load_game_meta(game)
    entries = dict(table_entries(config))
    described = {entry_filename(entry).lower() for entry in entries.values()}
    present = {name.lower() for name in on_disk}
    found = absent = returned = 0

    for name in on_disk:
        if name.lower() in described:
            continue
        # Keyed by filename with no id, which is the shape the minting pass expects of
        # an entry it has not reached yet.
        entries[name] = {TABLE_FILENAME_KEY: name}
        found += 1

    for key, entry in list(entries.items()):
        filename = entry_filename(entry).lower()
        if not filename:
            continue
        recorded = str(entry.get(ABSENT_SINCE_KEY, "") or "")
        if filename not in present and not recorded:
            entries[key] = {**entry, ABSENT_SINCE_KEY: utc_now_iso()}
            absent += 1
        elif filename in present and recorded:
            entries[key] = {k: v for k, v in entry.items() if k != ABSENT_SINCE_KEY}
            returned += 1

    config[TABLES_KEY] = entries
    return config, found, absent, returned


def discover(games) -> dict[str, int]:
    """Reconcile every game's tables against the files the scan found on disk.

    Writes only where something changed, so a settled library costs a pass over what is
    already in memory and no I/O at all.
    """
    totals = {"found": 0, "absent": 0, "returned": 0, "games": 0}
    for game in games:
        on_disk = getattr(game, "table_files", None)
        # None means the scan never recorded a listing for this game, and empty means it
        # read one and saw nothing. Concluding "every table is gone" from a listing we do
        # not have is the one outcome worth refusing outright.
        if not on_disk:
            continue
        try:
            config, found, absent, returned = _reconcile(game, list(on_disk))
        except Exception:
            logger.exception("Could not reconcile tables for %s",
                             getattr(game, "gameDirName", "?"))
            continue
        if not (found or absent or returned):
            continue
        try:
            persist_game_meta(game, config)
        except Exception:
            logger.exception("Could not write tables for %s",
                             getattr(game, "gameDirName", "?"))
            continue
        totals["found"] += found
        totals["absent"] += absent
        totals["returned"] += returned
        totals["games"] += 1

    if totals["games"]:
        logger.info("Discovery: %s tables found, %s newly absent, %s back, across %s games",
                    totals["found"], totals["absent"], totals["returned"], totals["games"])
    return totals


def absent_since(entry: dict[str, Any] | None) -> str:
    """When the file behind this entry was first not found, or ""."""
    if not isinstance(entry, dict):
        return ""
    return str(entry.get(ABSENT_SINCE_KEY, "") or "")
