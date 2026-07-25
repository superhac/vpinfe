"""Play-host state.

Interim: the frontend polls launch state once a second because there is nothing
to subscribe to yet. The event stream replaces both the poll and this endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter

from common import launch_state

from . import scopes
from .auth import requires

router = APIRouter(prefix="/play", tags=["play"])


@router.get("/state", summary="What this play host is doing",
            dependencies=[requires(scopes.PLAY_READ)])
def get_play_state() -> dict:
    return launch_state.current().as_dict()
