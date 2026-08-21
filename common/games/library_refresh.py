"""Bringing what VPinFE knows in line with what is on disk.

Three passes, and the order is the point: re-read the folders, reconcile the tables each
one holds, then read the ones nothing has read. Discovery works from the listing the scan
took, so without the re-read in front of it a second run finds what the first one did.

Refresh, not scan: `POST /library/scan` already means the VPSdb rebuild.
"""

from __future__ import annotations

import logging

from common.games.library_discovery import discover
from common.games.library_enrichment import enrich
from common.games.table_identity import ensure_unique_table_ids
from common.jobs import JobReporter

logger = logging.getLogger("vpinfe.common.games.library_refresh")


def refresh(reporter: JobReporter | None = None) -> dict:
    """Reconcile the library, and read whatever that turns up."""
    from common.games.game_repository import all_games

    if reporter:
        reporter.progress(0, 3, "Reading the library")
    games = all_games(reload=True)

    if reporter:
        reporter.progress(1, 3, "Reconciling tables")
    found = discover(games)
    # Between the halves, not after: this is what makes a discovered entry addressable.
    ensure_unique_table_ids(games)

    if reporter:
        reporter.progress(2, 3, "Reading new tables")
    read = enrich(games, reporter)

    result = {"games": len(games), **{f"discovered_{k}": v for k, v in found.items()},
              **{f"enriched_{k}": v for k, v in read.items()}}
    if reporter:
        reporter.progress(3, 3, "Done")
    logger.info("Library refresh: %s games, %s tables found, %s read",
                len(games), found["found"], read["read"])
    return result
