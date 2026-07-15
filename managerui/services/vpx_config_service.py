from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from common.iniconfig import IniConfig

from managerui.paths import CONFIG_DIR, VPINFE_INI_PATH


VPX_BACKUP_DIR = CONFIG_DIR / "backups" / "vpx_ini"


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


def parse_comment_details(comment_lines: list[str]) -> tuple[str, str, str]:
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


def parse_ini(path: Path) -> ParsedIni:
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
        label, description, default_text = parse_comment_details(pending_comments)
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


def write_updated_ini(
    ini_path: Path,
    displayed_sections: list[dict],
    values: dict[str, dict[str, str]],
) -> None:
    """Rewrite only the displayed keys in-place, preserving every other line.

    `values` maps section name -> key -> new value. Keys already present are
    replaced on their original line; new keys are appended to the end of their
    existing section so unrelated content and comments survive untouched.
    """
    parsed = parse_ini(ini_path)
    lines = parsed.lines[:]
    pending_insertions: dict[str, list[FieldMeta]] = {}

    for section in displayed_sections:
        section_name = section["name"]
        for field_meta in section["fields"]:
            value = values.get(section_name, {}).get(field_meta.key, "")
            value = "" if value is None else str(value).strip()

            current_section = parsed.sections.get(section_name)
            existing = current_section.fields.get(field_meta.key.lower()) if current_section else None
            if existing and existing.line_index is not None:
                lines[existing.line_index] = f"{existing.original_key} = {value}\n"
            else:
                pending_insertions.setdefault(section_name, []).append(
                    FieldMeta(
                        section=section_name,
                        key=field_meta.key,
                        original_key=field_meta.original_key,
                        value=value,
                        line_index=None,
                        comment_lines=field_meta.comment_lines[:],
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

        for field_meta in additions:
            for comment_line in field_meta.comment_lines:
                block.append(f"; {comment_line}\n")
            block.append(f"{field_meta.original_key} = {field_meta.value}\n")
            block.append("\n")

        lines[insert_at:insert_at] = block

    ini_path.write_text("".join(lines), encoding="utf-8")


def load_vpx_ini_path() -> Path | None:
    config = IniConfig(str(VPINFE_INI_PATH))
    raw_path = config.config.get("Settings", "vpxinipath", fallback="").strip()
    if not raw_path:
        return None
    return Path(os.path.expanduser(raw_path))


def backup_filename(ini_path: Path, reason: str = "manual") -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{ini_path.stem}-{reason}-{timestamp}{ini_path.suffix}"


def sanitize_backup_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(label or "").strip())
    cleaned = cleaned.strip("-.")
    return cleaned[:64]


def create_backup(ini_path: Path, reason: str = "manual", label: str = "") -> Path:
    VPX_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    filename = backup_filename(ini_path, reason=reason)
    safe_label = sanitize_backup_label(label)
    if safe_label:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{ini_path.stem}-{reason}-{safe_label}-{timestamp}{ini_path.suffix}"
    backup_path = VPX_BACKUP_DIR / filename
    shutil.copy2(ini_path, backup_path)
    return backup_path


def list_backups() -> list[Path]:
    if not VPX_BACKUP_DIR.exists():
        return []
    return sorted(
        (path for path in VPX_BACKUP_DIR.iterdir() if path.is_file() and path.suffix.lower() == ".ini"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
