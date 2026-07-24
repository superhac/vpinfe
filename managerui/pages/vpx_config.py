from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from nicegui import ui

from common.iniconfig import IniConfig
from managerui.paths import CONFIG_DIR, VPINFE_INI_PATH
from managerui.services import vpx_config_service
from managerui.services.vpx_config_service import FieldMeta, ParsedIni, SectionMeta
from managerui.ui_helpers import load_page_style, attach_shell_save_bar


logger = logging.getLogger("vpinfe.manager.vpx_config")

VPX_BACKUP_DIR = vpx_config_service.VPX_BACKUP_DIR

EDITOR_INCLUDED_KEYS = [
    "EnableLog",
    "ThrowBallsAlwaysOn",
    "BallControlAlwaysOn",
    "LogScriptOutput",
]

EDITOR_FALLBACK_COMMENTS = {
    "EnableLog": "Enable Log: Enable general logging to the vinball.log file [Default: 1]",
    "ThrowBallsAlwaysOn": "Throw Balls Always On: Permanently enable 'throw ball' debugging mode [Default: 0]",
    "BallControlAlwaysOn": "Ball Control Always On: Permanently enable 'ball control' debugging mode [Default: 0]",
    "LogScriptOutput": "LogScriptOutput: Enable script logging output [Default: 1]",
}

KEEP_ALL_SECTIONS = {
    "Editor",
    "Player",
    "Backglass",
    "ScoreView",
    "Topper",
    "PlayerVR",
    "DefaultCamera",
    "TableOverride",
    "Input",
    "DMD",
    "Alpha",
    "Controller",
    "Standalone",
    "TableOption",
}

SECTION_DESCRIPTIONS = {
    "Editor": "Editor debugging, layout, and appearance settings from VPinballX.ini.",
    "Player": "Runtime audio, display, physics, and table player settings.",
    "Backglass": "Backglass output and positioning settings.",
    "ScoreView": "ScoreView window and rendering settings.",
    "Topper": "Topper output and placement settings.",
    "PlayerVR": "VR preview, table placement, and headset rendering settings.",
    "DefaultCamera": "Default desktop and full single-screen camera settings.",
    "TableOverride": "Global table view, difficulty, exposure, and tone mapping overrides.",
    "Input": "Input, controller, keyboard, and nudge settings.",
    "DMD": "DMD rendering and layout settings.",
    "Alpha": "Alpha-numeric display rendering settings.",
    "Controller": "Controller integrations and external system settings.",
    "Standalone": "Standalone VPX runtime behavior and Linux cabinet integration settings.",
    "TableOption": "Table script options saved by VPX tables.",
}

SECTION_ICONS = {
    "Editor": "edit_note",
    "Player": "sports_esports",
    "Backglass": "tv",
    "ScoreView": "scoreboard",
    "Topper": "view_day",
    "PlayerVR": "view_in_ar",
    "DefaultCamera": "photo_camera",
    "TableOverride": "tune",
    "Input": "keyboard",
    "DMD": "developer_board",
    "Alpha": "text_fields",
    "Controller": "gamepad",
    "Standalone": "terminal",
    "TableOption": "rule",
}


def _load_vpx_ini_path() -> Path | None:
    try:
        return vpx_config_service.load_vpx_ini_path()
    except Exception:
        logger.exception("Failed to read vpxinipath from vpinfe.ini")
        return None


_parse_comment_details = vpx_config_service.parse_comment_details
_parse_ini = vpx_config_service.parse_ini


def _build_display_sections(parsed: ParsedIni) -> list[dict]:
    display_sections: list[dict] = []

    for section_name in parsed.section_order:
        section_meta = parsed.sections[section_name]

        if section_name == "Editor":
            fields: list[FieldMeta] = list(section_meta.fields.values())
            for key in EDITOR_INCLUDED_KEYS:
                existing = section_meta.fields.get(key.lower())
                if existing is not None:
                    continue

                fallback = EDITOR_FALLBACK_COMMENTS.get(key, key)
                label, description, default_text = _parse_comment_details([fallback])
                fields.append(
                    FieldMeta(
                        section=section_name,
                        key=key,
                        original_key=key,
                        value="",
                        line_index=None,
                        comment_lines=[fallback],
                        label=label or key,
                        description=description,
                        default_text=default_text,
                    )
                )
            display_sections.append({"name": section_name, "fields": fields})
            continue

        if section_name in KEEP_ALL_SECTIONS:
            display_sections.append(
                {
                    "name": section_name,
                    "fields": list(section_meta.fields.values()),
                }
            )
            continue

        # Plugin.* sections are edited on the VPX-Plugins page, which supports
        # per-profile overrides. Everything else is left out of this editor.

    return display_sections


def _filter_sections(sections: list[dict], query: str, only_non_default: bool = False) -> list[dict]:
    search = (query or "").strip().lower()
    filtered: list[dict] = []
    for section in sections:
        matching_fields = [
            field
            for field in section["fields"]
            if (
                (not search
                 or search in field.key.lower()
                 or search in field.original_key.lower()
                 or search in field.label.lower())
                and (not only_non_default or bool((field.value or "").strip()))
            )
        ]
        if matching_fields:
            filtered.append({"name": section["name"], "fields": matching_fields})
    return filtered


def _write_updated_ini(
    ini_path: Path,
    displayed_sections: list[dict],
    inputs: dict[str, dict[str, ui.input]],
) -> None:
    values = {
        section: {key: getattr(inp, "value", "") for key, inp in section_inputs.items()}
        for section, section_inputs in inputs.items()
    }
    vpx_config_service.write_updated_ini(ini_path, displayed_sections, values)


def _backup_filename(ini_path: Path, reason: str = "manual") -> str:
    return vpx_config_service.backup_filename(ini_path, reason)


def _sanitize_backup_label(label: str) -> str:
    return vpx_config_service.sanitize_backup_label(label)


def _create_backup(ini_path: Path, reason: str = "manual", label: str = "") -> Path:
    return vpx_config_service.create_backup(ini_path, reason, label)


def _list_backups() -> list[Path]:
    return vpx_config_service.list_backups()


def _safe_mtime(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def render_panel() -> None:
    ini_path = _load_vpx_ini_path()

    load_page_style("vpx_config.css")

    with ui.column().classes("w-full vpx-config-shell"):
        with ui.card().classes("w-full vpx-config-hero").style("overflow: hidden;"):
            with ui.row().classes("w-full items-center justify-between p-6 gap-6"):
                with ui.row().classes("items-center gap-4"):
                    ui.icon("tune", size="34px").style("color: var(--ink) !important;")
                    with ui.column().classes("gap-1"):
                        ui.label("VPinballX.ini").classes("vpx-config-kicker")
                        ui.label("VPX Config").classes("text-2xl font-bold").style(
                            "color: var(--ink) !important;"
                        )
                        ui.label(
                            "Edit selected VPX sections directly from Manager UI while preserving the rest of the file."
                        ).classes("text-sm").style("color: var(--ink-muted) !important;")
                with ui.column().classes("items-end gap-1"):
                    ui.label("Source File").classes("text-xs font-semibold").style(
                        "color: var(--ink-muted) !important;"
                    )
                    ui.label(str(ini_path) if ini_path else "Not configured").classes(
                        "text-sm"
                    ).style("color: var(--ink) !important;")

        if ini_path is None:
            with ui.card().classes("w-full p-5").style(
                "background: var(--surface); border: 1px solid var(--line);"
            ):
                ui.label("`vpxinipath` is not set in vpinfe.ini.").classes(
                    "text-lg font-semibold"
                ).style("color: var(--bad) !important;")
                ui.label(
                    "Set `Settings.vpxinipath` on the Configuration page first, then reopen VPX Config."
                ).classes("text-sm").style("color: var(--ink-muted) !important;")
            return

        if not ini_path.exists():
            with ui.card().classes("w-full p-5").style(
                "background: var(--surface); border: 1px solid var(--line);"
            ):
                ui.label("Configured VPinballX.ini file was not found.").classes(
                    "text-lg font-semibold"
                ).style("color: var(--bad) !important;")
                ui.label(str(ini_path)).classes("text-sm").style(
                    "color: var(--ink-muted) !important;"
                )
            return

        try:
            parsed = _parse_ini(ini_path)
        except Exception as exc:
            logger.exception("Failed to parse %s", ini_path)
            with ui.card().classes("w-full p-5").style(
                "background: var(--surface); border: 1px solid var(--line);"
            ):
                ui.label("Failed to parse VPinballX.ini").classes(
                    "text-lg font-semibold"
                ).style("color: var(--bad) !important;")
                ui.label(str(exc)).classes("text-sm").style(
                    "color: var(--ink-muted) !important;"
                )
            return

        displayed_sections = _build_display_sections(parsed)
        inputs: dict[str, dict[str, ui.input]] = {}
        search_state = {"query": "", "only_non_default": False}

        # Track the on-disk mtime so we can reload when VPX (or anything else)
        # rewrites VPinballX.ini while this page is open. Without this, the input
        # fields keep the values loaded at render time and Save would clobber the
        # changes VPX wrote when the table exited.
        disk_state = {"mtime": _safe_mtime(ini_path)}
        pending_reload = {"value": False}

        def _has_unsaved_edits() -> bool:
            for section in displayed_sections:
                name = section["name"]
                for field in section["fields"]:
                    inp = inputs.get(name, {}).get(field.key)
                    if inp is None:
                        continue
                    typed = "" if inp.value is None else str(inp.value)
                    if typed.strip() != (field.value or "").strip():
                        return True
            return False

        def reload_from_disk() -> None:
            nonlocal displayed_sections
            try:
                reloaded = _parse_ini(ini_path)
            except Exception as exc:
                logger.exception("Failed to reload %s", ini_path)
                ui.notify(f"Failed to reload VPinballX.ini: {exc}", type="negative")
                return
            displayed_sections = _build_display_sections(reloaded)
            inputs.clear()
            disk_state["mtime"] = _safe_mtime(ini_path)
            pending_reload["value"] = False
            reload_banner.refresh()
            render_filtered_sections.refresh()
            update_save_bar()
            ui.notify("VPinballX.ini reloaded from disk", type="info")

        def dismiss_reload() -> None:
            pending_reload["value"] = False
            reload_banner.refresh()

        def check_disk_changes() -> None:
            current = _safe_mtime(ini_path)
            if current is None or current == disk_state["mtime"]:
                return
            disk_state["mtime"] = current
            # If the user has typed changes, don't discard them silently; prompt
            # instead. Otherwise reload the fresh values immediately.
            if _has_unsaved_edits():
                pending_reload["value"] = True
                reload_banner.refresh()
            else:
                reload_from_disk()

        @ui.refreshable
        def reload_banner() -> None:
            if not pending_reload["value"]:
                return
            with ui.card().classes("w-full p-4").style(
                "background: var(--surface); border: 1px solid var(--neon-yellow);"
            ):
                with ui.row().classes("w-full items-center justify-between gap-4"):
                    with ui.row().classes("items-center gap-3"):
                        ui.icon("sync_problem", size="24px").style(
                            "color: var(--neon-yellow) !important;"
                        )
                        with ui.column().classes("gap-0"):
                            ui.label("VPinballX.ini changed on disk").classes(
                                "text-sm font-semibold"
                            ).style("color: var(--ink) !important;")
                            ui.label(
                                "VPX updated the file. Reload to load the new values, or keep your unsaved edits."
                            ).classes("text-xs").style("color: var(--ink-muted) !important;")
                    with ui.row().classes("gap-2"):
                        ui.button("Reload", icon="sync", on_click=reload_from_disk).props("outline").style(
                            "color: var(--neon-cyan) !important; border: 1px solid var(--neon-cyan);"
                        )
                        ui.button("Keep my edits", on_click=dismiss_reload).props("flat").style(
                            "color: var(--ink-muted) !important;"
                        )

        def create_backup() -> None:
            with ui.dialog() as dialog, ui.card().classes("w-full").style(
                "background: var(--surface); border: 1px solid var(--line); min-width: min(92vw, 520px);"
            ):
                with ui.column().classes("w-full gap-4"):
                    ui.label("Create VPinballX.ini Backup").classes("text-xl font-bold").style(
                        "color: var(--ink) !important;"
                    )
                    ui.label(
                        "Give this backup an optional name. It will be added to the filename with a timestamp."
                    ).classes("text-sm").style("color: var(--ink-muted) !important;")
                    backup_name_input = ui.input(
                        label="Backup Name",
                        placeholder="Example: before-audio-tuning"
                    ).props("outlined clearable").classes("w-full")

                def _confirm_backup() -> None:
                    try:
                        backup_path = _create_backup(
                            ini_path,
                            reason="manual",
                            label=str(backup_name_input.value or ""),
                        )
                        dialog.close()
                        ui.notify(f"Backup created: {backup_path.name}", type="positive")
                    except Exception as exc:
                        logger.exception("Failed to create backup for %s", ini_path)
                        ui.notify(f"Failed to create backup: {exc}", type="negative")

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=dialog.close).style(
                        "color: var(--ink-muted) !important; background: var(--surface) !important; "
                        "border: 1px solid var(--line); border-radius: 18px; padding: 4px 10px;"
                    )
                    ui.button("Create Backup", icon="archive", on_click=_confirm_backup).style(
                        "color: var(--neon-cyan) !important; background: var(--surface) !important; "
                        "border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;"
                    )

            dialog.open()

        def restore_backup_dialog() -> None:
            backups = _list_backups()

            with ui.dialog() as dialog, ui.card().classes("w-full").style(
                "background: var(--surface); border: 1px solid var(--line); min-width: min(92vw, 900px);"
            ):
                with ui.column().classes("w-full gap-4"):
                    ui.label("Restore VPinballX.ini Backup").classes("text-xl font-bold").style(
                        "color: var(--ink) !important;"
                    )
                    ui.label(str(VPX_BACKUP_DIR)).classes("text-xs break-all").style(
                        "color: var(--ink-muted) !important;"
                    )

                    if not backups:
                        ui.label("No backups are available yet.").classes("text-sm").style(
                            "color: var(--ink-muted) !important;"
                        )
                    else:
                        with ui.scroll_area().classes("w-full").style("max-height: 28rem;"):
                            with ui.column().classes("w-full gap-3"):
                                for backup in backups:
                                    stat = backup.stat()
                                    modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                                    size_kb = max(1, round(stat.st_size / 1024))
                                    with ui.card().classes("w-full p-4").style(
                                        "background: var(--surface-soft); border: 1px solid var(--line);"
                                    ):
                                        with ui.row().classes("w-full items-center justify-between gap-4"):
                                            with ui.column().classes("gap-1"):
                                                ui.label(backup.name).classes("text-sm font-semibold").style(
                                                    "color: var(--ink) !important;"
                                                )
                                                ui.label(
                                                    f"Modified: {modified} | Size: {size_kb} KB"
                                                ).classes("text-xs").style(
                                                    "color: var(--ink-muted) !important;"
                                                )

                                            def _restore(path: Path = backup) -> None:
                                                try:
                                                    safety_backup = _create_backup(ini_path, reason="pre-restore")
                                                    shutil.copy2(path, ini_path)
                                                    dialog.close()
                                                    ui.notify(
                                                        f"Restored {path.name}. Safety backup created: {safety_backup.name}",
                                                        type="positive",
                                                    )
                                                    ui.navigate.to("/?page=vpx_config")
                                                except Exception as exc:
                                                    logger.exception("Failed to restore backup %s", path)
                                                    ui.notify(f"Failed to restore backup: {exc}", type="negative")

                                            ui.button(
                                                "Restore",
                                                icon="history",
                                                on_click=_restore,
                                            ).style(
                                                "color: var(--neon-cyan) !important; background: var(--surface) !important; "
                                                "border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;"
                                            )

                with ui.row().classes("w-full justify-end"):
                    ui.button("Close", on_click=dialog.close).style(
                        "color: var(--ink-muted) !important; background: var(--surface) !important; "
                        "border: 1px solid var(--line); border-radius: 18px; padding: 4px 10px;"
                    )

            dialog.open()

        def save_config() -> None:
            nonlocal displayed_sections
            try:
                _write_updated_ini(ini_path, displayed_sections, inputs)
                # Re-sync so our own write isn't mistaken for an external VPX change
                # by the disk watcher (and so unsaved-edit detection stays accurate).
                displayed_sections = _build_display_sections(_parse_ini(ini_path))
                disk_state["mtime"] = _safe_mtime(ini_path)
                ui.notify("VPinballX.ini saved", type="positive")
            except Exception as exc:
                logger.exception("Failed to save %s", ini_path)
                ui.notify(f"Failed to save VPinballX.ini: {exc}", type="negative")

        reload_banner()

        with ui.card().classes("w-full p-4").style(
            "background: var(--surface); border: 1px solid var(--line);"
        ):
            with ui.row().classes("w-full items-center justify-between gap-4"):
                with ui.column().classes("gap-1"):
                    ui.label("Backup and Restore").classes("text-sm font-semibold").style(
                        "color: var(--ink) !important;"
                    )
                    ui.label(
                        f"Backups are stored in {VPX_BACKUP_DIR}"
                    ).classes("text-xs break-all").style("color: var(--ink-muted) !important;")
                with ui.row().classes("gap-2"):
                    ui.button("Backup", icon="archive", on_click=create_backup).props("outline").style(
                        "color: var(--neon-cyan) !important; border: 1px solid var(--neon-cyan);"
                    )
                    ui.button("Restore", icon="restore", on_click=restore_backup_dialog).props("outline").style(
                        "color: var(--neon-yellow) !important; border: 1px solid var(--neon-yellow);"
                    )

        if not displayed_sections:
            with ui.card().classes("w-full p-5").style(
                "background: var(--surface); border: 1px solid var(--line);"
            ):
                ui.label("No configured VPX sections were found in this file.").classes(
                    "text-lg font-semibold"
                ).style("color: var(--warn) !important;")
            return

        with ui.card().classes("w-full p-4").style(
            "background: var(--surface); border: 1px solid var(--line);"
        ):
            with ui.row().classes("w-full items-center gap-4"):
                search_input = ui.input(
                    label="Filter by key name",
                    placeholder="Example: MusicVolume, EnableLog, Dmd..."
                ).props("outlined clearable").classes("w-full")
                non_default_only = ui.checkbox(
                    "Only show non-default values",
                    value=False,
                ).classes("shrink-0")
            ui.label(
                "Search narrows by key name. The non-default filter shows only settings with an explicit value instead of a blank/default entry."
            ).classes("text-sm").style("color: var(--ink-muted) !important;")

        @ui.refreshable
        def render_filtered_sections() -> None:
            filtered_sections = _filter_sections(
                displayed_sections,
                search_state["query"],
                search_state["only_non_default"],
            )

            if not filtered_sections:
                with ui.card().classes("w-full p-5").style(
                    "background: var(--surface); border: 1px solid var(--line);"
                ):
                    ui.label("No keys matched the current filter.").classes(
                        "text-lg font-semibold"
                    ).style("color: var(--warn) !important;")
                    ui.label(
                        "Try a partial key name like `volume`, `window`, or `dmd`, or turn off the non-default filter."
                    ).classes("text-sm").style("color: var(--ink-muted) !important;")
                return

            with ui.tabs().classes("w-full vpx-config-tabs").props(
                "inline-label active-color=cyan indicator-color=transparent"
            ) as tabs:
                for section in filtered_sections:
                    name = section["name"]
                    ui.tab(name, label=name, icon=SECTION_ICONS.get(name, "settings"))

            with ui.tab_panels(tabs, value=filtered_sections[0]["name"]).classes("w-full"):
                for section in filtered_sections:
                    name = section["name"]
                    inputs.setdefault(name, {})
                    with ui.tab_panel(name):
                        with ui.element("div").classes("vpx-config-panel w-full"):
                            with ui.element("div").classes("vpx-config-header"):
                                with ui.row().classes("items-center gap-3"):
                                    ui.icon(
                                        SECTION_ICONS.get(name, "settings"),
                                        size="24px",
                                    ).style("color: var(--neon-cyan) !important;")
                                    with ui.column().classes("gap-0"):
                                        ui.label(name).classes("vpx-config-section-title")
                                        ui.label(
                                            SECTION_DESCRIPTIONS.get(
                                                name,
                                                "VPX settings loaded from the VPinballX.ini file.",
                                            )
                                        ).classes("vpx-config-section-description")
                                ui.label(
                                    f'{len(section["fields"])} setting{"s" if len(section["fields"]) != 1 else ""}'
                                ).classes("text-xs font-semibold").style(
                                    "color: var(--ink-muted) !important;"
                                )

                            with ui.element("div").classes("vpx-config-grid"):
                                for field in section["fields"]:
                                    with ui.element("div").classes("vpx-config-field"):
                                        ui.label(field.key).classes("vpx-config-key")
                                        ui.label(field.label or field.key).classes("vpx-config-label")
                                        help_text = field.description or "Blank value lets VPX fall back to its default."
                                        ui.label(help_text).classes("vpx-config-help")
                                        if field.default_text:
                                            ui.label(field.default_text).classes("vpx-config-default")
                                        existing_input = inputs[name].get(field.key)
                                        current_value = getattr(existing_input, "value", field.value)
                                        inp = ui.input(
                                            value=current_value,
                                            placeholder="Blank = VPX default",
                                        ).props("outlined dense").classes("w-full vpx-config-input")
                                        inputs[name][field.key] = inp
                                        inp.on_value_change(lambda _: update_save_bar())

        def on_search_change() -> None:
            search_state["query"] = str(search_input.value or "")
            render_filtered_sections.refresh()

        def on_non_default_change() -> None:
            search_state["only_non_default"] = bool(non_default_only.value)
            render_filtered_sections.refresh()

        search_input.on_value_change(lambda _: on_search_change())
        non_default_only.on_value_change(lambda _: on_non_default_change())

        # --- Save bar (shared shell footer) --------------------------------
        # Reuse the existing baseline (each field's loaded value) as the dirty
        # source, so this coexists with the disk-reload watcher.
        def _norm(value):
            return "" if value is None else str(value)

        def changed_count():
            count = 0
            for section in displayed_sections:
                name = section["name"]
                for field in section["fields"]:
                    inp = inputs.get(name, {}).get(field.key)
                    if inp is None:
                        continue
                    if _norm(inp.value).strip() != _norm(field.value).strip():
                        count += 1
            return count

        def on_discard():
            for section in displayed_sections:
                name = section["name"]
                for field in section["fields"]:
                    inp = inputs.get(name, {}).get(field.key)
                    if inp is not None:
                        inp.value = field.value

        update_save_bar = attach_shell_save_bar(
            count=changed_count, on_save=save_config, on_discard=on_discard
        )

        render_filtered_sections()
        update_save_bar()

        # Watch VPinballX.ini for external changes (e.g. VPX rewriting it when a
        # table exits) and reload so stale values can't be saved back over them.
        ui.timer(0.5, check_disk_changes)
