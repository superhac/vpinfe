"""What this instance can do, declared for discovery.

Only capabilities with endpoints behind them - advertising one that nothing serves
would make discovery a wish list. See docs/http_api.md.
"""

from __future__ import annotations

import logging

from . import capabilities

logger = logging.getLogger("vpinfe.httpapi.core_capabilities")


def _peripherals_available() -> bool | tuple[bool, str]:
    """Available if any peripheral is switched on, not only DOF."""
    try:
        from common.host.dof_service import _is_enabled as dof_enabled
        from common.host.libdmdutil_service import _is_enabled as dmd_enabled
        from common.paths import get_ini_config

        config = get_ini_config()
        enabled = [name for name, check in (("DOF", dof_enabled), ("real-DMD", dmd_enabled))
                   if check(config)]
        if not enabled:
            return False, "No peripherals are turned on in configuration"
        return True
    except Exception as exc:
        return False, f"Could not determine peripheral state: {exc}"


def declare_core() -> None:
    """Declare the capabilities this build actually serves."""
    capabilities.declare(capabilities.Capability(
        name="library",
        residency=[capabilities.RESIDENCY_CATALOG],
        description="Table inventory, identity, metadata and media",
    ))
    capabilities.declare(capabilities.Capability(
        name="acquisition",
        residency=[capabilities.RESIDENCY_CATALOG],
        description="Upload sessions and the asset import pipeline",
    ))
    capabilities.declare(capabilities.Capability(
        name="play",
        residency=[capabilities.RESIDENCY_PLAY_HOST],
        description="Launch lifecycle state for this machine",
    ))
    capabilities.declare(capabilities.Capability(
        name="peripherals",
        residency=[capabilities.RESIDENCY_PLAY_HOST],
        description="DOF, real-DMD and other attached devices",
        is_available=_peripherals_available,
    ))
    capabilities.declare(capabilities.Capability(
        name="events",
        residency=[capabilities.RESIDENCY_CATALOG, capabilities.RESIDENCY_PLAY_HOST],
        description="Table lifecycle, play state and job progress as they happen",
    ))
