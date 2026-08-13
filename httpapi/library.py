"""Operations over the library as a whole, rather than one game.

A scan rewrites metadata across every game folder, which is why it lives here and
not under /games/{id} - it is not an operation on a game, and pretending it were
would put a library-wide write behind a per-table path.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Response

from common import jobs as job_registry
from common.games import game_service

from . import jobs as jobs_api
from . import models, scopes
from .auth import requires
from .errors import ConflictError

router = APIRouter(prefix="/library", tags=["library"])

# Which values answer for which axis. Stated, not derived: `game_type`/`types` do not
# correspond, so pluralising the name would be a rule with an exception.
_VALUES_FOR = {
    "letter": "letters",
    "theme": "themes",
    "game_type": "types",
    "manufacturer": "manufacturers",
    "year": "years",
}


@router.get("/filters", summary="What this library can be filtered on",
            dependencies=[requires(scopes.GAMES_READ)])
def filters() -> models.FilterAxisList:
    """Every filter axis, with the values this library holds.

    Projected from the registry the resolver matches on, so the two cannot disagree.
    A rating axis carries no values: it is 0-5 whatever is installed.
    """
    from common.games.collection_filters import AXES, GameListFilters
    from common.games.game_repository import ensure_games_loaded

    available = GameListFilters(ensure_games_loaded()).available_options()
    return {"axes": [{"name": axis.name, "scope": axis.scope, "kind": axis.kind,
                      "summary": axis.summary,
                      "values": available.get(_VALUES_FOR.get(axis.name))}
                     for axis in AXES]}


@router.get("/entries", summary="The entries the whole library resolves to",
            dependencies=[requires(scopes.GAMES_READ)])
def entries() -> models.EntryList:
    """The play lens over everything, which is what a frontend shows before a collection
    is chosen. `GET /collections/{name}/entries` is the same lens narrowed to one.

    A collection cannot answer this: there is no stored collection meaning "all of it",
    and inventing one would put a name in every user's file to serve a default view.
    """
    from common.games.collection_resolver import entries_for
    from common.games.game_repository import ensure_games_loaded

    from .collections import _entry_resource

    resolved = entries_for(ensure_games_loaded())
    return {"collection": "", "count": len(resolved),
            "entries": [_entry_resource(entry) for entry in resolved]}


@router.post("/scan", summary="Rebuild game metadata from VPSdb", status_code=202,
             dependencies=[requires(scopes.GAMES_WRITE)])
def scan(response: Response,
         request: models.ScanRequest | None = Body(default=None)) -> models.JobResource:
    """Accepted, not done: the work runs on its own thread and reports on the event
    stream. The scope is games:write because that is what a scan does - it writes
    a .info for every game it can match."""
    options = request or models.ScanRequest()

    def work(job: job_registry.Job):
        return game_service.build_metadata(
            job=job,
            downloadMedia=options.download_media,
            updateAll=options.update_all,
        )

    try:
        job = job_registry.submit(job_registry.KIND_LIBRARY_SCAN, work)
    except job_registry.JobBusyError as exc:
        raise ConflictError(str(exc)) from exc

    response.headers["Location"] = f"/api/v1/jobs/{job.id}"
    return jobs_api.resource(job)
