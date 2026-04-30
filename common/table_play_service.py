from __future__ import annotations

import logging
import time
from copy import deepcopy
from pathlib import Path

from common.collections_service import get_collections_manager
from common.table_metadata import (
    get_or_create_user_meta,
    load_table_meta,
    normalize_meta,
    persist_table_meta,
    section,
)


logger = logging.getLogger("vpinfe.common.table_play_service")


def track_table_play(table, collection_name: str = "Last Played", max_items: int = 30) -> None:
    meta = normalize_meta(getattr(table, "metaConfig", {}))
    vpsid = section(meta, "Info").get("VPSId")
    if not vpsid:
        logger.debug("Table has no VPSId, cannot track play")
        return

    collections = get_collections_manager()
    if collection_name not in collections.get_collections_name():
        logger.info("Creating '%s' collection", collection_name)
        collections.add_collection(collection_name, vpsids=[])

    ids = collections.get_vpsids(collection_name)
    if vpsid in ids:
        ids.remove(vpsid)
    ids.insert(0, vpsid)
    collections.config[collection_name]["vpsids"] = ",".join(ids[:max_items])
    collections.save()
    logger.info("Tracked table play: %s (now %s in %s)", vpsid, len(ids[:max_items]), collection_name)


def increment_start_count(table) -> None:
    config = clone_table_meta(table)
    if not config:
        logger.warning("Could not increment StartCount: invalid table metadata for %s", table.tableDirName)
        return

    user = apply_start_count_update(config)
    persist_table_meta(table, config)
    logger.info("Updated User.StartCount for %s -> %s", table.tableDirName, user["StartCount"])


def add_runtime_minutes(table, elapsed_seconds: float) -> None:
    config = clone_table_meta(table)
    if not config:
        logger.warning("Could not update RunTime: invalid table metadata for %s", table.tableDirName)
        return

    user = apply_runtime_update(config, elapsed_seconds)
    persist_table_meta(table, config)
    logger.info(
        "Updated User.RunTime for %s: +%s min (total=%s)",
        table.tableDirName,
        int((elapsed_seconds + 59) // 60),
        user["RunTime"],
    )


def clone_table_meta(table) -> dict:
    config = load_table_meta(table)
    return deepcopy(config) if isinstance(config, dict) else {}


def apply_start_count_update(config: dict, played_at: int | None = None) -> dict:
    user = get_or_create_user_meta(config)
    try:
        user["StartCount"] = int(user.get("StartCount", 0)) + 1
    except (TypeError, ValueError):
        user["StartCount"] = 1
    user["LastRun"] = int(played_at or time.time())
    return user


def apply_runtime_update(config: dict, elapsed_seconds: float) -> dict:
    session_minutes = int((elapsed_seconds + 59) // 60)
    user = get_or_create_user_meta(config)
    try:
        prior_runtime = int(user.get("RunTime", 0))
    except (TypeError, ValueError):
        prior_runtime = 0
    user["RunTime"] = prior_runtime + session_minutes
    return user


def parse_score_from_nvram(table) -> tuple[dict | None, str | None]:
    config = clone_table_meta(table)
    if not config:
        logger.warning("Could not parse Score: invalid table metadata for %s", table.tableDirName)
        return None, None

    rom = str(section(config, "Info").get("Rom", "") or "").strip()
    if not rom:
        logger.debug("No ROM name found for %s, skipping score update", table.tableDirName)
        return None, None

    try:
        from common.score_parser import read_rom_with_source, result_to_jsonable

        parsed_result, score_path = read_rom_with_source(rom, table.fullPathTable)
        score_data = result_to_jsonable(rom, parsed_result, score_path)
    except FileNotFoundError:
        logger.debug("No score source found for %s and ROM %s", table.tableDirName, rom)
        return None, None
    except KeyError:
        logger.debug("ROM %s is not supported for score parsing", rom)
        return None, None
    except Exception:
        logger.exception("Failed to parse score data for %s", table.tableDirName)
        return None, None

    if not score_data:
        logger.debug("Parsed score data for %s was empty, skipping metadata update", table.tableDirName)
        return None, None

    return score_data, score_path


def apply_score_update(config: dict, score_data: dict) -> dict:
    user = get_or_create_user_meta(config)
    user["Score"] = score_data
    return user


def build_runtime_submission_meta(table, user_state: dict) -> dict:
    config = clone_table_meta(table)
    if not config:
        logger.warning("Could not build runtime submission metadata for %s", table.tableDirName)
        return {}

    user = get_or_create_user_meta(config)
    user.clear()
    user.update(
        {
            "Rating": 0,
            "Favorite": 0,
            "LastRun": user_state.get("LastRun"),
            "StartCount": user_state.get("StartCount", 0),
            "RunTime": user_state.get("RunTime", 0),
            "Tags": [],
            "FrontendDOFEvent": "",
        }
    )
    if user_state.get("Score") is not None:
        user["Score"] = user_state.get("Score")
    return config


def update_score_from_nvram(table) -> None:
    config = clone_table_meta(table)
    if not config:
        logger.warning("Could not update Score: invalid table metadata for %s", table.tableDirName)
        return

    score_data, score_path = parse_score_from_nvram(table)
    if not score_data:
        return

    apply_score_update(config, score_data)
    persist_table_meta(table, config)
    logger.info("Updated User.Score for %s from %s", table.tableDirName, score_path)


def delete_nvram_if_configured(table) -> None:
    config = normalize_meta(getattr(table, "metaConfig", {}))
    vpinfe = section(config, "VPinFE")
    if not vpinfe.get("deletedNVRamOnClose", False):
        return

    rom = section(config, "Info").get("Rom", "")
    if not rom:
        logger.warning("No ROM name found for table, skipping NVRAM deletion")
        return

    nvram_path = Path(table.fullPathTable) / "pinmame" / "nvram" / f"{rom}.nv"
    if nvram_path.exists():
        nvram_path.unlink()
        logger.info("Deleted NVRAM file: %s", nvram_path)
    else:
        logger.info("NVRAM file not found (nothing to delete): %s", nvram_path)
