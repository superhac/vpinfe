"""Listing this machine's folders, for a folder field's Browse button.

Unbounded on purpose, unlike `common/games/media_browse.py`: picking where a library
lives means seeing the whole disk, not just what a library already contains.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from common import service_errors
from common.i18n import t

# Relative to home, so each resolves under whatever account runs VPinFE.
_PRIVATE_COMMON: tuple[str, ...] = (
    ".ssh", ".gnupg", ".aws", ".config/gcloud", ".kube", ".docker", ".password-store",
)
_PRIVATE_DARWIN: tuple[str, ...] = (
    "Library/Keychains",
    "Library/Cookies",
    "Library/Application Support/Google/Chrome",
    "Library/Application Support/Firefox",
    "Library/Application Support/1Password",
)
_PRIVATE_LINUX: tuple[str, ...] = (
    ".mozilla", ".config/google-chrome", ".config/chromium", ".local/share/keyrings",
)
_PRIVATE_WIN32: tuple[str, ...] = (
    "AppData/Roaming/Microsoft/Credentials",
    "AppData/Roaming/Microsoft/Protect",
    "AppData/Local/Google/Chrome/User Data",
    "AppData/Roaming/Mozilla/Firefox",
)
_PRIVATE_BY_PLATFORM: dict[str, tuple[str, ...]] = {
    "darwin": _PRIVATE_DARWIN,
    "linux": _PRIVATE_LINUX,
    "win32": _PRIVATE_WIN32,
}


def _name(path: Path) -> str:
    return path.name or str(path)


def _private_roots() -> tuple[Path, ...]:
    home = Path.home()
    relative = _PRIVATE_COMMON + _PRIVATE_BY_PLATFORM.get(sys.platform, ())
    return tuple(candidate.resolve() for rel in relative
                 if (candidate := home / rel).exists())


def _is_private(path: Path, private: tuple[Path, ...]) -> bool:
    """Resolved, so a symlink into one of these cannot read as outside it."""
    resolved = path.resolve()
    return any(resolved.is_relative_to(root) for root in private)


def _subfolders(path: Path, private: tuple[Path, ...]) -> list[dict]:
    found = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                try:
                    if not entry.is_dir():
                        continue
                except OSError:
                    continue
                if _is_private(Path(entry.path), private):
                    continue
                found.append({"name": entry.name, "path": entry.path})
    except PermissionError as exc:
        raise service_errors.RefusedError(t("error.folders.cannot_read")) from exc
    found.sort(key=lambda item: item["name"].lower())
    return found


def _roots() -> list[dict]:
    home = Path.home()
    if sys.platform == "win32":
        found = [{"name": f"{letter}:", "path": f"{letter}:\\"} for letter in
                 (chr(code) for code in range(ord("A"), ord("Z") + 1))
                 if Path(f"{letter}:\\").exists()]
        found.append({"name": _name(home), "path": str(home)})
        return found
    found = [{"name": "/", "path": "/"}, {"name": _name(home), "path": str(home)}]
    if sys.platform == "darwin" and Path("/Volumes").exists():
        found.append({"name": t("word.volumes"), "path": "/Volumes"})
    return found


def listing(path: str = "") -> dict:
    """One folder's immediate subfolders, and where browsing can start over.

    Empty `path` is the home folder - the first place someone is likely to keep
    tables, and never one VPinFE picked for them.
    """
    here = Path.home() if not path else Path(os.path.abspath(os.path.expanduser(path)))
    if not here.is_dir():
        raise service_errors.NotFoundError(t("error.folders.no_folder"))
    private = _private_roots()
    if _is_private(here, private):
        raise service_errors.RefusedError(t("error.folders.private"))
    parent = here.parent
    return {"path": str(here), "parent": "" if parent == here else str(parent),
            "folders": _subfolders(here, private), "roots": _roots()}
