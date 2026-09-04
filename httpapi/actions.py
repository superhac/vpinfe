"""What this install can be told to do to itself.

The lifecycle vocabulary served over HTTP: close the table, reopen the frontend windows,
restart VPinFE, reboot the machine. `common/lifecycle.py` already owns which pairs exist,
what each is called and what performs it, so this serves that rather than restating it -
a pair added there appears here without this file being touched.

Two lists, not one. What the vocabulary allows is fixed by the build; what is wired up
depends on the install, and a headless one owns no frontend windows. A button that
reports success while nothing happened is worse than a button that is not offered, so
both facts travel together.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Body

from common import device_client, lifecycle

from . import models, scopes
from .auth import requires
from .errors import FeatureUnavailableError, InvalidRequestError

logger = logging.getLogger("vpinfe.httpapi.actions")

router = APIRouter(prefix="/actions", tags=["actions"])

# The ones that take the answer with them. A process that is stopping cannot report
# whether it stopped, so these are handed to a background task and the response goes out
# first - the same order `POST /update` uses, and for the same reason.
GOES_AWAY = frozenset({
    (lifecycle.APP, lifecycle.STOP), (lifecycle.APP, lifecycle.RESTART),
    (lifecycle.SYSTEM, lifecycle.STOP), (lifecycle.SYSTEM, lifecycle.RESTART),
})

# Why an action is not offered, in the words a person reads. The API answers with the
# fact; the sentence for it belongs to whatever is showing it, but a caller with no
# surface of its own still needs one.
NOT_WIRED = "Nothing on this install performs that."


def _describe(scope: str, action: str) -> dict:
    performable = lifecycle.performable(scope, action)
    return {"scope": scope, "action": action,
            "label": lifecycle.describe(scope, action),
            "available": performable,
            "reason": "" if performable else NOT_WIRED}


@router.get("", summary="What this install can be asked to do",
            dependencies=[requires(scopes.SYSTEM_READ)])
def list_actions() -> models.ActionList:
    """Every pair, offered or not: a surface greys one rather than hiding it, because two
    installs showing different buttons look like different products."""
    found = [_describe(scope, action) for scope, action in lifecycle.offered()]
    return {"count": len(found), "actions": found}


@router.post("", summary="Do one of them",
             dependencies=[requires(scopes.SYSTEM_ADMIN)])
def perform_action(background: BackgroundTasks,
                   payload: models.ActionRequest = Body(...)) -> models.ActionResult:
    """Confirm-announce-perform, through the same path every other surface takes.

    Never asks the caller to confirm: an HTTP request is over by the time anything here
    could put the question, so whoever called put it to their own user first. That is
    what the API origin means and it is why this passes no confirm scopes.
    """
    scope, action = payload.scope.strip().lower(), payload.action.strip().lower()
    if (scope, action) not in lifecycle.offered():
        raise InvalidRequestError(
            f"Not something an install does: {action} the {scope}. "
            "GET /actions lists them.")
    if not lifecycle.performable(scope, action):
        raise FeatureUnavailableError(NOT_WIRED,
                                      details={"scope": scope, "action": action})

    what = lifecycle.describe(scope, action)
    reason = payload.reason.strip() or "asked over the API"
    if (scope, action) in GOES_AWAY:
        background.add_task(_perform, scope, action, reason)
        return {"scope": scope, "action": action, "what": what, "performed": True}
    return {"scope": scope, "action": action, "what": what,
            "performed": bool(_perform(scope, action, reason))}


def _perform(scope: str, action: str, reason: str) -> bool:
    # Closing a table goes through the play route's own handler rather than straight to
    # the lifecycle scope. That one checks whether a table is running first, so asking to
    # close one when none is reports honestly instead of reporting that it closed one.
    if (scope, action) == (lifecycle.TABLE, lifecycle.STOP):
        from .play import stop_play

        return bool(stop_play().get("stopped"))
    return device_client.local().request(
        scope, action, origin=lifecycle.Origin(lifecycle.SURFACE_API), reason=reason)
