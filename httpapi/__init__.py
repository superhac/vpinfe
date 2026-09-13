"""VPinFE's HTTP API: a FastAPI app mounted at /api/v1.

Mounted rather than added to the NiceGUI app so the envelope, CORS and the auth
boundary apply here and nowhere else. Rationale in docs/http_api.md.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import (
    about,
    actions,
    assets,
    auth,
    capabilities,
    collections,
    config,
    core_capabilities,
    devices,
    events,
    extensions,
    filesystem,
    games,
    input,
    instance,
    jobs,
    launchers,
    library,
    locations,
    logs,
    manufacturers,
    media,
    mediasources,
    metrics,
    play,
    preferences,
    scopes,
    tables,
    themes,
    uploads,
)
from .errors import (
    ApiError,
    FeatureUnavailableError,
    InvalidRequestError,
    NotFoundError,
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
    "FeatureUnavailableError",
    "InvalidRequestError",
    "NotFoundError",
    "auth",
    "capabilities",
    "create_api_app",
    "error_response",
    "events",
    "extensions",
    "register",
    "scopes",
]


def create_api_app() -> FastAPI:
    """Build the /api/v1 app. Standalone: importable and testable without NiceGUI."""
    # What extensions may do to the library, handed to the host before anything loads.
    # Here rather than at startup so a test app offers the same set the real one does.
    from . import extension_ops

    extension_ops.offer_all()

    api = FastAPI(
        title="VPinFE API",
        version=API_VERSION,
        description="HTTP API for VPinFE. Unstable until v1 is declared.",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    # Matches what the endpoints this will absorb already allow. Tightening it is
    # a policy decision for the authorization boundary.
    # Auth first so CORS ends up outermost: a preflight OPTIONS has no identity to
    # stamp and CORSMiddleware answers it before anything else sees it.
    api.add_middleware(auth.ScopeMiddleware)
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    install_error_handlers(api, on_unhandled=extensions.blame)
    api.include_router(instance.build_router(API_PREFIX, API_VERSION))
    api.include_router(events.router)
    api.include_router(collections.router)
    api.include_router(jobs.router)
    api.include_router(library.router)
    api.include_router(devices.router)
    api.include_router(actions.router)
    api.include_router(logs.router)
    api.include_router(preferences.router)
    api.include_router(config.router)
    api.include_router(launchers.router)
    api.include_router(locations.router)
    api.include_router(metrics.router)
    api.include_router(themes.router)
    api.include_router(about.router)
    api.include_router(manufacturers.router)
    api.include_router(play.router)
    api.include_router(input.router)
    api.include_router(games.router)
    api.include_router(tables.router)
    api.include_router(media.router)
    api.include_router(assets.router)
    api.include_router(filesystem.router)
    api.include_router(mediasources.router)
    api.include_router(uploads.router)
    api.include_router(uploads.vps_router)
    api.include_router(extensions.router)
    # Last, so an extension cannot take a path core wanted: a router already
    # included answers first, and the prefix keeps them apart anyway.
    extensions.mount(api)

    instance.mint_identity()
    core_capabilities.declare_core()
    play.declare_snapshots()
    events.attach()
    auth.assert_every_route_declares_a_scope(api)
    return api


def register(app) -> None:
    """Mount the API on the given FastAPI/NiceGUI app."""
    api = create_api_app()

    # Without this, "/api/v1" redirects to "/api/v1/". Must precede the mount to
    # win the route match.
    app.add_api_route(
        API_PREFIX,
        lambda: instance.discovery_payload(API_PREFIX, API_VERSION),
        methods=["GET"],
        include_in_schema=False,
    )
    app.mount(API_PREFIX, api)
    logger.info("HTTP API mounted at %s", API_PREFIX)
