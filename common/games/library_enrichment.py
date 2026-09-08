"""Reading the tables discovery found, so an entry says more than its own name.

Discovery is cheap because it only compares listings. This is the other half and it is
not cheap: `extractFile` hashes the whole `.vpx` to fill `file_hash`, so enriching one
table is a full file read. That is why this never runs inline - it belongs on a job,
where it can report progress and be watched.

Only entries nothing has read are touched. `is_parsed` is the test, so a table keeps
whatever was recorded about it and the pass costs nothing on a library it has finished.
"""

from __future__ import annotations

import logging
from pathlib import Path

from common.games.game_metadata import load_game_meta, persist_game_meta
from common.games.tables import (
    TABLES_KEY,
    entry_filename,
    entry_from_parsed,
    is_parsed,
    table_entries,
)
from common.jobs import JobReporter

logger = logging.getLogger("vpinfe.common.games.library_enrichment")


def pending(games) -> list[tuple[object, str, str]]:
    """Every (game, key, filename) an entry exists for and nothing has read yet.

    Counted before the work starts so a job can say how many of how many, which on a
    network share is the difference between a progress bar and a hang.
    """
    todo = []
    for game in games:
        on_disk = {name.lower() for name in (getattr(game, "table_files", None) or ())}
        if not on_disk:
            continue
        for key, entry in table_entries(getattr(game, "meta_config", {})).items():
            filename = entry_filename(entry)
            if filename.lower() in on_disk and not is_parsed(entry):
                todo.append((game, key, filename))
    return todo


def _read(parser, game, filename: str) -> dict | None:
    path = Path(str(getattr(game, "fullPathGame", "") or "")) / filename
    try:
        return parser.singleFileExtract(str(path))
    except Exception:
        logger.exception("Could not read %s", path)
        return None


def enrich(games, reporter: JobReporter | None = None) -> dict[str, int]:
    """Fill in what a parse knows for every table nothing has read.

    Written per game rather than per table: a folder with three unread builds is one
    `.info` write, not three.
    """
    from common.games.vpx_parser import VPXParser

    todo = pending(games)
    totals = {"read": 0, "failed": 0, "games": 0}
    if not todo:
        return totals

    parser = VPXParser()
    by_game: dict[int, list[tuple[str, str]]] = {}
    order: list[object] = []
    for game, key, filename in todo:
        if id(game) not in by_game:
            by_game[id(game)] = []
            order.append(game)
        by_game[id(game)].append((key, filename))

    done = 0
    for game in order:
        config = load_game_meta(game)
        entries = dict(table_entries(config))
        changed = False
        for key, filename in by_game[id(game)]:
            done += 1
            if reporter:
                reporter.progress(done, len(todo), filename)
            parsed = _read(parser, game, filename)
            if not parsed:
                totals["failed"] += 1
                continue
            # Merged over the entry, never replacing it: hidden, play stats and match
            # records live here too and a parse knows nothing about them.
            entries[key] = {**entries.get(key, {}), **entry_from_parsed(parsed)}
            totals["read"] += 1
            changed = True
        if not changed:
            continue
        config[TABLES_KEY] = entries
        try:
            persist_game_meta(game, config)
        except Exception:
            logger.exception("Could not write tables for %s",
                             getattr(game, "gameDirName", "?"))
            continue
        totals["games"] += 1

    message = (f"Enrichment: read {totals['read']} tables across {totals['games']} games"
               + (f", {totals['failed']} could not be read" if totals["failed"] else ""))
    (reporter.log(message) if reporter else logger.info(message))
    return totals
