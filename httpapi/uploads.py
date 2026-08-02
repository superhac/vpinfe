"""Upload sessions and the asset import pipeline.

Services still live under managerui/ for now; they are not UI code and move in the
package reorganization.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from managerui.services import upload_session_service
from managerui.services.asset_analyzer_service import (
    AnalysisResult,
    DetectedAsset,
    analyze_upload_session,
)
from managerui.services.asset_import_service import (
    ImportPlan,
    build_import_plan,
    execute_import_plan,
    find_vps_entry,
    select_plan_items,
    vps_folder_name,
)
from managerui.services.asset_registry import spec_for
from managerui.services.upload_session_service import UnknownSession, UnsafePath, UploadTooLarge

from . import models, scopes
from .auth import requires
from .errors import ApiError, InvalidRequestError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.uploads")

router = APIRouter(prefix="/uploads", tags=["uploads"])
vps_router = APIRouter(prefix="/vps", tags=["vps"])


def _asset_to_dict(asset: DetectedAsset) -> dict:
    return {
        "kind": asset.kind,
        "label": asset.label,
        "media_key": asset.media_key,
        "root": asset.root,
        "size": asset.size,
        "detail": asset.detail,
        "preview": asset.preview,
    }


def _analysis_to_dict(analysis: AnalysisResult) -> dict:
    return {
        "source_kind": analysis.source_kind,
        "source_name": analysis.source_name,
        "has_game": analysis.has_game,
        "assets": [_asset_to_dict(a) for a in analysis.assets],
        "notes": list(analysis.notes),
        "error": analysis.error,
        "unrecognized": list(analysis.unrecognized),
        "bundle_info": analysis.bundle_info,
    }


def _plan_to_dict(plan: ImportPlan) -> dict:
    return {
        "game_path": plan.game_path,
        "new_game_dir_name": plan.new_game_dir_name,
        "rom_name": plan.rom_name,
        "items": [
            {
                "index": index,
                "kind": item.asset.kind,
                "label": spec_for(item.asset.kind).label,
                "detail": item.asset.detail,
                "destination": item.destination,
                "action": item.action,
                "default_enabled": item.default_enabled,
                "size": item.asset.size,
                "media_key": item.asset.media_key,
            }
            for index, item in enumerate(plan.items)
        ],
        "blocked": [{"kind": b.asset.kind, "reason": b.reason} for b in plan.blocked],
    }


def _session_dir(upload_id: str):
    try:
        return upload_session_service.get_session_dir(upload_id)
    except UnknownSession as exc:
        raise NotFoundError(str(exc)) from exc


def _analysis_for(upload_id: str):
    analysis, source_path = analyze_upload_session(_session_dir(upload_id))
    if analysis.error:
        raise ApiError("unprocessable_upload", analysis.error, status_code=422)
    return analysis, source_path


def _vps_entry(vps_id: str):
    vps_id = (vps_id or "").strip()
    if not vps_id:
        return None
    entry = find_vps_entry(vps_id)
    if entry is None:
        raise InvalidRequestError(f"Unknown vps_id: {vps_id}")
    return entry


@router.post("", summary="Begin an upload session", dependencies=[requires(scopes.UPLOADS_WRITE)])
def begin_upload() -> models.UploadBegun:
    return {"id": upload_session_service.begin_session().upload_id}


@router.get("/{upload_id}", summary="Upload session summary",
             dependencies=[requires(scopes.UPLOADS_WRITE)])
def get_upload(upload_id: str) -> models.UploadSummary:
    try:
        return upload_session_service.finish_session(upload_id)
    except UnknownSession as exc:
        raise NotFoundError(str(exc)) from exc


@router.delete("/{upload_id}", summary="Abort an upload session",
             dependencies=[requires(scopes.UPLOADS_WRITE)])
def abort_upload(upload_id: str) -> models.Acknowledged:
    upload_session_service.cleanup_session(upload_id)
    return {"ok": True}


@router.post("/{upload_id}/files", summary="Add a file to an upload session",
             dependencies=[requires(scopes.UPLOADS_WRITE)])
async def add_upload_file(upload_id: str, relpath: str = Form(...),
                          file: UploadFile = File(...)) -> models.FileStored:
    try:
        written = await run_in_threadpool(
            upload_session_service.store_file, upload_id, relpath, file.file)
    except UploadTooLarge as exc:
        raise ApiError("payload_too_large", str(exc), status_code=413) from exc
    except UnknownSession as exc:
        raise NotFoundError(str(exc)) from exc
    except UnsafePath as exc:
        raise InvalidRequestError(str(exc)) from exc
    return {"bytes": written}


@router.get("/{upload_id}/analysis", summary="Analyze an upload session",
             dependencies=[requires(scopes.UPLOADS_WRITE)])
def analyze_upload(upload_id: str) -> models.Analysis:
    analysis, _source = analyze_upload_session(_session_dir(upload_id))
    return _analysis_to_dict(analysis)


@router.post("/{upload_id}/plan", summary="Build an import plan",
             dependencies=[requires(scopes.UPLOADS_WRITE)])
def plan_upload(upload_id: str,
                payload: models.PlanRequest = Body(default_factory=models.PlanRequest),
                ) -> models.ImportPlanResource:
    analysis, _source = _analysis_for(upload_id)
    vps_entry = _vps_entry(payload.vps_id)
    plan = build_import_plan(
        analysis,
        game_path=payload.game_path,
        rom_name=payload.rom_name,
        allow_new_game=payload.allow_new_game,
    )
    if vps_entry is not None and plan.new_game_dir_name:
        plan = select_plan_items(plan, None, vps_folder_name(vps_entry))
    return _plan_to_dict(plan)


@router.post("/{upload_id}/import", summary="Execute an import plan",
             dependencies=[requires(scopes.UPLOADS_WRITE)])
def import_upload(upload_id: str,
                  payload: models.ImportRequest = Body(default_factory=models.ImportRequest),
                  ) -> models.ImportReport:
    analysis, source_path = _analysis_for(upload_id)
    vps_entry = _vps_entry(payload.vps_id)
    plan = build_import_plan(
        analysis,
        game_path=payload.game_path,
        rom_name=payload.rom_name,
        allow_new_game=payload.allow_new_game,
    )
    if vps_entry is not None and not plan.new_game_dir_name:
        raise InvalidRequestError("vps_id only applies to new-game imports")

    # Folder naming precedence: explicit new_game_dir_name > VPS-derived > vpx stem.
    new_name = payload.new_game_dir_name
    if new_name is None and vps_entry is not None:
        new_name = vps_folder_name(vps_entry)
    try:
        plan = select_plan_items(plan, payload.selected, new_name)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc

    blocked = [{"kind": b.asset.kind, "reason": b.reason} for b in plan.blocked]
    if not plan.items:
        raise ApiError("no_importable_assets", "No importable assets",
                       status_code=422, details={"blocked": blocked})
    try:
        report = execute_import_plan(plan, source_path)
    except (ValueError, FileNotFoundError) as exc:
        raise InvalidRequestError(str(exc)) from exc
    upload_session_service.cleanup_session(upload_id)
    report["blocked"] = blocked

    if vps_entry is not None and report.get("new_table"):
        # Files are on disk; association failure is reported, not fatal.
        from managerui.services.game_service import associate_vps_to_folder, build_metadata

        try:
            associate_vps_to_folder(Path(report["table_path"]), vps_entry, True)
            build_metadata(downloadMedia=True, updateAll=True,
                           gameName=Path(report["table_path"]).name)
            report["vps_associated"] = True
        except Exception as exc:
            logger.exception("VPS association failed after import")
            report["vps_associated"] = False
            report["vps_error"] = str(exc)
    return report


@vps_router.get("/search", summary="Search VPSdb", dependencies=[requires(scopes.VPS_READ)])
def search_vps(q: str = "", limit: int = 20) -> models.VpsSearchResults:
    from managerui.services.game_service import search_vpsdb

    return {
        "results": [
            {
                "vps_id": e.get("id"),
                "name": e.get("name"),
                "manufacturer": e.get("manufacturer"),
                "year": e.get("year"),
                "type": e.get("type"),
                "folder_name": vps_folder_name(e),
            }
            for e in search_vpsdb(q, limit=limit)
        ]
    }
