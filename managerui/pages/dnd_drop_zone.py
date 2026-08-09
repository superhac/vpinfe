"""The drop target itself - what the browser hands us when a file is dragged in."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from nicegui import context, run, ui

from common.games import identity_claims
from common.uploads import upload_session_service
from common.uploads.asset_analyzer_service import AnalysisResult, analyze_upload_session
from common.uploads.asset_import_service import build_import_plan, build_media_slot_plan
from managerui.pages.import_confirm_dialog import open_import_confirm_dialog

logger = logging.getLogger("vpinfe.manager.dnd_ui")

_script_clients: set[str] = set()


@dataclass(frozen=True)
class DropContext:
    game_path: str = ""
    game_row: dict | None = None
    rom_name: str = ""
    allow_new_game: bool = False


_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _asset_version(filename: str) -> int:
    """File mtime as a cache-busting query value, so browsers pick up updated assets."""
    try:
        return int((_STATIC_DIR / filename).stat().st_mtime)
    except OSError:
        return 0


def _ensure_assets() -> None:
    ui.add_head_html(
        f'<link rel="stylesheet" href="/static/dnd_upload.css?v={_asset_version("dnd_upload.css")}">')
    client_id = context.client.id
    if client_id not in _script_clients:
        ui.add_head_html(
            f'<script src="/static/dnd_upload.js?v={_asset_version("dnd_upload.js")}"></script>')
        _script_clients.add(client_id)


def _declared_for(game_path: str, filenames) -> dict:
    """What a drop says about the files it carried.

    The gesture is the declaration: letting go on a game row names that game, and on a
    media slot the kind as well. A person chose the target, so the basis is `user` - not
    `declared`, which is reserved for something that fetched the file from a named record
    and therefore witnessed the identity rather than deciding it.

    No upstream record is named here, so nothing enters the `.info` claiming to be a VPS
    file. That binding only arrives from a client that actually fetched one.
    """
    game_id = _game_id_for(game_path)
    if not game_id:
        return {}
    identity = identity_claims.DeclaredIdentity(
        game_id=game_id, host="user", confirmed_by=identity_claims.USER)
    return {name: identity for name in filenames}


def _game_id_for(game_path: str) -> str:
    """The game's own id, read off the folder it was dropped on."""
    if not game_path:
        return ""
    try:
        from common.games.game_metadata import vpinfe_section
        from common.games.info_file import GAME_ID_KEY, MetaConfig
        folder = Path(game_path)
        info = folder / f"{folder.name}.info"
        if not info.exists():
            return ""
        return str(vpinfe_section(MetaConfig(str(info)).data).get(GAME_ID_KEY, "") or "")
    except Exception:
        logger.debug("Could not read a game id for %s", game_path, exc_info=True)
        return ""


def create_drop_zone(*, label: str, get_context: Callable[[], DropContext],
                     on_imported: Callable[[dict], None] | None = None,
                     visible: bool = True) -> ui.element:
    """Render a drag/drop target that analyzes dropped assets and opens an import dialog.

    With visible=False the zone renders hidden and only hosts the event plumbing —
    used by pages whose real drop targets are rows or cells (see enable_row_drops /
    enable_cell_drops).
    """
    _ensure_assets()
    token = uuid4().hex[:12]
    state = {"busy": False, "client": context.client}

    zone = ui.element("div").classes(f"dnd-drop-zone vpinfe-dnd-{token}")
    if not visible:
        zone.style("display: none;")
    with zone:
        ui.icon("cloud_upload").classes("dnd-drop-zone__icon")
        status_label = ui.label(label).style("color: inherit;")

    async def handle_done(upload_id: str, display_name: str, row_key: str = "",
                          cell_row: str = "", cell_media_key: str = "") -> None:
        if state["busy"]:
            return
        state["busy"] = True
        client = state["client"]
        try:
            session_dir = upload_session_service.get_session_dir(upload_id)

            cell_resolver = state.get("resolve_cell")
            if cell_row and cell_media_key and cell_resolver is not None:
                # Slot-targeted drop: the cell dictates game and media key; no analysis.
                game_path = cell_resolver(cell_row)
                files = [p for p in session_dir.iterdir() if p.is_file()]
                dirs = [p for p in session_dir.iterdir() if p.is_dir()]
                with client:
                    if not game_path:
                        ui.notify("Could not resolve the drop target table", type="negative")
                        upload_session_service.cleanup_session(upload_id)
                        return
                    if dirs or len(files) != 1:
                        ui.notify("Drop a single media file on a slot", type="warning")
                        upload_session_service.cleanup_session(upload_id)
                        return
                    plan = build_media_slot_plan(files[0], game_path=game_path,
                                                 media_key=cell_media_key)
                    if not plan.items:
                        reasons = "; ".join(sorted({b.reason for b in plan.blocked})) or "Nothing to import"
                        ui.notify(reasons, type="warning")
                        upload_session_service.cleanup_session(upload_id)
                        return
                    cell_analysis = AnalysisResult("file", files[0].name, (), False)
                    open_import_confirm_dialog(
                        cell_analysis, plan, files[0], upload_id, on_imported,
                        refresh_media_cache=False,
                        declared=_declared_for(game_path, {files[0].name}))
                return

            analysis, source_path = await run.io_bound(analyze_upload_session, session_dir)
            resolver = state.get("resolve_row")
            if row_key and resolver is not None:
                # A drop on a row targets that row's game, regardless of selection.
                ctx = resolver(row_key)
                if ctx is None:
                    with client:
                        ui.notify("Could not resolve the drop target table", type="negative")
                    upload_session_service.cleanup_session(upload_id)
                    return
            else:
                ctx = get_context()
            with client:
                status_label.set_text(label)
                if analysis.error:
                    ui.notify(f"Could not import: {analysis.error}", type="negative")
                    upload_session_service.cleanup_session(upload_id)
                    return
                plan = build_import_plan(
                    analysis,
                    game_path=ctx.game_path,
                    game_row=ctx.game_row,
                    rom_name=ctx.rom_name,
                    allow_new_game=ctx.allow_new_game,
                )
                if not plan.items:
                    reasons = "; ".join(sorted({b.reason for b in plan.blocked})) or "Nothing to import"
                    ui.notify(reasons, type="warning")
                    upload_session_service.cleanup_session(upload_id)
                    return
                # A drop on a row names that game; a drop on the page names nothing, and
                # nothing is what gets declared - an unclaimed file joins the manual queue
                # rather than entering the record on a guess.
                names = {entry.path.rsplit("/", 1)[-1]
                         for asset in analysis.assets for entry in asset.entries}
                open_import_confirm_dialog(
                    analysis, plan, source_path, upload_id, on_imported,
                    display_name=display_name,
                    declared=_declared_for(ctx.game_path if row_key else "", names))
        except Exception:
            logger.exception("Drag/drop analysis failed")
            with client:
                ui.notify("Drag/drop analysis failed", type="negative")
            upload_session_service.cleanup_session(upload_id)
        finally:
            state["busy"] = False

    def on_event(event) -> None:
        payload = event.args or {}
        if payload.get("token") != token:
            return
        status = payload.get("status")
        if status == "progress":
            total = payload.get("total") or 0
            done = payload.get("done") or 0
            name = payload.get("name") or ""
            if total:
                status_label.set_text(f"Uploading {done}/{total}… {name}")
        elif status == "done":
            asyncio.create_task(handle_done(payload.get("upload_id"), payload.get("name") or "",
                                            payload.get("row_key") or "",
                                            payload.get("cell_row") or "",
                                            payload.get("cell_media_key") or ""))
        elif status == "error":
            status_label.set_text(label)
            ui.notify(f"Upload failed: {payload.get('message', '')}", type="negative")

    ui.on("vpinfe_dnd", on_event)
    # The static script auto-attaches drop zones via a MutationObserver, so no
    # server-side timer is needed (and none can outlive a client reconnect).
    zone.dnd_token = token
    zone.dnd_state = state
    return zone


def enable_row_drops(zone: ui.element, container: ui.element,
                     resolve_row_context: Callable[[str], DropContext | None]) -> None:
    """Make rows inside container individual drop targets for an existing zone.

    Rows must carry a data-drop-table-id attribute; a drop on a row resolves its
    DropContext via resolve_row_context (the row under the cursor always wins over
    any checked selection).
    """
    zone.dnd_state["resolve_row"] = resolve_row_context
    container.classes(f"vpinfe-dnd-rows-{zone.dnd_token}")


def enable_cell_drops(zone: ui.element, container: ui.element,
                      resolve_game_path: Callable[[str], str | None]) -> None:
    """Make media cells inside container slot-targeted drop targets.

    Cells must carry data-drop-media-key and data-drop-media-row attributes; the cell
    dictates both the target game (resolved via resolve_game_path) and the media slot.
    """
    zone.dnd_state["resolve_cell"] = resolve_game_path
    container.classes(f"vpinfe-dnd-cells-{zone.dnd_token}")
