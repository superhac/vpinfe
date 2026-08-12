"""The players a hub knows about.

A player announces itself; the hub records what it said and when it last said it. That is
the whole of it - there is no routing, no aggregation and no picking one to launch on,
because all three need decisions *across* players that nothing has made yet.

What it buys now is attribution: an event carries the `install_id` it happened on
(PAR-55), and a roster is what turns that id into a name someone recognizes.

The roster is a cache of what each install last reported about itself. It goes stale by
design - the install owns its own name and roles, and this is a copy.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Request, Response

from common.roster import get_roster

from . import models, scopes
from .auth import requires
from .errors import InvalidRequestError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.players")

router = APIRouter(prefix="/players", tags=["players"])


def _resource(player) -> dict:
    return player.as_dict() | {"links": {"self": f"/api/v1/players/{player.install_id}"}}


@router.get("", summary="The players this hub knows",
            dependencies=[requires(scopes.PLAYERS_READ)])
def list_players() -> models.PlayerList:
    players = get_roster().players()
    return {"count": len(players), "players": [_resource(p) for p in players]}


@router.get("/{install_id}", summary="One player",
            dependencies=[requires(scopes.PLAYERS_READ)])
def get_player(install_id: str) -> models.PlayerResource:
    player = get_roster().get(install_id)
    if player is None:
        raise NotFoundError(f"No player with install id {install_id}")
    return _resource(player)


@router.put("", summary="Announce a player to this hub", status_code=200,
            dependencies=[requires(scopes.PLAYERS_WRITE)])
def announce(request: Request,
             payload: models.PlayerAnnouncement = Body(...)) -> models.PlayerResource:
    """Idempotent: announcing twice is one player, heard from twice.

    The address is taken from the socket rather than the body. A player behind a
    router does not know how the hub reaches it, and a body that said would be a
    claim rather than an observation.
    """
    install_id = payload.install_id.strip()
    if not install_id:
        raise InvalidRequestError("A player needs an install id")

    client = getattr(request, "client", None)
    player = get_roster().record(
        install_id,
        display_name=payload.display_name.strip(),
        roles=tuple(payload.roles),
        address=getattr(client, "host", "") or "",
    )
    if player is None:
        raise InvalidRequestError("A player needs an install id")
    return _resource(player)


@router.delete("/{install_id}", summary="Forget a player", status_code=204,
               dependencies=[requires(scopes.PLAYERS_WRITE)])
def forget(install_id: str):
    """Forgetting one that is still running only means it announces itself again."""
    if not get_roster().forget(install_id):
        raise NotFoundError(f"No player with install id {install_id}")
    return Response(status_code=204)
