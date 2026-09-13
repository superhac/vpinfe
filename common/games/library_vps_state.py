"""What the catalog lists against what the library holds, counted across every game.

The per-game answer is `GET /games/{id}/vps_state`; this is the same question asked of
the whole library, which is the only way to see that a kind is held by nothing at all.

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
from pathlib import Path
from typing import Any

from common import timestamps
from common.games.media_service import CACHE_DIR
from common.online import vps_kinds

logger = logging.getLogger("vpinfe.common.games.library_vps_state")

ROLLUP_PATH = CACHE_DIR / "vps-rollup.json"
SCHEMA = 1


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


def compute(games: dict, per_game, reporter=None) -> dict[str, Any]:
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


def recompute(games: list, per_game, reporter=None) -> dict[str, Any]:
    """Count it and keep it. What the job runs."""
    rollup = compute(games, per_game, reporter)
    store(rollup)
    return rollup
