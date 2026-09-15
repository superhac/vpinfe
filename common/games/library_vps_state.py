"""What the catalog lists against what the library holds, per game and across the library.

`state_of` answers one game. The rollup asks the same question of every game, which is
the only way to see that a kind is held by nothing at all - and it counts `state_of`'s
answer rather than forming a second opinion of its own.

On a job, because resolving media for every game measured 650ms over 149 folders.
Resolving only the kinds this needs is not the fix it looks like: virtual kinds borrow
from `logo` and a `fallback_kind` borrows another kind's winner, so a filtered resolve
answers differently rather than faster.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from common import timestamps
from common.games import (
    asset_origin,
    game_lens,
    game_repository,
    game_service,
    media_service,
    watching,
)
from common.games.game import Game
from common.games.game_service import load_vpsdb
from common.games.media_service import CACHE_DIR
from common.jobs import JobReporter
from common.online import obtainability, vps_kinds

logger = logging.getLogger("vpinfe.common.games.library_vps_state")

ROLLUP_PATH = CACHE_DIR / "vps-rollup.json"
SCHEMA = 1


@lru_cache(maxsize=1)
def _crowded_links_for(size: int) -> frozenset[str]:
    """The links standing behind enough records to be somewhere to browse.

    Keyed on the catalog's length, which is a cheap stand-in for "the snapshot has been
    replaced" - the alternative is walking 17,000 URLs on every request to answer a
    question about the corpus that changes only when the corpus does.
    """
    return obtainability.crowded(
        link.get("url")
        for entry in load_vpsdb()
        for kind in vps_kinds.BY_LISTING
        for record in (entry.get(kind) or [])
        for link in (record.get("urls") or []))


def _crowded_links() -> frozenset[str]:
    return _crowded_links_for(len(load_vpsdb()))


# The inventory still answers for color and sound under the flat names it used before
# the asset registry existed. Translated here rather than in the kind table, which
# names the registry's kinds because those are the real ones.
_INVENTORY_NAME = {"altcolor_serum": "alt_color", "altcolor_vni": "alt_color",
                   "altsound": "alt_sound"}


def _we_hold(kind: vps_kinds.VpsKind, inventory: dict, media: dict) -> bool:
    """Whether this game has any of what the entry is offering.

    Any, not all: a kind maps to more than one of ours where VPS draws the line in a
    different place, and holding either Serum or VNI is holding a colorization.
    """
    for name in kind.ours:
        if kind.held_in == vps_kinds.MEDIA:
            if (media.get(name) or {}).get("present"):
                return True
        elif (inventory.get(_INVENTORY_NAME.get(name, name)) or {}).get("present"):
            return True
    return False


def _moved_since(records: list, baseline: str, dismissed: set) -> list:
    """The records that changed upstream after this game's baseline.

    No baseline means nobody has said when to start watching, and everything ever
    published is not a useful first answer. A record with no `updatedAt` is never
    reported: 48 in the catalog have none, and guessing is worse than silence.
    """
    start = timestamps.iso_to_epoch(baseline) if baseline else None
    if start is None:
        return []
    moved = []
    for record in records:
        if str(record.get("id") or "") in dismissed:
            continue
        stamp = record.get("updatedAt")
        try:
            when = int(stamp) / 1000
        except (TypeError, ValueError):
            continue
        if when > start:
            moved.append(record)
    return moved


def state_of(game: Game, game_id: str = "") -> dict:
    """One game's state. The same answer the endpoint serves and the rollup counts,
    so the two cannot form separate opinions.

    `game_id` addresses the media links and selects this game's watching baseline.
    """
    entry = game_service.matched_vps_entry(game)
    game_dir = Path(str(game.full_path_game))
    inventory = game_lens.inventory_assets(game_dir)
    prefix = f"/api/v1/games/{game_id}/media"
    media = media_service.media_entries(
        media_service.resolved_media(game_dir, None), game_dir, prefix)
    shared = _crowded_links()
    # A record id is only in one kind's list, so the ids alone place every binding.
    bound = {str(source.get("vps_file_id") or "")
             for source in asset_origin.sources(game_dir).values()}
    bound.discard("")
    baseline = watching.since_for(game_id)
    dismissed = watching.acknowledged(game_id) if game_id else {}

    kinds = []
    for kind in vps_kinds.KINDS:
        records = list(entry.get(kind.listed_as) or []) if entry else []
        answers = [obtainability.best_of(
            [link.get("url") for link in (record.get("urls") or [])], shared)
            for record in records]
        moved = _moved_since(records, baseline,
                             dismissed.get(kind.listed_as) or set())
        kinds.append({
            "kind": kind.listed_as,
            "ours": list(kind.ours),
            "held_in": kind.held_in,
            "held": _we_hold(kind, inventory, media),
            "identified": any(str(record.get("id") or "") in bound
                              for record in records),
            "updated": any(str(record.get("id") or "") in bound for record in moved),
            "new_upstream": sum(1 for record in moved
                                if str(record.get("id") or "") not in bound),
            "listed": len(records),
            "obtainable": sum(1 for word in answers
                              if word == obtainability.AVAILABLE),
            "why_not": sorted({word for word in answers
                               if word != obtainability.AVAILABLE}),
        })
    return {"matched": bool(entry), "kinds": kinds}


def stored() -> dict[str, Any]:
    """The last rollup, or empty for one that has never run. Empty is not zero: a
    consumer must not read "never counted" as "you own none of these"."""
    try:
        data = json.loads(ROLLUP_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        logger.warning("Could not read %s; treating it as never computed", ROLLUP_PATH)
        return {}
    return data if isinstance(data, dict) and data.get("schema") == SCHEMA else {}


def store(rollup: dict[str, Any]) -> None:
    """Written whole and atomically - a half-written rollup reads as a plausible one,
    and the numbers would be believed."""
    ROLLUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(dir=ROLLUP_PATH.parent,
                                         prefix=".vpinfe_write_", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump({"schema": SCHEMA, **rollup}, out, indent=2)
        os.replace(temp_path, ROLLUP_PATH)
    except Exception:
        logger.exception("Could not write %s", ROLLUP_PATH)
        Path(temp_path).unlink(missing_ok=True)


_TALLIES = ("holding", "identified", "listed", "obtainable", "updated", "new_upstream")


def compute(games: dict, per_game: Callable[[Game, str], dict],
            reporter: JobReporter | None = None) -> dict[str, Any]:
    """Count every kind across the library, from `{game_id: game}`.

    Keyed by id because each game is measured against its own watching baseline.
    `per_game` answers one game's state, so the two cannot drift. A game that cannot be
    read still counts in `games` - dropping it would shrink the denominator silently.
    """
    counts = {kind.listed_as: dict.fromkeys(_TALLIES, 0)
              for kind in vps_kinds.KINDS}
    matched = 0
    total = len(games)
    for index, (game_id, game) in enumerate(games.items()):
        if reporter is not None:
            reporter.progress(index, total, "Counting what the catalog lists")
        try:
            state = per_game(game, game_id)
        except Exception:
            logger.warning("Could not read VPS state for %s", game_id, exc_info=True)
            continue
        matched += 1 if state.get("matched") else 0
        for item in state.get("kinds") or []:
            tally = counts.get(str(item.get("kind") or ""))
            if tally is None:
                continue
            tally["holding"] += 1 if item.get("held") else 0
            tally["identified"] += 1 if item.get("identified") else 0
            tally["listed"] += 1 if int(item.get("listed") or 0) else 0
            tally["obtainable"] += 1 if int(item.get("obtainable") or 0) else 0
            tally["updated"] += 1 if item.get("updated") else 0
            tally["new_upstream"] += 1 if int(item.get("new_upstream") or 0) else 0
    return {
        "computed": timestamps.utc_now_iso(),
        "games": total,
        "matched": matched,
        "kinds": [{"kind": kind.listed_as, "ours": list(kind.ours),
                   "held_in": kind.held_in, **counts[kind.listed_as]}
                  for kind in vps_kinds.KINDS],
    }


def recompute(games: dict, per_game: Callable[[Game, str], dict],
              reporter: JobReporter | None = None) -> dict[str, Any]:
    """Count it and keep it."""
    rollup = compute(games, per_game, reporter)
    store(rollup)
    return rollup


def recount(reporter: JobReporter | None = None) -> dict[str, Any]:
    """Count the whole library and keep the answer. What the job runs."""
    return recompute(game_repository.catalog(), state_of, reporter)
