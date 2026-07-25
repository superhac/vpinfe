"""DOF and real-DMD, driven by table lifecycle events.

Hooks rather than subscribers: VPX drives the same devices, so releasing them is
part of launching rather than a notification about it.
"""

from __future__ import annotations

import logging

from common import events
from common.host.dof_service import start_dof_service_if_enabled, stop_dof_service
from common.host.libdmdutil_service import stop_libdmdutil_service

logger = logging.getLogger("vpinfe.common.host.peripherals")

# Ahead of anything else that hooks a launch: the devices come first.
PRIORITY = 10

_registered = False


def release_for_launch(**_payload) -> None:
    """Hand the devices over before the game file starts."""
    stop_dof_service()
    stop_libdmdutil_service(clear=False)


def reacquire_after_exit(*, ini_config=None, **_payload) -> None:
    """Take the devices back once the game file has exited."""
    start_dof_service_if_enabled(ini_config)


def register() -> None:
    """Attach to the bus. Safe to call more than once."""
    global _registered
    if _registered:
        return
    events.hook(events.TABLE_LAUNCHING, release_for_launch, priority=PRIORITY)
    events.hook(events.TABLE_EXITED, reacquire_after_exit, priority=PRIORITY)
    _registered = True
    logger.debug("Feedback hardware attached to table lifecycle events")


def reset_for_tests() -> None:
    global _registered
    _registered = False
