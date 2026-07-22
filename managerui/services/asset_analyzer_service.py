from __future__ import annotations

import fnmatch
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from managerui.services.asset_registry import (
    ARCHIVE_EXTENSIONS,
    match_media_key,
    spec_for,
)

try:
    import rarfile
except ImportError:  # pragma: no cover - optional dependency
    rarfile = None

try:
    import py7zr
except ImportError:  # pragma: no cover - optional dependency
    py7zr = None


logger = logging.getLogger("vpinfe.manager.asset_analyzer")

_CHUNK = 1024 * 1024

_JUNK_COMPONENTS = {"__macosx", ".ds_store", "thumbs.db", "desktop.ini"}
_ROM_SUFFIXES = {".bin", ".rom", ".cpu", ".snd", ".dat"}
_VIDEO_SUFFIXES = {".mp4", ".avi", ".mkv", ".webm"}
_AUDIO_SUFFIXES = {".mp3", ".ogg", ".wav"}
_ALTSOUND_MARKERS = {"altsound.csv", "g-sound.csv"}
_PUP_MARKERS_EXACT = {"screens.pup", "editthispuppack.bat", "scriptonly.txt"}
_PUP_MARKER_GLOBS = ("*option*.bat", "*screen*.bat")
_PUP_FALLBACK_MIN_SUBDIRS = 10
_PUP_FALLBACK_MIN_VIDEOS = 10


@dataclass(frozen=True)
class SourceEntry:
    path: str        # key within the source, used for extraction
    arcname: str     # normalized path (wrapper stripped), used for layout and rules
    size: int
    is_dir: bool


@dataclass(frozen=True)
class DetectedAsset:
    kind: str
    label: str
    entries: tuple[SourceEntry, ...]
    root: str = ""          # arcname-space subtree root for folder kinds; "" for file kinds
    media_key: str = ""
    size: int = 0
    detail: str = ""


@dataclass(frozen=True)
class AnalysisResult:
    source_kind: str
    source_name: str
    assets: tuple[DetectedAsset, ...]
    has_table: bool
    notes: tuple[str, ...] = ()
    error: str = ""
    unrecognized: tuple[str, ...] = ()   # source-relative paths that no rule claimed
    bundle_info: dict | None = None      # parsed .info content when a bundle carries one


# --- Source backends -------------------------------------------------------

class AssetSource(Protocol):
    name: str
    kind: str

    def entries(self) -> list[SourceEntry]: ...
    def extract_member(self, entry_path: str, dest: Path) -> None: ...
    def archive_path(self) -> Path | None: ...
    def close(self) -> None: ...


def _clean_name(raw: str) -> str:
    name = raw.replace("\\", "/").strip()
    while name.startswith("/"):
        name = name[1:]
    return name.rstrip("/")


class ZipSource:
    def __init__(self, path: Path) -> None:
        self.name = path.name
        self.kind = "zip"
        self._path = path
        self._zip = zipfile.ZipFile(path)
        self._raw_by_path: dict[str, str] = {}
        for info in self._zip.infolist():
            if info.is_dir():
                continue
            cleaned = _clean_name(info.filename)
            if cleaned:
                self._raw_by_path.setdefault(cleaned, info.filename)

    def entries(self) -> list[SourceEntry]:
        out: list[SourceEntry] = []
        for info in self._zip.infolist():
            cleaned = _clean_name(info.filename)
            if not cleaned:
                continue
            out.append(SourceEntry(cleaned, cleaned, info.file_size, info.is_dir()))
        return out

    def extract_member(self, entry_path: str, dest: Path) -> None:
        raw = self._raw_by_path[entry_path]
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._zip.open(raw) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst, _CHUNK)

    def archive_path(self) -> Path | None:
        return self._path

    def close(self) -> None:
        self._zip.close()


class RarSource:
    def __init__(self, path: Path) -> None:
        self.name = path.name
        self.kind = "rar"
        self._path = path
        self._rar = rarfile.RarFile(path)
        self._raw_by_path: dict[str, str] = {}
        for info in self._rar.infolist():
            if info.isdir():
                continue
            cleaned = _clean_name(info.filename)
            if cleaned:
                self._raw_by_path.setdefault(cleaned, info.filename)

    def entries(self) -> list[SourceEntry]:
        out: list[SourceEntry] = []
        for info in self._rar.infolist():
            cleaned = _clean_name(info.filename)
            if not cleaned:
                continue
            out.append(SourceEntry(cleaned, cleaned, info.file_size, info.isdir()))
        return out

    def extract_member(self, entry_path: str, dest: Path) -> None:
        raw = self._raw_by_path[entry_path]
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._rar.open(raw) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst, _CHUNK)

    def archive_path(self) -> Path | None:
        return self._path

    def close(self) -> None:
        self._rar.close()


class SevenZipSource:
    def __init__(self, path: Path) -> None:
        self.name = path.name
        self.kind = "7z"
        self._path = path
        self._members: list[SourceEntry] = []
        self._raw_by_path: dict[str, str] = {}
        with py7zr.SevenZipFile(path, "r") as archive:
            for info in archive.list():
                cleaned = _clean_name(info.filename)
                if not cleaned:
                    continue
                size = int(getattr(info, "uncompressed", 0) or 0)
                self._members.append(SourceEntry(cleaned, cleaned, size, info.is_directory))
                if not info.is_directory:
                    self._raw_by_path.setdefault(cleaned, info.filename)

    def entries(self) -> list[SourceEntry]:
        return list(self._members)

    def extract_member(self, entry_path: str, dest: Path) -> None:
        raw = self._raw_by_path[entry_path]
        dest.parent.mkdir(parents=True, exist_ok=True)
        # py7zr has no cheap per-member stream, so extract into a scratch dir and copy out.
        with tempfile.TemporaryDirectory() as scratch:
            with py7zr.SevenZipFile(self._path, "r") as archive:
                archive.extract(path=scratch, targets=[raw])
            extracted = Path(scratch) / raw
            shutil.copyfile(extracted, dest)

    def archive_path(self) -> Path | None:
        return self._path

    def close(self) -> None:
        return None


class DirSource:
    def __init__(self, path: Path) -> None:
        self.name = path.name
        self.kind = "dir"
        self._root = path

    def entries(self) -> list[SourceEntry]:
        out: list[SourceEntry] = []
        for dirpath, dirnames, filenames in os.walk(self._root):
            rel_dir = Path(dirpath).relative_to(self._root)
            for name in dirnames:
                rel = (rel_dir / name).as_posix()
                out.append(SourceEntry(rel, rel, 0, True))
            for name in filenames:
                rel = (rel_dir / name).as_posix()
                try:
                    size = (Path(dirpath) / name).stat().st_size
                except OSError:
                    size = 0
                out.append(SourceEntry(rel, rel, size, False))
        return out

    def extract_member(self, entry_path: str, dest: Path) -> None:
        src = self._root / Path(*PurePosixPath(entry_path).parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)

    def archive_path(self) -> Path | None:
        return None

    def close(self) -> None:
        return None


class SingleFileSource:
    def __init__(self, path: Path) -> None:
        self.name = path.name
        self.kind = "file"
        self._path = path

    def entries(self) -> list[SourceEntry]:
        try:
            size = self._path.stat().st_size
        except OSError:
            size = 0
        return [SourceEntry(self._path.name, self._path.name, size, False)]

    def extract_member(self, entry_path: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._path, dest)

    def archive_path(self) -> Path | None:
        return self._path

    def close(self) -> None:
        return None


def configure_rar_tool(path: str) -> None:
    """Point rarfile at a specific unar/unrar/bsdtar binary.

    An empty path leaves rarfile's default behavior, which searches PATH for the tool.
    A value is useful when the tool is installed somewhere off PATH (common on locked-down
    cabs launched from a frontend or service with a minimal environment).
    """
    if rarfile is None or not path:
        return
    name = Path(path).name.lower()
    if "unrar" in name:
        rarfile.UNRAR_TOOL = path
    elif "unar" in name:
        rarfile.UNAR_TOOL = path
    elif "bsdtar" in name:
        rarfile.BSDTAR_TOOL = path
    else:
        rarfile.UNRAR_TOOL = path   # assume an unrar-compatible binary


def rar_tool_available() -> bool:
    """True if rarfile can find a working extraction tool (unrar, unar, or bsdtar)."""
    if rarfile is None:
        return False
    try:
        rarfile.tool_setup(force=True)
        return True
    except Exception:
        return False


def rar_tool_hint() -> str:
    """Platform-appropriate guidance for installing a RAR extraction tool.

    Deliberately avoids naming a specific package manager — Linux distributions differ —
    and points at the configurable path setting as the alternative to a PATH install.
    """
    if sys.platform.startswith("win"):
        return ("RAR support needs UnRAR.exe, which ships with WinRAR or 7-Zip. Install one "
                "of those, or set the RAR tool path in Configuration.")
    if sys.platform == "darwin":
        how = "install it (for example, brew install unar)"
    else:
        how = "install it from your distribution's package manager (usually the 'unar' or 'unrar' package)"
    return (f"RAR support needs the 'unar' or 'unrar' tool — {how}, "
            "or set the RAR tool path in Configuration.")


def open_source(path: Path) -> AssetSource:
    """Open a path as a uniform asset source (directory, archive, or single file)."""
    path = Path(path)
    if path.is_dir():
        return DirSource(path)
    ext = path.suffix.lower()
    if ext in {".zip", ".vpxz"}:
        return ZipSource(path)
    if ext == ".rar":
        if rarfile is None:
            raise _MissingBackend("RAR support requires the 'rarfile' package")
        return RarSource(path)
    if ext == ".7z":
        if py7zr is None:
            raise _MissingBackend("7z support requires the 'py7zr' package")
        return SevenZipSource(path)
    return SingleFileSource(path)


class _MissingBackend(RuntimeError):
    pass


# --- Normalization ---------------------------------------------------------

def _is_junk(arcname: str) -> bool:
    parts = [p.lower() for p in PurePosixPath(arcname).parts]
    if any(p in _JUNK_COMPONENTS for p in parts):
        return True
    base = PurePosixPath(arcname).name
    return base.startswith("._")


def _normalize(entries: list[SourceEntry]) -> list[SourceEntry]:
    # Drop OS junk only. A wrapper directory is intentionally left in place: folder
    # kinds carry a `root` and import lays them out relative to it, so a redundant
    # top folder never reaches the destination, while pack detection keeps its signal.
    return [e for e in entries if e.arcname and not _is_junk(e.arcname)]


# --- Detection helpers -----------------------------------------------------

def _parent(arcname: str) -> str:
    parent = PurePosixPath(arcname).parent
    return "" if str(parent) == "." else str(parent)


def _under(arcname: str, root: str) -> bool:
    if root == "":
        return True
    return arcname == root or arcname.startswith(root + "/")


def _suffix(arcname: str) -> str:
    return PurePosixPath(arcname).suffix.lower()


def _basename(arcname: str) -> str:
    return PurePosixPath(arcname).name


# --- Detection -------------------------------------------------------------

def _analyze_entries(entries: list[SourceEntry]) -> tuple[list[DetectedAsset], list[str], bool]:
    norm = _normalize(entries)
    files = [e for e in norm if not e.is_dir]
    claimed: set[str] = set()
    assets: list[DetectedAsset] = []
    notes: list[str] = []

    def unclaimed() -> list[SourceEntry]:
        return [e for e in files if e.path not in claimed]

    def claim_subtree(root: str) -> list[SourceEntry]:
        picked = [e for e in files if e.path not in claimed and _under(e.arcname, root)]
        for e in picked:
            claimed.add(e.path)
        return picked

    # 1. Table
    has_table = False
    vpx_dirs: set[str] = set()
    for e in list(unclaimed()):
        if _suffix(e.arcname) == ".vpx":
            claimed.add(e.path)
            has_table = True
            vpx_dirs.add(_parent(e.arcname))
            assets.append(DetectedAsset("table", "Table", (e,), size=e.size, detail=_basename(e.arcname)))

    # 1b. Table metadata — bundle-scoped only: a .info beside a claimed .vpx. A lone
    # .info stays unrecognized (wholesale metadata replacement is never inferred).
    for e in list(unclaimed()):
        if _suffix(e.arcname) == ".info" and _parent(e.arcname) in vpx_dirs:
            claimed.add(e.path)
            assets.append(DetectedAsset("table_info", "Metadata", (e,), size=e.size,
                                        detail=_basename(e.arcname)))

    # 2. Backglass
    for e in list(unclaimed()):
        if _suffix(e.arcname) == ".directb2s":
            claimed.add(e.path)
            assets.append(DetectedAsset("backglass", "Backglass", (e,), size=e.size, detail=_basename(e.arcname)))

    # Subtree claimers run before loose-file claimers so files inside a pack are not grabbed loose.
    # 3. AltSound
    altsound_roots: list[str] = []
    for e in unclaimed():
        if _basename(e.arcname).lower() in _ALTSOUND_MARKERS:
            altsound_roots.append(_parent(e.arcname))
    for root in _dedupe_roots(altsound_roots):
        picked = claim_subtree(root)
        if picked:
            assets.append(DetectedAsset(
                "altsound", "AltSound", tuple(picked), root=root,
                size=sum(p.size for p in picked), detail=f"{len(picked)} files"))

    # 4. PUP pack
    pup_roots = _find_pup_roots(unclaimed())
    for root in pup_roots:
        picked = claim_subtree(root)
        if picked:
            assets.append(DetectedAsset(
                "pup_pack", "PUP Pack", tuple(picked), root=root,
                size=sum(p.size for p in picked), detail=f"{len(picked)} files"))

    # 5. Music
    for root in _find_music_roots(unclaimed()):
        picked = claim_subtree(root)
        if picked:
            assets.append(DetectedAsset(
                "music", "Music", tuple(picked), root=root,
                size=sum(p.size for p in picked), detail=f"{len(picked)} files"))

    # 6. AltColor
    for e in list(unclaimed()):
        if _suffix(e.arcname) == ".crz":
            claimed.add(e.path)
            assets.append(DetectedAsset("altcolor_serum", "Serum Color", (e,), size=e.size, detail=_basename(e.arcname)))
    vni_by_dir: dict[str, list[SourceEntry]] = {}
    for e in unclaimed():
        if _suffix(e.arcname) in {".vni", ".pal", ".pac"}:
            vni_by_dir.setdefault(_parent(e.arcname), []).append(e)
    for group in vni_by_dir.values():
        for e in group:
            claimed.add(e.path)
        assets.append(DetectedAsset(
            "altcolor_vni", "VNI/PAL Color", tuple(group),
            size=sum(g.size for g in group), detail=", ".join(_basename(g.arcname) for g in group)))

    # 7. ROM
    remaining = unclaimed()
    is_flat = not any(e.is_dir for e in norm) and all("/" not in e.arcname for e in remaining)
    if remaining and is_flat and all(_is_rom_suffix(e.arcname) for e in remaining):
        for e in remaining:
            claimed.add(e.path)
        assets.append(DetectedAsset(
            "rom", "ROM", tuple(remaining), size=sum(e.size for e in remaining),
            detail="whole archive"))
    else:
        for e in list(unclaimed()):
            if _suffix(e.arcname) == ".zip":
                claimed.add(e.path)
                assets.append(DetectedAsset("rom", "ROM", (e,), size=e.size, detail=_basename(e.arcname)))

    # 8. INI
    for e in list(unclaimed()):
        if _suffix(e.arcname) == ".ini":
            claimed.add(e.path)
            assets.append(DetectedAsset("ini", "Table INI", (e,), size=e.size, detail=_basename(e.arcname)))

    # 9. Media
    for e in list(unclaimed()):
        media_key = match_media_key(_basename(e.arcname))
        if media_key:
            claimed.add(e.path)
            assets.append(DetectedAsset(
                "media", spec_for("media").label, (e,), media_key=media_key,
                size=e.size, detail=f"{_basename(e.arcname)} → {media_key}"))

    unrecognized = tuple(e.arcname for e in files if e.path not in claimed)
    return assets, notes, has_table, unrecognized


def _dedupe_roots(roots: list[str]) -> list[str]:
    """Keep only outermost roots (drop any root nested under another)."""
    unique = sorted(set(roots), key=lambda r: (len(PurePosixPath(r).parts), r))
    kept: list[str] = []
    for root in unique:
        if any(_under(root, existing) and root != existing for existing in kept):
            continue
        kept.append(root)
    return kept


def _find_pup_roots(entries: list[SourceEntry]) -> list[str]:
    marker_roots: list[str] = []
    for e in entries:
        base = _basename(e.arcname).lower()
        if base in _PUP_MARKERS_EXACT or any(fnmatch.fnmatch(base, g) for g in _PUP_MARKER_GLOBS):
            marker_roots.append(_parent(e.arcname))
    if marker_roots:
        return _dedupe_roots(marker_roots)
    return _find_pup_roots_by_shape(entries)


def _find_pup_roots_by_shape(entries: list[SourceEntry]) -> list[str]:
    subdirs: dict[str, set[str]] = {}
    videos: dict[str, int] = {}
    for e in entries:
        parts = PurePosixPath(e.arcname).parts
        if len(parts) < 2:
            continue
        root = parts[0]
        subdirs.setdefault(root, set()).add(parts[1])
        if _suffix(e.arcname) in _VIDEO_SUFFIXES:
            videos[root] = videos.get(root, 0) + 1
    roots = [
        root for root, dirs in subdirs.items()
        if len(dirs) >= _PUP_FALLBACK_MIN_SUBDIRS and videos.get(root, 0) >= _PUP_FALLBACK_MIN_VIDEOS
    ]
    return _dedupe_roots(roots)


def _find_music_roots(entries: list[SourceEntry]) -> list[str]:
    by_dir: dict[str, list[SourceEntry]] = {}
    for e in entries:
        top = PurePosixPath(e.arcname).parts[0] if PurePosixPath(e.arcname).parts else ""
        if top == "" or "/" not in e.arcname:
            continue   # root-level files are ambiguous (e.g. table audio.mp3); leave to media
        by_dir.setdefault(top, []).append(e)
    roots: list[str] = []
    for root, members in by_dir.items():
        suffixes = {_suffix(m.arcname) for m in members}
        has_audio = bool(suffixes & _AUDIO_SUFFIXES)
        has_video = bool(suffixes & _VIDEO_SUFFIXES)
        if has_audio and not has_video and suffixes <= _AUDIO_SUFFIXES:
            roots.append(root)
    return roots


def _is_rom_suffix(arcname: str) -> bool:
    suffix = _suffix(arcname)
    if suffix in _ROM_SUFFIXES:
        return True
    ext = suffix.lstrip(".")
    return 1 <= len(ext) <= 2 and ext[-1:].isdigit()


_INFO_MAX_BYTES = 2 * 1024 * 1024


def _read_bundle_info(source: AssetSource, asset: DetectedAsset) -> dict | None:
    """Extract and parse a bundle's .info; None if oversized, unreadable, or not a JSON dict."""
    import json

    entry = asset.entries[0]
    if entry.size > _INFO_MAX_BYTES:
        return None
    with tempfile.TemporaryDirectory() as scratch:
        dest = Path(scratch) / "bundle.info"
        try:
            source.extract_member(entry.path, dest)
            data = json.loads(dest.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Unreadable bundle .info: %s", entry.arcname)
            return None
    return data if isinstance(data, dict) else None


# --- Public API ------------------------------------------------------------

def analyze_path(path: Path) -> AnalysisResult:
    """Analyze a file, archive, or directory and report the assets it contains."""
    path = Path(path)
    try:
        source = open_source(path)
    except _MissingBackend as exc:
        return AnalysisResult(_source_kind(path), path.name, (), False, error=str(exc))
    except Exception:
        logger.exception("Failed to open source: %s", path)
        return AnalysisResult(_source_kind(path), path.name, (), False, error="Could not read the dropped item")

    # Surface a missing RAR tool up front, before the confirm dialog, rather than
    # failing at extraction time after the user has committed to the import.
    if source.kind == "rar" and not rar_tool_available():
        source.close()
        return AnalysisResult(source.kind, source.name, (), False, error=rar_tool_hint())

    try:
        try:
            entries = source.entries()
        except _rar_exec_errors() as exc:
            logger.warning("RAR backend unavailable: %s", exc)
            return AnalysisResult(source.kind, source.name, (), False,
                                  error="RAR extraction requires the 'unar' or 'unrar' tool to be installed")
        except Exception:
            logger.exception("Failed to list source: %s", path)
            return AnalysisResult(source.kind, source.name, (), False, error="Could not read the dropped item")

        assets, notes, has_table, unrecognized = _analyze_entries(entries)

        # A bundle .info is read up front (it is tiny) so its content can seed the
        # import dialog and be validated before anything is written.
        bundle_info = None
        info_assets = [a for a in assets if a.kind == "table_info"]
        if info_assets:
            bundle_info = _read_bundle_info(source, info_assets[0])
            if bundle_info is None:
                assets = [a for a in assets if a.kind != "table_info"]
                unrecognized = unrecognized + tuple(e.arcname for e in info_assets[0].entries)
                notes = list(notes) + ["bundle .info is not valid metadata and was skipped"]
    finally:
        source.close()

    if not assets:
        return AnalysisResult(source.kind, source.name, (), False, tuple(notes),
                              error="No recognized assets found", unrecognized=unrecognized)
    return AnalysisResult(source.kind, source.name, tuple(assets), has_table, tuple(notes),
                          unrecognized=unrecognized, bundle_info=bundle_info)


def analyze_upload_session(session_dir: Path) -> tuple[AnalysisResult, Path]:
    """Analyze a staged upload session and return the result plus the path to analyze/import from.

    A session holding a single archive analyzes that archive; a single non-archive file
    is analyzed on its own; anything else is treated as a dropped folder tree.
    """
    session_dir = Path(session_dir)
    top_files = [p for p in session_dir.iterdir() if p.is_file()]
    top_dirs = [p for p in session_dir.iterdir() if p.is_dir()]
    if len(top_files) == 1 and not top_dirs:
        only = top_files[0]
        if only.suffix.lower() in ARCHIVE_EXTENSIONS:
            return analyze_path(only), only
        return analyze_path(only), only
    return analyze_path(session_dir), session_dir


def _source_kind(path: Path) -> str:
    if path.is_dir():
        return "dir"
    ext = path.suffix.lower()
    if ext in {".zip", ".vpxz"}:
        return "zip"
    if ext == ".rar":
        return "rar"
    if ext == ".7z":
        return "7z"
    return "file"


def _rar_exec_errors() -> tuple[type[BaseException], ...]:
    if rarfile is None:
        return (RuntimeError,)
    return (rarfile.RarCannotExec, rarfile.BadRarFile)
