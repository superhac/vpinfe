"""Listing this machine's folders and files, for a path field's Browse button.

Unbounded on purpose, unlike `common/games/media_browse.py`: picking a path means seeing
the whole disk, not just what a library already contains.
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

_DEFAULT_PATHEXT = ".exe;.bat;.cmd;.com"


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


def _is_bundle(path: Path) -> bool:
    """A macOS `.app`, which an `exe` field picks whole rather than walking into."""
    return sys.platform == "darwin" and path.suffix.lower() == ".app"


def _bundle_boundary(path: Path) -> Path | None:
    """The `.app` in `path`'s ancestry, if any - so a value saved from inside one still
    opens beside it rather than being asked for as a folder."""
    if sys.platform != "darwin":
        return None
    current = path
    while True:
        if _is_bundle(current):
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _pathext() -> tuple[str, ...]:
    raw = os.environ.get("PATHEXT", _DEFAULT_PATHEXT)
    return tuple(ext.strip().lower() for ext in raw.split(";") if ext.strip())


def _is_executable(entry: os.DirEntry) -> bool:
    if sys.platform == "win32":
        return entry.name.lower().endswith(_pathext())
    try:
        return os.access(entry.path, os.X_OK)
    except OSError:
        return False


def _wanted_file(entry: os.DirEntry, kind: str, suffixes: tuple[str, ...]) -> bool:
    if kind == "exe":
        return _is_executable(entry)
    lowered = tuple(s.lower() for s in suffixes)
    return not lowered or entry.name.lower().endswith(lowered)


def _entries(path: Path, private: tuple[Path, ...], kind: str,
             suffixes: tuple[str, ...]) -> tuple[list[dict], list[dict]]:
    folders: list[dict] = []
    files: list[dict] = []
    try:
        with os.scandir(path) as scanned:
            for entry in scanned:
                if entry.name.startswith("."):
                    continue
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    continue
                if is_dir:
                    if _is_private(Path(entry.path), private):
                        continue
                    if kind == "exe" and _is_bundle(Path(entry.path)):
                        files.append({"name": entry.name, "path": entry.path})
                    else:
                        folders.append({"name": entry.name, "path": entry.path})
                elif kind != "dir" and _wanted_file(entry, kind, suffixes):
                    files.append({"name": entry.name, "path": entry.path})
    except PermissionError as exc:
        raise service_errors.RefusedError(t("error.folders.cannot_read")) from exc
    folders.sort(key=lambda item: item["name"].lower())
    files.sort(key=lambda item: item["name"].lower())
    return folders, files


def _labeled(roots: list[dict]) -> list[dict]:
    """Each root named for its folder, unless that repeats another root's - then both
    say the whole path, the only way left to tell them apart."""
    counts: dict[str, int] = {}
    for root in roots:
        counts[root["name"]] = counts.get(root["name"], 0) + 1
    return [{"name": root["name"] if counts[root["name"]] == 1 else root["path"],
             "path": root["path"]} for root in roots]


def _common_roots() -> list[dict]:
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
    if sys.platform == "linux":
        found += [{"name": _name(Path(extra)), "path": extra}
                 for extra in ("/media", "/mnt") if Path(extra).exists()]
    return found


def _program_roots() -> list[dict]:
    home = Path.home()
    if sys.platform == "darwin":
        found = [{"name": _name(candidate), "path": str(candidate)} for candidate in
                (Path("/Applications"), home / "Applications",
                 Path("/opt/homebrew/bin"), Path("/usr/local/bin")) if candidate.exists()]
        found.append({"name": _name(home), "path": str(home)})
        found.append({"name": "/", "path": "/"})
        return found
    if sys.platform == "win32":
        found = [{"name": _name(Path(candidate)), "path": candidate} for candidate in
                (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"))
                if candidate and Path(candidate).exists()]
        found += [{"name": f"{letter}:", "path": f"{letter}:\\"} for letter in
                 (chr(code) for code in range(ord("A"), ord("Z") + 1))
                 if Path(f"{letter}:\\").exists()]
        return found
    found = [{"name": _name(candidate), "path": str(candidate)} for candidate in
            (Path("/usr/bin"), Path("/usr/local/bin"), Path("/opt")) if candidate.exists()]
    found.append({"name": _name(home), "path": str(home)})
    found.append({"name": "/", "path": "/"})
    return found


def _roots(kind: str) -> list[dict]:
    return _labeled(_program_roots() if kind == "exe" else _common_roots())


def _start(kind: str) -> Path:
    """Where an empty path opens: home for a folder or a file, an `exe` field's own
    first root for a program - never one VPinFE picked for somebody."""
    if kind == "exe":
        found = _program_roots()
        if found:
            return Path(found[0]["path"])
    return Path.home()


def listing(path: str = "", kind: str = "dir", suffixes: tuple[str, ...] = ()) -> dict:
    """One folder's contents, and where browsing can start over.

    `kind` says what `files` holds: nothing for `dir`, whatever this account can run for
    `exe` - an `.app` bundle included, on macOS, as one of its own entries rather than
    something to walk into - and whatever matches `suffixes` for `file`, or every
    non-hidden file where `suffixes` is empty.

    A `path` naming a file, or one inside a macOS `.app` bundle, lists the folder that
    holds it instead of failing to list a file as though it were one.
    """
    if kind not in ("dir", "file", "exe"):
        raise service_errors.RefusedError(t("error.folders.unknown_kind"))
    if not path:
        here = _start(kind)
    else:
        raw = Path(os.path.abspath(os.path.expanduser(path)))
        bundle = _bundle_boundary(raw)
        here = bundle.parent if bundle is not None else raw.parent if raw.is_file() else raw
    if not here.is_dir():
        raise service_errors.NotFoundError(t("error.folders.no_folder"))
    private = _private_roots()
    if _is_private(here, private):
        raise service_errors.RefusedError(t("error.folders.private"))
    parent = here.parent
    folders, files = _entries(here, private, kind, suffixes)
    return {"path": str(here), "parent": "" if parent == here else str(parent),
            "folders": folders, "files": files, "roots": _roots(kind)}
