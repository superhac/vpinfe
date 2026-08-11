"""What this instance is: discovery and health.

Not "meta" - every endpoint is metadata about something. These answer "what am I
talking to", which is the question discovery exists for. Table metadata is a
different thing entirely and lives under common/.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from common import install_identity
from common.app_version import get_version
from common.config_access import NetworkConfig
from common.paths import get_ini_config

from . import capabilities, models, scopes
from .auth import requires

logger = logging.getLogger("vpinfe.httpapi.instance")


def mint_identity() -> None:
    """Give this install an id if it has none, at startup rather than on a request.

    Discovery only reads, so a GET never writes to the config file - and the id is on
    disk before anything can ask for it.
    """
    try:
        install_identity.ensure_id(get_ini_config())
    except Exception as exc:
        logger.warning("Could not mint this install's identity: %s", exc)


def _identity() -> dict:
    """Who is answering. A broken config must not take discovery down with it, so this
    degrades to the unidentified answer 2.x gave rather than raising."""
    try:
        config = get_ini_config()
        return {
            "install_id": install_identity.install_id(config),
            "display_name": install_identity.display_name(config),
            "roles": install_identity.roles(config),
        }
    except Exception as exc:
        logger.warning("Could not read this install's identity: %s", exc)
        return {"install_id": "", "display_name": "", "roles": []}


def _services() -> dict:
    """Where this install's other servers are, for a client that is not on this machine.

    Only the asset server so far, and only its port: the host is wherever the caller
    reached this document, which is the one address known to be routable to here. A
    player needs this because artwork is served off a different port from the API, and
    nothing else tells it which - guessing 8000 is right until someone moves it.
    """
    try:
        return {"assets": {"port": NetworkConfig.from_config(get_ini_config()).theme_assets_port}}
    except Exception as exc:
        logger.warning("Could not read this install's service ports: %s", exc)
        return {}


def discovery_payload(prefix: str, api_version: str) -> dict:
    """The discovery document. Links are relative so they survive a reverse proxy;
    present-but-null means a known link this instance does not offer."""
    return {
        # `name` is the product, byte-identical everywhere; `install_id` is who this is.
        "name": "VPinFE",
        **_identity(),
        "api_version": api_version,
        "app_version": get_version(),
        "capabilities": capabilities.declared(),
        "services": _services(),
        "extensions": [],
        "links": {
            "self": prefix,
            "health": f"{prefix}/health",
            "openapi": f"{prefix}/openapi.json",
            "docs": f"{prefix}/docs",
            "collections": f"{prefix}/collections",
            "events": f"{prefix}/events",
            "jobs": f"{prefix}/jobs",
            "manufacturers": f"{prefix}/manufacturers",
        },
    }


def build_router(prefix: str, api_version: str) -> APIRouter:
    router = APIRouter(tags=["instance"])

    @router.get("/", summary="API discovery", dependencies=[requires(scopes.INSTANCE_READ)])
    def discovery() -> models.Discovery:
        return discovery_payload(prefix, api_version)

    @router.get("/health", summary="Liveness check", dependencies=[requires(scopes.INSTANCE_READ)])
    def health() -> models.Health:
        return {"status": "ok"}

    return router
