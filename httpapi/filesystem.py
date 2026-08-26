"""Walking this machine's directories, so artwork can be picked from where it landed.

Art arrives on a cabinet by every route there is - a browser download, a USB stick, a
share - and asking someone to move a file into the right game folder before the app
will look at it is asking them to do the app's job.

Reading a directory over HTTP is a real capability, so it is bounded rather than
trusted: the game library, plus whatever folders the owner listed, and nothing else.
The check is on the resolved path, so a symlink out of a root is out of a root.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Query
from starlette.responses import FileResponse

from common.config_access import SettingsConfig
from common.media_specs import AUDIO_FAMILY, DOC_FAMILY, IMAGE_FAMILY, VIDEO_FAMILY
from common.paths import get_ini_config

from . import models, scopes
from .auth import requires
from .errors import InvalidRequestError

logger = logging.getLogger("vpinfe.httpapi.filesystem")

router = APIRouter(prefix="/filesystem", tags=["filesystem"])

_FAMILIES = {"image": IMAGE_FAMILY, "video": VIDEO_FAMILY,
             "audio": AUDIO_FAMILY, "doc": DOC_FAMILY}


def family_of(path: Path) -> str:
    """Which kind of media this file is, or "" for anything that is not media."""
    suffix = path.suffix.lower()
    return next((name for name, exts in _FAMILIES.items() if suffix in exts), "")


def roots(game_dir: str = "") -> list[dict]:
    """Where browsing may start.

    A game's own folder first when one is named: that is where its art is most likely
    to already be, and it is the one starting point that is not a setting.
    """
    settings = SettingsConfig.from_config(get_ini_config())
    found: list[dict] = []
    seen: set[Path] = set()

    def offer(raw: str, source: str) -> None:
        if not raw:
            return
        try:
            path = Path(raw).expanduser().resolve()
        except OSError:
            return
        if path in seen or not path.is_dir():
            return
        seen.add(path)
        found.append({"path": str(path), "name": path.name or str(path),
                      "source": source})

    if game_dir:
        offer(game_dir, "game")
    offer(settings.game_root_dir, "library")
    for extra in settings.media_browse_dirs:
        offer(extra, "configured")
    return found


def _escapes(entry: Path, allowed: list[Path]) -> bool:
    """Whether following this entry leaves every root.

    Only a symlink can: anything else under a resolved root is under it by
    construction, and resolving every entry would be a stat per file on a library
    that may well be over the network.
    """
    if not entry.is_symlink():
        return False
    try:
        target = entry.resolve()
    except OSError:
        return True
    return not any(target == root or root in target.parents for root in allowed)


def within_roots(raw: str) -> Path:
    """The path as a real location under some root, or a refusal.

    Resolved before it is checked, so `..` and a symlink are the same question. A root
    itself counts as inside itself - that is where browsing starts.
    """
    try:
        path = Path(raw).expanduser().resolve()
    except OSError as exc:
        raise InvalidRequestError("That path cannot be read",
                                  details={"path": raw}) from exc
    allowed = [Path(item["path"]) for item in roots()]
    if not any(path == root or root in path.parents for root in allowed):
        raise InvalidRequestError(
            "That folder is not one this hub may read",
            details={"path": raw, "allowed": [str(root) for root in allowed]})
    return path


@router.get("/roots", summary="Where browsing for media may start",
            dependencies=[requires(scopes.FILESYSTEM_READ)])
def get_roots(game: str = Query("")) -> models.FilesystemRootList:
    """An empty list is the honest answer for an install with no library configured
    and nothing allowlisted - not an error, and not a reason to offer the whole disk."""
    from .games import _catalog

    game_dir = ""
    if game:
        found = _catalog().get(game)
        game_dir = str(getattr(found, "fullPathGame", "") or "") if found else ""
    return {"roots": roots(game_dir)}


@router.get("/file", summary="One browsable media file",
            dependencies=[requires(scopes.FILESYSTEM_READ)])
def get_file(path: str = Query(...)) -> FileResponse:
    """Serve a file so it can be looked at before it is taken.

    Judging artwork means seeing it, and a name and a byte count do not do that. Bounded
    the same way the listing is, and to media on top of that: the containment check
    alone would happily serve a .vpx or an .info, and neither is something to hand out
    because a path was typed at this route.
    """
    here = within_roots(path)
    family = family_of(here)
    if not here.is_file() or not family:
        raise InvalidRequestError("That is not a media file", details={"path": path})
    return FileResponse(here)


@router.get("/entries", summary="What is in one folder",
            dependencies=[requires(scopes.FILESYSTEM_READ)])
def get_entries(path: str = Query(...)) -> models.FilesystemListing:
    """Folders and media files, folders first, both by name.

    Only media is listed. A directory walker that returns every file is a file browser,
    and this exists to find artwork - a .vpx or a .ini in the list is noise at best and
    a way to get a table file into an <img> at worst.
    """
    here = within_roots(path)
    if not here.is_dir():
        raise InvalidRequestError("That is not a folder", details={"path": path})

    folders, files = [], []
    allowed = [Path(item["path"]) for item in roots()]
    try:
        for entry in sorted(here.iterdir(), key=lambda item: item.name.lower()):
            # A link out of the allowed folders is not offered, because importing it
            # would be refused - listing it would be offering something that cannot
            # work, and "sleeve.png" pointing at /etc/passwd should not be on a menu.
            if _escapes(entry, allowed):
                continue
            # A folder someone cannot open is still worth showing; the refusal comes
            # when they try, and naming it is better than pretending it is not there.
            if entry.is_dir():
                folders.append({"name": entry.name, "path": str(entry),
                                "kind": "folder", "family": "", "size_bytes": None})
                continue
            family = family_of(entry)
            if family:
                files.append({"name": entry.name, "path": str(entry), "kind": "file",
                              "family": family, "size_bytes": entry.stat().st_size})
    except OSError as exc:
        raise InvalidRequestError("That folder cannot be read",
                                  details={"path": path}) from exc

    # Null at a root, so a client knows where "up" stops without knowing the rules.
    parent = here.parent
    at_root = any(here == Path(item["path"]) for item in roots())
    return {"path": str(here), "parent": None if at_root else str(parent),
            "entries": folders + files}
