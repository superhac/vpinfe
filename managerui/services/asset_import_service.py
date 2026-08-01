from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Callable

from common.media_paths import media_filename_map
from common.tables.metaconfig import VPINFE_SECTION, MetaConfig
from common.tables.game_repository import refresh_game
from common.tables.vpxparser import VPXParser
from managerui.paths import get_games_path
from managerui.services.asset_analyzer_service import (
    AnalysisResult,
    DetectedAsset,
    SourceEntry,
    open_source,
)
from managerui.services.asset_registry import ARCHIVE_EXTENSIONS, spec_for
from managerui.services.media_service import IMAGE_EXTENSIONS, replace_media_file
from managerui.services.game_service import (
    _find_directb2s_file,
    _find_ini_file,
    _find_vpx_file,
    _safe_upload_name,
    ensure_dir,
)


logger = logging.getLogger("vpinfe.manager.asset_import")

_MEDIA_FILENAMES = media_filename_map("table")


@dataclass(frozen=True)
class PlannedItem:
    asset: DetectedAsset
    destination: str        # absolute path (file target, or base dir for tree kinds)
    action: str             # replace_vpx | replace_b2s | copy | zip_rom | extract_tree
                            # | replace_media | apply_patch | write_info
    default_enabled: bool = True


@dataclass(frozen=True)
class BlockedItem:
    asset: DetectedAsset
    reason: str


@dataclass(frozen=True)
class ImportPlan:
    table_path: str          # target table dir (existing, or the resolved new-table dir)
    new_table_dir_name: str  # non-empty only for new-table bundle imports
    rom_name: str
    items: tuple[PlannedItem, ...]
    blocked: tuple[BlockedItem, ...]


def _basename(arcname: str) -> str:
    return PurePosixPath(arcname).name


def _is_rar_exec_error(exc: BaseException) -> bool:
    try:
        import rarfile
    except ImportError:  # pragma: no cover - optional dependency
        return False
    return isinstance(exc, rarfile.RarCannotExec)


def _safe_dest(base_dir: Path, relative: str) -> Path:
    """Resolve a relative path under base_dir, rejecting traversal or absolute paths."""
    rel = PurePosixPath(relative)
    drive_letter = len(relative) >= 2 and relative[1] == ":"
    if rel.is_absolute() or ".." in rel.parts or drive_letter:
        raise ValueError(f"Unsafe path: {relative}")
    dest = (base_dir / Path(*rel.parts)).resolve()
    try:
        dest.relative_to(base_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Unsafe path: {relative}") from exc
    return dest


def _rel_under_root(arcname: str, root: str) -> str:
    if not root:
        return arcname
    if arcname == root:
        return _basename(arcname)
    if arcname.startswith(root + "/"):
        return arcname[len(root) + 1:]
    return _basename(arcname)


def _rom_dest_name(asset: DetectedAsset, source_name: str) -> tuple[str, str]:
    """Return (filename, action) for a ROM asset destination under pinmame/roms."""
    if len(asset.entries) == 1 and PurePosixPath(asset.entries[0].arcname).suffix.lower() == ".zip":
        return _safe_upload_name(_basename(asset.entries[0].arcname)), "copy"
    stem = Path(source_name).stem or "rom"
    return f"{_safe_upload_name(stem)}.zip", "zip_rom"


def _patched_vpx_name(asset: DetectedAsset, base: Path, vpx_stem: str) -> str:
    """The filename applying this patch will produce.

    The patch's own name, so a mod's sidecars and artwork still match it by stem. Tagged
    only where that would land on a .vpx already here: never overwrite the base, which is
    the one file the result cannot be rebuilt without.
    """
    name = _safe_upload_name(Path(_basename(asset.entries[0].arcname)).stem)
    # Case-insensitively: on macOS and Windows "table.vpx" IS "Table.vpx".
    if name.lower() == vpx_stem.lower() or (base / f"{name}.vpx").exists():
        name = f"{name} [patched]"
    return f"{name}.vpx"


def _sidecar_stem(assets, base: Path, vpx_stem: str) -> str:
    """Which game file a bundle's .directb2s and .ini belong to: the patched table when the
    bundle carries a patch, since they describe what the patch produces, not the base.

    Deselecting the patch afterwards leaves them named for a .vpx that never gets built.
    """
    for asset in assets:
        if asset.kind == "patch" and vpx_stem:
            return Path(_patched_vpx_name(asset, base, vpx_stem)).stem
    return vpx_stem


def _plan_asset(asset: DetectedAsset, base: Path, vpx_stem: str, rom_name: str,
                source_name: str, game_kind_action: str,
                sidecar_stem: str = "") -> tuple[PlannedItem | None, BlockedItem | None]:
    kind = asset.kind
    spec = spec_for(kind)
    if spec.requires_rom and not rom_name:
        return None, BlockedItem(asset, "Table has no ROM name; import a ROM first")

    if kind == "table":
        dest = base / _safe_upload_name(_basename(asset.entries[0].arcname))
        return PlannedItem(asset, str(dest), game_kind_action), None
    if kind == "table_info":
        # Always written as <folder>.info — the parser matches it by folder name.
        return PlannedItem(asset, str(base / f"{base.name}.info"), "write_info"), None
    if kind == "backglass":
        stem = sidecar_stem or vpx_stem or Path(_basename(asset.entries[0].arcname)).stem
        return PlannedItem(asset, str(base / f"{stem}.directb2s"), "replace_b2s"), None
    if kind == "ini":
        stem = sidecar_stem or vpx_stem or Path(_basename(asset.entries[0].arcname)).stem
        return PlannedItem(asset, str(base / f"{stem}.ini"), "copy"), None
    if kind == "rom":
        name, action = _rom_dest_name(asset, source_name)
        return PlannedItem(asset, str(base / "pinmame" / "roms" / name), action), None
    if kind == "altcolor_serum":
        dest = base / "serum" / rom_name / _safe_upload_name(_basename(asset.entries[0].arcname))
        return PlannedItem(asset, str(dest), "copy"), None
    if kind == "altcolor_vni":
        dest = base / "vni" / rom_name / _safe_upload_name(_basename(asset.entries[0].arcname))
        return PlannedItem(asset, str(dest), "copy"), None
    if kind == "altsound":
        return PlannedItem(asset, str(base / "pinmame" / "altsound" / rom_name), "extract_tree"), None
    if kind == "pup_pack":
        return PlannedItem(asset, str(base / "pupvideos"), "extract_tree"), None
    if kind == "music":
        return PlannedItem(asset, str(base / "music"), "extract_tree"), None
    if kind == "readme":
        name = _safe_upload_name(_basename(asset.entries[0].arcname))
        return PlannedItem(asset, str(base / name), "copy"), None
    if kind == "patch":
        if not vpx_stem:
            return None, BlockedItem(asset, "No table to patch; import the base table first")
        return PlannedItem(asset, str(base / _patched_vpx_name(asset, base, vpx_stem)),
                           "apply_patch"), None
    if kind == "media":
        filename = _MEDIA_FILENAMES.get(asset.media_key, asset.media_key)
        return PlannedItem(asset, str(base / "medias" / filename), "replace_media"), None
    return None, BlockedItem(asset, f"Unsupported asset type: {kind}")


def build_import_plan(analysis: AnalysisResult, *, table_path: str = "", game_row: dict | None = None,
                      rom_name: str = "", allow_new_table: bool = False,
                      games_path: str | None = None) -> ImportPlan:
    """Route detected assets to destinations for an existing table or a new table bundle."""
    items: list[PlannedItem] = []
    blocked: list[BlockedItem] = []
    new_bundle = analysis.has_table and allow_new_table

    if new_bundle:
        game_asset = next(a for a in analysis.assets if a.kind == "table")
        vpx_stem = Path(_basename(game_asset.entries[0].arcname)).stem
        new_dir_name = _safe_upload_name(vpx_stem)
        base = Path(games_path or get_games_path()).expanduser() / new_dir_name
        sidecar_stem = _sidecar_stem(analysis.assets, base, vpx_stem)
        for asset in analysis.assets:
            item, block = _plan_asset(asset, base, vpx_stem, rom_name, analysis.source_name,
                                      game_kind_action="copy", sidecar_stem=sidecar_stem)
            (items if item else blocked).append(item or block)
        return ImportPlan(str(base), new_dir_name, "", tuple(items), tuple(blocked))

    if table_path:
        base = Path(table_path).expanduser()
        try:
            vpx_stem = _find_vpx_file(base).stem
        except (FileNotFoundError, OSError):
            vpx_stem = ""
        # A table dropped onto an existing table replaces its .vpx (the "update table" case).
        # New-table creation is handled by the new_bundle branch above.
        sidecar_stem = _sidecar_stem(analysis.assets, base, vpx_stem)
        for asset in analysis.assets:
            item, block = _plan_asset(asset, base, vpx_stem, rom_name, analysis.source_name,
                                      game_kind_action="replace_vpx", sidecar_stem=sidecar_stem)
            (items if item else blocked).append(item or block)
        return ImportPlan(str(base), "", rom_name, tuple(items), tuple(blocked))

    for asset in analysis.assets:
        if spec_for(asset.kind).requires_game:
            blocked.append(BlockedItem(asset, "Select a table row, or drop onto a table's detail dialog"))
        else:
            blocked.append(BlockedItem(asset, "Drop onto the Tables page to import as a new table"))
    return ImportPlan("", "", rom_name, (), tuple(blocked))


def build_media_slot_plan(source_path: Path, *, table_path: str, media_key: str) -> ImportPlan:
    """Plan a targeted media-slot import from a single dropped file.

    The slot dictates the media key (no filename inference); the file only has to
    belong to the slot's family (image slots take images, video slots .mp4, audio .mp3).
    Unsuitable drops come back as a blocked item with the reason.
    """
    canonical = _MEDIA_FILENAMES.get(media_key)
    if canonical is None:
        raise ValueError(f"Unknown media slot: {media_key}")
    src = Path(source_path)
    try:
        size = src.stat().st_size
    except OSError:
        size = 0
    entry = SourceEntry(src.name, src.name, size, False)
    asset = DetectedAsset("media", "Media", (entry,), media_key=media_key,
                          size=size, detail=f"{src.name} → {media_key}")

    if src.is_dir() or src.suffix.lower() in ARCHIVE_EXTENSIONS:
        blocked = BlockedItem(asset, "Drop a single media file on a slot")
        return ImportPlan(table_path, "", "", (), (blocked,))

    slot_suffix = Path(canonical).suffix.lower()
    suffix = src.suffix.lower()
    if slot_suffix in {".mp4", ".mp3"}:
        suitable = suffix == slot_suffix
        expected = slot_suffix
    else:
        suitable = suffix in IMAGE_EXTENSIONS
        expected = "an image file"
    if not suitable:
        blocked = BlockedItem(asset, f"This slot expects {expected}, not {suffix or 'a file without extension'}")
        return ImportPlan(table_path, "", "", (), (blocked,))

    destination = str(Path(table_path) / "medias" / canonical)
    item = PlannedItem(asset, destination, "replace_media")
    return ImportPlan(table_path, "", "", (item,), ())


def sanitize_dir_name(name: str) -> str:
    """Strip filesystem-reserved characters from a proposed table folder name."""
    return "".join(c for c in (name or "") if c not in '<>:"/\\|?*').strip()


def vps_folder_name(vps_entry: dict) -> str:
    """Derive the canonical table folder name from a VPS entry (same shape the
    Import Table dialog builds: "Name (Manufacturer Year)")."""
    name = vps_entry.get("name", "")
    mfg = vps_entry.get("manufacturer") or vps_entry.get("mfg") or ""
    year = vps_entry.get("year") or ""
    if mfg and year:
        folder = f"{name} ({mfg} {year})"
    elif mfg:
        folder = f"{name} ({mfg})"
    elif year:
        folder = f"{name} ({year})"
    else:
        folder = name
    return sanitize_dir_name(folder)


def find_vps_entry(vps_id: str) -> dict | None:
    """Look up a VPS entry by its id."""
    from managerui.services.game_service import load_vpsdb

    wanted = (vps_id or "").strip()
    if not wanted:
        return None
    for entry in load_vpsdb():
        if entry.get("id") == wanted:
            return entry
    return None


def select_plan_items(plan: ImportPlan, indices: list[int] | None = None,
                      new_table_dir_name: str | None = None) -> ImportPlan:
    """Narrow a plan to the chosen item indices and optionally rename a new-table target.

    indices=None keeps every item. For new-table bundles, passing a new name rebases all
    item destinations under the renamed folder. Shared by the confirm dialog and the HTTP
    import endpoint so both honor selection and rename identically.
    """
    if indices is None:
        chosen = plan.items
    else:
        wanted = set(indices)
        chosen = tuple(item for index, item in enumerate(plan.items) if index in wanted)

    if not plan.new_table_dir_name:
        return replace(plan, items=chosen)

    new_name = sanitize_dir_name(new_table_dir_name) if new_table_dir_name is not None else plan.new_table_dir_name
    if not new_name:
        raise ValueError("Table folder name required")
    if new_name == plan.new_table_dir_name:
        return replace(plan, items=chosen)

    old_base = plan.table_path
    new_base = str(Path(old_base).parent / new_name)
    rebased = tuple(replace(item, destination=item.destination.replace(old_base, new_base, 1)) for item in chosen)
    return replace(plan, table_path=new_base, new_table_dir_name=new_name, items=rebased)


# Medias stays listed although nothing writes it any more: an imported .info written by
# a 2.x build still carries one, and dropping it from here would let it back in as an
# unmanaged section and be preserved forever.
_MANAGED_INFO_SECTIONS = {"Info", "User", VPINFE_SECTION, "game_files", "assets", "Medias"}
_MACHINE_LOCAL_INFO_KEYS = {"alt_launcher", "plugin_profile"}


def _is_empty_value(value) -> bool:
    return value in (None, "", 0, [], {})


def _resolves_locally(key: str, value) -> bool:
    """Machine-specific override values must exist on this machine to be adopted."""
    text = str(value or "")
    if not text:
        return False
    if key == "alt_launcher":
        return Path(text).expanduser().exists()
    if key == "plugin_profile":
        from managerui.paths import PLUGIN_PROFILES_DIR

        try:
            return any(p.stem == text or p.name == text for p in Path(PLUGIN_PROFILES_DIR).iterdir())
        except OSError:
            return False
    return True


def merge_info(incoming: dict, existing: dict) -> dict:
    """Merge an imported .info into an existing one: fill gaps, never replace.

    Info is adopted wholesale only when the existing table has no VPS association.
    User and VPinFE fill empty fields (machine-specific overrides only if they resolve
    locally). game_files and assets always keep the local version: game_files describes
    the builds on THIS disk and carries decisions made here — what is hidden, what has
    been patched, and later play stats — none of which an imported file can speak for.
    assets records what we placed in THIS folder, so an imported list describes files
    that are not here. Unknown sections are added when absent, never replaced.
    """
    merged = dict(existing)

    for section, value in incoming.items():
        if section not in merged and section not in _MANAGED_INFO_SECTIONS:
            merged[section] = value

    if not (existing.get("Info") or {}).get("VPSId") and incoming.get("Info"):
        merged["Info"] = incoming["Info"]

    local_user = dict(existing.get("User") or {})
    for key, value in (incoming.get("User") or {}).items():
        if _is_empty_value(local_user.get(key)) and not _is_empty_value(value):
            local_user[key] = value
    if local_user:
        merged["User"] = local_user

    local_vpinfe = dict(existing.get(VPINFE_SECTION) or {})
    for key, value in (incoming.get(VPINFE_SECTION) or {}).items():
        if not _is_empty_value(local_vpinfe.get(key)) or _is_empty_value(value):
            continue
        if key in _MACHINE_LOCAL_INFO_KEYS and not _resolves_locally(key, value):
            continue
        local_vpinfe[key] = value
    if local_vpinfe:
        merged[VPINFE_SECTION] = local_vpinfe

    return merged


def _import_game_info(source, asset: DetectedAsset, base: Path) -> None:
    import json

    entry = asset.entries[0]
    with tempfile.TemporaryDirectory() as scratch:
        staged = Path(scratch) / "bundle.info"
        source.extract_member(entry.path, staged)
        incoming = json.loads(staged.read_text(encoding="utf-8"))
    if not isinstance(incoming, dict):
        raise ValueError("Bundle .info is not valid metadata")

    dest = base / f"{base.name}.info"
    if dest.exists():
        try:
            existing = json.loads(dest.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Existing .info is unreadable; treating as empty: %s", dest)
            existing = {}
        if not isinstance(existing, dict):
            existing = {}
        shutil.copy2(dest, dest.with_name(dest.name + ".bak"))
        payload = merge_info(incoming, existing)
    else:
        payload = incoming

    tmp = dest.with_name(f".{dest.name}.uploading")
    tmp.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    os.replace(tmp, dest)


# --- Execution -------------------------------------------------------------

def _extract_replace(source, entry: SourceEntry, dest: Path) -> None:
    ensure_dir(dest.parent)
    tmp = dest.with_name(f".{dest.name}.uploading")
    source.extract_member(entry.path, tmp)
    os.replace(tmp, dest)


def _replace_vpx_from_file(source, asset: DetectedAsset, base: Path) -> None:
    entry = asset.entries[0]
    safe = _safe_upload_name(_basename(entry.arcname))
    if not safe.lower().endswith(".vpx"):
        raise ValueError("Only .vpx files can update the table file")
    new_vpx = base / safe
    try:
        old_vpx = _find_vpx_file(base)
    except FileNotFoundError:
        old_vpx = None
    old_b2s = _find_directb2s_file(base, old_vpx.stem) if old_vpx else None
    old_ini = _find_ini_file(base, old_vpx.stem) if old_vpx else None

    tmp = new_vpx.with_name(f".{new_vpx.name}.uploading")
    source.extract_member(entry.path, tmp)
    if old_vpx and old_vpx.resolve() != new_vpx.resolve():
        old_vpx.unlink()
    os.replace(tmp, new_vpx)

    if old_b2s and old_b2s.exists():
        new_b2s = base / f"{new_vpx.stem}.directb2s"
        if old_b2s.resolve() != new_b2s.resolve():
            if new_b2s.exists():
                new_b2s.unlink()
            os.replace(old_b2s, new_b2s)
    _record_replaced_game_file(base, new_vpx,
                           old_vpx.name if old_vpx and old_vpx.name != new_vpx.name else None)

    if old_ini and old_ini.exists():
        new_ini = base / f"{new_vpx.stem}.ini"
        if old_ini.resolve() != new_ini.resolve():
            if new_ini.exists():
                new_ini.unlink()
            os.replace(old_ini, new_ini)
    refresh_game(str(base))


def _build_rom_zip(source, asset: DetectedAsset, dest: Path) -> None:
    ensure_dir(dest.parent)
    tmp = dest.with_name(f".{dest.name}.uploading")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in asset.entries:
            if entry.is_dir:
                continue
            with tempfile.NamedTemporaryFile(delete=False) as handle:
                scratch = Path(handle.name)
            try:
                source.extract_member(entry.path, scratch)
                archive.write(scratch, arcname=_basename(entry.arcname))
            finally:
                scratch.unlink(missing_ok=True)
    os.replace(tmp, dest)


def _extract_tree(source, asset: DetectedAsset, base_dir: Path) -> None:
    for entry in asset.entries:
        if entry.is_dir:
            continue
        rel = _rel_under_root(entry.arcname, asset.root)
        dest = _safe_dest(base_dir, rel)
        source.extract_member(entry.path, dest)


def _import_media(source, asset: DetectedAsset, table_path: Path) -> None:
    entry = asset.entries[0]
    suffix = PurePosixPath(entry.arcname).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        scratch = Path(handle.name)
    try:
        source.extract_member(entry.path, scratch)
        replace_media_file(str(table_path), table_path.name, asset.media_key, str(scratch))
    finally:
        scratch.unlink(missing_ok=True)


def _record_replaced_game_file(game_dir: Path, vpx: Path, removed: str | None) -> None:
    """Describe the new .vpx in the table's .info, and drop the entry for the one it
    replaced. Best effort - the table is on disk either way.
    """
    try:
        meta = MetaConfig(str(game_dir / f"{game_dir.name}.info"))
        parsed = VPXParser().singleFileExtract(str(vpx))
        if parsed or removed:
            meta.replace_game_file(removed, vpx.name, parsed)
    except Exception:
        logger.warning("Replaced the table with %s, but could not record it in the .info",
                       vpx.name, exc_info=True)


def _record_patched_game_file(game_dir: Path, vpx: Path, base_file: str, base_hash: str) -> None:
    """Write the new game file into the table's .info: what it says about itself, and where
    it came from. Best effort - the table is on disk and playable either way.
    """
    try:
        meta = MetaConfig(str(game_dir / f"{game_dir.name}.info"))
        parsed = VPXParser().singleFileExtract(str(vpx))
        if parsed:
            # A failed parse leaves the entry unparsed rather than filled with empties.
            meta.refresh_game_file(vpx.name, parsed)
        meta.record_patch_source(vpx.name, base_file, base_hash, "jojodiff")
    except Exception:
        logger.warning("Patched %s, but could not record it in the .info", vpx.name,
                       exc_info=True)


def _apply_patch(source, asset: DetectedAsset, base: Path, dest: Path) -> None:
    """Apply a .dif to the table already in this folder, writing a new .vpx beside it.

    The base is chosen by size: a patch is built against the real table, and a folder can
    hold small helper .vpx files. Getting this wrong produces a corrupt result rather than
    an error, so the base is recorded by name and hash - in the log for whoever has to work
    out what happened, and in the .info because the result cannot be rebuilt without it.
    """
    from common.jdiffpatch import PatchError, apply_patch

    candidates = sorted(base.glob("*.vpx"), key=lambda p: p.stat().st_size, reverse=True)
    candidates = [c for c in candidates if c != dest]
    if not candidates:
        raise ValueError("No table in this folder to patch")
    original = candidates[0]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".dif") as tmp:
        patch_tmp = Path(tmp.name)
    try:
        _extract_replace(source, asset.entries[0], patch_tmp)
        with open(original, "rb") as src, open(patch_tmp, "rb") as pat, open(dest, "wb") as out:
            try:
                apply_patch(src, pat, out)
            except PatchError as exc:
                dest.unlink(missing_ok=True)
                raise ValueError(
                    f"Patch does not apply to \"{original.name}\". A .dif is built against "
                    f"one exact table; this is probably not that table. ({exc})") from exc
        base_hash = _sha256(original)
        logger.info("Patched %s -> %s (base sha256 %s)", original.name, dest.name,
                    base_hash[:16])
        _record_patched_game_file(base, dest, original.name, base_hash)
    finally:
        patch_tmp.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def execute_import_plan(plan: ImportPlan, source_path: Path,
                        *, progress_cb: Callable[[str], None] | None = None) -> dict:
    """Execute an import plan, streaming each asset from source_path to its destination."""
    base = Path(plan.table_path)
    if plan.new_table_dir_name:
        if base.exists():
            raise ValueError(f"Table folder already exists: {base.name}")
        base.mkdir(parents=True)

    source = open_source(Path(source_path))
    imported: list[str] = []
    media_keys: list[str] = []
    try:
        for item in plan.items:
            if progress_cb:
                progress_cb(spec_for(item.asset.kind).label)
            dest = Path(item.destination)
            if item.action == "replace_vpx":
                _replace_vpx_from_file(source, item.asset, base)
            elif item.action == "replace_b2s":
                _extract_replace(source, item.asset.entries[0], dest)
            elif item.action == "copy":
                _extract_replace(source, item.asset.entries[0], dest)
            elif item.action == "apply_patch":
                _apply_patch(source, item.asset, base, dest)
            elif item.action == "zip_rom":
                _build_rom_zip(source, item.asset, dest)
            elif item.action == "extract_tree":
                _extract_tree(source, item.asset, dest)
            elif item.action == "write_info":
                _import_game_info(source, item.asset, base)
            elif item.action == "replace_media":
                _import_media(source, item.asset, base)
                media_keys.append(item.asset.media_key)
            else:
                raise ValueError(f"Unknown import action: {item.action}")
            imported.append(item.asset.kind)
    except Exception as exc:
        if _is_rar_exec_error(exc):
            raise ValueError("RAR extraction requires the 'unar' or 'unrar' tool to be installed") from exc
        raise
    finally:
        source.close()

    return {
        "imported": imported,
        "skipped": [b.asset.kind for b in plan.blocked],
        "table_path": str(base),
        "new_table": bool(plan.new_table_dir_name),
        "media_keys": media_keys,
    }
