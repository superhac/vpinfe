"""Upload sessions and the asset import pipeline.

Services still live under managerui/ for now; they are not UI code and move in the
package reorganization.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from common import timestamps
from common.games import identity_claims
from common.games.asset_registry import spec_for
from common.uploads import upload_session_service
from common.uploads.asset_analyzer_service import (
    AnalysisResult,
    DetectedAsset,
    analyze_upload_session,
)
from common.uploads.asset_import_service import (
    ImportPlan,
    build_import_plan,
    execute_import_plan,
    find_vps_entry,
    select_plan_items,
    vps_folder_name,
)
from common.uploads.upload_session_service import (
    UnknownSessionError,
    UnsafePathError,
    UploadTooLargeError,
)

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
        "media_kind": asset.media_kind,
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
        "game_dir": plan.game_dir,
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
                "media_kind": item.asset.media_kind,
            }
            for index, item in enumerate(plan.items)
        ],
        "blocked": [{"kind": b.asset.kind, "reason": b.reason} for b in plan.blocked],
    }


def _session_dir(upload_id: str):
    try:
        return upload_session_service.get_session_dir(upload_id)
    except UnknownSessionError as exc:
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
    except UnknownSessionError as exc:
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
    except UploadTooLargeError as exc:
        raise ApiError("payload_too_large", str(exc), status_code=413) from exc
    except UnknownSessionError as exc:
        raise NotFoundError(str(exc)) from exc
    except UnsafePathError as exc:
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
        game_dir=Path(payload.game_dir) if payload.game_dir else None,
        rom_name=payload.rom_name,
        allow_new_game=payload.allow_new_game,
    )
    if vps_entry is not None and plan.new_game_dir_name:
        plan = select_plan_items(plan, None, vps_folder_name(vps_entry))
    return _plan_to_dict(plan)


def _declared_identities(declared) -> dict:
    """Turn the request's declared identities into the vocabulary the writer speaks.

    Rejected here rather than recorded and regretted: a claim that names an upstream
    record without saying how it is known, or that sends a basis outside the closed set,
    is a client asserting a confidence it has not earned - which is the failure the
    matcher measurements ruled out for good.
    """
    if not declared:
        return {}
    out, problems = {}, []
    for name, sent in declared.items():
        identity = identity_claims.DeclaredIdentity(
            vps_file_id=sent.vps_file_id, host_item_id=sent.host_item_id,
            host=sent.host, game_id=sent.game_id, table_id=sent.table_id,
            confirmed_by=sent.confirmed_by)
        problems += [f"{name}: {why}" for why in identity.problems()]
        out[name] = identity
    if problems:
        raise InvalidRequestError("; ".join(problems))
    return out


@router.post("/{upload_id}/import", summary="Execute an import plan",
             dependencies=[requires(scopes.UPLOADS_WRITE)])
def import_upload(upload_id: str,
                  payload: models.ImportRequest = Body(default_factory=models.ImportRequest),
                  ) -> models.ImportReport:
    # Before the session is even looked up: a claim we cannot trust is a bad request
    # whichever upload it names, and saying so early keeps the reason readable.
    declared = _declared_identities(payload.declared)
    analysis, source_path = _analysis_for(upload_id)
    vps_entry = _vps_entry(payload.vps_id)
    plan = build_import_plan(
        analysis,
        game_dir=Path(payload.game_dir) if payload.game_dir else None,
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
        report = execute_import_plan(plan, source_path, declared=declared)
    except (ValueError, FileNotFoundError) as exc:
        raise InvalidRequestError(str(exc)) from exc
    upload_session_service.cleanup_session(upload_id)
    report["blocked"] = blocked

    if vps_entry is not None and report.get("new_game"):
        # Files are on disk; association failure is reported, not fatal.
        from common.games.game_service import associate_vps_to_folder, build_metadata

        try:
            associate_vps_to_folder(Path(report["game_dir"]), vps_entry, True)
            build_metadata(downloadMedia=True, updateAll=True,
                           gameName=Path(report["game_dir"]).name)
            report["vps_associated"] = True
        except Exception as exc:
            logger.exception("VPS association failed after import")
            report["vps_associated"] = False
            report["vps_error"] = str(exc)
    return report


def _vps_resource(entry: dict) -> dict:
    """One VPSdb entry as the API reports it, for the search and for a single lookup.

    One builder because both answer with the same model: two copies of a field list
    behind one response type drift a field at a time and the type does not catch it.
    """
    return {
        "vps_id": entry.get("id"), "name": entry.get("name"),
        "manufacturer": entry.get("manufacturer"), "year": entry.get("year"),
        "type": entry.get("type"), "folder_name": vps_folder_name(entry),
        "releases": len(entry.get("tableFiles") or []),
        # Present on 39% of entries, measured on a 2570-entry snapshot. A surface that
        # leads with it has to hold its own shape when there is none.
        "img_url": entry.get("imgUrl") or "",
        "url": f"https://virtualpinballspreadsheet.github.io/?game={entry.get('id')}",
    }


@vps_router.get("/entry/{vps_id}", summary="One VPSdb entry",
                dependencies=[requires(scopes.VPS_READ)])
def vps_entry(vps_id: str) -> models.VpsSearchResult:
    """What a game is matched to, so a surface can show the match rather than its id.

    Under `/entry/` rather than `/{vps_id}` so it cannot swallow `/search`, and so a
    later verb here does not have to be a reserved word.
    """
    from common.games.game_service import load_vpsdb

    found = next((e for e in load_vpsdb() if str(e.get("id") or "") == vps_id), None)
    if found is None:
        raise NotFoundError("No such VPS entry", details={"vps_id": vps_id})
    return _vps_resource(found)


def _release_resource(release: dict) -> dict:
    """One build of a machine, in what somebody would recognise their own copy by.

    Version and authors, because that is what a `.vpx` carries and so what a person can
    compare against. Not a filename: VPS records one on 3% of releases, so a surface
    built around matching names would be empty almost always.
    """
    urls = [str(item.get("url") or "") for item in (release.get("urls") or [])]
    return {
        "vps_file_id": str(release.get("id") or ""),
        "version": str(release.get("version") or ""),
        "authors": [str(name) for name in (release.get("authors") or [])],
        "format": str(release.get("tableFormat") or ""),
        "features": [str(word) for word in (release.get("features") or [])],
        "comment": str(release.get("comment") or ""),
        # On 95% of releases, against 39% of the entries they belong to - so unlike the
        # entry list, a surface here can lead with the picture.
        "img_url": str(release.get("imgUrl") or ""),
        "updated_at": _as_iso(release.get("updatedAt")),
        "url": next((link for link in urls if link), ""),
    }


def _as_iso(stamp: Any) -> str:
    """VPS keeps epoch milliseconds; everything else here is ISO 8601 UTC seconds."""
    try:
        return timestamps.epoch_to_iso(int(stamp) // 1000)
    except (TypeError, ValueError):
        return ""


@vps_router.get("/entry/{vps_id}/releases", summary="The builds VPSdb lists for one entry",
                dependencies=[requires(scopes.VPS_READ)])
def vps_releases(vps_id: str) -> models.VpsReleases:
    """Every build of this machine, in the order VPSdb holds them.

    Deliberately unordered by anything resembling quality or likeness. A scorer over
    exactly this question was measured at chance and confidently wrong more than half
    the time, so an order implying "yours is probably this one" would carry a
    confidence the evidence does not support.
    """
    from common.games.game_service import load_vpsdb

    found = next((e for e in load_vpsdb() if str(e.get("id") or "") == vps_id), None)
    if found is None:
        raise NotFoundError("No such VPS entry", details={"vps_id": vps_id})
    return {"releases": [_release_resource(item)
                         for item in (found.get("tableFiles") or [])]}


@vps_router.get("/search", summary="Search VPSdb", dependencies=[requires(scopes.VPS_READ)])
def search_vps(q: str = "", limit: int = 20) -> models.VpsSearchResults:
    from common.games.game_service import search_vpsdb

    return {"results": [_vps_resource(e) for e in search_vpsdb(q, limit=limit)]}
