"""An upload session, what it turns out to hold, and bringing it into the library.

Four steps, each answerable on its own: begin a session, add files to it, analyze what
arrived, and execute a plan over it. The plan is a separate step because what a drop does
to the folders already there is the question somebody is actually answering when they
confirm, and it can only be answered on this side - a caller cannot see the install's disk.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import IO, Any

from common import service_errors
from common.games import identity_claims
from common.games.asset_registry import spec_for
from common.i18n import t
from common.uploads import upload_session_service
from common.uploads.asset_analyzer_service import (
    AnalysisResult,
    DetectedAsset,
    analyze_upload_session,
)
from common.uploads.asset_import_service import (
    ImportPlan,
    PlannedItem,
    build_import_plan,
    build_media_slot_plan,
    execute_import_plan,
    find_vps_entry,
    only_kind,
    select_plan_items,
    vps_folder_name,
)
from common.uploads.upload_session_service import (
    UnknownSessionError,
    UnsafePathError,
    UploadTooLargeError,
)

__all__ = ["NothingImportableError", "UnprocessableUploadError", "UploadTooLargeError",
           "abort", "add_file", "analysis_of", "begin", "execute", "plan_for", "summary"]


class UnprocessableUploadError(service_errors.ServiceError):
    """The session is there and nothing can be made of what is in it."""


class NothingImportableError(service_errors.ServiceError):
    """A plan with no items. `details` carries what was blocked and why."""


def _asset_to_dict(asset: DetectedAsset) -> dict:
    return {
        "kind": asset.kind,
        "label": asset.label,
        "label_key": f"asset.kind.{asset.kind}.label",
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
        "assets": [_asset_to_dict(one) for one in analysis.assets],
        "notes": list(analysis.notes),
        "error": analysis.error,
        "unrecognized": list(analysis.unrecognized),
        "bundle_info": analysis.bundle_info,
    }


def _item_name(item: PlannedItem) -> str:
    """What the file being brought in is called, for a surface that lists what will land.
    Several files under one asset - a pup pack, a tree - are a count instead."""
    entries = [one for one in item.asset.entries if not one.is_dir]
    if len(entries) == 1:
        return PurePosixPath(entries[0].arcname).name
    return f"{len(entries)} files"


def _replaces(plan: ImportPlan, item: PlannedItem) -> str:
    """What this item does to whatever is already there, said before it happens.

    Asked of the disk, so it belongs on this side: a caller cannot see the install's
    folders, and "will this overwrite something" is the question somebody is actually
    answering when they confirm.
    """
    if item.action == "write_info":
        if plan.new_game_dir_name:
            return "adopts bundle metadata"
        base = Path(plan.game_dir)
        if (base / f"{base.name}.info").exists():
            return "merges into existing metadata - fills gaps only, backup kept"
        return "adopts bundle metadata"
    if plan.new_game_dir_name:
        return ""   # a folder that does not exist yet has nothing to replace
    base = Path(plan.game_dir)
    if item.action == "replace_vpx":
        # Which suffixes are tables is the registry's answer, not a constant here - an app
        # this build gains claims its own, and a glob would not know.
        from common import apps

        wanted = tuple(apps.table_suffixes())
        existing = sorted(one for one in base.iterdir()
                          if one.is_file() and one.suffix.lower() in wanted)
        return f"replaces {existing[0].name}" if existing else ""
    if item.action == "replace_media":
        return "replaces current" if Path(item.destination).exists() else "slot is empty"
    if item.action in {"replace_b2s", "copy"} and Path(item.destination).exists():
        return "replaces existing file"
    return ""


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
                "label_key": f"asset.kind.{item.asset.kind}.label",
                "detail": item.asset.detail,
                "destination": item.destination,
                "action": item.action,
                "default_enabled": item.default_enabled,
                "size": item.asset.size,
                "media_kind": item.asset.media_kind,
                # What the file is called, and what it does to what is already there.
                # Both are answers about this machine's disk, so a caller cannot work
                # them out and would have to ask anyway.
                "name": _item_name(item),
                "replaces": _replaces(plan, item),
            }
            for index, item in enumerate(plan.items)
        ],
        "blocked": _blocked(plan),
    }


def _blocked(plan: ImportPlan) -> list[dict]:
    return [{"kind": one.asset.kind, "reason": one.reason} for one in plan.blocked]


def _session_dir(upload_id: str) -> Path:
    try:
        return upload_session_service.get_session_dir(upload_id)
    except UnknownSessionError as exc:
        raise service_errors.NotFoundError(str(exc)) from exc


def _analysis_for(upload_id: str) -> tuple[AnalysisResult, Path]:
    analysis, source_path = analyze_upload_session(_session_dir(upload_id))
    if analysis.error:
        raise UnprocessableUploadError(analysis.error)
    return analysis, source_path


def _vps_entry(vps_id: str) -> dict | None:
    vps_id = (vps_id or "").strip()
    if not vps_id:
        return None
    entry = find_vps_entry(vps_id)
    if entry is None:
        raise service_errors.RefusedError(
            t("error.uploads.unknown_vps_id", vps_id=(vps_id)))
    return entry


def begin() -> dict[str, Any]:
    return {"id": upload_session_service.begin_session().upload_id}


def summary(upload_id: str) -> dict[str, Any]:
    try:
        return upload_session_service.finish_session(upload_id)
    except UnknownSessionError as exc:
        raise service_errors.NotFoundError(str(exc)) from exc


def abort(upload_id: str) -> None:
    upload_session_service.cleanup_session(upload_id)


def add_file(upload_id: str, relpath: str, stream: IO[bytes]) -> dict[str, Any]:
    try:
        return {"bytes": upload_session_service.store_file(upload_id, relpath, stream)}
    except UnknownSessionError as exc:
        raise service_errors.NotFoundError(str(exc)) from exc
    except UnsafePathError as exc:
        raise service_errors.RefusedError(str(exc)) from exc


def analysis_of(upload_id: str) -> dict[str, Any]:
    analysis, _source = analyze_upload_session(_session_dir(upload_id))
    return _analysis_to_dict(analysis)


def _slot_plan(upload_id: str, game_dir: str, media_kind: str) -> ImportPlan:
    """A drop that named a slot, which decides the media key on its own.

    Nothing is read off the filename - any image works on an image slot and is written
    under that slot's own name. The file only has to belong to the slot's family, and one
    file only, because a slot holds one thing.
    """
    if not game_dir:
        raise service_errors.RefusedError(
            t("error.uploads.slot_import_needs_game"))
    session = _session_dir(upload_id)
    files = [one for one in session.iterdir() if one.is_file()]
    if [one for one in session.iterdir() if one.is_dir()] or len(files) != 1:
        raise service_errors.RefusedError(t("error.uploads.drop_single_file_slot"))
    try:
        return build_media_slot_plan(files[0], game_dir=Path(game_dir),
                                     media_kind=media_kind)
    except ValueError as exc:
        raise service_errors.RefusedError(str(exc)) from exc


def _built_plan(analysis: AnalysisResult, request: dict[str, Any]) -> ImportPlan:
    try:
        plan = build_import_plan(
            analysis,
            game_dir=Path(request["game_dir"]) if request.get("game_dir") else None,
            rom_name=request.get("rom_name") or "",
            allow_new_game=request.get("allow_new_game", False),
            location_id=request.get("location_id") or "",
        )
    except ValueError as exc:
        # Nowhere to put it. Something a person fixes - a share to mount, a location to
        # pick - so it is blocked rather than a fault.
        raise service_errors.BlockedError(str(exc)) from exc
    return only_kind(plan, request.get("asset_kind") or "")


def plan_for(upload_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """What the drop would do, before it does any of it."""
    if request.get("media_kind"):
        return _plan_to_dict(_slot_plan(upload_id, request.get("game_dir") or "",
                                        request["media_kind"]))
    analysis, _source = _analysis_for(upload_id)
    vps_entry = _vps_entry(request.get("vps_id") or "")
    plan = _built_plan(analysis, request)
    if vps_entry is not None and plan.new_game_dir_name:
        plan = select_plan_items(plan, None, vps_folder_name(vps_entry))
    return _plan_to_dict(plan)


def _declared_identities(declared: Mapping[str, Any] | None) -> dict:
    """Turn the caller's declared identities into the vocabulary the writer speaks.

    Rejected here rather than recorded and regretted: a claim that names an upstream
    record without saying how it is known, or that sends a basis outside the closed set,
    is a caller asserting a confidence it has not earned.
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
        raise service_errors.RefusedError("; ".join(problems))
    return out


def _run(plan: ImportPlan, source: Path, declared: dict,
         upload_id: str) -> dict[str, Any]:
    blocked = _blocked(plan)
    if not plan.items:
        raise NothingImportableError(t("error.uploads.no_importable_assets"),
                                     details={"blocked": blocked})
    try:
        report = execute_import_plan(plan, source, declared=declared)
    except (ValueError, FileNotFoundError) as exc:
        raise service_errors.RefusedError(str(exc)) from exc
    upload_session_service.cleanup_session(upload_id)
    report["blocked"] = blocked
    return report


def execute(upload_id: str, request: dict[str, Any],
            declared: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Bring the session into the library, and clear it."""
    # Before the session is even looked up: a claim we cannot trust is a bad request
    # whichever upload it names, and saying so early keeps the reason readable.
    identities = _declared_identities(declared)

    if request.get("media_kind"):
        # A slot import has one file and no choice to make about it: the slot decided the
        # destination, so there is nothing to select from and nothing to name.
        plan = _slot_plan(upload_id, request.get("game_dir") or "",
                          request["media_kind"])
        source = next(one for one in _session_dir(upload_id).iterdir() if one.is_file())
        return _run(plan, source, identities, upload_id)

    analysis, source_path = _analysis_for(upload_id)
    vps_entry = _vps_entry(request.get("vps_id") or "")
    plan = _built_plan(analysis, request)
    if vps_entry is not None and not plan.new_game_dir_name:
        raise service_errors.RefusedError(t("error.uploads.vps_id_applies_new"))

    # Folder naming precedence: explicit new_game_dir_name > VPS-derived > vpx stem.
    new_name = request.get("new_game_dir_name")
    if new_name is None and vps_entry is not None:
        new_name = vps_folder_name(vps_entry)
    try:
        plan = select_plan_items(plan, request.get("selected"), new_name)
    except ValueError as exc:
        raise service_errors.RefusedError(str(exc)) from exc

    report = _run(plan, source_path, identities, upload_id)
    if vps_entry is not None and report.get("new_game"):
        _associate(report, vps_entry)
    return report


def _associate(report: dict, vps_entry: dict) -> None:
    """Files are on disk; association failure is reported, not fatal."""
    import logging

    from common.games.game_service import associate_vps_to_folder, build_metadata

    try:
        associate_vps_to_folder(Path(report["game_dir"]), vps_entry, True)
        build_metadata(download_media=True, update_all=True,
                       game_name=Path(report["game_dir"]).name)
        report["vps_associated"] = True
    except Exception as exc:
        logging.getLogger("vpinfe.common.uploads.upload_ops").exception(
            "VPS association failed after import")
        report["vps_associated"] = False
        report["vps_error"] = str(exc)
