"""Stable local identity for one installation: an opaque id at `install.id`.

Follows `common/games/game_identity.py`: opaque id, explicit minting, reading never
writes. Nothing resolves through `display_name`, so renaming an install is safe.
"""

from __future__ import annotations

import logging
import socket

from common.config_access import cfg_get, cfg_list, cfg_set
from common.games.ids import new_id

logger = logging.getLogger("vpinfe.common.install_identity")

ID_SECTION = "install"
ID_KEY = "id"

HUB = "hub"
DEVICE = "device"
ROLES = (HUB, DEVICE)

# What every 2.x install and every desktop install already is.
DEFAULT_ROLES = (HUB, DEVICE)


def install_id(config) -> str:
    """This install's id, or "" if it has not been minted. Never writes."""
    return cfg_get(config, ID_SECTION, ID_KEY).strip()


def ensure_id(config) -> str:
    """This install's id, minting and saving one if it has none. An id that is not on
    disk is not an identity: the next start would mint another and become someone else."""
    existing = install_id(config)
    if existing:
        return existing

    minted = new_id()
    cfg_set(config, ID_SECTION, ID_KEY, minted)
    config.save()
    logger.info("Minted install id %s", minted)
    return minted


def display_name(config) -> str:
    """What to call this install, falling back to the hostname. Reading never writes the
    default down, so a renamed machine follows instead of keeping its first name."""
    configured = cfg_get(config, ID_SECTION, "display_name").strip()
    if configured:
        return configured
    return _hostname()


def _hostname() -> str:
    try:
        name = socket.gethostname().split(".")[0].strip()
    except Exception:
        name = ""
    return name or "VPinFE"


def roles(config) -> list[str]:
    """The roles this install serves, in a stable order. Empty or unrecognized falls back
    to both, never to none: a typo must not decide this machine stopped launching games."""
    configured = [role.strip().lower() for role in cfg_list(config, ID_SECTION, "roles")]
    known = [role for role in ROLES if role in configured]
    unknown = sorted(set(configured) - set(ROLES))
    if unknown:
        logger.warning("Ignoring unknown install roles: %s", ", ".join(unknown))
    return known or list(DEFAULT_ROLES)


def has_role(config, role: str) -> bool:
    return role in roles(config)
