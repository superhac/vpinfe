"""One-time conversions to a user's device registry.

Separate from `device_registry`, which says what a device is allowed to be.
"""

from __future__ import annotations

import logging

from common.config_access import cfg_get
from common.device_registry import KIND_VPX_MOBILE, mint_device_id

logger = logging.getLogger("vpinfe.common.device_migration")

# 2.x could hold one mobile device, as two keys in [mobile]. It becomes a registry entry,
# after which several can coexist and the keys are read by nothing.
MOBILE_MIGRATION = "mobile_ini_becomes_a_device"
MOBILE_SECTION = "mobile"
MOBILE_DISPLAY_NAME = "VPX Mobile"
DEFAULT_MOBILE_PORT = 2112


def ensure_mobile_device(registry, config) -> int:
    """Import `[mobile]` as a `vpx_mobile` entry. Returns how many were created.

    Marked whatever the outcome, including when there was nothing to import: the marker
    records that this build has looked, so a user who later clears the setting does not
    get the old address back on the next start.
    """
    if registry.has_migrated(MOBILE_MIGRATION):
        return 0

    address = str(cfg_get(config, MOBILE_SECTION, "device_ip", "") or "").strip()
    existing = [d for d in registry.devices() if d.kind == KIND_VPX_MOBILE]
    if not address or existing:
        # An entry already there means someone has configured this since; the ini is the
        # older statement and must not overwrite it.
        registry.record_migration(MOBILE_MIGRATION)
        return 0

    registry.record(mint_device_id(), kind=KIND_VPX_MOBILE,
                    display_name=MOBILE_DISPLAY_NAME,
                    address=address, port=_port(config))
    registry.record_migration(MOBILE_MIGRATION)
    logger.info("Imported [mobile] %s as a device", address)
    return 1


def _port(config) -> int:
    raw = cfg_get(config, MOBILE_SECTION, "device_port", "") or DEFAULT_MOBILE_PORT
    try:
        return int(str(raw).strip() or DEFAULT_MOBILE_PORT)
    except ValueError:
        return DEFAULT_MOBILE_PORT
