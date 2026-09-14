"""Where this install looks for entries, over the wire.

Its own resource rather than part of `/config`, for the reason launchers are: a location
is an object somebody adds and removes, and the config endpoints answer with a fixed set
of settings and have nowhere to put a list of things.

It keeps the config scopes. This was a setting until it moved, so reading and writing it
is the same power it always was, and a token that could already point an install at its
library should not need a new grant to keep doing it.

`common/games/location_ops.py` is what answers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from common.games import location_ops

from . import scopes
from .auth import requires

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", summary="Every location this install looks in",
            dependencies=[requires(scopes.CONFIG_READ)])
def list_locations() -> dict[str, Any]:
    """The locations in order, each with what the disk says about it right now."""
    return location_ops.listing()


@router.put("/order", summary="Set which location outranks which",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def set_order(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """The order is the priority.

    Declared above `/{location_id}`, which would otherwise match "order" as an id.
    """
    return location_ops.reorder(body.get("order"))


@router.get("/destination", summary="Where a new game would be created",
            dependencies=[requires(scopes.CONFIG_READ)])
def new_game_destination() -> dict[str, Any]:
    """Where it would go, or why it could not, and what else it could go to instead.

    Declared above `/{location_id}`, which would otherwise read "destination" as an id.
    """
    return location_ops.destination()


@router.put("/{location_id}", summary="Add or replace a location",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def put_location(location_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Whole, under the id the caller names, the way a launcher arrives."""
    return location_ops.put(location_id, str(body.get("path") or ""),
                            str(body.get("kind") or ""))


@router.delete("/{location_id}", summary="Forget a location",
               dependencies=[requires(scopes.CONFIG_WRITE)])
def delete_location(location_id: str) -> dict[str, Any]:
    """The records inside it go with it. A contained entry keeps its record in its own
    folder, so it leaves with the location and is there again if it comes back."""
    return location_ops.forget(location_id)


@router.get("/{location_id}/shadowed",
            summary="Game folders here whose id something else answers for",
            dependencies=[requires(scopes.CONFIG_READ)])
def list_shadowed(location_id: str) -> dict[str, Any]:
    """Both sides, because the question a person brings here is which of the two copies
    they meant to keep - and that cannot be answered by naming only one of them."""
    return location_ops.shadowed_in(location_id)


@router.post("/{location_id}/shadowed/adopt",
             summary="Give one shadowed folder an id of its own",
             dependencies=[requires(scopes.CONFIG_WRITE)])
def adopt_shadowed(location_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Settle one clash by making this folder a game in its own right.

    The other way to settle it is to remove the location, which is right when the whole
    location is a second view of one library. That is `DELETE /locations/{id}` and it
    writes nothing at all.
    """
    return location_ops.adopt(location_id, str(body.get("path") or ""))


@router.put("/{location_id}/write-to", summary="Create new games here",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def set_write_to(location_id: str) -> dict[str, Any]:
    return location_ops.set_write_to(location_id)
