"""The extension host: what an install has loaded, and what each one may reach.

An extension is a directory holding `extension.json` beside a Python package whose
`register(ctx)` core calls once at startup. `common/extensions/contract.py` is the whole
of what an implementation imports; the context it is handed is the whole of its reach.

Two `extensions` names, the way the apps do it: this one is core's host, and the
extensions themselves live in their own directories under the config dir.

Loading is explicit and happens once, before the API is built - the API mounts what the
registry already holds, so a test drives a fixture root instead of whatever the machine
running it happens to have installed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .context import LOG_ROOT, ExtensionContext, logger_for
from .contract import (
    PLATFORM_ABI,
    ContractError,
    Manifest,
    ManifestError,
    parse,
    read_manifest,
)
from .host import (
    BUNDLED_DIR,
    DISABLED,
    FAILED,
    INSTALLED_DIR,
    LOADED,
    OFF,
    Record,
    Registry,
)
from .store import ExtensionStore, get_extension_store

__all__ = [
    "BUNDLED_DIR", "DISABLED", "FAILED", "INSTALLED_DIR", "LOADED", "LOG_ROOT", "OFF",
    "PLATFORM_ABI",
    "ContractError", "ExtensionContext", "ExtensionStore", "Manifest", "ManifestError",
    "Record", "Registry", "clear", "disable", "get_extension_store", "granted_scopes",
    "load_from", "load_installed", "logger_for", "mounted", "parse", "read_manifest",
    "read_roots", "hand_over", "records", "refuse", "registry", "running", "set_registry",
]

logger = logging.getLogger("vpinfe.common.extensions")

_registry: Registry | None = None


def registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry


def set_registry(replacement: Registry) -> None:
    """Swap the registry. For tests, and for whenever an install loads from elsewhere."""
    global _registry
    _registry = replacement


def hand_over(config) -> int:
    """Give each extension the settings core used to hold for it. Once, before loading."""
    from . import handover

    try:
        return handover.seed(get_extension_store(), config)
    except Exception:
        logger.exception("Could not hand settings to the extensions that own them")
        return 0


def load_installed() -> list[Record]:
    return registry().load_installed()


def load_from(root: Path | str) -> list[Record]:
    return registry().load_from(root)


def records() -> list[Record]:
    return registry().records()


def running(name: str) -> bool:
    return registry().running(name)


def granted_scopes() -> frozenset[str]:
    return registry().granted_scopes()


def mounted() -> list[tuple[Record, object, str]]:
    return registry().mounted()


def read_roots() -> tuple[str, ...]:
    return registry().read_roots()


def disable(name: str, reason: str) -> None:
    registry().disable(name, reason)


def refuse(name: str, reason: str) -> None:
    registry().refuse(name, reason)


def clear() -> None:
    registry().clear()
