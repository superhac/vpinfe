"""DOF and real-DMD, driven by table lifecycle events.

These are hooks rather than subscribers on purpose. VPX talks to the same devices,
so the hardware has to be released before it starts and reacquired after it exits -
if releasing fails, launching anyway would hand VPX a device something else still
holds. A hook that raises stops the launch, which is the wanted behavior.

Both launch paths - the frontend wheel and the Remote Control page - announce the
same events, so this protocol lives in one place instead of being repeated by
whoever happens to be starting a table.
"""

from __future__ import annotations

import logging

from common import events
from common.dof_service import start_dof_service_if_enabled, stop_dof_service
from common.libdmdutil_service import stop_libdmdutil_service

logger = logging.getLogger("vpinfe.common.feedback_hardware")

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
