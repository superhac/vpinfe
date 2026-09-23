"""Frontend themes: what is available, what is installed, and which one plays, over the
wire.

`common/online/theme_ops.py` holds the registry and does the work. What is here is the
wire, and the two statuses only this layer can give: a source that will not load is 503
because nothing about this install is wrong, and an install or removal that failed
upstream is 502.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from common.online import theme_ops

from . import scopes
from .auth import requires
from .errors import ApiError

router = APIRouter(prefix="/themes", tags=["themes"])


@router.get("", summary="Every theme this install knows",
            dependencies=[requires(scopes.CONFIG_READ)])
def list_themes(refresh: bool = False) -> dict[str, Any]:
    """Active first, then installed, then the rest.

    `refresh` re-reads the sources now. Without it the answer is the last read, which is
    kept between restarts and repeated on the schedule set in `themes.refresh`.
    """
    try:
        return theme_ops.listing(refresh)
    except theme_ops.SourceUnavailableError as exc:
        raise ApiError("theme_source_unavailable", str(exc), status_code=503) from exc


@router.post("/{key}/install", summary="Install or update a theme",
             dependencies=[requires(scopes.CONFIG_WRITE)])
def install(key: str) -> dict[str, Any]:
    """One call for both. Installing over an existing copy is what an update is, and two
    endpoints doing it would be two names for one act."""
    try:
        return theme_ops.install(key)
    except theme_ops.InstallFailedError as exc:
        raise ApiError("theme_install_failed", str(exc), status_code=502) from exc


@router.delete("/{key}", summary="Remove an installed theme",
               dependencies=[requires(scopes.CONFIG_WRITE)])
def remove(key: str) -> dict[str, Any]:
    try:
        return theme_ops.remove(key)
    except theme_ops.RemoveFailedError as exc:
        raise ApiError("theme_remove_failed", str(exc), status_code=502) from exc


@router.put("/active", summary="Choose which theme the frontend plays",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def activate(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Written to the config. It takes effect when the frontend next starts, which the
    caller is expected to say - this endpoint changes a setting rather than restarting
    anything."""
    return theme_ops.activate(str(body.get("key") or ""))


@router.get("/{key}/options", summary="A theme's own settings",
            dependencies=[requires(scopes.CONFIG_READ)])
def options(key: str) -> dict[str, Any]:
    """The schema a theme declares, and what it is currently set to. Its own shape rather
    than the install's config schema: a theme can declare a control this install has
    never heard of."""
    return theme_ops.options(key)


@router.put("/{key}/options", summary="Change a theme's own settings",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def save_options(key: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Kept beside the config rather than inside the theme, because the package is
    deleted by an update and values written into it were reset by the next one."""
    return theme_ops.save_options(key, dict(body.get("values") or {}))
