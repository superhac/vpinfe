"""Bringing what VPinFE knows in line with what is on disk.

Three passes, and the order is the point: re-read the folders, reconcile the tables each
one holds, then read the ones nothing has read. Discovery works from the listing the scan
took, so without the re-read in front of it a second run finds what the first one did.

Refresh, not scan: `POST /library/scan` already means the VPSdb rebuild.
"""

from __future__ import annotations

import logging
import threading

from common import jobs, shutdown
from common.games.library_discovery import discover
from common.games.library_enrichment import enrich
from common.games.table_identity import ensure_unique_table_ids
from common.jobs import JobReporter

logger = logging.getLogger("vpinfe.common.games.library_refresh")

_stop = threading.Event()
_ticker: threading.Thread | None = None


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


def start_periodic(minutes: int) -> None:
    """Refresh every `minutes`, forever. Zero or less never runs, which is the default.

    A tick that finds the library busy is dropped rather than queued: the thing it
    would have done is already being done, and a queue would mean a run for every
    tick that passed while the first one worked.
    """
    global _ticker
    if minutes <= 0 or _ticker is not None:
        return
    _stop.clear()

    def _tick() -> None:
        while not _stop.wait(minutes * 60):
            if shutdown.requested():
                return
            try:
                jobs.submit(jobs.KIND_LIBRARY_SCAN, lambda job: refresh(job.reporter()))
            except jobs.JobBusyError:
                logger.debug("Periodic refresh skipped; the library is busy")
            except Exception:
                logger.exception("Periodic refresh could not start")

    _ticker = threading.Thread(target=_tick, daemon=True, name="library-refresh")
    _ticker.start()
    logger.info("Looking for new tables every %s minutes", minutes)


def stop_periodic() -> None:
    global _ticker
    _stop.set()
    _ticker = None
