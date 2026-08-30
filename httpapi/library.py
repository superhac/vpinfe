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
    from common.games.game_repository import all_games

    available = GameListFilters(all_games()).available_options()
    return {"axes": [{"name": axis.name, "scope": axis.scope, "kind": axis.kind,
                      # The name a reader sees, which the registry owns. Without it a
                      # client derives one from the key and gets "Game type" where the
                      # rest of the app says "Type" - section 2.15 puts the naming here.
                      "label": axis.label,
                      "summary": axis.summary,
                      # Whether the axis takes several values, which is an OR across
                      # them. Declared here so a client renders the right control
                      # without knowing which axes exist - section 2.15's whole point.
                      "many": axis.many,
                      "values": available.get(_VALUES_FOR.get(axis.name))}
                     for axis in AXES]}


@router.get("/entries", summary="The entries the whole library resolves to",
            dependencies=[requires(scopes.GAMES_READ)])
def entries() -> models.EntryList:
    """The play lens over everything, which is what a frontend shows before a collection
    is chosen. `GET /collections/{name}/entries` is the same lens narrowed to one.

    The whole library is a collection - `builtin:all`, synthesized rather than stored, so
    it answers here without putting a row in anyone's file. It keeps its own path because
    that is the one a client would guess, and because the prefix is core's business.
    """
    from common.games.collection_resolver import resolve
    from common.games.collection_store import BUILTIN_ALL
    from common.games.collections_service import get_collections_manager
    from common.games.game_repository import all_games

    from .collections import _entry_resource

    resolved = resolve(BUILTIN_ALL, get_collections_manager(), all_games())
    return {"collection": "", "count": len(resolved),
            "entries": [_entry_resource(entry) for entry in resolved]}


@router.post("/preview", summary="What a rule would match, storing nothing",
             dependencies=[requires(scopes.GAMES_READ)])
def preview(request: models.PreviewRequest = Body(...)) -> models.EntryList:
    """Resolve criteria against the library without writing them anywhere.

    An unsaved rule is `builtin:all` plus its criteria, so this is the ordinary resolve
    with nothing stored. A POST because criteria are a structure rather than a query
    string: the registry grows, and several axes take a list.
    """
    from common.games.collection_resolver import resolve
    from common.games.collection_store import BUILTIN_ALL
    from common.games.collections_service import get_collections_manager
    from common.games.game_repository import all_games

    from .collections import _criteria_for, _entry_resource

    manager = get_collections_manager()
    # Set for this call and cleared after it, because the store object outlives the
    # request and a leftover constraint would narrow the next reader's whole library.
    try:
        manager.set_view_filters(_criteria_for(request.filters))
        resolved = resolve(BUILTIN_ALL, manager, all_games())
    finally:
        manager.set_view_filters(None)
    if request.limit and request.limit > 0:
        resolved = resolved[:request.limit]
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


@router.post("/refresh", summary="Find tables added or removed on disk", status_code=202,
             dependencies=[requires(scopes.GAMES_WRITE)])
def refresh(response: Response) -> models.JobResource:
    """Accepted, not done. This is the local counterpart to a scan: it re-reads the
    folders, gives every .vpx it finds an id, notes the ones that are gone, and reads
    whatever nothing has read yet. It never touches the network.

    Shares the scan's job kind deliberately - both write a .info for every game they
    touch, so running them at once would interleave writes to the same files.
    """
    from common.games.library_refresh import refresh as run_refresh

    try:
        job = job_registry.submit(job_registry.KIND_LIBRARY_SCAN,
                                  lambda job: run_refresh(job.reporter()))
    except job_registry.JobBusyError as exc:
        raise ConflictError(str(exc)) from exc

    response.headers["Location"] = f"/api/v1/jobs/{job.id}"
    return jobs_api.resource(job)
