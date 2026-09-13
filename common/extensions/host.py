"""Loading extensions, and keeping a broken one from taking core with it.

Every step is contained: reading a manifest, importing the package and calling
`register(ctx)` are each somebody else's code, and the answer to any of them failing is
one extension that is not running and a line saying which and why.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common import events as core_events
from common import install_identity
from common.paths import CONFIG_DIR, bundled, get_ini_config

from . import contributions
from .context import ExtensionContext
from .contract import MANIFEST_NAME, Manifest, ManifestError, read_manifest
from .store import ExtensionStore, get_extension_store

logger = logging.getLogger("vpinfe.common.extensions")

# Where an install keeps the ones it has, and where the build keeps the ones it ships.
# Installed first: an extension somebody installed under the same name as one we ship is
# the one they meant, and shadowing it quietly the other way would be unexplainable.
INSTALLED_DIR = CONFIG_DIR / "extensions"
BUNDLED_DIR = bundled("extensions")
SEARCH_PATH = (INSTALLED_DIR, BUNDLED_DIR)

# Running.
LOADED = "loaded"
# Never got as far as running: a manifest that would not parse, a package that would not
# import, or a `register` that raised.
FAILED = "failed"
# Ran, then something it owns threw. For this run only.
DISABLED = "disabled"
# Switched off by the user, or not for this machine.
OFF = "off"

_PLATFORMS = {"linux": "linux", "win32": "windows", "darwin": "macos"}


def this_platform() -> str:
    return _PLATFORMS.get(sys.platform, sys.platform)


@dataclass
class Record:
    """One extension, and what became of it."""

    name: str
    directory: Path
    manifest: Manifest | None = None
    state: str = FAILED
    reason: str = ""
    # (router, scope), collected at registration and mounted once by the API.
    routers: list[tuple[Any, str]] = field(default_factory=list)
    subscriptions: list[tuple[str, Any]] = field(default_factory=list)
    files: Any = None
    actions: list[dict] = field(default_factory=list)
    surfaces: dict = field(default_factory=dict)

    @property
    def running(self) -> bool:
        return self.state == LOADED

    @property
    def display_name(self) -> str:
        return self.manifest.display_name if self.manifest else self.name

    def as_dict(self) -> dict[str, Any]:
        found = self.manifest.as_dict() if self.manifest else {"name": self.name}
        return {**found, "state": self.state, "reason": self.reason,
                "routes": [scope for _router, scope in self.routers],
                # Only while it is running: an action on an extension that is not
                # there would draw a button that refuses.
                "actions": list(self.actions) if self.running else [],
                "surfaces": dict(self.surfaces) if self.running else {}}


class Registry:
    """Every extension this install has looked at."""

    def __init__(self, store: ExtensionStore | None = None) -> None:
        self._store = store or get_extension_store()
        self._records: dict[str, Record] = {}
        self._lock = threading.RLock()

    # -- reading -------------------------------------------------------------

    def records(self) -> list[Record]:
        with self._lock:
            return sorted(self._records.values(), key=lambda one: one.name)

    def get(self, name: str) -> Record | None:
        with self._lock:
            return self._records.get(str(name or "").strip())

    def running(self, name: str) -> bool:
        found = self.get(name)
        return found is not None and found.running

    def granted_scopes(self) -> frozenset[str]:
        """The `ext:` scopes a caller may hold right now.

        Only from an extension that is running: disabling one takes its scopes with it,
        which is what makes the kill switch reach a route already mounted.
        """
        return frozenset(scope for record in self.records() if record.running
                         for _router, scope in record.routers)

    def read_roots(self) -> tuple[str, ...]:
        """Every folder a running extension says it works from.

        Only from one that is running: an extension that has been taken out stops
        widening what this install will read, the same way it stops holding its scopes.
        """
        return tuple(root for record in self.records() if record.running
                     for root in (record.files.roots() if record.files else ()))

    def mounted(self) -> list[tuple[Record, Any, str]]:
        """Every router that registered, whatever state its extension is in now.

        Routes are mounted once, at startup. A disabled extension keeps its paths and
        refuses on them, which is a better answer than a 404 that reads as a typo.
        """
        return [(record, router, scope) for record in self.records()
                for router, scope in record.routers]

    # -- loading -------------------------------------------------------------

    def load_from(self, root: Path | str) -> list[Record]:
        """Load every extension directly under a root."""
        return [self.load(directory) for directory in _directories(root)]

    def load_installed(self) -> list[Record]:
        """Every extension this install has, from every root it keeps them in.

        A name already loaded is not loaded again, which is what makes the search order
        the precedence: an installed copy answers, and the bundled one is left alone
        rather than replacing it halfway through a run.
        """
        found = []
        for root in SEARCH_PATH:
            for directory in _directories(root):
                if self.get(directory.name) is not None:
                    logger.info("Not loading %s from %s: already loaded",
                                directory.name, root)
                    continue
                found.append(self.load(directory))
        return found

    def load(self, directory: Path | str) -> Record:
        directory = Path(directory)
        record = Record(name=directory.name, directory=directory)
        try:
            record.manifest = _read_manifest(directory)
            record.name = record.manifest.name
        except ManifestError as exc:
            return self._remember(_failed(record, str(exc)))

        skip = self._why_not(record.manifest)
        if skip:
            record.state, record.reason = OFF, skip
            return self._remember(record)

        try:
            module = _import(record.manifest.name, directory)
            register = getattr(module, "register", None)
            if not callable(register):
                raise TypeError("its package defines no register(ctx)")
            context = ExtensionContext(
                record.manifest, self._store,
                on_failure=lambda why, name=record.name: self.disable(name, why))
            register(context)
            context.open = False
        except Exception as exc:
            logger.exception("Extension %s did not load", record.name)
            return self._remember(_failed(record, _said(exc)))

        record.routers = list(context.routers)
        record.subscriptions = list(context.events.registered)
        record.files = context.files
        record.actions = list(context.ui.actions)
        record.surfaces = {
            "settings": context.ui.settings_base,
            "settings_label": context.ui.settings_label,
            "state": context.ui.state_base,
            "state_label": context.ui.state_label,
        }
        record.state, record.reason = LOADED, ""
        logger.info("Extension %s %s loaded", record.name, record.manifest.version)
        return self._remember(record)

    def _why_not(self, manifest: Manifest) -> str:
        if not self._store.enabled(manifest.name):
            return "Switched off"
        if manifest.platforms and this_platform() not in manifest.platforms:
            return f"Not for {this_platform()}"
        missing = sorted(set(manifest.requires_features) - set(_features()))
        if missing:
            return f"This install does not do {', '.join(missing)}"
        return ""

    # -- the kill switch -----------------------------------------------------

    def disable(self, name: str, reason: str) -> None:
        """Stop an extension without stopping anything else.

        Its subscriptions go, so it is told nothing more; its scopes go with its state,
        so its routes refuse. Not written down: a fault that happened once must not take
        the extension away until somebody notices a setting they never set.
        """
        self._stop(name, DISABLED, reason)

    def refuse(self, name: str, reason: str) -> None:
        """Take one out for something only the seam it registered at could see - an
        extension that never really loaded, rather than one that broke."""
        self._stop(name, FAILED, reason)

    def _stop(self, name: str, state: str, reason: str) -> None:
        with self._lock:
            record = self._records.get(str(name or "").strip())
            if record is None or record.state != LOADED:
                return
            for event, handler in record.subscriptions:
                core_events.unsubscribe(event, handler)
            record.subscriptions = []
            contributions.forget(record.name)
            record.state, record.reason = state, reason
        logger.error("Extension %s %s: %s", name, state, reason)

    def clear(self) -> None:
        """Forget everything loaded, unsubscribing as it goes. For tests."""
        with self._lock:
            for record in self._records.values():
                for event, handler in record.subscriptions:
                    core_events.unsubscribe(event, handler)
            self._records.clear()

    def _remember(self, record: Record) -> Record:
        with self._lock:
            self._records[record.name] = record
        return record


def _said(exc: Exception) -> str:
    """What to put in front of whoever installed this, which is not a traceback.

    The type and the stack are in the log, under the extension's own namespace. On screen
    the useful half is the sentence - and the type only when there is no sentence.
    """
    return str(exc).strip() or type(exc).__name__


def _failed(record: Record, reason: str) -> Record:
    record.state, record.reason = FAILED, reason
    logger.error("Extension %s: %s", record.name, reason)
    return record


def _features() -> tuple[str, ...]:
    try:
        return tuple(install_identity.features(get_ini_config()))
    except Exception:
        # An install whose config cannot be read is not one to start refusing
        # extensions at: the honest fallback is what every install does.
        return tuple(install_identity.DEFAULT_FEATURES)


def _directories(root: Path | str) -> Iterator[Path]:
    root = Path(root)
    if not root.is_dir():
        return
    for found in sorted(root.iterdir()):
        if found.is_dir() and (found / MANIFEST_NAME).is_file():
            yield found


def _read_manifest(directory: Path) -> Manifest:
    manifest = read_manifest(directory)
    if manifest.name != directory.name:
        raise ManifestError(f"{directory.name} holds a manifest calling itself "
                            f"{manifest.name}; the folder is the name")
    return manifest


def _import(name: str, directory: Path) -> Any:
    """Import the extension's package from its own directory.

    Loaded by path under a reserved module name rather than by putting the directory on
    `sys.path`, so an extension cannot shadow one of ours by naming a file after it.
    """
    module_name = f"vpinfe_ext_{name}"
    init = directory / "__init__.py"
    if not init.is_file():
        raise ModuleNotFoundError(f"no __init__.py in {directory.name}")
    spec = importlib.util.spec_from_file_location(
        module_name, init, submodule_search_locations=[str(directory)])
    if spec is None or spec.loader is None:
        raise ImportError(f"{directory.name} could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module
