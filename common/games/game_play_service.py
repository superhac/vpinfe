from __future__ import annotations

import logging
import time
from copy import deepcopy
from pathlib import Path

from common.games import game_identity
from common.games.collections_service import get_collections_manager
from common.games.game_metadata import (
    default_table_entry,
    get_or_create_table_user,
    get_or_create_user_meta,
    load_game_meta,
    normalize_meta,
    persist_game_meta,
    section,
    vpinfe_section,
)
from common.games.collection_store import MEMBERS_KEY
from common.timestamps import epoch_to_iso

logger = logging.getLogger("vpinfe.common.games.game_play_service")


def track_game_play(game, collection_name: str = "Last Played", max_items: int = 30) -> None:
    meta = normalize_meta(getattr(game, "meta_config", {}))
    # Membership is the game's own id; VPSId is a fallback for a game that has
    # not been assigned one yet.
    member_id = game_identity.game_id(game) or section(meta, "Info").get("VPSId")
    if not member_id:
        logger.debug("Game has no id, cannot track play")
        return

    collections = get_collections_manager()
    if collection_name not in collections.get_collections_name():
        logger.info("Creating '%s' collection", collection_name)
        collections.add_collection(collection_name, members=[])

    # Most-recent-first and capped, so this writes the list rather than using
    # add_member - order carries the meaning here.
    ids = collections.get_members(collection_name)
    if member_id in ids:
        ids.remove(member_id)
    ids.insert(0, member_id)
    collections.set_members(collection_name, ids[:max_items])
    collections.save()
    logger.info("Tracked game play: %s (now %s in %s)", member_id, len(ids[:max_items]), collection_name)


def increment_start_count(game, table: str = "") -> None:
    config = clone_game_meta(game)
    if not config:
        logger.warning("Could not increment StartCount: invalid game metadata for %s", game.gameDirName)
        return

    user = apply_start_count_update(config, table=table)
    persist_game_meta(game, config)
    logger.debug("Updated User.StartCount for %s -> %s", game.gameDirName, user["StartCount"])


def add_runtime_minutes(game, elapsed_seconds: float, table: str = "") -> None:
    config = clone_game_meta(game)
    if not config:
        logger.warning("Could not update RunTime: invalid game metadata for %s", game.gameDirName)
        return

    user = apply_runtime_update(config, elapsed_seconds, table=table)
    persist_game_meta(game, config)
    logger.info(
        "Updated User.RunTime for %s: +%s min (total=%s)",
        game.gameDirName,
        int((elapsed_seconds + 59) // 60),
        user["RunTime"],
    )


def clone_game_meta(game) -> dict:
    config = load_game_meta(game)
    return deepcopy(config) if isinstance(config, dict) else {}


def _plus(mapping: dict, key: str, amount: int) -> None:
    try:
        mapping[key] = int(mapping.get(key, 0)) + amount
    except (TypeError, ValueError):
        mapping[key] = amount


def apply_start_count_update(config: dict, played_at: int | None = None,
                             table: str = "") -> dict:
    """Count a launch against the game, and against the table that was launched.

    The two accumulate independently rather than one being a rollup of the other:
    deleting a table would otherwise un-play hours that were played.
    """
    user = get_or_create_user_meta(config)
    _plus(user, "StartCount", 1)
    user["LastRun"] = int(played_at or time.time())

    if table:
        played = get_or_create_table_user(config, table)
        _plus(played, "start_count", 1)
        # ISO, where User.LastRun is an epoch integer it cannot stop being: it is a
        # specced key and goes to the VPinPlay API verbatim. Ours says what it is.
        played["last_run"] = epoch_to_iso(user["LastRun"])
    return user


def apply_runtime_update(config: dict, elapsed_seconds: float, table: str = "") -> dict:
    session_minutes = int((elapsed_seconds + 59) // 60)
    user = get_or_create_user_meta(config)
    _plus(user, "RunTime", session_minutes)
    if table:
        # Seconds, and the name says so. User.RunTime is minutes, undocumented as such
        # and wrong in docs/technical_details.md for as long as it has existed.
        _plus(get_or_create_table_user(config, table), "run_time_seconds",
              int(round(elapsed_seconds)))
    return user


def score_rom_from_meta(config: dict) -> str:
    """The ROM of the table we would launch, or "".

    No fall back to a game-level Info.Rom: the migration drops that key, and a value
    it kept could disagree with the file it claims to describe. A game that has not
    been through a metadata build since has no ROM recorded, which is the truth.
    """
    return str(default_table_entry(config).get("rom", "") or "").strip()


def parse_score_from_nvram(game) -> tuple[dict | None, str | None]:
    config = clone_game_meta(game)
    if not config:
        logger.warning("Could not parse Score: invalid game metadata for %s", game.gameDirName)
        return None, None

    rom = score_rom_from_meta(config)
    if not rom:
        logger.debug("No ROM name found for %s, skipping score update", game.gameDirName)
        return None, None

    try:
        from common.games.score_parser import read_rom_with_source, result_to_jsonable

        parsed_result, score_path = read_rom_with_source(rom, game.fullPathGame)
        score_data = result_to_jsonable(rom, parsed_result, score_path)
    except FileNotFoundError:
        logger.debug("No score source found for %s and ROM %s", game.gameDirName, rom)
        return None, None
    except KeyError:
        logger.debug("ROM %s is not supported for score parsing", rom)
        return None, None
    except Exception:
        logger.exception("Failed to parse score data for %s", game.gameDirName)
        return None, None

    if not score_data:
        logger.debug("Parsed score data for %s was empty, skipping metadata update", game.gameDirName)
        return None, None

    return score_data, score_path


def apply_score_update(config: dict, score_data: dict) -> dict:
    user = get_or_create_user_meta(config)
    user["Score"] = score_data
    return user


def build_runtime_submission_meta(game, user_state: dict) -> dict:
    config = clone_game_meta(game)
    if not config:
        logger.warning("Could not build runtime submission metadata for %s", game.gameDirName)
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
        }
    )
    if user_state.get("Score") is not None:
        user["Score"] = user_state.get("Score")
    return config


def update_score_from_nvram(game) -> None:
    config = clone_game_meta(game)
    if not config:
        logger.warning("Could not update Score: invalid game metadata for %s", game.gameDirName)
        return

    score_data, score_path = parse_score_from_nvram(game)
    if not score_data:
        return

    apply_score_update(config, score_data)
    persist_game_meta(game, config)
    logger.info("Updated User.Score for %s from %s", game.gameDirName, score_path)


def delete_nvram_if_configured(game) -> None:
    config = normalize_meta(getattr(game, "meta_config", {}))
    vpinfe = vpinfe_section(config)
    if not vpinfe.get("delete_nvram_on_close", False):
        return

    rom = score_rom_from_meta(config)
    if not rom:
        logger.warning("No ROM name found for table, skipping NVRAM deletion")
        return

    nvram_path = Path(game.fullPathGame) / "pinmame" / "nvram" / f"{rom}.nv"
    if nvram_path.exists():
        nvram_path.unlink()
        logger.info("Deleted NVRAM file: %s", nvram_path)
    else:
        logger.info("NVRAM file not found (nothing to delete): %s", nvram_path)
