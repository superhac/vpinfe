"""Frontend themes: what is available, what is installed, and which one plays.

"Theme" unqualified means the frontend's, which is a decision the tree already made -
a game's `themes` are what a machine is about and the grid heads that column *Game
Themes* for exactly this reason.

Reading the registry reaches the network, so it is cached per process and refreshed only
when a caller asks. A page that re-read it on every draw would spend a round trip per
render on a list that changes when somebody publishes a release.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import APIRouter, Body

from . import scopes
from .auth import requires
from .errors import ApiError, InvalidRequestError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.themes")

router = APIRouter(prefix="/themes", tags=["themes"])

_lock = threading.RLock()
_registry: Any = None


def _loaded(refresh: bool = False):
    """The registry, read once and kept. Network work, so not per request."""
    global _registry
    with _lock:
        if _registry is None or refresh:
            from common.online import theme_service

            _registry = theme_service.load_registry()
        return _registry


def _described(registry, active: str) -> list[dict[str, Any]]:
    from common.online import theme_service

    found = registry.get_themes()
    try:
        updates = registry.check_for_updates(list(found))
    except Exception:  # noqa: BLE001 - an update check that fails is not a broken list
        logger.warning("Could not check themes for updates", exc_info=True)
        updates = {}

    out = []
    for key, entry in found.items():
        manifest = dict(entry.get("manifest") or {})
        info = dict(entry.get("registry_info") or {})
        installed = registry.is_installed(key)
        update = updates.get(key) or {}
        schema = (theme_service.load_theme_option_schema(key, registry)
                  if installed else None)
        out.append({
            "key": key,
            "name": str(manifest.get("name") or key),
            "author": str(manifest.get("author") or ""),
            "description": str(manifest.get("description") or ""),
            "version": str(update.get("remote_version")
                           or manifest.get("version") or ""),
            "installed_version": str(update.get("installed_version") or ""),
            # What it needs to show itself: 1 is a desktop, 3 is a cabinet.
            "screens": manifest.get("supported_screens"),
            "type": str(manifest.get("type") or ""),
            "url": str(info.get("theme_base_url") or info.get("url") or ""),
            # Where the picture is, resolved here rather than by each client: an
            # installed theme serves its own from /themes/, and one that is not has to
            # be fetched from where its manifest lives.
            "preview": _preview(key, manifest, info, installed),
            "change_log": str(manifest.get("change_log") or ""),
            "installed": installed,
            "active": key == active,
            "default_install": bool(info.get("default_install")),
            "update_available": bool(update.get("update_available")) and installed,
            "configurable": bool(schema and schema.get("options")),
        })
    # Active first, then installed, then the rest - the order somebody scans in.
    out.sort(key=lambda one: (not one["active"], not one["installed"],
                              one["name"].lower()))
    return out


def _preview(key: str, manifest: dict, info: dict, installed: bool) -> str:
    name = str(manifest.get("preview_image") or "").strip()
    if not name:
        return ""
    if name.startswith("http"):
        return name
    if installed:
        return f"/themes/{key}/{name}"
    where = str(info.get("theme_manifest_url") or "")
    return f"{where.rsplit('/', 1)[0]}/{name}" if where else ""


@router.get("", summary="Every theme this install knows",
            dependencies=[requires(scopes.CONFIG_READ)])
def list_themes(refresh: bool = False) -> dict[str, Any]:
    """Active first, then installed, then the rest.

    `refresh` re-reads the sources. Without it the answer is whatever was read when this
    process first asked, which is right for a page that draws several times a minute.
    """
    from common.online import theme_service

    try:
        registry = _loaded(refresh)
    except Exception as exc:  # noqa: BLE001 - a source that will not load is news
        raise ApiError("theme_source_unavailable",
                       f"Could not read the theme sources: {exc}",
                       status_code=503) from exc
    active = theme_service.get_active_theme()
    return {"active": active, "themes": _described(registry, active)}


@router.post("/{key}/install", summary="Install or update a theme",
             dependencies=[requires(scopes.CONFIG_WRITE)])
def install(key: str) -> dict[str, Any]:
    """One call for both. Installing over an existing copy is what an update is, and two
    endpoints doing it would be two names for one act."""
    from common.online import theme_service

    registry = _loaded()
    try:
        theme_service.install_theme(registry, key)
    except Exception as exc:  # noqa: BLE001
        raise ApiError("theme_install_failed", f"Could not install {key}: {exc}",
                       status_code=502) from exc
    return {"key": key, "installed": registry.is_installed(key)}


@router.delete("/{key}", summary="Remove an installed theme",
               dependencies=[requires(scopes.CONFIG_WRITE)])
def remove(key: str) -> dict[str, Any]:
    from common.online import theme_service

    registry = _loaded()
    if not registry.is_installed(key):
        raise NotFoundError(f"{key} is not installed")
    if key == theme_service.get_active_theme():
        # Refused rather than allowed with a warning: the frontend would come up with
        # no theme at all, and the way out of that is a config file.
        raise InvalidRequestError(
            f"{key} is the active theme. Make another one active first.")
    try:
        theme_service.delete_theme(registry, key)
    except Exception as exc:  # noqa: BLE001
        raise ApiError("theme_remove_failed", f"Could not remove {key}: {exc}",
                       status_code=502) from exc
    return {"key": key, "installed": False}


@router.put("/active", summary="Choose which theme the frontend plays",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def activate(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Written to the config. It takes effect when the frontend next starts, which the
    caller is expected to say - this endpoint changes a setting rather than restarting
    anything."""
    from common.online import theme_service

    key = str(body.get("key") or "").strip()
    registry = _loaded()
    if not key or not registry.is_installed(key):
        raise InvalidRequestError(f"{key or 'That theme'} is not installed.")
    theme_service.set_active_theme(key)
    return {"active": theme_service.get_active_theme()}


@router.get("/{key}/options", summary="A theme's own settings",
            dependencies=[requires(scopes.CONFIG_READ)])
def options(key: str) -> dict[str, Any]:
    """The schema a theme declares, and what it is currently set to.

    Its own shape rather than the install's config schema: these belong to the theme,
    live in its `theme.json`, and a theme can declare a control this install has never
    heard of.
    """
    from common.online import theme_service

    registry = _loaded()
    if not registry.is_installed(key):
        raise NotFoundError(f"{key} is not installed")
    schema = theme_service.load_theme_option_schema(key, registry)
    if not schema:
        return {"key": key, "title": "", "description": "", "options": [], "values": {}}
    return {"key": key, "title": schema.get("title", ""),
            "description": schema.get("description", ""),
            "options": schema.get("options") or [],
            "values": theme_service.get_theme_option_values(key, registry)}


@router.put("/{key}/options", summary="Change a theme's own settings",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def save_options(key: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Kept beside the config rather than inside the theme.

    The package is deleted by an update, so values written into it were reset by the
    next one - every time, with no warning. The theme still declares what its options
    *are*; this is only what somebody chose.
    """
    from common.online import theme_service

    registry = _loaded()
    if not registry.is_installed(key):
        raise NotFoundError(f"{key} is not installed")
    try:
        theme_service.save_theme_option_values(key, dict(body.get("values") or {}),
                                               registry)
    except Exception as exc:  # noqa: BLE001
        raise InvalidRequestError(f"Could not save those settings: {exc}") from exc
    return {"key": key, "values": theme_service.get_theme_option_values(key, registry)}
