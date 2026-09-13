"""Fetching what extensions contribute about the game the player moved to.

Core makes the call and the windows are told the answer. The alternative is what one
vendor has today: every window on a cabinet calling somebody else's server for the same
game, three times, and losing the lot on a reload.

Off the wheel's thread. A connector's server being slow must not be something the player
feels while turning the wheel, so the fetch runs behind the selection rather than in it.
"""

from __future__ import annotations

import logging
import threading

from common import events
from common.extensions import contributions
from common.games import game_identity
from common.games.game_metadata import game_title, normalize_meta, section

logger = logging.getLogger("vpinfe.frontend.ext_data")

_registered = False
_broadcast = None


def descriptor_for(game) -> dict:
    """What a contributor is told about a game.

    A plain description and never our object: an extension holding one could reach the
    whole library through it, which is the thing the context exists to prevent.
    """
    info = section(normalize_meta(game.meta_config), "Info")
    return {
        "game_id": game_identity.game_id(game),
        "vps_id": str(info.get("VPSId", "") or ""),
        "name": game_title(game),
        "manufacturer": str(info.get("Manufacturer", "") or ""),
        "year": str(info.get("Year", "") or ""),
    }


def _fetch_and_tell(games) -> None:
    """The selected game first, then the ones either side of it.

    In that order and not together: the player is looking at the first one, and a
    neighbour fetched ahead of it would put somebody else's server between them and what
    is on screen.
    """
    for index, game in enumerate(games):
        descriptor = descriptor_for(game)
        found = contributions.refresh(descriptor)
        # A neighbour is fetched to be ready, not to be shown. Telling the windows about
        # a game nobody is looking at is a message per wheel step for nothing.
        if not found or index or _broadcast is None:
            continue
        # The message names the game it is about, so an answer arriving after the wheel
        # has moved lands on the entry it belongs to rather than the one now in front of
        # the player. Nothing has to be thrown away to prevent that.
        _broadcast({"type": "EntryDataChange",
                    "game_id": descriptor["game_id"], "ext": found})


def on_selected(*, game=None, neighbors=(), **_payload) -> None:
    """The player moved to a game. Ask about it, and about where they are heading.

    The neighbours are asked on the same signal and for the same reason media is
    preloaded there: what somebody sees is then the answer fetched a step ago, and the
    gap only shows on the first game of a cold start.
    """
    if game is None or not contributions.keys():
        return
    wanted = [game, *[one for one in (neighbors or ()) if one is not None]]
    threading.Thread(target=_fetch_and_tell, args=(wanted,), daemon=True,
                     name="ext-data").start()


def register(broadcast) -> None:
    """Attach to the bus. Safe to call more than once."""
    global _registered, _broadcast
    _broadcast = broadcast
    if _registered:
        return
    events.subscribe(events.GAME_SELECTED, on_selected)
    _registered = True


def reset_for_tests() -> None:
    global _registered, _broadcast
    if _registered:
        events.unsubscribe(events.GAME_SELECTED, on_selected)
    _registered = False
    _broadcast = None
