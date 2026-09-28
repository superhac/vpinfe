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


def _name(path: Path) -> str:
    return path.name or str(path)


def _subfolders(path: Path) -> list[dict]:
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
    parent = here.parent
    return {"path": str(here), "parent": "" if parent == here else str(parent),
            "folders": _subfolders(here), "roots": _roots()}
