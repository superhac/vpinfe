"""Where this install looks for entries, over the wire.

Its own resource rather than part of `/config`, for the reason launchers are: a location
is an object somebody adds and removes, and the config endpoints answer with a fixed set
of settings and have nowhere to put a list of things.

It keeps the config scopes. This was a setting until it moved, so reading and writing it
is the same power it always was, and a token that could already point an install at its
library should not need a new grant to keep doing it.

Reachable and writable come back with each row and are asked of the disk on every read.
They are facts about this machine at this moment, not something stored: a stored answer
is wrong the moment a mount drops.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body

from common.games import locations

from . import scopes
from .auth import requires
from .errors import InvalidRequestError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.locations")

router = APIRouter(prefix="/locations", tags=["locations"])


def _described(location: locations.Location, write_to: str,
               shadowed: int = 0) -> dict[str, Any]:
    state = locations.state_of(location)
    return {
        "location_id": location.location_id,
        "path": location.path,
        "name": location.name,
        "kind": location.kind,
        "reachable": state.reachable,
        "writable": state.writable,
        # Empty when there is nothing to say. A reason on every row would say nothing.
        "reason": state.reason,
        "write_to": location.location_id == write_to,
        # How many of this location's game folders hold an id a higher one is already
        # using. Nearly always zero; the case it exists for is one library reached
        # through two locations, where it is the whole count and says so.
        "shadowed": shadowed,
    }


def _shadowed() -> Any:
    """What each location holds that something above it is answering for.

    Asked of the library on every read, like reachable and writable: whether a folder is
    shadowed depends on the other locations, so a stored answer would be wrong the
    moment one is added, removed or reordered.
    """
    from common.games.game_identity import resolve_ids
    from common.games.game_repository import all_games

    return resolve_ids(all_games())


@router.get("", summary="Every location this install looks in",
            dependencies=[requires(scopes.CONFIG_READ)])
def list_locations() -> dict[str, Any]:
    """The locations in order, each with what the disk says about it right now.

    `write_to` is named rather than left to be worked out: it falls back to the first
    writable root when the stored choice is unreachable, and a client re-deriving that
    is a second place for it to be wrong.
    """
    store = locations.get_location_store()
    held = store.locations()
    target = store.write_to()
    write_to = target.location_id if target is not None else ""
    found = _shadowed()
    return {
        "locations": [_described(one, write_to, len(found.under(one.location_id)))
                      for one in held],
        "write_to": write_to,
        "kinds": list(locations.KINDS),
        # The order is the priority: an id two folders hold is answered by the one in
        # the location nearer the top. Said here rather than left to be inferred from
        # the list being a list.
        "order_is_priority": True,
    }


@router.put("/order", summary="Set which location outranks which",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def set_order(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """The order is the priority.

    A game folder carries its id, so one library reached through two locations holds
    every id twice, and the folder that answers for an id is the one in the location
    nearer the top. Nothing is written to a game folder to settle that, which is why
    this is the control that settles it.

    Declared above `/{location_id}`, which would otherwise match "order" as an id.
    """
    order = body.get("order")
    if not isinstance(order, list) or not order:
        raise InvalidRequestError("Name the locations, in the order you want them.")
    if not locations.get_location_store().reorder([str(one) for one in order]):
        raise NotFoundError("None of those are locations this install has.")
    return list_locations()


@router.get("/destination", summary="Where a new game would be created",
            dependencies=[requires(scopes.CONFIG_READ)])
def new_game_destination() -> dict[str, Any]:
    """Where it would go, or why it could not, and what else it could go to instead.

    Asked before an import rather than discovered by one: a destination that has gone
    read-only refuses rather than quietly becoming a different folder, and a refusal is
    only useful if it says where else this could land.

    Declared above `/{location_id}`, which would otherwise read "destination" as an id.
    """
    found = locations.destination()
    return {
        "location_id": found.location.location_id if found.location else "",
        "path": found.path,
        "name": found.location.name if found.location else "",
        "reason": found.reason,
        # Every other writable root, so a surface can offer them for this one import
        # without asking somebody to go and change a setting first.
        "alternatives": [{"location_id": one.location_id, "name": one.name,
                          "path": one.path} for one in found.alternatives],
        # Whether to ask at all. Never where there is only one place it could go: a
        # question with one answer is a click charged for nothing.
        "ask": (_asks() and bool(found.alternatives)),
    }


def _asks() -> bool:
    from common.config_access import cfg_bool
    from common.paths import get_ini_config

    return cfg_bool(get_ini_config(), "general", "ask_where_new_games_go", True)


@router.put("/{location_id}", summary="Add or replace a location",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def put_location(location_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Whole, under the id the caller names, the way a launcher arrives.

    A path already held under another id replaces that row rather than making a second:
    two rows for one place would each report their own state.
    """
    wanted = str(location_id or "").strip()
    if not wanted:
        raise InvalidRequestError("A location needs an id.")
    path = str(body.get("path") or "").strip()
    if not path:
        raise InvalidRequestError("A location needs a path.")
    kind = str(body.get("kind") or locations.KIND_ROOT).strip()
    if kind not in locations.KINDS:
        raise InvalidRequestError(
            f"No location kind called {kind!r}. This build knows "
            f"{', '.join(locations.KINDS)}.")

    store = locations.get_location_store()
    written = store.put(locations.Location(location_id=wanted, path=path, kind=kind))
    target = store.write_to()
    return _described(written, target.location_id if target is not None else "")


@router.delete("/{location_id}", summary="Forget a location",
               dependencies=[requires(scopes.CONFIG_WRITE)])
def delete_location(location_id: str) -> dict[str, Any]:
    """The records inside it go with it. A contained entry keeps its record in its own
    folder, so it leaves with the location and is there again if it comes back."""
    if not locations.get_location_store().remove(location_id):
        raise NotFoundError(f"No location called {location_id!r}.")
    return {"removed": location_id}


@router.get("/{location_id}/shadowed",
            summary="Game folders here whose id something else answers for",
            dependencies=[requires(scopes.CONFIG_READ)])
def list_shadowed(location_id: str) -> dict[str, Any]:
    """What this location holds that is out of the library, and what took its place.

    Both sides, because the question a person brings here is which of the two copies
    they meant to keep - and that cannot be answered by naming only one of them.
    """
    if locations.get_location_store().get(location_id) is None:
        raise NotFoundError(f"No location called {location_id!r}.")
    return {"shadowed": [
        {"game_id": one.game_id, "path": one.path,
         "used_path": one.used_path, "used_location_id": one.used_location_id}
        for one in _shadowed().under(location_id)]}


@router.post("/{location_id}/shadowed/adopt",
             summary="Give one shadowed folder an id of its own",
             dependencies=[requires(scopes.CONFIG_WRITE)])
def adopt_shadowed(location_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Settle one clash by making this folder a game in its own right.

    **The one write in any of this, and it only happens because somebody asked.** The
    folder keeps everything else it has - its media, its curation, its play record - and
    gains a new id, so it stops being a copy of the other and starts being its own game.
    Anything that named the id keeps pointing at the folder that kept it.

    The other way to settle it is to remove the location, which is right when the whole
    location is a second view of one library. That is `DELETE /locations/{id}` and it
    writes nothing at all.
    """
    from common.games.game_identity import ensure_id

    if locations.get_location_store().get(location_id) is None:
        raise NotFoundError(f"No location called {location_id!r}.")
    wanted = locations.canonical(str(body.get("path") or ""))
    if not wanted:
        raise InvalidRequestError("Name the folder to give an id to.")

    found = _shadowed()
    one = next((entry for entry in found.under(location_id)
                if locations.canonical(entry.path) == wanted), None)
    if one is None:
        raise NotFoundError(
            "Nothing here is shadowed at that path. It may have been settled already.",
            details={"path": str(body.get("path") or "")})

    from common.games.game_repository import all_games

    game = next((held for held in all_games()
                 if locations.canonical(str(getattr(held, "fullPathGame", "") or ""))
                 == wanted), None)
    if game is None:
        raise NotFoundError("That folder is no longer in the library.")
    return {"path": one.path, "game_id": ensure_id(game, force_new=True)}


@router.put("/{location_id}/write-to", summary="Create new games here",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def set_write_to(location_id: str) -> dict[str, Any]:
    if not locations.get_location_store().set_write_to(location_id):
        raise NotFoundError(f"No location called {location_id!r}.")
    return {"write_to": location_id}
