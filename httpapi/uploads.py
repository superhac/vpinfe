"""Upload sessions, the asset import pipeline, and the VPSdb lens.

`common/uploads/upload_ops.py` runs the pipeline; `common/online/vps_lens.py` answers for
the catalog. What is here is the wire, and the two statuses only this layer can give: a
file that was too big is 413, and a session nothing can be made of is 422.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, File, Form, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from common.online import vps_lens
from common.uploads import upload_ops

from . import models, scopes
from .auth import requires
from .errors import ApiError

router = APIRouter(prefix="/uploads", tags=["uploads"])
vps_router = APIRouter(prefix="/vps", tags=["vps"])


@router.post("", summary="Begin an upload session", dependencies=[requires(scopes.UPLOADS_WRITE)])
def begin_upload() -> models.UploadBegun:
    return models.UploadBegun(**upload_ops.begin())


@router.get("/{upload_id}", summary="Upload session summary",
            dependencies=[requires(scopes.UPLOADS_WRITE)])
def get_upload(upload_id: str) -> models.UploadSummary:
    return models.UploadSummary(**upload_ops.summary(upload_id))


@router.delete("/{upload_id}", summary="Abort an upload session",
               dependencies=[requires(scopes.UPLOADS_WRITE)])
def abort_upload(upload_id: str) -> models.Acknowledged:
    upload_ops.abort(upload_id)
    return models.Acknowledged(ok=True)


@router.post("/{upload_id}/files", summary="Add a file to an upload session",
             dependencies=[requires(scopes.UPLOADS_WRITE)])
async def add_upload_file(upload_id: str, relpath: str = Form(...),
                          file: UploadFile = File(...)) -> models.FileStored:
    try:
        stored = await run_in_threadpool(upload_ops.add_file, upload_id, relpath,
                                         file.file)
    except upload_ops.UploadTooLargeError as exc:
        raise ApiError("payload_too_large", str(exc), status_code=413) from exc
    return models.FileStored(**stored)


@router.get("/{upload_id}/analysis", summary="Analyze an upload session",
            dependencies=[requires(scopes.UPLOADS_WRITE)])
def analyze_upload(upload_id: str) -> models.Analysis:
    return models.Analysis(**upload_ops.analysis_of(upload_id))


@router.post("/{upload_id}/plan", summary="Build an import plan",
             dependencies=[requires(scopes.UPLOADS_WRITE)])
def plan_upload(upload_id: str,
                payload: models.PlanRequest = Body(default_factory=models.PlanRequest),
                ) -> models.ImportPlanResource:
    """What the drop would do, before it does any of it."""
    try:
        return models.ImportPlanResource(
            **upload_ops.plan_for(upload_id, payload.model_dump()))
    except upload_ops.UnprocessableUploadError as exc:
        raise ApiError("unprocessable_upload", str(exc), status_code=422) from exc


@router.post("/{upload_id}/import", summary="Execute an import plan",
             dependencies=[requires(scopes.UPLOADS_WRITE)])
def import_upload(upload_id: str,
                  payload: models.ImportRequest = Body(default_factory=models.ImportRequest),
                  ) -> models.ImportReport:
    try:
        report = upload_ops.execute(upload_id, payload.model_dump(exclude={"declared"}),
                                    payload.declared)
    except upload_ops.UnprocessableUploadError as exc:
        raise ApiError("unprocessable_upload", str(exc), status_code=422) from exc
    except upload_ops.NothingImportableError as exc:
        raise ApiError("no_importable_assets", str(exc), status_code=422,
                       details=exc.details) from exc
    return models.ImportReport(**report)


@vps_router.get("/entry/{vps_id}", summary="One VPSdb entry",
                dependencies=[requires(scopes.VPS_READ)])
def vps_entry(vps_id: str) -> models.VpsSearchResult:
    """Under `/entry/` rather than `/{vps_id}` so it cannot swallow `/search`, and so a
    later verb here does not have to be a reserved word."""
    return models.VpsSearchResult(**vps_lens.entry(vps_id))


@vps_router.get("/entry/{vps_id}/releases", summary="The builds VPSdb lists for one entry",
                dependencies=[requires(scopes.VPS_READ)])
def vps_releases(vps_id: str,
                 listed_as: str = Query("tableFiles")) -> models.VpsReleases:
    """Every record of one kind this machine has, in the order VPSdb holds them - never
    ordered by likeness, which was measured at chance."""
    return models.VpsReleases.model_validate(vps_lens.releases(vps_id, listed_as))


@vps_router.get("/sync", summary="When the catalog was last checked",
                dependencies=[requires(scopes.VPS_READ)])
def vps_sync_state() -> models.VpsSyncState:
    """What a surface needs to say how fresh the answers it is giving are."""
    return models.VpsSyncState(**vps_lens.sync_state())


@vps_router.post("/sync", summary="Check VPSdb for a newer catalog now",
                 dependencies=[requires(scopes.GAMES_WRITE)])
async def vps_sync() -> models.VpsSyncResult:
    """Asked for, so it ignores the schedule. The check is one line and the catalog is
    about 7 MB, so this is off the loop."""
    return models.VpsSyncResult(**await run_in_threadpool(vps_lens.sync_now))


@vps_router.get("/search", summary="Search VPSdb", dependencies=[requires(scopes.VPS_READ)])
def search_vps(q: str = "", limit: int = 20) -> models.VpsSearchResults:
    return models.VpsSearchResults.model_validate(vps_lens.search(q, limit))
