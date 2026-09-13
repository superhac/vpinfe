"""Stable local identity for games: an opaque id in the .info at `vpinfe.game_id`.

Addresses a game in the HTTP API, in events and in jobs. VPSId cannot do that job
and keeps its own. Reading never writes; minting is explicit. See docs/http_api.md.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from common.games.game_metadata import (
    load_game_meta,
    normalize_meta,
    persist_game_meta,
    section,
)
from common.games.ids import ALPHABET as ID_ALPHABET
from common.games.ids import LENGTH as ID_LENGTH
from common.games.ids import new_id
from common.games.info_file import GAME_ID_KEY, VPINFE_SECTION

logger = logging.getLogger("vpinfe.common.games.game_identity")

# Also written by MetaConfig.write_config_meta, which mints during a metadata rebuild.
ID_SECTION = VPINFE_SECTION
ID_KEY = GAME_ID_KEY

__all__ = ["ID_ALPHABET", "ID_LENGTH", "ID_KEY", "ID_SECTION", "new_id",
           "game_id", "ensure_id", "ensure_unique_ids", "resolve_ids", "Resolution",
           "Shadowed", "find_by_id"]


def game_id(game) -> str:
    """The table's id, or "" if it hasn't been assigned one. Never writes."""
    meta = normalize_meta(getattr(game, "meta_config", {}))
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
        game.meta_config = config
        return existing

    minted = new_id()
    vpinfe[ID_KEY] = minted
    persist_game_meta(game, config)
    logger.debug("Assigned game id %s to %s", minted, getattr(game, "gameDirName", "?"))
    return minted


@dataclass(frozen=True)
class Shadowed:
    """A game folder whose id another folder is already using.

    Named for what happened to it rather than for the fault: nothing is wrong with this
    folder, and nothing has been done to it. Another one answers for its id, so this one
    is out of the library until somebody says which should.
    """

    game_id: str
    path: str
    location_id: str
    # The folder that is answering for the id instead, so the report can say what won.
    used_path: str
    used_location_id: str


@dataclass(frozen=True)
class Resolution:
    """Which folder answers for each id, and which were shadowed doing it."""

    by_id: dict[str, Any]
    shadowed: tuple[Shadowed, ...] = ()

    def under(self, location_id: str) -> tuple[Shadowed, ...]:
        """What this location holds that something else is answering for."""
        return tuple(one for one in self.shadowed
                     if one.location_id == str(location_id or ""))


def _priority(games: Iterable[Any], order: Sequence[str] | None) -> list[Any]:
    """Games in the order their claim on an id is honoured.

    Locations are a list and that list is the priority: the earlier location wins, which
    is the same rule `LocationStore.write_to` already applies when it falls back to the
    first writable one. Within one location there is no priority to appeal to, so the
    tie goes to the first by path - arbitrary, but the same answer on every run, which
    directory order is not.
    """
    if order is None:
        from common.games.locations import configured

        order = [one.location_id for one in configured()]
    rank = {location_id: index for index, location_id in enumerate(order)}
    # A location the list does not name goes last rather than first: it is not part of
    # the answer somebody arranged, so it cannot outrank what is.
    unranked = len(rank)
    return sorted(
        games,
        key=lambda game: (rank.get(str(getattr(game, "location_id", "") or ""),
                                  unranked),
                          str(getattr(game, "fullPathGame", "") or "")))


def resolve_ids(games: Iterable[Any],
                order: Sequence[str] | None = None) -> Resolution:
    """Which folder answers for each id. **Nothing is rewritten to settle a clash.**

    A folder carries its id, so two folders holding one means the same game is in the
    library twice - a copy, or the same tree reached through two locations. Re-minting
    the loser used to settle it silently, and that is a write to somebody's file to
    resolve something only they can: it makes the copy a different game for good, and
    anything that named it goes with it.

    So the higher-priority location answers, the rest are reported, and the decision
    waits for a person. Ids are still minted for folders that have none - that is not a
    clash, and a game with no id cannot be addressed at all.
    """
    by_id: dict[str, Any] = {}
    holder: dict[str, Any] = {}
    shadowed: list[Shadowed] = []
    minted = 0

    for game in _priority(games, order):
        current = game_id(game)
        if not current:
            current = ensure_id(game)
            minted += 1
        if current in by_id:
            first = holder[current]
            shadowed.append(Shadowed(
                game_id=current,
                path=str(getattr(game, "fullPathGame", "") or ""),
                location_id=str(getattr(game, "location_id", "") or ""),
                used_path=str(getattr(first, "fullPathGame", "") or ""),
                used_location_id=str(getattr(first, "location_id", "") or "")))
            continue
        by_id[current] = game
        holder[current] = game

    if minted:
        logger.info("Assigned ids to %s of %s games", minted, len(by_id))
    if shadowed:
        logger.warning(
            "%s game folder(s) hold an id another folder is already using; they are "
            "out of the library until somebody says which should have it", len(shadowed))
    return Resolution(by_id=by_id, shadowed=tuple(shadowed))


def ensure_unique_ids(games: Iterable[Any],
                      order: Sequence[str] | None = None) -> dict[str, Any]:
    """Every game that answers for an id, keyed by it. The shadowed ones are not here -
    `resolve_ids` is what reports those."""
    return resolve_ids(games, order).by_id


def find_by_id(games: Iterable[Any], wanted: str) -> Any | None:
    """The game with this id, or None. A game with no id can't match."""
    wanted = (wanted or "").strip()
    if not wanted:
        return None
    for game in games:
        if game_id(game) == wanted:
            return game
    return None
