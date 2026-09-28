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
from common import i18n, install_identity, tokens
from common.paths import CONFIG_DIR, bundled, get_ini_config

from . import catalogs, contributions, services
from .context import ExtensionApps, ExtensionContext
from .contract import MANIFEST_NAME, Manifest, ManifestError, read_manifest
from .store import ExtensionStore, get_extension_store

logger = logging.getLogger("vpinfe.common.extensions.host")

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
SWITCHED_OFF = "extension.reason.switched_off"
# Switched on since this run started.
STARTS_AT_RESTART = "extension.reason.starts_at_restart"

_PLATFORMS = {"linux": "linux", "win32": "windows", "darwin": "macos"}
PLATFORM_NAMES = {"linux": "extension.platform.linux",
                  "windows": "extension.platform.windows",
                  "macos": "extension.platform.macos"}


def this_platform() -> str:
    return _PLATFORMS.get(sys.platform, sys.platform)


def _read(value: str | tuple[str, ...]) -> str:
    return ", ".join(i18n.t(key) for key in value) if isinstance(value, tuple) else value


@dataclass
class Record:
    """One extension, and what became of it."""

    name: str
    directory: Path
    manifest: Manifest | None = None
    # What the person set, which is not whether it is running.
    enabled: bool = True
    state: str = FAILED
    why: str = ""
    why_values: dict[str, str | tuple[str, ...]] = field(default_factory=dict)
    # (router, scope), collected at registration and mounted once by the API.
    routers: list[tuple[Any, str]] = field(default_factory=list)
    subscriptions: list[tuple[str, Any]] = field(default_factory=list)
    apps: ExtensionApps | None = None
    files: Any = None
    actions: list[dict] = field(default_factory=list)
    surfaces: dict = field(default_factory=dict)
    community: list[dict] = field(default_factory=list)
    # {base, label, cards, marker} when a player can hold an account with it.
    account: dict = field(default_factory=dict)

    @property
    def running(self) -> bool:
        return self.state == LOADED

    @property
    def reason(self) -> str:
        if not self.why:
            return ""
        return i18n.t(self.why, **{slot: _read(value)
                                   for slot, value in self.why_values.items()})

    def became(self, state: str, why: str = "", **values: str | tuple[str, ...]) -> None:
        self.state, self.why, self.why_values = state, why, values

    def said(self, literal: str, key: str, fallback: str = "") -> tuple[str, str]:
        """Words it declared: `literal` as written, else `ext.<name>.<key>` from its own
        catalog, else `fallback`. With the key they came from."""
        return i18n.literal_or(literal, f"ext.{self.name}.{key}", fallback=fallback)

    @property
    def display_name(self) -> str:
        return self.said(self.manifest.display_name if self.manifest else "", "name",
                         self.name)[0]

    @property
    def description(self) -> str:
        return self.said(self.manifest.description if self.manifest else "",
                         "description")[0]

    def lists(self) -> list[dict]:
        """Its Community lists, in the language now set."""
        return [self._list(one) for one in self.community]

    def _list(self, declared: dict) -> dict:
        under = f"community.{declared['key']}"
        return {
            **declared,
            "title": self.said(declared["title"], f"{under}.title", declared["key"])[0],
            "columns": [{**one,
                         "header": self.said(one["header"],
                                             f"{under}.column.{one['field']}.header",
                                             one["field"])[0],
                         "help": self.said(one["help"],
                                           f"{under}.column.{one['field']}.help")[0]}
                        for one in declared["columns"]],
            "views": [{**one,
                       "name": self.said(one["name"], f"{under}.view.{one['key']}.name",
                                         one["key"])[0],
                       "help": self.said(one["help"], f"{under}.view.{one['key']}.help")[0]}
                      for one in declared["views"]],
        }

    def _action(self, declared: dict) -> dict:
        key = declared["key"]
        label, label_key = self.said(declared["label"], f"action.{key}.label", key)
        return {**declared, "label": label, "label_key": label_key,
                "description": self.said(declared["description"],
                                         f"action.{key}.description")[0]}

    def account_declared(self) -> dict:
        """Its account, in the language now set. Empty when it offers none."""
        if not self.account:
            return {}
        return {**self.account,
                "label": self.said(self.account["label"], "account.label",
                                   self.display_name)[0]}

    def _surfaces(self) -> dict:
        found = dict(self.surfaces)
        for which in ("settings", "state"):
            found[f"{which}_label"] = self.said(str(found.get(f"{which}_label") or ""),
                                                f"{which}.label")[0]
        return found

    def as_dict(self) -> dict[str, Any]:
        found = self.manifest.as_dict() if self.manifest else {"name": self.name}
        return {**found, "display_name": self.display_name,
                "description": self.description, "enabled": self.enabled,
                "state": self.state, "reason": self.reason, "reason_key": self.why,
                "routes": [scope for _router, scope in self.routers],
                # Only while it is running: an action on an extension that is not
                # there would draw a button that refuses.
                "actions": ([self._action(one) for one in self.actions]
                            if self.running else []),
                "surfaces": self._surfaces() if self.running else {},
                "community": self.lists() if self.running else [],
                "account": self.account_declared() if self.running else {}}


class Registry:
    """Every extension this install has looked at."""

    def __init__(self, store: ExtensionStore | None = None) -> None:
        self._store = store or get_extension_store()
        self._records: dict[str, Record] = {}
        self._lock = threading.RLock()

    # -- reading -------------------------------------------------------------

    @property
    def store(self) -> ExtensionStore:
        """Where the extensions it loaded keep their settings and accounts."""
        return self._store

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
        record = Record(name=directory.name, directory=directory,
                        enabled=self._store.enabled(directory.name))
        try:
            record.manifest = _read_manifest(directory)
            record.name = record.manifest.name
        except ManifestError as exc:
            logger.error("Extension %s: %s", record.name,
                         i18n.t_source(exc.key, **exc.values), exc_info=exc.__cause__)
            record.became(FAILED, exc.key, **exc.values)
            return self._remember(record)
        i18n.own(f"ext.{record.name}", directory / "i18n")

        why, values = ((SWITCHED_OFF, {}) if not record.enabled
                       else _cannot_run(record.manifest))
        if why:
            record.became(OFF, why, **values)
            return self._remember(record)

        context: ExtensionContext | None = None
        try:
            module = _import(record.manifest.name, directory)
            register = getattr(module, "register", None)
            if not callable(register):
                raise TypeError("its package defines no register(ctx)")
            name = record.name
            context = ExtensionContext(
                record.manifest, self._store,
                on_failure=lambda why, **values: self.disable(name, why, **values),
                directory=directory)
            register(context)
            context.open = False
        except Exception as exc:
            logger.exception("Extension %s did not load: %r", record.name, exc)
            if context is not None:
                _withdraw(record.name, context.events.registered, context.apps)
            record.became(FAILED, "extension.reason.did_not_start")
            return self._remember(record)

        record.routers = list(context.routers)
        record.subscriptions = list(context.events.registered)
        record.apps = context.apps
        record.files = context.files
        record.actions = list(context.ui.actions)
        record.community = list(context.ui.community_lists)
        record.surfaces = {
            "settings": context.ui.settings_base,
            "settings_label": context.ui.settings_label,
            "state": context.ui.state_base,
            "state_label": context.ui.state_label,
        }
        record.account = dict(context.ui.account_offered)
        record.became(LOADED)
        logger.info("Extension %s %s loaded", record.name, record.manifest.version)
        return self._remember(record)

    # -- the switch ----------------------------------------------------------

    def switch(self, name: str, on: bool) -> Record | None:
        """Written to `extensions.json`. None when there is no such extension."""
        with self._lock:
            record = self._records.get(str(name or "").strip())
            if record is None:
                return None
            self._store.set_enabled(record.name, on)
            record.enabled = on
            logger.info("Extension %s switched %s", record.name, "on" if on else "off")
            # A refused manifest is refused at every start, whatever the switch says.
            if record.manifest is None:
                return record
            if not on:
                if not self._take_out(record.name, OFF, SWITCHED_OFF):
                    record.became(OFF, SWITCHED_OFF)
            elif record.state == OFF:
                why, values = _cannot_run(record.manifest)
                record.became(OFF, why or STARTS_AT_RESTART, **values)
            return record

    # -- the kill switch -----------------------------------------------------

    def disable(self, name: str, why: str, **values: str) -> None:
        """Stop one without stopping anything else, for `why`, a catalog key. Not written
        down: a fault that happened once must not take it away until somebody notices a
        setting they never set."""
        self._stop(name, DISABLED, why, **values)

    def refuse(self, name: str, why: str, **values: str) -> None:
        """Take one out for something only the seam it registered at could see - an
        extension that never really loaded, rather than one that broke."""
        self._stop(name, FAILED, why, **values)

    def _stop(self, name: str, state: str, why: str, **values: str) -> None:
        if self._take_out(name, state, why, **values):
            logger.error("Extension %s %s: %s", name, state,
                         i18n.t_source(why, **values))

    def _take_out(self, name: str, state: str, why: str, **values: str) -> bool:
        """Withdraw a running one and record why. False when it was not running."""
        with self._lock:
            record = self._records.get(str(name or "").strip())
            if record is None or record.state != LOADED:
                return False
            _withdraw(record.name, record.subscriptions, record.apps)
            record.subscriptions = []
            record.became(state, why, **values)
        return True

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


def _withdraw(name: str, subscriptions: list[tuple[str, Any]],
              apps: ExtensionApps | None) -> None:
    for event, handler in subscriptions:
        core_events.unsubscribe(event, handler)
    contributions.forget(name)
    catalogs.forget(name)
    tokens.forget(name)
    services.forget(name)
    if apps is not None:
        apps.withdraw()


def _cannot_run(manifest: Manifest) -> tuple[str, dict[str, str | tuple[str, ...]]]:
    """Why this device cannot run it whatever the switch says, or `""`."""
    platform = this_platform()
    if manifest.platforms and platform not in manifest.platforms:
        return "extension.reason.not_for_platform", {
            "platform": (PLATFORM_NAMES.get(platform, platform),)}
    missing = [name for name in install_identity.FEATURES
               if name in manifest.requires_features and name not in _features()]
    if missing:
        return "extension.reason.lacks_features", {
            "features": tuple(install_identity.LABELS[name] for name in missing)}
    return "", {}


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
        raise ManifestError("extension.reason.manifest_names_another", name=manifest.name)
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
