"""Operations over the library as a whole, rather than one game.

A scan rewrites metadata across every game folder, which is why it lives here and
not under /games/{id} - it is not an operation on a game, and pretending it were
would put a library-wide write behind a per-table path.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Response

from common import jobs as job_registry

from . import jobs as jobs_api
from . import models, scopes
from .auth import requires
from .errors import ConflictError

router = APIRouter(prefix="/library", tags=["library"])


@router.post("/scan", summary="Rebuild game metadata from VPSdb", status_code=202,
             dependencies=[requires(scopes.GAMES_WRITE)])
def scan(response: Response,
         request: models.ScanRequest | None = Body(default=None)) -> models.JobResource:
    """Accepted, not done: the work runs on its own thread and reports on the event
    stream. The scope is tables:write because that is what a scan does - it writes
    a .info for every game it can match."""
    options = request or models.ScanRequest()

    # Imported here: the Manager UI service pulls in NiceGUI, and the API is meant
    # to be importable without it.
    from managerui.services import game_service

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
