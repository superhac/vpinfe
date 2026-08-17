"""What the Manager UI does to a game: rate it, re-match it, put it in a collection."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from common import jobs
from common.config_access import SettingsConfig, cfg_get
from common.config_store import ConfigStore
from common.games import game_index_service, game_repository, info_maintenance, metadata_service
from common.games.collection_store import CollectionStore
from common.games.game_metadata import vpinfe_section
from common.games.game_repository import refresh_game
from common.games.info_file import VPINFE_SECTION
from common.games.tables import default_table, recorded_default, table_entries
from common.games.vpx_parser import VPXParser
from common.paths import COLLECTIONS_PATH, CONFIG_DIR, VPINFE_INI_PATH, get_games_path

logger = logging.getLogger("vpinfe.manager.game_service")

VPSDB_JSON_PATH = VPINFE_INI_PATH.parent / "vpsdb.json"
_vpsdb_cache: list[dict] | None = None


def _fresh_config() -> ConfigStore:
    return ConfigStore(str(VPINFE_INI_PATH))


def normalize_game_rating(value) -> int:
    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        normalized = 0
    return max(0, min(5, normalized))


def ensure_vpsdb_downloaded() -> bool:
    global _vpsdb_cache
    from common.online.vpsdb import VPSdb
    try:
        config = _fresh_config()
        VPSdb(SettingsConfig.from_config(config).game_root_dir, config)
        _vpsdb_cache = None
        return VPSDB_JSON_PATH.exists()
    except Exception as e:
        logger.error("Failed to ensure vpsdb: %s", e)
        return VPSDB_JSON_PATH.exists()


def get_game_collections_map() -> dict[str, list[str]]:
    return game_repository.collections_by_game_id()


def get_game_collections() -> list[str]:
    result = []
    try:
        collections = CollectionStore(str(COLLECTIONS_PATH))
        for collection_name in collections.get_collections_name():
            if not collections.is_filter_based(collection_name):
                result.append(collection_name)
    except Exception:
        pass
    return result


def add_game_to_collection(game_id: str, collection_name: str) -> bool:
    try:
        collections = CollectionStore(str(COLLECTIONS_PATH))
        collections.add_member(collection_name, game_id)
        collections.save()
        return True
    except Exception as e:
        logger.error("Failed to add game to collection: %s", e)
        return False


def update_info_section(game_dir: Path, section: str, key: str, value) -> bool:
    try:
        info_file = game_dir / f"{game_dir.name}.info"
        if not info_file.exists():
            logger.error("Info file not found: %s", info_file)
            return False

        data = json.loads(info_file.read_text(encoding="utf-8"))
        data.setdefault(section, {})[key] = value
        info_file.write_text(json.dumps(data, indent=4), encoding="utf-8")
        refresh_game(game_dir)
        return True
    except Exception as e:
        logger.error("Failed to update %s.%s: %s", section, key, e)
        return False


def update_vpinfe_setting(game_dir: Path, key: str, value) -> bool:
    return update_info_section(game_dir, VPINFE_SECTION, key, value)


def update_user_setting(game_dir: Path, key: str, value) -> bool:
    return update_info_section(game_dir, "User", key, value)


def load_vpsdb() -> list[dict]:
    global _vpsdb_cache
    if _vpsdb_cache is not None:
        return _vpsdb_cache
    try:
        data = json.loads(VPSDB_JSON_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            _vpsdb_cache = data
        else:
            _vpsdb_cache = data.get("games") or data.get("items") or []
    except Exception as e:
        logger.error("Failed to load vpsdb.json: %s", e)
        _vpsdb_cache = []
    return _vpsdb_cache


def search_vpsdb(term: str, limit: int = 50) -> list[dict]:
    term = (term or "").strip().lower()
    if not term:
        return []
    results = []
    for item in load_vpsdb():
        if term in (item.get("name") or "").lower():
            results.append(item)
        if len(results) >= limit:
            break
    return results


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_upload_bytes(dest_file: Path, content: bytes) -> None:
    ensure_dir(dest_file.parent)
    dest_file.write_bytes(content)


def _safe_upload_name(filename: str) -> str:
    safe_name = Path(filename or "").name
    if not safe_name or safe_name in {".", ".."}:
        raise ValueError("Invalid upload filename")
    return safe_name


def _find_vpx_file(game_dir: Path, preferred_filename: str = "") -> Path:
    names = [path.name for path in game_dir.iterdir() if path.is_file()]
    chosen = default_table(names, game_dir.name, Path(preferred_filename or "").name)
    if not chosen:
        raise FileNotFoundError(f"No .vpx found in {game_dir}")
    return game_dir / chosen


def _find_directb2s_file(game_dir: Path, preferred_stem: str = "") -> Path | None:
    b2s_files = sorted(path for path in game_dir.iterdir() if path.is_file() and path.suffix.lower() == ".directb2s")
    if not b2s_files:
        return None

    preferred_stem_lower = preferred_stem.lower()
    if preferred_stem_lower:
        for path in b2s_files:
            if path.stem.lower() == preferred_stem_lower:
                return path
    return b2s_files[0]


def _find_ini_file(game_dir: Path, preferred_stem: str = "") -> Path | None:
    ini_files = sorted(path for path in game_dir.iterdir() if path.is_file() and path.suffix.lower() == ".ini")
    if not ini_files:
        return None

    preferred_stem_lower = preferred_stem.lower()
    if preferred_stem_lower:
        for path in ini_files:
            if path.stem.lower() == preferred_stem_lower:
                return path
    return ini_files[0]


def _write_replace(dest_file: Path, content: bytes) -> None:
    ensure_dir(dest_file.parent)
    tmp_file = dest_file.with_name(f".{dest_file.name}.uploading")
    tmp_file.write_bytes(content)
    os.replace(tmp_file, dest_file)


def replace_table(game_dir: Path, filename: str, content: bytes, file_type: str,
                  current_vpx_filename: str = "") -> dict[str, str]:
    game_dir = game_dir.expanduser()
    if not game_dir.exists() or not game_dir.is_dir():
        raise FileNotFoundError(f"Table folder not found: {game_dir}")

    safe_name = _safe_upload_name(filename)
    ext = Path(safe_name).suffix.lower()

    if file_type == "vpx":
        if ext != ".vpx":
            raise ValueError("Only .vpx files can update the table file")

        old_vpx = _find_vpx_file(game_dir, current_vpx_filename)
        new_vpx = game_dir / safe_name
        old_b2s = _find_directb2s_file(game_dir, old_vpx.stem)
        old_ini = _find_ini_file(game_dir, old_vpx.stem)

        if old_vpx.resolve() == new_vpx.resolve():
            _write_replace(new_vpx, content)
        else:
            tmp_file = new_vpx.with_name(f".{new_vpx.name}.uploading")
            tmp_file.write_bytes(content)
            old_vpx.unlink()
            os.replace(tmp_file, new_vpx)

        renamed_b2s = ""
        if old_b2s and old_b2s.exists():
            new_b2s = game_dir / f"{new_vpx.stem}.directb2s"
            if old_b2s.resolve() != new_b2s.resolve():
                if new_b2s.exists():
                    new_b2s.unlink()
                os.replace(old_b2s, new_b2s)
            renamed_b2s = new_b2s.name

        renamed_ini = ""
        if old_ini and old_ini.exists():
            new_ini = game_dir / f"{new_vpx.stem}.ini"
            if old_ini.resolve() != new_ini.resolve():
                if new_ini.exists():
                    new_ini.unlink()
                os.replace(old_ini, new_ini)
            renamed_ini = new_ini.name

        refresh_game(game_dir)
        return {
            "file_type": "vpx",
            "filename": new_vpx.name,
            "game_dir": str(game_dir),
            "directb2s_filename": renamed_b2s,
            "ini_filename": renamed_ini,
        }

    if file_type == "directb2s":
        if ext != ".directb2s":
            raise ValueError("Only .directb2s files can update the backglass file")

        current_vpx = _find_vpx_file(game_dir, current_vpx_filename)
        old_b2s = _find_directb2s_file(game_dir, current_vpx.stem)
        target_b2s = old_b2s if old_b2s else game_dir / f"{current_vpx.stem}.directb2s"
        _write_replace(target_b2s, content)

        refresh_game(game_dir)
        return {
            "file_type": "directb2s",
            "filename": target_b2s.name,
            "game_dir": str(game_dir),
        }

    raise ValueError("Unsupported table update type")


def associate_vps_to_folder(
    game_dir: Path,
    vps_entry: dict,
    download_media: bool = False,
) -> None:
    from common.games.info_file import MetaConfig

    if not game_dir.exists():
        raise FileNotFoundError(f"Folder not found: {game_dir}")

    meta_path = game_dir / f"{game_dir.name}.info"
    recorded = ""
    if meta_path.exists():
        try:
            meta = MetaConfig(str(meta_path)).data
            recorded = recorded_default(vpinfe_section(meta), table_entries(meta))
        except Exception:
            recorded = ""

    vpx_file = _find_vpx_file(game_dir, recorded)
    parser = VPXParser()
    vpxdata = parser.singleFileExtract(str(vpx_file))

    meta = MetaConfig(str(meta_path))
    meta.write_config_meta({"vpsdata": vps_entry, "vpxdata": vpxdata})

    if download_media:
        from common.online.vpsdb import VPSdb

        config = _fresh_config()
        vps = VPSdb(SettingsConfig.from_config(config).game_root_dir, config)

        class _LightGame:
            def __init__(self, folder: Path, vpx: Path):
                self.gameDirName = folder.name
                self.fullPathGame = str(folder)
                self.fullPathVPXfile = str(vpx)
                self.BGImagePath = None
                self.DMDImagePath = None
                self.PlayfieldImagePath = None
                self.WheelImagePath = None
                self.CabImagePath = None
                self.realDMDImagePath = None
                self.realDMDColorImagePath = None
                self.FlyerImagePath = None
                self.PlayfieldVideoPath = None
                self.BGVideoPath = None
                self.DMDVideoPath = None
                self.AudioPath = None

        vps.downloadMediaForGame(_LightGame(game_dir, vpx_file), vps_entry.get("id"), meta_config=meta)

    from common.games.media_service import invalidate_media_cache
    invalidate_media_cache()
    refresh_game(game_dir)


def scan_game_rows(reload: bool = False) -> list[dict]:
    return game_index_service.scan_rows(reload=reload)


def scan_missing_game_rows(reload: bool = False) -> list[dict]:
    return game_index_service.scan_missing_rows(reload=reload)


def extract_vbs(game_dir: Path, vpx_filename: str, altlauncher: str = "") -> dict:
    """Run the VPX binary with -extractvbs to extract a table's .vbs script.

    VPX writes the extracted .vbs next to the .vpx file (the game's root dir)
    automatically, so we only need to invoke the binary and report the result.

    Returns {'vbs_path': str} on success. Raises on failure.
    """
    import platform as _platform
    import subprocess
    import sys as _sys

    from common.host.launch import get_effective_launcher

    cfg = _fresh_config()
    vpxbin = cfg_get(cfg, 'Settings', 'vpx_bin_path', '')
    meta = {VPINFE_SECTION: {"alt_launcher": (altlauncher or "").strip()}}
    vpxbin_path, source_key, _configured = get_effective_launcher(vpxbin, meta)
    if not vpxbin_path:
        raise RuntimeError("No launcher configured (set Settings.vpxbinpath or VPinFE.altlauncher)")
    if not vpxbin_path.exists():
        raise FileNotFoundError(f"Launcher not found ({source_key}): {vpxbin_path}")

    vpx_file = game_dir / vpx_filename
    if not vpx_file.is_file():
        raise FileNotFoundError(f"Table file not found: {vpx_file}")

    # Match the launch env handling: on frozen Linux builds, restore the
    # original LD_LIBRARY_PATH so VPX does not pick up incompatible bundled libs.
    launch_env = os.environ.copy()
    if _platform.system() == "Linux" and getattr(_sys, "frozen", False):
        lp_orig = launch_env.get('LD_LIBRARY_PATH_ORIG')
        if lp_orig is not None:
            launch_env['LD_LIBRARY_PATH'] = lp_orig

    cmd = [str(vpxbin_path), "-extractvbs", str(vpx_file)]
    logger.info("Extracting VBS: %s", cmd)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=launch_env,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"VPX exited with code {result.returncode}: {detail}")

    vbs_file = vpx_file.with_suffix('.vbs')
    return {'vbs_path': str(vbs_file), 'vbs_exists': vbs_file.is_file()}


def _scan(job, *args, **kwargs):
    return metadata_service.build_metadata(
        *args, iniconfig=_fresh_config(),
        progress_cb=job.progress, log_cb=job.log, **kwargs)


def build_metadata(*args, progress_cb=None, log_cb=None, job=None, **kwargs):
    """A library scan is a job wherever it was started from.

    Routing the Manager UI's own scan through the registry costs it nothing - it
    keeps its callbacks and its return value - and buys two things: the scan reaches
    the event stream, and it shares the one-at-a-time rule with the API instead of
    the two paths being able to rewrite the same .info files at once.

    `job` is for a caller that already registered one; without it this call owns the
    registration, which is what makes the Manager UI's existing call site work
    unchanged.
    """
    if job is not None:
        return _scan(job, *args, **kwargs)
    with jobs.track(jobs.KIND_LIBRARY_SCAN, progress_cb=progress_cb, log_cb=log_cb) as tracked:
        return _scan(tracked, *args, **kwargs)


def info_maintenance_counts(reload: bool = False):
    """What the Tables page needs to decide whether to offer upgrade or a restore."""
    return game_repository.info_maintenance_counts(reload=reload)


def unreadable_games():
    return game_repository.unreadable_games()


def pending_upgrade_game_names():
    return game_repository.pending_upgrade_game_names()


def newest_backup_stamp():
    return game_repository.newest_backup_stamp()


def collections_restorable():
    """Whether a newer VPinFE left a collections file this build can put back."""
    from common.games.collection_store import restorable_collections_backup

    return bool(restorable_collections_backup(CONFIG_DIR))


def restorable_game_names():
    return game_repository.restorable_game_names()


def upgrade_info(progress_cb=None, log_cb=None, **kwargs):
    """Upgrade every game's .info in one pass.

    Registered as a library scan rather than a kind of its own: the point of the kind is
    that two things rewriting the same .info files must not overlap, and this rewrites
    exactly the files a scan does.
    """
    with jobs.track(jobs.KIND_LIBRARY_SCAN, progress_cb=progress_cb, log_cb=log_cb) as job:
        result = info_maintenance.upgrade_library(
            get_games_path(), progress_cb=job.progress, log_cb=job.log, **kwargs)
    game_repository.refresh_games()
    return result


def restore_info(progress_cb=None, log_cb=None, **kwargs):
    """Put back the .info files saved before upgrade, for every game that has one."""
    with jobs.track(jobs.KIND_LIBRARY_SCAN, progress_cb=progress_cb, log_cb=log_cb) as job:
        result = info_maintenance.restore_library(
            get_games_path(), config_dir=CONFIG_DIR,
            progress_cb=job.progress, log_cb=job.log, **kwargs)
    game_repository.refresh_games()
    return result


def apply_vpx_patches(*args, **kwargs):
    return metadata_service.apply_vpx_patches(*args, iniconfig=_fresh_config(), **kwargs)
