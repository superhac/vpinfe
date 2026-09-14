"""What this install can be told to do to itself, over the wire.

The lifecycle vocabulary served over HTTP: close the table, reopen the frontend windows,
restart VPinFE, reboot the machine. `common/host/action_ops.py` answers; what is here is
the path, the scope, and the one thing only a request has - a background task to hand the
actions that take the answer with them.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Body

from common.host import action_ops

from . import models, scopes
from .auth import requires

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("", summary="What this install can be asked to do",
            dependencies=[requires(scopes.SYSTEM_READ)])
def list_actions() -> models.ActionList:
    """Every pair, offered or not: a surface greys one rather than hiding it, because two
    installs showing different buttons look like different products."""
    return models.ActionList.model_validate(action_ops.listing())


@router.post("", summary="Do one of them",
             dependencies=[requires(scopes.SYSTEM_ADMIN)])
def perform_action(background: BackgroundTasks,
                   payload: models.ActionRequest = Body(...)) -> models.ActionResult:
    """Confirm-announce-perform, through the same path every other surface takes.

    Never asks the caller to confirm: an HTTP request is over by the time anything here
    could put the question, so whoever called put it to their own user first. That is what
    the API origin means and it is why this passes no confirm scopes.

    A process that is stopping cannot report whether it stopped, so those go to a
    background task and the response goes out first - the same order `POST /update` uses.
    """
    from common import lifecycle

    scope, action = action_ops.check(payload.scope, payload.action)
    reason = payload.reason.strip() or "asked over the API"
    body = {"scope": scope, "action": action,
            "what": lifecycle.describe(scope, action)}
    if (scope, action) in action_ops.GOES_AWAY:
        background.add_task(action_ops.perform, scope, action, reason)
        return models.ActionResult.model_validate({**body, "performed": True})
    return models.ActionResult.model_validate(
        {**body, "performed": bool(action_ops.perform(scope, action, reason))})
