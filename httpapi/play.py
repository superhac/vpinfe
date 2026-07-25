"""Play-host state.

The snapshot a client takes once; `play.state_changed` on the event stream is how
it hears about every change after that.
"""

from __future__ import annotations

from fastapi import APIRouter

from common import events
from common.host import launch_state

from . import scopes
from .auth import requires
from .events import declare_snapshot

router = APIRouter(prefix="/play", tags=["play"])


@router.get("/state", summary="What this play host is doing",
            dependencies=[requires(scopes.PLAY_READ)])
def get_play_state() -> dict:
    return launch_state.current().as_dict()


def declare_snapshots() -> None:
    """Hand the current state to a client the moment it subscribes.

    Without it a client connecting mid-launch sees nothing until the launch ends,
    and a reconnect after a gap would leave the overlay stuck.
    """
    declare_snapshot(events.PLAY_STATE_CHANGED,
                     lambda: {"state": launch_state.current().as_dict()})
