"""How this install presents itself to everything else: its registry row and its
announcement. Both carry the same two facts, so they are written together."""

from __future__ import annotations

import logging

from common import device_registry, discovery, install_identity
from common.device_registry import get_device_registry
from common.paths import get_ini_config

logger = logging.getLogger("vpinfe.common.install_presence")


def record_self() -> None:
    """Put what this install currently calls itself into its own registry entry.

    Called again whenever the name changes, not only at startup. A registry entry is a
    copy of what an install reported, which for a remote device goes stale by design -
    but this install can say so the moment it is renamed, and every screen listing
    devices reads the registry rather than asking each one.
    """
    try:
        config = get_ini_config()
        get_device_registry().record(
            install_identity.install_id(config),
            kind=device_registry.KIND_VPINFE,
            display_name=install_identity.display_name(config),
            features=install_identity.features(config),
        )
    except Exception as exc:
        # A registry that cannot be written must not stop the API starting: the entry is
        # a label, and the install is identified with or without it.
        logger.warning("Could not record this install in its own registry: %s", exc)
        return
    # The announcement carries the same two facts, so it is refreshed with them rather
    # than left saying what this install used to be called until the next restart.
    discovery.refresh(config)
