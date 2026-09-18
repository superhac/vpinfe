"""Frontend themes: what is available, what is installed, and which one plays.

"Theme" unqualified means the frontend's, which is a decision the tree already made - a
game's `themes` are what a machine is about.

Reading the registry reaches the network, so it is held per process and refreshed only
when a caller asks. Re-reading it on every draw would spend a round trip per render on a
list that changes when somebody publishes a release.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from common import service_errors
from common.i18n import t
from common.online import theme_service
from common.online.themes import ThemeRegistry

logger = logging.getLogger("vpinfe.common.online.theme_ops")


class SourceUnavailableError(service_errors.ServiceError):
    """A theme source that will not load. Nothing about this install is wrong."""


class InstallFailedError(service_errors.ServiceError):
    """The registry was read and the install did not finish."""


class RemoveFailedError(service_errors.ServiceError):
    """The theme is installed and could not be taken away."""


_lock = threading.RLock()
_registry: Any = None


def _loaded(refresh: bool = False) -> ThemeRegistry:
    """The registry, read once and kept. Network work, so not per request."""
    global _registry
    with _lock:
        if _registry is None or refresh:
                    _registry = theme_service.load_registry()
        return _registry


def _described(registry: ThemeRegistry, active: str) -> list[dict[str, Any]]:
    found = registry.get_themes()
    try:
        updates = registry.check_for_updates(list(found))
    except Exception:  # noqa: BLE001 - an update check that fails is not a broken list
        logger.warning("Could not check themes for updates", exc_info=True)
        updates = {}

    out: list[dict[str, Any]] = []
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


def listing(refresh: bool = False) -> dict[str, Any]:
    """Active first, then installed, then the rest.

    `refresh` re-reads the sources. Without it the answer is whatever was read when this
    process first asked, which is right for a page that draws several times a minute.
    """
    try:
        registry = _loaded(refresh)
    except Exception as exc:  # noqa: BLE001 - a source that will not load is news
        raise SourceUnavailableError(
            t("error.themes.could_not_read_theme", exc=(exc))) from exc
    active = theme_service.get_active_theme()
    return {"active": active, "themes": _described(registry, active)}


def install(key: str) -> dict[str, Any]:
    """One call for both. Installing over an existing copy is what an update is, and two
    endpoints doing it would be two names for one act."""
    registry = _loaded()
    try:
        theme_service.install_theme(registry, key)
    except Exception as exc:  # noqa: BLE001
        raise InstallFailedError(
            t("error.themes.could_not_install", key=(key), exc=(exc))) from exc
    return {"key": key, "installed": registry.is_installed(key)}


def remove(key: str) -> dict[str, Any]:
    registry = _loaded()
    if not registry.is_installed(key):
        raise service_errors.NotFoundError(t("error.themes.not_installed", key=(key)))
    if key == theme_service.get_active_theme():
        # Refused rather than allowed with a warning: the frontend would come up with
        # no theme at all, and the way out of that is a config file.
        raise service_errors.RefusedError(
            t("error.themes.active_theme_make_another", key=(key)))
    try:
        theme_service.delete_theme(registry, key)
    except Exception as exc:  # noqa: BLE001
        raise RemoveFailedError(
            t("error.themes.could_not_remove", key=(key), exc=(exc))) from exc
    return {"key": key, "installed": False}


def activate(key: str) -> dict[str, Any]:
    """Written to the config. It takes effect when the frontend next starts, which the
    caller is expected to say - this endpoint changes a setting rather than restarting
    anything."""
    key = str(key or "").strip()
    registry = _loaded()
    if not key or not registry.is_installed(key):
        raise service_errors.RefusedError(
            t("error.themes.not_installed_2", value=(key or 'That theme')))
    theme_service.set_active_theme(key)
    return {"active": theme_service.get_active_theme()}


def options(key: str) -> dict[str, Any]:
    """The schema a theme declares, and what it is currently set to.

    Its own shape rather than the install's config schema: these belong to the theme,
    live in its `theme.json`, and a theme can declare a control this install has never
    heard of.
    """
    registry = _loaded()
    if not registry.is_installed(key):
        raise service_errors.NotFoundError(t("error.themes.not_installed", key=(key)))
    schema = theme_service.load_theme_option_schema(key, registry)
    if not schema:
        return {"key": key, "title": "", "description": "", "options": [], "values": {}}
    return {"key": key, "title": schema.get("title", ""),
            "description": schema.get("description", ""),
            "options": schema.get("options") or [],
            "values": theme_service.get_theme_option_values(key, registry)}


def save_options(key: str, values: dict[str, Any]) -> dict[str, Any]:
    """Kept beside the config rather than inside the theme.

    The package is deleted by an update, so values written into it were reset by the
    next one - every time, with no warning. The theme still declares what its options
    *are*; this is only what somebody chose.
    """
    registry = _loaded()
    if not registry.is_installed(key):
        raise service_errors.NotFoundError(t("error.themes.not_installed", key=(key)))
    try:
        theme_service.save_theme_option_values(key, dict(values or {}), registry)
    except Exception as exc:  # noqa: BLE001
        raise service_errors.RefusedError(
            t("error.themes.could_not_save_settings", exc=(exc))) from exc
    return {"key": key, "values": theme_service.get_theme_option_values(key, registry)}
