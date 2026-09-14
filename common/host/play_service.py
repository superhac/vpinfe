"""Closing the table this host is playing, and saying what was closed."""

from __future__ import annotations

from common import device_client, lifecycle
from common.host import launch_state


def stop_playing(reason: str = "asked over the API") -> dict:
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
        reason=reason)
    return {"stopped": bool(went_ahead),
            "game_name": state.game_name if went_ahead else None}
