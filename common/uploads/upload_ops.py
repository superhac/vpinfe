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

from common import media_browse, service_errors
from common.failures import why
from common.games import identity_claims, media_placement, media_service
from common.games.asset_registry import spec_for
from common.games.game_metadata import made_from
from common.games.table_lens import table_settings
from common.i18n import t
from common.uploads import upload_session_service
from common.uploads.asset_analyzer_service import (
    AnalysisResult,
    DetectedAsset,
    analyze_path,
    analyze_upload_session,
)
from common.uploads.asset_import_service import (
    ImportPlan,
    PlannedItem,
    build_import_plan,
    build_media_slot_plan,
    build_readme_plan,
    execute_import_plan,
    find_vps_entry,
    only_kind,
    replaced_table,
    select_plan_items,
    vps_folder_name,
)
from common.uploads.upload_session_service import (
    UnknownSessionError,
    UnsafePathError,
    UploadTooLargeError,
)

__all__ = ["NothingImportableError", "UnprocessableUploadError", "UploadTooLargeError",
           "abort", "add_file", "analysis_of", "begin", "begin_from", "execute", "plan_for",
           "summary"]


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
    return t("asset.analysis.files", count=len(entries))


def _replaces(plan: ImportPlan, item: PlannedItem) -> str:
    """What this item does to whatever is already there, said before it happens.

    Asked of the disk, so it belongs on this side: a caller cannot see the install's
    folders, and "will this overwrite something" is the question somebody is actually
    answering when they confirm.
    """
    if item.action == "write_info":
        if plan.new_game_dir_name:
            return t("asset.plan.adopts_info")
        base = Path(plan.game_dir)
        if (base / f"{base.name}.info").exists():
            return t("asset.plan.merges_info")
        return t("asset.plan.adopts_info")
    if plan.new_game_dir_name:
        return ""   # a folder that does not exist yet has nothing to replace
    base = Path(plan.game_dir)
    if item.action == "replace_vpx":
        replaced = replaced_table(base)
        return t("asset.plan.replaces_named", name=replaced.name) if replaced else ""
    if item.action == "replace_media":
        return _media_replaces(base, item)
    if item.action in {"replace_b2s", "copy"} and Path(item.destination).exists():
        return t("asset.plan.replaces_file")
    return ""


def _media_replaces(base: Path, item: PlannedItem) -> str:
    kind = item.asset.media_kind
    if media_placement.displaced(base, kind, base.name, Path(item.destination).suffix):
        return t("asset.plan.replaces_current")
    shown = media_service.resolved_media(base).get(kind)
    if shown is None or shown.path is None:
        return t("asset.plan.slot_empty")
    return ""


def _made_from_replaced(plan: ImportPlan, item: PlannedItem) -> list[str]:
    """The tables a patch made from the file this item deletes, by filename."""
    if item.action != "replace_vpx" or plan.new_game_dir_name:
        return []
    game_dir = Path(plan.game_dir)
    replaced = replaced_table(game_dir)
    return made_from(table_settings(game_dir), replaced.name) if replaced else []


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
                "made_from_it": _made_from_replaced(plan, item),
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
    analysis, source_path = _analyzed(upload_id)
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


def begin_from(path: str) -> dict[str, Any]:
    """A session over a file, a folder or an archive already on this machine, bounded the
    way browsing is."""
    source = media_browse.within_roots(path)
    if not source.exists():
        raise service_errors.RefusedError(t("error.filesystem.nothing_there"),
                                          details={"path": path})
    return {"id": upload_session_service.begin_session(source=source).upload_id}


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


def _source_of(upload_id: str) -> Path | None:
    try:
        return upload_session_service.get_session_source(upload_id)
    except UnknownSessionError as exc:
        raise service_errors.NotFoundError(str(exc)) from exc


def _analyzed(upload_id: str) -> tuple[AnalysisResult, Path]:
    source = _source_of(upload_id)
    if source is not None:
        return analyze_path(source), source
    return analyze_upload_session(_session_dir(upload_id))


def _single_file(upload_id: str) -> Path:
    """The one file a slot import takes, or a refusal."""
    source = _source_of(upload_id)
    if source is not None:
        files = [source] if source.is_file() else []
    else:
        session = _session_dir(upload_id)
        if any(one.is_dir() for one in session.iterdir()):
            files = []
        else:
            files = [one for one in session.iterdir() if one.is_file()]
    if len(files) != 1:
        raise service_errors.RefusedError(t("error.uploads.drop_single_file_slot"))
    return files[0]


def analysis_of(upload_id: str) -> dict[str, Any]:
    analysis, _source = _analyzed(upload_id)
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
    try:
        return build_media_slot_plan(_single_file(upload_id), game_dir=Path(game_dir),
                                     media_kind=media_kind)
    except ValueError as exc:
        raise service_errors.RefusedError(str(exc)) from exc


def _named_plan(upload_id: str, request: dict[str, Any]) -> ImportPlan | None:
    """The plan for a drop whose one file the sender has already named, or None where
    the analysis decides what arrived."""
    game_dir = request.get("game_dir") or ""
    if request.get("media_kind"):
        return _slot_plan(upload_id, game_dir, request["media_kind"])
    if request.get("asset_kind") != "readme":
        return None
    if not game_dir:
        raise service_errors.RefusedError(t("error.uploads.slot_import_needs_game"))
    return build_readme_plan(_single_file(upload_id), game_dir=Path(game_dir))


def _built_plan(analysis: AnalysisResult, request: dict[str, Any]) -> ImportPlan:
    try:
        plan = build_import_plan(
            analysis,
            game_dir=Path(request["game_dir"]) if request.get("game_dir") else None,
            rom_name=request.get("rom_name") or "",
            allow_new_game=request.get("allow_new_game", False),
            location_id=request.get("location_id") or "",
            add_table=bool(request.get("add_table")),
        )
    except ValueError as exc:
        # Nowhere to put it. Something a person fixes - a share to mount, a location to
        # pick - so it is blocked rather than a fault.
        raise service_errors.BlockedError(str(exc)) from exc
    return only_kind(plan, request.get("asset_kind") or "")


def plan_for(upload_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """What the drop would do, before it does any of it."""
    named = _named_plan(upload_id, request)
    if named is not None:
        return _plan_to_dict(named)
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
    out, refused = {}, []
    for name, sent in declared.items():
        identity = identity_claims.DeclaredIdentity(
            vps_file_id=sent.vps_file_id, host_item_id=sent.host_item_id,
            host=sent.host, game_id=sent.game_id, table_id=sent.table_id,
            confirmed_by=sent.confirmed_by)
        refused += [{"file": name, "why": why} for why in identity.problems()]
        out[name] = identity
    if refused:
        first = refused[0]
        raise service_errors.RefusedError(
            t("error.uploads.declared_identity_refused", file=first["file"], why=first["why"]),
            details={"refused": refused})
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

    named = _named_plan(upload_id, request)
    if named is not None:
        # A slot import has one file and no choice to make about it: the slot decided the
        # destination, so there is nothing to select from and nothing to name.
        return _run(named, _single_file(upload_id), identities, upload_id)

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
    if report.get("new_game"):
        if vps_entry is not None:
            _associate(report, vps_entry)
        else:
            _guess(report)
    return report


def _guess(report: dict) -> None:
    """Match a new game nobody picked an entry for, from its folder name. Offline, and
    never fatal: the files are on disk whatever this finds."""
    import logging

    from common.games import auto_match, media_fill
    from common.games.game import Game
    from common.games.game_metadata import load_game_meta
    from common.games.game_repository import refresh_game

    game_dir = Path(report["game_dir"])
    game = Game(game_dir_name=game_dir.name, full_path_game=str(game_dir))
    try:
        game.meta_config = load_game_meta(game)
        report["vps_matched"] = auto_match.match_new([game])["matched"] > 0
        refresh_game(game_dir)
        if report["vps_matched"]:
            media_fill.request([game_dir])
    except Exception:
        logging.getLogger("vpinfe.common.uploads.upload_ops").exception(
            "Matching the new game failed after import")
        report["vps_matched"] = False


def _associate(report: dict, vps_entry: dict) -> None:
    """Files are on disk; association failure is reported, not fatal."""
    import logging

    from common.games import media_fill
    from common.games.game_metadata import MATCHED_ON_IMPORT
    from common.games.game_service import associate_vps_to_folder

    try:
        associate_vps_to_folder(Path(report["game_dir"]), vps_entry, False,
                                matched_by=MATCHED_ON_IMPORT)
        report["vps_associated"] = True
        media_fill.request([report["game_dir"]])
    except FileNotFoundError as exc:
        report["vps_associated"] = False
        report["vps_error"] = why(exc)
    except Exception:
        logging.getLogger("vpinfe.common.uploads.upload_ops").exception(
            "VPS association failed after import")
        report["vps_associated"] = False
        report["vps_error"] = t("error.uploads.log_says_why")
