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
from common.i18n import t
from common.jobs import JobReporter

logger = logging.getLogger("vpinfe.common.games.library_refresh")

_stop = threading.Event()
_ticker: threading.Thread | None = None


def refresh(reporter: JobReporter | None = None) -> dict:
    """Reconcile the library, and read whatever that turns up."""
    from common.games import auto_match, game_identity, watching
    from common.games.game_repository import all_games

    if reporter:
        reporter.progress(0, 4, t("said.reading_the_library"))
    games = all_games(reload=True)
    # Taken straight after the read: any request that reaches the catalog gives these
    # an id, and then nothing can tell they are new.
    unseen = [game for game in games
              if not (game_identity.game_id(game) or game_identity.held_id(game))]

    if reporter:
        reporter.progress(1, 4, t("said.finding_tables"))
    found = discover(games)
    # Between the halves, not after: this is what makes a discovered entry addressable.
    ensure_unique_table_ids(games)

    if reporter:
        reporter.progress(2, 4, t("said.matching_new_games"))
    matched = auto_match.match_new(unseen)

    if reporter:
        reporter.progress(3, 4, t("said.reading_new_tables"))
    read = enrich(games, reporter)

    # Stamped here because this is the pass that knows a game is new. A game added
    # next year must not arrive holding a year of upstream activity it was not around
    # for - and a read path that stamped would make asking the question change it.
    watching.note_games(game_identity.ensure_unique_ids(games))
    _art_for(unseen)

    result = {"games": len(games), **{f"discovered_{k}": v for k, v in found.items()},
              **{f"enriched_{k}": v for k, v in read.items()},
              **{f"new_{k}": v for k, v in matched.items()},
              "new_unmatched_ids": _waiting(unseen)}
    if reporter:
        reporter.progress(4, 4, t("word.done"))
    logger.info("Library refresh: %s games, %s tables found, %s read, %s of %s new "
                "games matched", len(games), found["found"], read["read"],
                matched["matched"], matched["games"])
    return result


def read_at_startup(games: list, unseen: list, reporter: JobReporter | None = None) -> dict:
    """Startup's half of a refresh, after its ids: match the games it found new, then
    read what nothing has read."""
    from common.games import auto_match

    matched = auto_match.match_new(unseen)
    read = enrich(games, reporter)
    _art_for(unseen)
    return {**{f"enriched_{k}": v for k, v in read.items()},
            **{f"new_{k}": v for k, v in matched.items()}}


def _waiting(unseen: list) -> list[str]:
    """The ids of the new games still waiting for a match. Asked once ids are given out."""
    from common.games import auto_match, game_identity
    from common.games.game_metadata import normalize_meta

    return [game_identity.game_id(game) for game in unseen
            if auto_match.unmatched(normalize_meta(game.meta_config or {}))
            and game_identity.game_id(game)]


def _art_for(unseen: list) -> None:
    """Hand the new games that are now matched to the art fill.

    After the tables are read, not before: the fill writes the same .info files.
    """
    from common.games import media_fill
    from common.games.game_metadata import effective_vps_id, normalize_meta

    media_fill.request([game.full_path_game for game in unseen
                        if effective_vps_id(normalize_meta(game.meta_config or {}))])


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
