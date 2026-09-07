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


def _described(location: locations.Location, write_to: str) -> dict[str, Any]:
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
    }


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
    return {
        "locations": [_described(one, write_to) for one in held],
        "write_to": write_to,
        "kinds": list(locations.KINDS),
    }


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


@router.put("/{location_id}/write-to", summary="Create new games here",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def set_write_to(location_id: str) -> dict[str, Any]:
    if not locations.get_location_store().set_write_to(location_id):
        raise NotFoundError(f"No location called {location_id!r}.")
    return {"write_to": location_id}
