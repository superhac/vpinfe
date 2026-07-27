"""What this instance is: discovery and health.

Not "meta" - every endpoint is metadata about something. These answer "what am I
talking to", which is the question discovery exists for. Table metadata is a
different thing entirely and lives under common/.
"""

from __future__ import annotations

from fastapi import APIRouter

from common.app_version import get_version

from . import capabilities, models, scopes
from .auth import requires


def discovery_payload(prefix: str, api_version: str) -> dict:
    """The discovery document. Links are relative so they survive a reverse proxy;
    present-but-null means a known link this instance does not offer."""
    return {
        "name": "VPinFE",
        "api_version": api_version,
        "app_version": get_version(),
        "capabilities": capabilities.declared(),
        "extensions": [],
        "links": {
            "self": prefix,
            "health": f"{prefix}/health",
            "openapi": f"{prefix}/openapi.json",
            "docs": f"{prefix}/docs",
            "events": f"{prefix}/events",
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
