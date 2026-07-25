"""What this instance can do, declared for discovery.

Only capabilities with endpoints behind them - advertising one that nothing serves
would make discovery a wish list. See docs/http_api.md.
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
