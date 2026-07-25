"""The authorization boundary.

The mechanism is here from the start; the policy it enforces is not. Today every
caller that can reach the API is granted every scope, which is exactly how the app
behaves now - this changes nothing for anyone. What it buys is that the boundary exists
and cannot be routed around, so tightening later is a policy change rather than a
retrofit across every endpoint.

Three properties hold it together:

- One middleware stamps an identity on every request into /api/v1. It runs before
  any route, so no route is reachable without passing it.
- Every route declares the scope it needs, checked at startup rather than trusted.
  A route that forgets one stops the app rather than quietly serving unguarded.
- Core services never learn about any of this. Authorization stays at the edge.

"Public" is not something a route asserts about itself. Discovery and health carry
`instance:read` like everything else; a policy decides whether to grant it to a caller
who presented nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware

from . import scopes
from .errors import CODE_FORBIDDEN, ApiError

logger = logging.getLogger("vpinfe.httpapi.auth")

_SCOPE_ATTR = "__vpinfe_scope__"


@dataclass(frozen=True)
class Identity:
    name: str
    scopes: frozenset[str]

    def can(self, scope: str) -> bool:
        return scope in self.scopes


class LocalTrustPolicy:
    """Whoever can reach this instance may do anything.

    The current behavior, written down. A cabinet on a home network has no
    tokens and no user accounts, and inventing them here would be friction with
    nothing on the other side of it. Replacing this class is how that changes.
    """

    name = "local-trust"

    def identify(self, request: Request) -> Identity:
        return Identity(name="local", scopes=scopes.CORE)


_policy: LocalTrustPolicy = LocalTrustPolicy()


def current_policy() -> LocalTrustPolicy:
    return _policy


def set_policy(policy) -> None:
    """Swap the policy. For tests, and for whenever the deployment stops being local."""
    global _policy
    _policy = policy


class ScopeMiddleware(BaseHTTPMiddleware):
    """Stamps the caller's identity on every request into the API."""

    async def dispatch(self, request: Request, call_next):
        request.state.identity = _policy.identify(request)
        return await call_next(request)


class ForbiddenError(ApiError):
    def __init__(self, message: str = "Not permitted", *, details=None) -> None:
        super().__init__(CODE_FORBIDDEN, message, status_code=403, details=details)


def requires(scope: str):
    """Declare the scope a route needs.

    Fails closed: if the identity is missing the boundary did not run, and the answer
    is no rather than a guess.
    """
    if not scopes.is_known(scope):
        raise ValueError(f"Unknown scope: {scope}")

    async def _check(request: Request) -> None:
        identity = getattr(request.state, "identity", None)
        if identity is None:
            logger.error("No identity on %s - the scope middleware did not run",
                         request.url.path)
            raise ForbiddenError("Authorization unavailable")
        if not identity.can(scope):
            raise ForbiddenError(f"Requires {scope}")

    setattr(_check, _SCOPE_ATTR, scope)
    return Depends(_check)


def route_scope(route: APIRoute) -> str | None:
    """The scope a route declares, or None."""
    for dependency in route.dependencies:
        call = getattr(dependency, "dependency", None)
        scope = getattr(call, _SCOPE_ATTR, None)
        if scope is not None:
            return scope
    return None


def iter_api_routes(app):
    """Every route on the app, including those inside included routers.

    FastAPI does not flatten an included router into app.routes, so a plain walk
    misses everything mounted through include_router - which is nearly all of it.
    """
    def walk(routes, prefix=""):
        for route in routes:
            if isinstance(route, APIRoute):
                yield prefix + route.path, route
            elif type(route).__name__ == "_IncludedRouter":
                original = getattr(route, "original_router", None)
                context = getattr(route, "include_context", None)
                inner = getattr(context, "prefix", "") if context is not None else ""
                if original is not None:
                    yield from walk(original.routes, prefix + (inner or ""))

    yield from walk(app.routes)


def assert_every_route_declares_a_scope(app) -> None:
    """Refuse to start with an unguarded route.

    The boundary is only un-bypassable if forgetting to use it is impossible, and the
    cheapest way to make it impossible is to not start.
    """
    missing = [
        f"{','.join(sorted(route.methods))} {path}"
        for path, route in iter_api_routes(app)
        if route_scope(route) is None
    ]
    if missing:
        raise RuntimeError(
            "These API routes declare no scope: " + "; ".join(sorted(missing))
            + ". Add requires(<scope>) to each."
        )
