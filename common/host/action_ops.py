"""What this install can be told to do to itself.

`common/lifecycle.py` owns which pairs exist, what each is called and what performs them,
so this serves that rather than restating it - a pair added there appears here without
this file being touched.

Two lists, not one. What the vocabulary allows is fixed by the build; what is wired up
depends on the install, and a headless one owns no frontend windows. A button that reports
success while nothing happened is worse than one that is not offered, so both facts travel
together.
"""

from __future__ import annotations

import logging

from common import device_client, lifecycle, service_errors
from common.host import play_service
from common.i18n import t

logger = logging.getLogger("vpinfe.common.host.action_ops")

# The ones that take the answer with them. A process that is stopping cannot report
# whether it stopped, so a caller hands these to a background task and answers first.
GOES_AWAY = frozenset({
    (lifecycle.VPINFE, lifecycle.STOP), (lifecycle.VPINFE, lifecycle.RESTART),
    (lifecycle.SYSTEM, lifecycle.STOP), (lifecycle.SYSTEM, lifecycle.RESTART),
})

# Why an action is not offered, in the words a person reads. The fact is what is answered;
# the sentence for it belongs to whatever is showing it, but a caller with no surface of
# its own still needs one.
NOT_WIRED = "Nothing on this install performs that."


def _describe(scope: str, action: str) -> dict:
    performable = lifecycle.performable(scope, action)
    return {"scope": scope, "action": action,
            "label": lifecycle.label(scope, action),
            "label_key": f"action.{scope}.{action}",
            "available": performable,
            "reason": "" if performable else NOT_WIRED}


def listing() -> dict:
    """Every pair, offered or not: a surface greys one rather than hiding it, because two
    installs showing different buttons look like different products."""
    found = [_describe(scope, action) for scope, action in lifecycle.offered()]
    return {"count": len(found), "actions": found}


def check(scope: str, action: str) -> tuple[str, str]:
    """The pair as the vocabulary spells it, or a refusal. Nothing is performed."""
    scope, action = scope.strip().lower(), action.strip().lower()
    if (scope, action) not in lifecycle.offered():
        raise service_errors.RefusedError(
            t("error.actions.not_something_install_get", action=(action), scope=(scope)))
    if not lifecycle.performable(scope, action):
        raise service_errors.UnavailableError(
            NOT_WIRED, details={"scope": scope, "action": action})
    return scope, action


def perform(scope: str, action: str, reason: str) -> bool:
    """Do one of them, through the same path every other surface takes."""
    # Closing a table goes through the play service rather than straight to the lifecycle
    # scope. That one checks whether a table is running first, so asking to close one when
    # none is reports honestly instead of reporting that it closed one.
    if (scope, action) == (lifecycle.TABLE, lifecycle.STOP):
        return bool(play_service.stop_playing(reason)["stopped"])
    return device_client.local().request(
        scope, action, origin=lifecycle.Origin(lifecycle.SURFACE_API), reason=reason)
