"""VPinFE's HTTP API: a FastAPI app mounted at /api/v1.

Mounted rather than added to the NiceGUI app so the envelope, CORS and the auth
seam apply here and nowhere else. Rationale in docs/http_api.md.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import capabilities, meta
from .errors import (
    ApiError,
    FeatureUnavailable,
    InvalidRequest,
    NotFound,
    error_response,
    install_error_handlers,
)

logger = logging.getLogger("vpinfe.httpapi")

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"

__all__ = [
    "API_PREFIX",
    "API_VERSION",
    "ApiError",
    "FeatureUnavailable",
    "InvalidRequest",
    "NotFound",
    "capabilities",
    "create_api_app",
    "error_response",
    "register",
]


def create_api_app() -> FastAPI:
    """Build the /api/v1 app. Standalone: importable and testable without NiceGUI."""
    api = FastAPI(
        title="VPinFE API",
        version=API_VERSION,
        description="HTTP API for VPinFE. Unstable until v1 is declared.",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    # Matches what the endpoints this will absorb already allow. Tightening it is
    # a policy decision for the auth seam.
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    install_error_handlers(api)
    api.include_router(meta.build_router(API_PREFIX, API_VERSION))
    return api


def register(app) -> None:
    """Mount the API on the given FastAPI/NiceGUI app."""
    api = create_api_app()

    # Without this, "/api/v1" redirects to "/api/v1/". Must precede the mount to
    # win the route match.
    app.add_api_route(
        API_PREFIX,
        lambda: meta.discovery_payload(API_PREFIX, API_VERSION),
        methods=["GET"],
        include_in_schema=False,
    )
    app.mount(API_PREFIX, api)
    logger.info("HTTP API mounted at %s", API_PREFIX)
