"""How this install presents itself to everything else.

Its id, the name it goes by, the ports its other servers answer on, its registry row and
its mDNS announcement. The registry row and the announcement carry the same two facts, so
they are written together.
"""

from __future__ import annotations

import logging

from common import device_registry, discovery, install_identity
from common.config_access import NetworkConfig
from common.device_registry import get_device_registry
from common.discovery import Peer
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


def announce_on_the_network() -> None:
    """Say what this install is, and note the ones that say back."""
    try:
        config = get_ini_config()
    except Exception as exc:
        logger.warning("Could not read this install to announce it: %s", exc)
        return
    discovery.start(config, on_peer=_heard_from)


def _heard_from(peer: Peer) -> None:
    """File an install this one heard from, when managing devices is its job.

    The feature is read per announcement rather than once at startup, so switching it on
    from the Console does not need every other machine to restart before it is noticed.
    """
    try:
        config = get_ini_config()
        if not install_identity.has_feature(config, install_identity.DEVICES):
            return
        get_device_registry().record(
            peer.install_id,
            kind=device_registry.KIND_VPINFE,
            display_name=peer.display_name,
            features=peer.features,
            address=peer.address,
            port=peer.port,
        )
    except Exception:
        logger.debug("Could not record the install that announced itself", exc_info=True)


def identity() -> dict:
    """Who is answering. A broken config must not take discovery down with it, so this
    degrades to the unidentified answer 2.x gave rather than raising."""
    try:
        config = get_ini_config()
        return {
            "install_id": install_identity.install_id(config),
            "display_name": install_identity.display_name(config),
            "features": install_identity.features(config),
        }
    except Exception as exc:
        logger.warning("Could not read this install's identity: %s", exc)
        return {"install_id": "", "display_name": "", "features": []}


def service_ports() -> dict:
    """Where this install's other servers are, for a caller that is not on this machine.

    Only the asset server so far, and only its port: the host is wherever the caller
    reached this install, which is the one address known to be routable to here. A device
    needs this because artwork is served off a different port from the API, and nothing
    else tells it which - guessing 8000 is right until someone moves it.
    """
    try:
        return {"assets": {
            "port": NetworkConfig.from_config(get_ini_config()).theme_assets_port}}
    except Exception as exc:
        logger.warning("Could not read this install's service ports: %s", exc)
        return {}
