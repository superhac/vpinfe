from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from managerui.services import upload_session_service
from managerui.services.asset_analyzer_service import AnalysisResult, DetectedAsset, analyze_upload_session
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


logger = logging.getLogger("vpinfe.manager.upload_api")

router = APIRouter()


def _asset_to_dict(asset: DetectedAsset) -> dict:
    return {
        "kind": asset.kind,
        "label": asset.label,
        "media_key": asset.media_key,
        "root": asset.root,
        "size": asset.size,
        "detail": asset.detail,
    }


def _analysis_to_dict(analysis: AnalysisResult) -> dict:
    return {
        "source_kind": analysis.source_kind,
        "source_name": analysis.source_name,
        "has_table": analysis.has_table,
        "assets": [_asset_to_dict(a) for a in analysis.assets],
        "notes": list(analysis.notes),
        "error": analysis.error,
        "unrecognized": list(analysis.unrecognized),
        "bundle_info": analysis.bundle_info,
    }


def _plan_to_dict(plan: ImportPlan) -> dict:
    return {
        "table_path": plan.table_path,
        "new_table_dir_name": plan.new_table_dir_name,
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


@router.post("/api/asset-upload/begin")
def asset_upload_begin() -> JSONResponse:
    session = upload_session_service.begin_session()
    return JSONResponse({"upload_id": session.upload_id})


@router.post("/api/asset-upload/file")
async def asset_upload_file(upload_id: str = Form(...), relpath: str = Form(...),
                            file: UploadFile = File(...)) -> JSONResponse:
    try:
        written = await run_in_threadpool(
            upload_session_service.store_file, upload_id, relpath, file.file)
    except UploadTooLarge as exc:
        return JSONResponse({"error": str(exc)}, status_code=413)
    except (UnknownSession, UnsafePath) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"bytes": written})


@router.post("/api/asset-upload/finish")
def asset_upload_finish(upload_id: str = Form(...)) -> JSONResponse:
    try:
        info = upload_session_service.finish_session(upload_id)
    except UnknownSession as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(info)


@router.post("/api/asset-upload/abort")
def asset_upload_abort(upload_id: str = Form(...)) -> JSONResponse:
    upload_session_service.cleanup_session(upload_id)
    return JSONResponse({"ok": True})


# --- Analysis / import over HTTP (transport-neutral; drivable without the UI) ----

def _session_or_error(upload_id: str):
    try:
        return upload_session_service.get_session_dir(upload_id), None
    except UnknownSession as exc:
        return None, JSONResponse({"error": str(exc)}, status_code=400)


@router.post("/api/asset-upload/analyze")
def asset_upload_analyze(payload: dict = Body(...)) -> JSONResponse:
    session_dir, error = _session_or_error(payload.get("upload_id", ""))
    if error is not None:
        return error
    analysis, _source = analyze_upload_session(session_dir)
    return JSONResponse(_analysis_to_dict(analysis))


def _resolve_vps(payload: dict):
    """Return (vps_entry | None, error_response | None) for an optional vps_id."""
    vps_id = (payload.get("vps_id") or "").strip()
    if not vps_id:
        return None, None
    entry = find_vps_entry(vps_id)
    if entry is None:
        return None, JSONResponse({"error": f"Unknown vps_id: {vps_id}"}, status_code=400)
    return entry, None


@router.post("/api/asset-upload/vps-search")
def asset_upload_vps_search(payload: dict = Body(...)) -> JSONResponse:
    from managerui.services.table_service import search_vpsdb

    results = search_vpsdb(payload.get("q", ""), limit=int(payload.get("limit", 20)))
    return JSONResponse({
        "results": [
            {
                "vps_id": e.get("id"),
                "name": e.get("name"),
                "manufacturer": e.get("manufacturer"),
                "year": e.get("year"),
                "type": e.get("type"),
                "folder_name": vps_folder_name(e),
            }
            for e in results
        ]
    })


@router.post("/api/asset-upload/plan")
def asset_upload_plan(payload: dict = Body(...)) -> JSONResponse:
    session_dir, error = _session_or_error(payload.get("upload_id", ""))
    if error is not None:
        return error
    vps_entry, error = _resolve_vps(payload)
    if error is not None:
        return error
    analysis, _source = analyze_upload_session(session_dir)
    if analysis.error:
        return JSONResponse({"error": analysis.error}, status_code=422)
    plan = build_import_plan(
        analysis,
        table_path=payload.get("table_path", ""),
        rom_name=payload.get("rom_name", ""),
        allow_new_table=bool(payload.get("allow_new_table", False)),
    )
    if vps_entry is not None and plan.new_table_dir_name:
        plan = select_plan_items(plan, None, vps_folder_name(vps_entry))
    return JSONResponse(_plan_to_dict(plan))


@router.post("/api/asset-upload/import")
def asset_upload_import(payload: dict = Body(...)) -> JSONResponse:
    upload_id = payload.get("upload_id", "")
    session_dir, error = _session_or_error(upload_id)
    if error is not None:
        return error
    vps_entry, error = _resolve_vps(payload)
    if error is not None:
        return error
    analysis, source_path = analyze_upload_session(session_dir)
    if analysis.error:
        return JSONResponse({"error": analysis.error}, status_code=422)
    plan = build_import_plan(
        analysis,
        table_path=payload.get("table_path", ""),
        rom_name=payload.get("rom_name", ""),
        allow_new_table=bool(payload.get("allow_new_table", False)),
    )
    if vps_entry is not None and not plan.new_table_dir_name:
        return JSONResponse({"error": "vps_id only applies to new-table imports"}, status_code=400)
    # Folder naming precedence: explicit new_table_dir_name > VPS-derived > vpx stem.
    new_name = payload.get("new_table_dir_name")
    if new_name is None and vps_entry is not None:
        new_name = vps_folder_name(vps_entry)
    try:
        plan = select_plan_items(plan, payload.get("selected"), new_name)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    blocked = [{"kind": b.asset.kind, "reason": b.reason} for b in plan.blocked]
    if not plan.items:
        return JSONResponse({"error": "No importable assets", "blocked": blocked}, status_code=422)
    try:
        report = execute_import_plan(plan, source_path)
    except (ValueError, FileNotFoundError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    upload_session_service.cleanup_session(upload_id)
    report["blocked"] = blocked

    if vps_entry is not None and report.get("new_table"):
        # Files are on disk; association failure is reported, not fatal.
        from managerui.services.table_service import associate_vps_to_folder, build_metadata

        try:
            associate_vps_to_folder(Path(report["table_path"]), vps_entry, True)
            build_metadata(downloadMedia=True, updateAll=True,
                          tableName=Path(report["table_path"]).name)
            report["vps_associated"] = True
        except Exception as exc:
            logger.exception("VPS association failed after import")
            report["vps_associated"] = False
            report["vps_error"] = str(exc)
    return JSONResponse(report)


def register_routes(app) -> None:
    """Attach the asset-upload routes to the given FastAPI app."""
    app.include_router(router)
