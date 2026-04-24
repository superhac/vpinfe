from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from clioptions import buildMetaData, vpxPatches
from common.iniconfig import IniConfig
from common.table_repository import get_missing_tables, get_table_rows, refresh_table
from common.vpxcollections import VPXCollections
from common.vpxparser import VPXParser

from managerui.paths import COLLECTIONS_PATH, VPINFE_INI_PATH, get_tables_path
from managerui.services import table_index_service


logger = logging.getLogger("vpinfe.manager.table_service")

VPSDB_JSON_PATH = VPINFE_INI_PATH.parent / "vpsdb.json"
_INI_CFG = IniConfig(str(VPINFE_INI_PATH))
_vpsdb_cache: Optional[List[Dict]] = None


def normalize_table_rating(value) -> int:
    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        normalized = 0
    return max(0, min(5, normalized))


def ensure_vpsdb_downloaded() -> bool:
    global _vpsdb_cache
    from common.vpsdb import VPSdb
    try:
        VPSdb(_INI_CFG.config["Settings"]["tablerootdir"], _INI_CFG)
        _vpsdb_cache = None
        return VPSDB_JSON_PATH.exists()
    except Exception as e:
        logger.error("Failed to ensure vpsdb: %s", e)
        return VPSDB_JSON_PATH.exists()


def get_vpsid_collections_map() -> Dict[str, List[str]]:
    vpsid_to_collections: Dict[str, List[str]] = {}
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        for collection_name in collections.get_collections_name():
            if collections.is_filter_based(collection_name):
                continue
            try:
                for vpsid in collections.get_vpsids(collection_name):
                    vpsid_to_collections.setdefault(vpsid, []).append(collection_name)
            except Exception:
                pass
    except Exception:
        pass
    return vpsid_to_collections


def get_vpsid_collections() -> List[str]:
    result = []
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        for collection_name in collections.get_collections_name():
            if not collections.is_filter_based(collection_name):
                result.append(collection_name)
    except Exception:
        pass
    return result


def add_table_to_collection(vpsid: str, collection_name: str) -> bool:
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        collections.add_vpsid(collection_name, vpsid)
        collections.save()
        return True
    except Exception as e:
        logger.error("Failed to add table to collection: %s", e)
        return False


def update_info_section(table_path: str, section: str, key: str, value) -> bool:
    try:
        table_dir = Path(table_path)
        info_file = table_dir / f"{table_dir.name}.info"
        if not info_file.exists():
            logger.error("Info file not found: %s", info_file)
            return False

        data = json.loads(info_file.read_text(encoding="utf-8"))
        data.setdefault(section, {})[key] = value
        info_file.write_text(json.dumps(data, indent=4), encoding="utf-8")
        refresh_table(table_path)
        return True
    except Exception as e:
        logger.error("Failed to update %s.%s: %s", section, key, e)
        return False


def update_vpinfe_setting(table_path: str, key: str, value) -> bool:
    return update_info_section(table_path, "VPinFE", key, value)


def update_user_setting(table_path: str, key: str, value) -> bool:
    return update_info_section(table_path, "User", key, value)


def load_vpsdb() -> List[Dict]:
    global _vpsdb_cache
    if _vpsdb_cache is not None:
        return _vpsdb_cache
    try:
        data = json.loads(VPSDB_JSON_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            _vpsdb_cache = data
        else:
            _vpsdb_cache = data.get("tables") or data.get("items") or []
    except Exception as e:
        logger.error("Failed to load vpsdb.json: %s", e)
        _vpsdb_cache = []
    return _vpsdb_cache


def search_vpsdb(term: str, limit: int = 50) -> List[Dict]:
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


def associate_vps_to_folder(
    table_folder: Path,
    vps_entry: Dict,
    download_media: bool = False,
    user_media: bool = False,
) -> None:
    from common.metaconfig import MetaConfig

    if not table_folder.exists():
        raise FileNotFoundError(f"Folder not found: {table_folder}")

    vpx_files = sorted([path for path in table_folder.glob("*.vpx")])
    if not vpx_files:
        vpx_files = sorted([path for path in table_folder.rglob("*.vpx") if path.parent == table_folder])
    if not vpx_files:
        raise FileNotFoundError(f"No .vpx found in {table_folder}")

    vpx_file = vpx_files[0]
    parser = VPXParser()
    vpxdata = parser.singleFileExtract(str(vpx_file))

    meta_path = table_folder / f"{table_folder.name}.info"
    meta = MetaConfig(str(meta_path))
    meta.writeConfigMeta({"vpsdata": vps_entry, "vpxdata": vpxdata})

    if user_media:
        from clioptions import _claimMediaForTable
        from common.table import Table

        tabletype = _INI_CFG.config["Media"].get("tabletype", "table").lower()
        pseudo = Table()
        pseudo.tableDirName = table_folder.name
        pseudo.fullPathTable = str(table_folder)
        _claimMediaForTable(pseudo, tabletype)
        meta = MetaConfig(str(meta_path))

    if download_media or user_media:
        from common.vpsdb import VPSdb

        vps = VPSdb(_INI_CFG.config["Settings"]["tablerootdir"], _INI_CFG)

        class _LightTable:
            def __init__(self, folder: Path, vpx: Path):
                self.tableDirName = folder.name
                self.fullPathTable = str(folder)
                self.fullPathVPXfile = str(vpx)
                self.BGImagePath = None
                self.DMDImagePath = None
                self.TableImagePath = None
                self.WheelImagePath = None
                self.CabImagePath = None
                self.realDMDImagePath = None
                self.realDMDColorImagePath = None
                self.FlyerImagePath = None
                self.TableVideoPath = None
                self.BGVideoPath = None
                self.DMDVideoPath = None
                self.AudioPath = None

        vps.downloadMediaForTable(_LightTable(table_folder, vpx_file), vps_entry.get("id"), metaConfig=meta)

    from managerui.services.media_service import invalidate_media_cache
    invalidate_media_cache()
    refresh_table(str(table_folder))


def scan_table_rows(reload: bool = False) -> List[Dict]:
    return table_index_service.scan_rows(reload=reload)


def scan_missing_table_rows(reload: bool = False) -> List[Dict]:
    return table_index_service.scan_missing_rows(reload=reload)


def build_metadata(*args, **kwargs):
    return buildMetaData(*args, **kwargs)


def apply_vpx_patches(*args, **kwargs):
    return vpxPatches(*args, **kwargs)
