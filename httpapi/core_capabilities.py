"""What this instance can do, declared for discovery.

Residency says where a capability has to run: `catalog` for things that only need
the library, `play_host` for things tied to the machine where tables launch and the
hardware lives. Availability is answered per request, so a capability that depends
on configuration or attached hardware tells the truth after the user changes
something rather than at whatever import time happened to be.

Only capabilities with endpoints behind them are declared. Advertising one that
nothing serves would make discovery a wish list.
"""

from __future__ import annotations

import logging

from . import capabilities

logger = logging.getLogger("vpinfe.httpapi.core_capabilities")


def _feedback_hardware_available() -> bool | tuple[bool, str]:
    """DOF is a config switch plus a working runner, not an assumption."""
    try:
        from common.dof_service import _is_enabled
        from common.paths import get_ini_config

        if not _is_enabled(get_ini_config()):
            return False, "DOF is turned off in configuration"
        return True
    except Exception as exc:
        return False, f"Could not determine DOF state: {exc}"


def declare_core() -> None:
    """Declare the capabilities this build actually serves."""
    capabilities.declare(capabilities.Capability(
        name="library",
        residency=capabilities.RESIDENCY_CATALOG,
        description="Table inventory, identity, metadata and media",
    ))
    capabilities.declare(capabilities.Capability(
        name="acquisition",
        residency=capabilities.RESIDENCY_CATALOG,
        description="Upload sessions and the asset import pipeline",
    ))
    capabilities.declare(capabilities.Capability(
        name="play",
        residency=capabilities.RESIDENCY_PLAY_HOST,
        description="Launch lifecycle state for this machine",
    ))
    capabilities.declare(capabilities.Capability(
        name="feedback_hardware",
        residency=capabilities.RESIDENCY_PLAY_HOST,
        description="DOF and real-DMD output",
        is_available=_feedback_hardware_available,
    ))
