from __future__ import annotations

import re
import shutil
from pathlib import Path

from common.launcher import DEFAULT_PROFILE_NAME
from common.paths import PLUGIN_PROFILES_DIR
from managerui.services import vpx_config_service


PLUGIN_SECTION_PREFIX = "Plugin."


def ensure_profiles_dir() -> Path:
    PLUGIN_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return PLUGIN_PROFILES_DIR


def sanitize_profile_name(name: str) -> str:
    """Reduce a user-supplied profile name to a safe .ini filename stem."""
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "-", str(name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -.")
    return cleaned[:64]


def is_default_profile(name: str) -> bool:
    return str(name or "").strip().lower() == DEFAULT_PROFILE_NAME.lower()


def list_custom_profiles() -> list[str]:
    if not PLUGIN_PROFILES_DIR.exists():
        return []
    stems = [
        path.stem
        for path in PLUGIN_PROFILES_DIR.iterdir()
        if path.is_file() and path.suffix.lower() == ".ini" and not is_default_profile(path.stem)
    ]
    return sorted(stems, key=str.lower)


def list_profiles() -> list[str]:
    """Default first, then custom profiles alphabetically."""
    return [DEFAULT_PROFILE_NAME] + list_custom_profiles()


def profile_path(name: str) -> Path | None:
    """Resolve a profile name to the .ini file that Save should write to."""
    if is_default_profile(name):
        return vpx_config_service.load_vpx_ini_path()
    stem = sanitize_profile_name(name)
    if not stem:
        return None
    return PLUGIN_PROFILES_DIR / f"{stem}.ini"


def profile_exists(name: str) -> bool:
    path = profile_path(name)
    return path is not None and path.exists()


def create_profile(name: str) -> Path:
    """Create a new profile as a full copy of the live VPinballX.ini."""
    stem = sanitize_profile_name(name)
    if not stem:
        raise ValueError("Enter a profile name using letters, numbers, spaces, dots, or dashes.")
    if is_default_profile(stem):
        raise ValueError(f'"{DEFAULT_PROFILE_NAME}" is reserved for the live VPinballX.ini.')

    source = vpx_config_service.load_vpx_ini_path()
    if source is None:
        raise ValueError("`vpxinipath` is not set in vpinfe.ini.")
    if not source.exists():
        raise ValueError(f"VPinballX.ini was not found at {source}")

    ensure_profiles_dir()
    destination = PLUGIN_PROFILES_DIR / f"{stem}.ini"
    if destination.exists():
        raise ValueError(f'A profile named "{stem}" already exists.')

    shutil.copy2(source, destination)
    return destination


def build_plugin_sections(parsed: vpx_config_service.ParsedIni) -> list[dict]:
    """Return the Plugin.* sections in file order, each with its editable keys."""
    sections: list[dict] = []
    for section_name in parsed.section_order:
        if not section_name.startswith(PLUGIN_SECTION_PREFIX):
            continue
        section_meta = parsed.sections[section_name]
        sections.append(
            {
                "name": section_name,
                "label": section_name[len(PLUGIN_SECTION_PREFIX):],
                "fields": list(section_meta.fields.values()),
            }
        )
    return sections


def load_plugin_sections(path: Path) -> list[dict]:
    return build_plugin_sections(vpx_config_service.parse_ini(path))
