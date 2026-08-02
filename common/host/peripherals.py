"""DOF and real-DMD, driven by game lifecycle events.

Handing the devices over for a launch is a hook: VPX drives the same hardware, so
releasing them is part of launching rather than a notification about it. Reacting
to a selection is not - see the subscribers below.
"""

from __future__ import annotations

import logging

from common import events
from common.games.game_metadata import game_frontend_dof_event
from common.host import realdmd
from common.host.dof_service import (
    send_frontend_dof_event,
    start_dof_service_if_enabled,
    stop_dof_service,
)
from common.host.libdmdutil_service import show_image, stop_libdmdutil_service

logger = logging.getLogger("vpinfe.common.host.peripherals")

# Ahead of anything else that hooks a launch: the devices come first.
PRIORITY = 10

_registered = False
_realdmd_updater: realdmd.RealDmdUpdater | None = None


def release_for_launch(**_payload) -> None:
    """Hand the devices over before the table starts."""
    stop_dof_service()
    stop_libdmdutil_service(clear=False)


def reacquire_after_exit(*, ini_config=None, **_payload) -> None:
    """Take the devices back once the table has exited."""
    start_dof_service_if_enabled(ini_config)


def play_dof_effect(*, game=None, ini_config=None, **_payload) -> None:
    """Fire the table's DOF effect - solenoids and lights."""
    if game is None:
        return
    send_frontend_dof_event(ini_config, game_frontend_dof_event(game))


def show_realdmd_art(*, game=None, ini_config=None, **_payload) -> None:
    """Put the table's art on the real DMD panel."""
    if game is None:
        return
    _updater(ini_config).queue_image_update(
        getattr(game, "gameDirName", ""),
        realdmd.get_realdmd_image_for_game(game, ini_config),
    )


def _updater(ini_config) -> realdmd.RealDmdUpdater:
    """One updater for the process, not one per frontend window.

    Three windows each hold an API instance. Only the `table` window used to make
    this call, enforced in the theme-served JS; on the bus every subscriber hears
    every event, so the panel would be written three times over.
    """
    global _realdmd_updater
    if _realdmd_updater is None:
        _realdmd_updater = realdmd.RealDmdUpdater(ini_config, "shared", show_image)
    return _realdmd_updater


def register() -> None:
    """Attach to the bus. Safe to call more than once."""
    global _registered
    if _registered:
        return
    events.hook(events.GAME_LAUNCHING, release_for_launch, priority=PRIORITY)
    events.hook(events.GAME_EXITED, reacquire_after_exit, priority=PRIORITY)
    # Two devices, two subscribers, one trigger. Neither knows the other exists,
    # so a DOF failure still leaves the art on the panel and vice versa - and a
    # third device is a third subscriber rather than an edit here.
    events.subscribe(events.GAME_SELECTED, play_dof_effect)
    events.subscribe(events.GAME_SELECTED, show_realdmd_art)
    _registered = True
    logger.debug("Peripherals attached to table lifecycle events")


def reset_for_tests() -> None:
    global _registered, _realdmd_updater
    _registered = False
    _realdmd_updater = None
