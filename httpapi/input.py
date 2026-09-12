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

from common import input_actions, input_registry
from common.i18n import t

from . import models, scopes
from .auth import requires
from .errors import InvalidRequestError

router = APIRouter(prefix="/input", tags=["input"])

TAP = "tap"
PHASES = (TAP, input_actions.PRESS, input_actions.RELEASE)


@router.post("/actions", summary="Press, hold or release an input action",
             dependencies=[requires(scopes.INPUT_ACT)])
def act(payload: models.InputActionRequest, request: Request) -> models.InputActionResult:
    """Put one press on this install's bus.

    A press with no matching release expires on its own, so a client holding a button
    renews it - send `press` again with the same action - for as long as the thumb is
    down. That is the same press as far as the frontend is concerned; only the first one
    is announced.
    """
    action = (payload.action or "").strip()
    if not input_actions.known(action):
        raise InvalidRequestError(
            t("error.input.no_input_action_called_one", action=(action),
                    join=(', '.join(one.name for one in input_registry.INPUT_ACTIONS))))
    phase = (payload.phase or TAP).strip().lower()
    if phase not in PHASES:
        raise InvalidRequestError(
            t("error.input.a_phase_is_one_of_not", join=(', '.join(PHASES)), phase=(phase)))

    source = _source(payload.source, request)
    if phase == input_actions.RELEASE:
        input_actions.release(action, source=source)
    elif phase == input_actions.PRESS:
        input_actions.press(action, source=source, ttl_ms=payload.ttl_ms)
    else:
        input_actions.tap(action, source=source)
    return {"action": action, "phase": phase,
            "ttl_ms": input_actions.clamp_ttl(payload.ttl_ms),
            "holding": sorted(input_actions.holding())}


def _source(said: str, request: Request) -> str:
    """Who pressed it, as one string for the log.

    The caller names itself and the boundary says where it came from. Both, because
    neither alone answers the question that made this worth recording: "remote" does not
    say which machine, and "network" does not say what kind of client.
    """
    who = (said or "").strip()[:40] or "api"
    identity = getattr(request.state, "identity", None)
    return f"{who}/{identity.origin}" if identity is not None else who
