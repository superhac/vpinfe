"""Acting as the player.

The one route that lets a caller press what a cabinet button presses. Everything about
what a press means - the vocabulary, the hold, the expiry - is `common/input_actions.py`;
this is the HTTP door onto it.

It reaches only this install's windows, and that is the whole of the routing story: a
client aimed at another machine calls that machine's copy of this route. `DeviceChannel`
fans to its own windows by construction, so the target picker in a client is a base URL
and not a new transport.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from common import input_actions

from . import models, scopes
from .auth import requires

router = APIRouter(prefix="/input", tags=["input"])


@router.post("/actions", summary="Press, hold or release an input action",
             dependencies=[requires(scopes.INPUT_ACT)])
def act(payload: models.InputActionRequest, request: Request) -> models.InputActionResult:
    """Put one press on this install's bus."""
    return models.InputActionResult.model_validate(
        input_actions.act(payload.action, payload.phase,
                          source=_source(payload.source, request),
                          ttl_ms=payload.ttl_ms))


def _source(said: str, request: Request) -> str:
    """Who pressed it, as one string for the log.

    The caller names itself and the boundary says where it came from. Both, because
    neither alone answers the question that made this worth recording: "remote" does not
    say which machine, and "network" does not say what kind of client.
    """
    who = (said or "").strip()[:40] or "api"
    identity = getattr(request.state, "identity", None)
    return f"{who}/{identity.origin}" if identity is not None else who
