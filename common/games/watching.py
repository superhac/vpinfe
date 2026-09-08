"""Since when a finding counts as new, and what has been dismissed.

Everything else about the catalog is derived. Transitions are the exception: "has this
changed since I last looked" needs a record of when that was.

Never the `.info` - an exported table folder must not carry somebody's dismissals with
it. And never keyed off file mtime: mtime overstates recency, so an update to a file
migrated since it was downloaded becomes invisible rather than merely late.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from common import timestamps
from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.common.games.watching")

WATCHING_PATH = CONFIG_DIR / "watching.json"
SCHEMA = 1

# What "review everything" means. Not the empty string: absent has to keep meaning
# "nobody has answered the question yet", which is a third state.
FROM_THE_BEGINNING = "1970-01-01T00:00:00Z"


def _load() -> dict[str, Any]:
    try:
        data = json.loads(WATCHING_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        logger.warning("Could not read %s; treating it as unset", WATCHING_PATH)
        return {}
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return {}
    return data


def _save(data: dict[str, Any]) -> None:
    WATCHING_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(dir=WATCHING_PATH.parent,
                                         prefix=".vpinfe_write_", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump({**data, "schema": SCHEMA}, out, indent=2)
        os.replace(temp_path, WATCHING_PATH)
    except Exception:
        logger.exception("Could not write %s", WATCHING_PATH)
        Path(temp_path).unlink(missing_ok=True)


def since() -> str:
    """When this install started watching, or "" for never answered."""
    return str(_load().get("watching_since") or "")


def set_since(value: str) -> None:
    """The first-run answer. "Review them" is the beginning of time, "Start clean" is
    now - one mechanism, no special mode, which is what keeps the dialog honest."""
    data = _load()
    data["watching_since"] = str(value or "")
    _save(data)


def since_for(game_id: str) -> str:
    """The baseline this game is measured against.

    Its own if it has one, so a game added a year from now does not arrive holding a
    year of upstream activity it was never around for. The install's otherwise.
    """
    data = _load()
    own = (data.get("games") or {}).get(str(game_id))
    return str(own or data.get("watching_since") or "")


def note_games(game_ids: Iterable[str]) -> int:
    """Stamp any game nothing has seen before, and answer how many were new.

    Called from the library reconcile, not from a read: a read path that stamped would
    make asking the question change the answer.
    """
    data = _load()
    if not data.get("watching_since"):
        # No backlog to inherit yet, and stamping would freeze a baseline nobody chose.
        return 0
    known = dict(data.get("games") or {})
    now = timestamps.utc_now_iso()
    fresh = [str(game_id) for game_id in game_ids
             if str(game_id) and str(game_id) not in known]
    if not fresh:
        return 0
    for game_id in fresh:
        known[game_id] = now
    data["games"] = known
    _save(data)
    return len(fresh)


def acknowledged(game_id: str) -> dict[str, set[str]]:
    """What has been dismissed for this game, by kind. Sparse: a game nobody has
    dismissed anything for holds nothing at all."""
    found = (_load().get("acknowledged") or {}).get(str(game_id)) or {}
    return {str(kind): {str(item) for item in (ids or [])}
            for kind, ids in found.items()}


def acknowledge(game_id: str, kind: str, vps_file_id: str) -> None:
    """Dismiss one record for one game and kind."""
    data = _load()
    games = dict(data.get("acknowledged") or {})
    for_game = {str(k): list(v or []) for k, v in (games.get(str(game_id)) or {}).items()}
    ids = for_game.setdefault(str(kind), [])
    if str(vps_file_id) not in ids:
        ids.append(str(vps_file_id))
    games[str(game_id)] = for_game
    data["acknowledged"] = games
    _save(data)


def forget(game_id: str) -> None:
    """Drop everything held about a game. For a game that is gone - keeping its
    dismissals would silently apply them to whatever takes its id next."""
    data = _load()
    for section in ("games", "acknowledged"):
        held = dict(data.get(section) or {})
        if held.pop(str(game_id), None) is not None:
            data[section] = held
    _save(data)
