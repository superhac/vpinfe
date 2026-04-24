from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from nicegui import ui

from common.iniconfig import IniConfig
from managerui.paths import CONFIG_DIR, VPINFE_INI_PATH
from managerui.services import vpx_config_service
from managerui.ui_helpers import load_page_style


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
    "Player",
    "Backglass",
    "ScoreView",
    "Topper",
    "Input",
    "DMD",
    "Alpha",
    "Controller",
}

SECTION_DESCRIPTIONS = {
    "Editor": "Selective editor debugging and logging settings from VPinballX.ini.",
    "Player": "Runtime audio, display, physics, and table player settings.",
    "Backglass": "Backglass output and positioning settings.",
    "ScoreView": "ScoreView window and rendering settings.",
    "Topper": "Topper output and placement settings.",
    "Input": "Input, controller, keyboard, and nudge settings.",
    "DMD": "DMD rendering and layout settings.",
    "Alpha": "Alpha-numeric display rendering settings.",
    "Controller": "Controller integrations and external system settings.",
}

SECTION_ICONS = {
    "Editor": "edit_note",
    "Player": "sports_esports",
    "Backglass": "tv",
    "ScoreView": "scoreboard",
    "Topper": "view_day",
    "Input": "keyboard",
    "DMD": "developer_board",
    "Alpha": "text_fields",
    "Controller": "gamepad",
}


@dataclass
class FieldMeta:
    section: str
    key: str
    original_key: str
    value: str
    line_index: int | None
    comment_lines: list[str] = field(default_factory=list)
    label: str = ""
    description: str = ""
    default_text: str = ""


@dataclass
class SectionMeta:
    name: str
    header_index: int
    fields: dict[str, FieldMeta] = field(default_factory=dict)


@dataclass
class ParsedIni:
    path: Path
    lines: list[str]
    sections: dict[str, SectionMeta]
    section_order: list[str]

    def section_insert_index(self, section_name: str) -> int:
        try:
            index = self.section_order.index(section_name)
        except ValueError:
            return len(self.lines)
        if index + 1 < len(self.section_order):
            next_section = self.sections[self.section_order[index + 1]]
            return next_section.header_index
        return len(self.lines)


def _load_vpx_ini_path() -> Path | None:
    try:
        return vpx_config_service.load_vpx_ini_path()
    except Exception:
        logger.exception("Failed to read vpxinipath from vpinfe.ini")
        return None


def _parse_comment_details(comment_lines: list[str]) -> tuple[str, str, str]:
    text = " ".join(line.strip() for line in comment_lines if line.strip()).strip()
    if not text:
        return "", "", ""

    default_text = ""
    default_match = re.search(r"(\[Default:.*\])", text)
    if default_match:
        default_text = default_match.group(1)
        text = text.replace(default_text, "").strip()

    if ":" in text:
        label, description = text.split(":", 1)
        return label.strip(), description.strip(), default_text

    return text.strip(), "", default_text


def _parse_ini(path: Path) -> ParsedIni:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    sections: dict[str, SectionMeta] = {}
    section_order: list[str] = []
    current_section: str | None = None
    pending_comments: list[str] = []

    section_pattern = re.compile(r"^\[(.+)\]\s*$")
    key_pattern = re.compile(r"^([^=]+?)=(.*)$")

    for index, line in enumerate(lines):
        stripped = line.strip()

        section_match = section_pattern.match(stripped)
        if section_match:
            current_section = section_match.group(1).strip()
            sections[current_section] = SectionMeta(name=current_section, header_index=index)
            section_order.append(current_section)
            pending_comments = []
            continue

        if stripped.startswith(";"):
            pending_comments.append(stripped[1:].strip())
            continue

        if not stripped:
            pending_comments = []
            continue

        if current_section is None:
            pending_comments = []
            continue

        key_match = key_pattern.match(line.rstrip("\n"))
        if not key_match:
            pending_comments = []
            continue

        original_key = key_match.group(1).strip()
        value = key_match.group(2).strip()
        label, description, default_text = _parse_comment_details(pending_comments)
        sections[current_section].fields[original_key.lower()] = FieldMeta(
            section=current_section,
            key=original_key,
            original_key=original_key,
            value=value,
            line_index=index,
            comment_lines=pending_comments[:],
            label=label or original_key,
            description=description,
            default_text=default_text,
        )
        pending_comments = []

    return ParsedIni(path=path, lines=lines, sections=sections, section_order=section_order)


def _build_display_sections(parsed: ParsedIni) -> list[dict]:
    display_sections: list[dict] = []

    for section_name in parsed.section_order:
        section_meta = parsed.sections[section_name]

        if section_name == "Editor":
            fields: list[FieldMeta] = []
            for key in EDITOR_INCLUDED_KEYS:
                existing = section_meta.fields.get(key.lower())
                if existing is not None:
                    fields.append(existing)
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

        if section_name.startswith("Plugin."):
            display_sections.append(
                {
                    "name": section_name,
                    "fields": list(section_meta.fields.values()),
                }
            )

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
    parsed = _parse_ini(ini_path)
    lines = parsed.lines[:]
    pending_insertions: dict[str, list[FieldMeta]] = {}

    for section in displayed_sections:
        section_name = section["name"]
        for field in section["fields"]:
            value = getattr(inputs.get(section_name, {}).get(field.key), "value", "")
            value = "" if value is None else str(value).strip()

            current_section = parsed.sections.get(section_name)
            existing = current_section.fields.get(field.key.lower()) if current_section else None
            if existing and existing.line_index is not None:
                lines[existing.line_index] = f"{existing.original_key} = {value}\n"
            else:
                pending_insertions.setdefault(section_name, []).append(
                    FieldMeta(
                        section=section_name,
                        key=field.key,
                        original_key=field.original_key,
                        value=value,
                        line_index=None,
                        comment_lines=field.comment_lines[:],
                    )
                )

    for section_name in reversed(parsed.section_order):
        additions = pending_insertions.get(section_name, [])
        if not additions:
            continue

        insert_at = parsed.section_insert_index(section_name)
        block: list[str] = []

        if insert_at > 0 and lines[insert_at - 1].strip():
            block.append("\n")

        for field in additions:
            for comment_line in field.comment_lines:
                block.append(f"; {comment_line}\n")
            block.append(f"{field.original_key} = {field.value}\n")
            block.append("\n")

        lines[insert_at:insert_at] = block

    ini_path.write_text("".join(lines), encoding="utf-8")


def _backup_filename(ini_path: Path, reason: str = "manual") -> str:
    return vpx_config_service.backup_filename(ini_path, reason)


def _sanitize_backup_label(label: str) -> str:
    return vpx_config_service.sanitize_backup_label(label)


def _create_backup(ini_path: Path, reason: str = "manual", label: str = "") -> Path:
    return vpx_config_service.create_backup(ini_path, reason, label)


def _list_backups() -> list[Path]:
    return vpx_config_service.list_backups()


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
            try:
                _write_updated_ini(ini_path, displayed_sections, inputs)
                ui.notify("VPinballX.ini saved", type="positive")
            except Exception as exc:
                logger.exception("Failed to save %s", ini_path)
                ui.notify(f"Failed to save VPinballX.ini: {exc}", type="negative")

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
                        "Try a partial key name like `volume`, `window`, or `plugin`, or turn off the non-default filter."
                    ).classes("text-sm").style("color: var(--ink-muted) !important;")
                return

            with ui.tabs().classes("w-full vpx-config-tabs").props(
                "inline-label active-color=cyan indicator-color=cyan"
            ) as tabs:
                for section in filtered_sections:
                    name = section["name"]
                    icon = "extension" if name.startswith("Plugin.") else SECTION_ICONS.get(name, "settings")
                    ui.tab(name, label=name, icon=icon)

            with ui.tab_panels(tabs, value=filtered_sections[0]["name"]).classes("w-full"):
                for section in filtered_sections:
                    name = section["name"]
                    inputs.setdefault(name, {})
                    with ui.tab_panel(name):
                        with ui.element("div").classes("vpx-config-panel w-full"):
                            with ui.element("div").classes("vpx-config-header"):
                                with ui.row().classes("items-center gap-3"):
                                    ui.icon(
                                        "extension" if name.startswith("Plugin.") else SECTION_ICONS.get(name, "settings"),
                                        size="24px",
                                    ).style("color: var(--neon-cyan) !important;")
                                    with ui.column().classes("gap-0"):
                                        ui.label(name).classes("vpx-config-section-title")
                                        ui.label(
                                            SECTION_DESCRIPTIONS.get(
                                                name,
                                                "Plugin-specific VPX settings loaded from the VPinballX.ini file."
                                                if name.startswith("Plugin.")
                                                else "VPX settings loaded from the VPinballX.ini file.",
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

        def on_search_change() -> None:
            search_state["query"] = str(search_input.value or "")
            render_filtered_sections.refresh()

        def on_non_default_change() -> None:
            search_state["only_non_default"] = bool(non_default_only.value)
            render_filtered_sections.refresh()

        search_input.on_value_change(lambda _: on_search_change())
        non_default_only.on_value_change(lambda _: on_non_default_change())
        render_filtered_sections()

        with ui.element("div").classes("w-full vpx-config-footer"):
            ui.button("Save Changes", icon="save", on_click=save_config).classes("px-6 py-3").style(
                "color: var(--neon-cyan) !important; background: var(--surface) !important; "
                "border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;"
            )
