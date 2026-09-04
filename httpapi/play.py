"""Play-host state.

The snapshot a client takes once; `play.state_changed` on the event stream is how
it hears about every change after that.
"""

from __future__ import annotations

from fastapi import APIRouter

from common import device_client, events, lifecycle
from common.host import launch_state

from . import models, scopes
from .auth import requires
from .events import declare_snapshot

router = APIRouter(prefix="/play", tags=["play"])


@router.get("/state", summary="What this play host is doing",
            dependencies=[requires(scopes.PLAY_READ)])
def get_play_state() -> models.PlayState:
    return launch_state.current().as_dict()


@router.post("/stop", summary="Close the table this play host is running",
             dependencies=[requires(scopes.PLAY_STOP)])
def stop_play() -> models.PlayStopped:
    """Close whatever is running, and say what was closed.

    Through the lifecycle scope rather than reaching for the process, so this takes the
    same confirm-announce-perform path as every other stop and the other surfaces hear
    `lifecycle.acting`. The name is read before the stop because the state clears as
    soon as the process dies.
    """
    state = launch_state.current()
    if not state.launching:
        # Nothing to announce either: a lifecycle request with no table would tell every
        # surface a table was closing when none was.
        return {"stopped": False, "game_name": None}

    went_ahead = device_client.local().request(
        lifecycle.TABLE, lifecycle.STOP,
        origin=lifecycle.Origin(lifecycle.SURFACE_API),
        reason="asked over the API")
    return {"stopped": bool(went_ahead),
            "game_name": state.game_name if went_ahead else None}


def declare_snapshots() -> None:
    """Hand the current state to a client the moment it subscribes.

    Without it a client connecting mid-launch sees nothing until the launch ends,
    and a reconnect after a gap would leave the overlay stuck.
    """
    declare_snapshot(events.PLAY_STATE_CHANGED,
                     lambda: {"state": launch_state.current().as_dict()})
