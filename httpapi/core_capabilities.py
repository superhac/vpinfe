"""What this instance can do, declared for discovery.

Only capabilities with endpoints behind them - advertising one that nothing serves
would make discovery a wish list. See docs/http_api.md.
"""

from __future__ import annotations

import logging
from pathlib import Path

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


def _launch_available() -> bool | tuple[bool, str]:
    """Whether this machine can actually start a game.

    Reading play state works without a launcher; starting one does not. Discovery
    has to say so, or an instance advertises a Play button that always fails.
    """
    try:
        from common.config_access import SettingsConfig
        from common.paths import get_ini_config

        configured = (SettingsConfig.from_config(get_ini_config()).vpx_bin_path or "").strip()
        if not configured:
            return False, ("No launcher configured. Set Settings.vpxbinpath, or "
                           "VPinFE.altlauncher on individual games.")
        if not Path(configured).exists():
            return False, f"Configured launcher does not exist: {configured}"
        return True
    except Exception as exc:
        return False, f"Could not determine launcher state: {exc}"


def _rom_audit_available() -> bool | tuple[bool, str]:
    """Whether this machine can run PinMAME's own ROM audit."""
    try:
        from common.config_access import SettingsConfig
        from common.host import pinmame_catalog
        from common.paths import get_ini_config

        vpx_bin = SettingsConfig.from_config(get_ini_config()).vpx_bin_path
        return pinmame_catalog.availability(vpx_bin)
    except Exception as exc:
        return False, f"Could not determine libpinmame state: {exc}"


def declare_core() -> None:
    """Declare the capabilities this build actually serves."""
    capabilities.declare(capabilities.Capability(
        name="library",
        residency=[capabilities.RESIDENCY_HUB],
        description="Game inventory, identity, metadata and media",
    ))
    capabilities.declare(capabilities.Capability(
        name="uploads",
        residency=[capabilities.RESIDENCY_HUB],
        description="Upload sessions and the asset import pipeline",
    ))
    capabilities.declare(capabilities.Capability(
        name="play",
        residency=[capabilities.RESIDENCY_PLAYER],
        description="Launch lifecycle state for this machine",
    ))
    capabilities.declare(capabilities.Capability(
        name="launch",
        residency=[capabilities.RESIDENCY_PLAYER],
        description="Starting a game on this machine",
        is_available=_launch_available,
    ))
    capabilities.declare(capabilities.Capability(
        name="peripherals",
        residency=[capabilities.RESIDENCY_PLAYER],
        description="DOF, real-DMD and other attached devices",
        is_available=_peripherals_available,
    ))
    capabilities.declare(capabilities.Capability(
        name="rom_audit",
        residency=[capabilities.RESIDENCY_PLAYER],
        description="ROM set verification through the VPX install's own PinMAME",
        is_available=_rom_audit_available,
    ))
    capabilities.declare(capabilities.Capability(
        name="events",
        residency=[capabilities.RESIDENCY_HUB, capabilities.RESIDENCY_PLAYER],
        description="Game lifecycle, play state and job progress as they happen",
    ))
    capabilities.declare(capabilities.Capability(
        name="jobs",
        residency=[capabilities.RESIDENCY_HUB],
        description="Slow work runs in the background and reports progress",
    ))
