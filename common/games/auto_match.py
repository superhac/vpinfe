"""Matching a game to its catalog entry from its folder name, where no person has.

From the catalog on disk only: every caller runs where the network is not allowed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from common.config_access import cfg_bool
from common.games import game_service
from common.games.game_metadata import (
    declared_no_match,
    dissolve_agreed_overrides,
    effective_vps_id,
    keep_game_meta,
    load_game_meta,
    merge_guides,
    normalize_meta,
    persist_game_meta,
    record_vps_match,
    vps_matched_by,
)
from common.games.info_file import GUIDES_KEY, guides_from_vps, info_from_vps
from common.online.vpsdb import guess
from common.paths import get_ini_config

logger = logging.getLogger("vpinfe.common.games.auto_match")


def enabled() -> bool:
    return cfg_bool(get_ini_config(), "updates", "match_new_games", True)


def unmatched(meta: dict[str, Any]) -> bool:
    """No entry in force, and nobody has said there is none."""
    return not effective_vps_id(meta) and not declared_no_match(meta)


def adopt_guess(game: Any, entry: dict[str, Any],
                write: Callable[[Any, dict[str, Any]], None] = persist_game_meta) -> None:
    """Write `entry` as the game's match from its folder name.

    The match alone: tables and a person's overrides are left as they are.
    """
    config = load_game_meta(game)
    config["Info"] = info_from_vps(entry)
    config[GUIDES_KEY] = merge_guides(config.get(GUIDES_KEY) or [], guides_from_vps(entry))
    record_vps_match(config, "")
    dissolve_agreed_overrides(config)
    write(game, config)


def match_new(games: Iterable[Any], catalog: list[dict] | None = None) -> dict[str, int]:
    """Guess each of `games` that nothing has matched, and count the result.

    `games` is every game handed in, `matched` those with an entry in force afterwards and
    `unmatched` those still waiting for one. A declared no-match is neither.
    """
    games = list(games)
    if games and enabled():
        held = game_service.load_vpsdb() if catalog is None else catalog
        for game in games:
            if not unmatched(normalize_meta(game.meta_config or {})):
                continue
            entry = guess(held, str(game.game_dir_name or ""))
            if entry is None:
                continue
            try:
                adopt_guess(game, entry, keep_game_meta)
            except Exception:
                logger.exception("Could not match %s", game.game_dir_name)
    metas = [normalize_meta(game.meta_config or {}) for game in games]
    return {"games": len(games),
            "matched": sum(1 for meta in metas if effective_vps_id(meta)),
            "unmatched": sum(1 for meta in metas if unmatched(meta))}


def match_again(games: Iterable[Any],
                catalog: list[dict] | None = None) -> tuple[dict[str, int], list[Any]]:
    """Guess each of `games` again, except where a person made the match or declared none.

    A guess that finds nothing leaves the match as it was. Answers the counts - `changed`
    the games whose match moved, `unmatched` those still without one, `yours` those left
    alone for a person's match - and the games that moved.
    """
    games = list(games)
    held = game_service.load_vpsdb() if catalog is None else catalog
    moved: list[Any] = []
    yours = 0
    for game in games:
        meta = normalize_meta(game.meta_config or {})
        if vps_matched_by(meta):
            yours += 1
            continue
        entry = guess(held, str(game.game_dir_name or ""))
        if entry is None or str(entry.get("id") or "") == effective_vps_id(meta):
            continue
        try:
            adopt_guess(game, entry)
        except Exception:
            logger.exception("Could not write the match for %s", game.game_dir_name)
            continue
        moved.append(game)
    waiting = sum(1 for game in games if unmatched(normalize_meta(game.meta_config or {})))
    return ({"games": len(games), "changed": len(moved), "unmatched": waiting,
             "yours": yours}, moved)
