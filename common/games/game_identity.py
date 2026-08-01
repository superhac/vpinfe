"""Stable local identity for tables: an opaque id in the .info at `VPinFE.id`.

Addresses a table in the HTTP API, in events and in jobs. VPSId cannot do that job
and keeps its own. Reading never writes; minting is explicit. See docs/http_api.md.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterable
from typing import Any

from common.games.game_metadata import (
    load_game_meta,
    normalize_meta,
    persist_game_meta,
    section,
)
from common.games.metaconfig import VPINFE_SECTION

logger = logging.getLogger("vpinfe.common.games.game_identity")

# Also written by MetaConfig.writeConfigMeta, which mints during a metadata rebuild.
ID_SECTION = VPINFE_SECTION
ID_KEY = "id"

# No 0/O or I/l, so an id survives being read down a phone or retyped out of a bug
# report. Ten of these is ~4e17 values; ensure_unique_ids re-mints the collision that
# will not happen.
ID_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ID_LENGTH = 10


def new_id() -> str:
    return "".join(secrets.choice(ID_ALPHABET) for _ in range(ID_LENGTH))


def game_id(game) -> str:
    """The table's id, or "" if it hasn't been assigned one. Never writes."""
    meta = normalize_meta(getattr(game, "metaConfig", {}))
    return str(section(meta, ID_SECTION).get(ID_KEY, "") or "").strip()


def _vpinfe_section(config: dict[str, Any]) -> dict[str, Any]:
    existing = config.get(ID_SECTION)
    if not isinstance(existing, dict):
        existing = {}
        config[ID_SECTION] = existing
    return existing


def ensure_id(game, *, force_new: bool = False) -> str:
    """The table's id, minting and persisting one if it has none.

    Re-reads from disk first so a stale in-memory copy isn't written back. Raises if
    the write fails: an id that isn't on disk isn't an identity.
    """
    if not force_new:
        existing = game_id(game)
        if existing:
            return existing

    config = load_game_meta(game)
    vpinfe = _vpinfe_section(config)
    existing = str(vpinfe.get(ID_KEY, "") or "").strip()
    if existing and not force_new:
        # Present on disk but not in the loaded copy; adopt it rather than mint.
        game.metaConfig = config
        return existing

    minted = new_id()
    vpinfe[ID_KEY] = minted
    persist_game_meta(game, config)
    logger.debug("Assigned table id %s to %s", minted, getattr(game, "tableDirName", "?"))
    return minted


def ensure_unique_ids(games: Iterable[Any]) -> dict[str, Any]:
    """Give every table an id, re-minting collisions so an id addresses one table.

    Two tables share an id when a table folder was copied.
    """
    by_id: dict[str, Any] = {}
    minted = 0
    for game in games:
        current = game_id(game)
        if not current:
            current = ensure_id(game)
            minted += 1
        if current in by_id:
            logger.warning(
                "Table id %s is used by both %s and %s; assigning a new id to the latter",
                current,
                getattr(by_id[current], "tableDirName", "?"),
                getattr(game, "tableDirName", "?"),
            )
            current = ensure_id(game, force_new=True)
            minted += 1
        by_id[current] = game
    if minted:
        logger.info("Assigned ids to %s of %s tables", minted, len(by_id))
    return by_id


def find_by_id(games: Iterable[Any], wanted: str) -> Any | None:
    """The table with this id, or None. A table with no id can't match."""
    wanted = (wanted or "").strip()
    if not wanted:
        return None
    for game in games:
        if game_id(game) == wanted:
            return game
    return None
