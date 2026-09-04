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

# What an install is *meant* to do, chosen deliberately. Roles said this before and said
# it badly: `hub` and `device` were trying to name both what an install does and what
# kind of thing it is, and neither word survived the second job.
LIBRARY = "library"
FRONTEND = "frontend"
DEVICES = "devices"
# A rollup over the other three rather than something this install does. Off unless it
# is asked for: it answers a question nobody had, and a front door that reports on a
# library this machine may not have is worse than no front door.
OVERVIEW = "overview"
FEATURES = (LIBRARY, FRONTEND, DEVICES, OVERVIEW)

# What every 2.x install and every desktop install already is. Not every feature: this
# is also what an empty or unreadable setting falls back to, so a feature that has to be
# asked for must not be in here or a typo would switch it on.
DEFAULT_FEATURES = (LIBRARY, FRONTEND, DEVICES)


def install_id(config) -> str:
    """This install's id, or "" if it has not been minted. Never writes."""
    return cfg_get(config, ID_SECTION, ID_KEY).strip()


def mint_id() -> str:
    """A fresh identity. One generator for every id a hub deals in, so one it minted for
    a phone and one an install minted for itself are indistinguishable - which is what
    lets the registry key on a single field."""
    return new_id()


def ensure_id(config) -> str:
    """This install's id, minting and saving one if it has none. An id that is not on
    disk is not an identity: the next start would mint another and become someone else."""
    existing = install_id(config)
    if existing:
        return existing

    minted = mint_id()
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


def features(config) -> list[str]:
    """What this install is meant to do, in a stable order.

    Empty or unrecognized falls back to the defaults, never to none: a typo must not
    decide this machine stopped launching games. It falls back to those rather than to
    every feature, so one that has to be asked for is never acquired by accident.
    """
    configured = [name.strip().lower()
                  for name in cfg_list(config, ID_SECTION, "features")]
    known = [name for name in FEATURES if name in configured]
    unknown = sorted(set(configured) - set(FEATURES))
    if unknown:
        logger.warning("Ignoring unknown install features: %s", ", ".join(unknown))
    return known or list(DEFAULT_FEATURES)


def has_feature(config, feature: str) -> bool:
    return feature in features(config)
