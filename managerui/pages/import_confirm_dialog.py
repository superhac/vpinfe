from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable

from nicegui import context, run, ui

from managerui.services import table_service, upload_session_service
from managerui.services.asset_analyzer_service import AnalysisResult
from managerui.services.asset_import_service import (
    ImportPlan,
    execute_import_plan,
    find_vps_entry,
    select_plan_items,
    vps_folder_name,
)
from managerui.services.asset_registry import spec_for
from managerui.services.media_service import MEDIA_TYPES, invalidate_media_cache
from managerui.ui_helpers import debounced_input, dialog_card


logger = logging.getLogger("vpinfe.manager.dnd_ui")

_MEDIA_LABELS = {key: label for key, label, _ in MEDIA_TYPES}

_CHIP_STYLE = ("font-size: 11px; letter-spacing: 0.04em; color: var(--neon-purple); "
               "border: 1px solid var(--line); border-radius: 10px; padding: 1px 6px; "
               "width: 112px; text-align: center; flex: none; overflow: hidden; "
               "text-overflow: ellipsis; white-space: nowrap;")


def _chip_label(asset) -> str:
    if asset.kind != "media":
        return spec_for(asset.kind).label
    label = _MEDIA_LABELS.get(asset.media_key, asset.media_key)
    if asset.media_key == "audio" or "Video" in label:
        return label
    return f"{label} image"


def _vps_search_term(name: str) -> str:
    """Reduce a vpx-derived name to a searchable VPS term (drop parenthetical/version tail)."""
    term = (name or "").split("(")[0].strip()
    return term or (name or "").strip()


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def open_import_confirm_dialog(analysis: AnalysisResult, plan: ImportPlan, source_path: Path,
                               upload_id: str, on_imported: Callable[[dict], None] | None,
                               display_name: str = "", refresh_media_cache: bool = True) -> None:
    """Confirm and execute an import plan, showing detected assets and their destinations."""
    state = {"busy": False, "client": context.client}
    checks: dict[int, ui.checkbox] = {}
    name_input = None
    vps_state = {"entry": None, "name_dirty": False, "last_set": ""}
    title_source = display_name or analysis.source_name
    single = len(plan.items) == 1 and not plan.blocked

    def _row_primary(item) -> str:
        entries = [e for e in item.asset.entries if not e.is_dir]
        if len(entries) == 1:
            return Path(entries[0].arcname).name
        return f"{len(entries)} files"

    def _row_destination(item) -> str:
        # Relative to the table folder; the folder itself is stated by the title/name field.
        base = Path(plan.table_path)
        dest = Path(item.destination)
        try:
            rel = dest.relative_to(base)
        except ValueError:
            return item.destination
        if item.action == "extract_tree":
            return f"{rel.as_posix()}/"
        if item.action == "replace_media":
            return rel.as_posix()   # canonical name is the point (wheel.png, bg.mp4, ...)
        if str(rel.parent) == ".":
            return "table folder root"
        if rel.name == _row_primary(item):
            return f"{rel.parent.as_posix()}/"
        return rel.as_posix()

    def _replace_note(item) -> str:
        if item.action == "write_info":
            if plan.new_table_dir_name:
                return "adopts bundle metadata"
            if Path(plan.table_path, f"{Path(plan.table_path).name}.info").exists():
                return "merges into existing metadata — fills gaps only · backup kept"
            return "adopts bundle metadata"
        if plan.new_table_dir_name:
            return ""   # brand-new folder; nothing can be replaced
        base = Path(plan.table_path)
        if item.action == "replace_vpx":
            existing = sorted(base.glob("*.vpx"))
            if existing:
                return f"replaces {existing[0].name}"
            return ""
        if item.action == "replace_media":
            return "replaces current" if Path(item.destination).exists() else "slot is empty"
        if item.action in {"replace_b2s", "copy"} and Path(item.destination).exists():
            return "replaces existing file"
        return ""

    dlg = ui.dialog().props("persistent")
    with dlg, dialog_card("640px"):
        if plan.new_table_dir_name:
            ui.label(f"Import from {title_source}").classes("text-lg font-bold").style("color: var(--ink);")
            ui.label("Files keep their names — only the folder is named here").classes(
                "text-xs").style("color: var(--ink-muted);")
        else:
            ui.label(f"Import to {Path(plan.table_path).name}").classes("text-lg font-bold").style("color: var(--ink);")
            if not single:
                ui.label(f"from {title_source}").classes("text-xs").style("color: var(--ink-muted);")

        if plan.new_table_dir_name:
            name_input = ui.input("New table folder", value=plan.new_table_dir_name).props("outlined dense").classes("w-full")

            def _on_name_edit(e) -> None:
                value = e.args if isinstance(e.args, str) else name_input.value
                # set_value round-trips through the client, so compare against the
                # last programmatic value instead of using a synchronous flag.
                if value != vps_state.get("last_set"):
                    vps_state["name_dirty"] = True

            vps_state["last_set"] = plan.new_table_dir_name
            name_input.on("update:model-value", _on_name_edit)

            with ui.row().classes("items-center gap-2 w-full no-wrap"):
                ui.icon("travel_explore").style("color: var(--neon-purple);")
                vps_label = ui.label("No VPS association — naming from file").style("color: var(--ink-muted);")
                vps_label.tooltip("Link this table to its Virtual Pinball Spreadsheet entry to name the "
                                  "folder canonically and download its media and metadata.")
                ui.space()
                vps_change_btn = ui.button("Search VPS").props("flat dense").style("color: var(--neon-cyan);")
                vps_clear_btn = ui.button(icon="close").props("flat dense round").style("color: var(--ink-muted);")
                vps_clear_btn.visible = False

            def _set_name(value: str) -> None:
                vps_state["last_set"] = value
                name_input.set_value(value)

            def _set_association(entry: dict | None) -> None:
                vps_state["entry"] = entry
                if entry is None:
                    vps_label.set_text("No VPS association — naming from file")
                    vps_label.style("color: var(--ink-muted);")
                    vps_clear_btn.visible = False
                    if not vps_state["name_dirty"]:
                        _set_name(plan.new_table_dir_name)
                    return
                label = vps_folder_name(entry) or entry.get("name", "")
                vps_label.set_text(f"VPS: {label}")
                vps_label.style("color: var(--ink);")
                vps_clear_btn.visible = True
                if not vps_state["name_dirty"]:
                    _set_name(vps_folder_name(entry))

            def _open_vps_picker() -> None:
                picker = ui.dialog()
                with picker, dialog_card("560px"):
                    ui.label("Select VPS entry").classes("text-lg font-bold").style("color: var(--ink);")
                    search_input = ui.input("Search", value=_vps_search_term(plan.new_table_dir_name)).props(
                        "outlined dense clearable").classes("w-full")
                    results_column = ui.column().classes("w-full gap-1").style("max-height: 320px; overflow-y: auto;")

                    def _render_results(entries: list[dict]) -> None:
                        results_column.clear()
                        with results_column:
                            if not entries:
                                ui.label("No matches").classes("text-sm").style("color: var(--ink-muted);")
                            for entry in entries:
                                def _choose(entry=entry) -> None:
                                    _set_association(entry)
                                    picker.close()
                                label = f"{entry.get('name', '')} ({entry.get('manufacturer', '?')} {entry.get('year', '?')})"
                                ui.button(label, on_click=_choose).props("flat align=left no-caps").classes(
                                    "w-full").style("color: var(--ink);")

                    async def _do_search() -> None:
                        entries = await run.io_bound(table_service.search_vpsdb, search_input.value or "", 20)
                        _render_results(entries)

                    debounced_input(search_input, 300)
                    search_input.on("update:model-value", lambda _e: asyncio.create_task(_do_search()))
                    asyncio.create_task(_do_search())
                picker.open()

            vps_change_btn.on_click(_open_vps_picker)
            vps_clear_btn.on_click(lambda: _set_association(None))

            async def _auto_associate() -> None:
                # A bundle .info with a resolvable VPS id is more authoritative than
                # filename guessing — seed the association from it and stop there.
                bundle_vps_id = ((analysis.bundle_info or {}).get("Info") or {}).get("VPSId", "")
                if bundle_vps_id:
                    entry = await run.io_bound(find_vps_entry, str(bundle_vps_id))
                    if entry is not None:
                        if vps_state["entry"] is None:
                            with state["client"]:
                                _set_association(entry)
                        return
                term = _vps_search_term(plan.new_table_dir_name)
                if not term:
                    return
                # vpx names often carry author/version tails ("Medieval Madness VPW v2"),
                # so retry with trailing words dropped until something matches.
                words = term.split()
                for count in range(len(words), 0, -1):
                    candidate = " ".join(words[:count])
                    entries = await run.io_bound(table_service.search_vpsdb, candidate, 5)
                    if entries:
                        if vps_state["entry"] is None:
                            with state["client"]:
                                _set_association(entries[0])
                        return

            asyncio.create_task(_auto_associate())

        with ui.column().classes("w-full gap-0 q-mt-sm"):
            for index, item in enumerate(plan.items):
                with ui.row().classes("items-center gap-2 w-full no-wrap").style(
                        "border-top: 1px solid var(--line); padding: 6px 0; min-width: 0;"):
                    if not single:
                        checks[index] = ui.checkbox(value=item.default_enabled).props("dense")
                    ui.label(_chip_label(item.asset)).style(_CHIP_STYLE)
                    with ui.column().classes("gap-0").style("flex: 1; min-width: 0;"):
                        ui.label(_row_primary(item)).classes("w-full truncate").style("color: var(--ink);")
                        note = _replace_note(item)
                        dest_text = f"→ {_row_destination(item)}" + (f"  ·  {note}" if note else "")
                        ui.label(dest_text).classes("text-xs w-full truncate").style(
                            "color: var(--ink-muted); font-family: monospace;")
                    if item.asset.size:
                        ui.label(_human_size(item.asset.size)).classes("text-xs").style(
                            "color: var(--ink-muted); flex: none;")

            for blocked in plan.blocked:
                with ui.row().classes("items-center gap-2 w-full no-wrap").style(
                        "border-top: 1px solid var(--line); padding: 6px 0; min-width: 0; opacity: 0.55;"):
                    ui.icon("block").style("color: var(--ink-muted); flex: none;")
                    ui.label(_chip_label(blocked.asset)).style(_CHIP_STYLE)
                    with ui.column().classes("gap-0").style("flex: 1; min-width: 0;"):
                        ui.label(_row_primary(blocked)).classes("w-full truncate").style("color: var(--ink-muted);")
                        ui.label(blocked.reason).classes("text-xs w-full truncate").style("color: var(--ink-muted);")

        for note in analysis.notes:
            ui.label(note).classes("text-xs").style("color: var(--ink-muted);")

        if analysis.unrecognized:
            count = len(analysis.unrecognized)
            with ui.expansion(f"{count} file{'s' if count != 1 else ''} won't be imported").props(
                    "dense").classes("w-full").style("color: var(--ink-muted); font-size: 13px;"):
                with ui.column().classes("gap-0 pl-4").style("max-height: 140px; overflow-y: auto;"):
                    for name in analysis.unrecognized:
                        ui.label(name).classes("text-xs").style(
                            "color: var(--ink-muted); font-family: monospace;")

        loading_overlay = ui.element("div").style(
            "position: absolute; top: 0; left: 0; right: 0; bottom: 0; "
            "background: var(--bg); opacity: 0.9; z-index: 1000; "
            "display: none; flex-direction: column; align-items: center; justify-content: center;"
        )
        with loading_overlay:
            with ui.column().classes("items-center justify-center gap-4 w-full"):
                ui.spinner("dots", size="xl", color="purple")
                loading_label = ui.label("Importing...").classes("text-lg text-center").style("color: var(--ink);")

        ui.separator()
        with ui.row().classes("justify-end gap-2 w-full"):
            def _cancel() -> None:
                dlg.close()
                upload_session_service.cleanup_session(upload_id)

            ui.button("Cancel", on_click=_cancel).props("flat").style("color: var(--ink-muted);")

            def _import_label() -> str:
                if single:
                    return "Import"
                count = sum(1 for check in checks.values() if check.value)
                return f"Import {count} item{'s' if count != 1 else ''}"

            import_btn = ui.button(_import_label(), icon="download").style(
                "color: var(--neon-cyan) !important; background: var(--surface) !important; "
                "border: 1px solid var(--neon-cyan) !important; border-radius: 18px; padding: 4px 10px;"
            )
            for check in checks.values():
                check.on_value_change(lambda _e: import_btn.set_text(_import_label()))

    def _resolved_plan() -> ImportPlan:
        indices = None if single else [index for index in range(len(plan.items)) if checks[index].value]
        new_name = name_input.value if name_input else None
        return select_plan_items(plan, indices, new_name)

    async def do_import() -> None:
        if state["busy"]:
            return
        if not single and not any(check.value for check in checks.values()):
            ui.notify("Select at least one item to import", type="warning")
            return
        state["busy"] = True
        client = state["client"]
        with client:
            loading_overlay.style(add="display: flex;", remove="display: none;")
            loading_label.set_text("Importing...")
            import_btn.disable()
        try:
            resolved = _resolved_plan()
            report = await run.io_bound(execute_import_plan, resolved, source_path)
            vps_entry = vps_state["entry"]
            if vps_entry is not None and report.get("new_table"):
                with client:
                    loading_label.set_text("Associating with VPS and downloading media...")
                try:
                    await run.io_bound(table_service.associate_vps_to_folder,
                                       Path(report["table_path"]), vps_entry, True)
                    await run.io_bound(table_service.build_metadata, downloadMedia=True,
                                       updateAll=True, tableName=resolved.new_table_dir_name)
                except Exception:
                    # The files are already imported; a failed association must not read as a failed import.
                    logger.exception("VPS association failed after import")
                    with client:
                        ui.notify("Imported, but VPS association failed", type="warning")
            with client:
                if refresh_media_cache:
                    invalidate_media_cache()
                ui.notify(f"Imported {len(report['imported'])} item(s)", type="positive")
            dlg.close()
            upload_session_service.cleanup_session(upload_id)
            if on_imported:
                on_imported(report)
        except Exception as ex:
            logger.exception("Import failed")
            with client:
                ui.notify(f"Import failed: {ex}", type="negative")
        finally:
            state["busy"] = False
            with client:
                loading_overlay.style(add="display: none;", remove="display: flex;")
                import_btn.enable()

    import_btn.on_click(lambda: asyncio.create_task(do_import()))
    dlg.open()
