"""The curated facade an extension is handed, and nothing else.

`register(ctx)` never receives the application. Everything below is a narrow view over
one core facility, named for the extension that holds it, so that "which extension did
this?" is answerable from a log line, a config file or a scope.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from common import events as core_events

from .contract import ContractError, Manifest
from .games import ExtensionGames
from .store import ExtensionStore

LOG_ROOT = "vpinfe.ext"


def logger_for(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOG_ROOT}.{name}")


class ExtensionConfig:
    """An extension's settings, under its own name."""

    def __init__(self, name: str, store: ExtensionStore) -> None:
        self._name = name
        self._store = store

    def get(self, key: str, default: str = "") -> str:
        return self.all().get(str(key or "").strip(), default)

    def all(self) -> dict[str, str]:
        return self._store.settings(self._name)

    def set(self, key: str, value: str) -> None:
        self._store.set_setting(self._name, key, value)


class ExtensionEvents:
    """The bus, seen from one extension: it is told what core did, and publishes under
    its own namespace so nothing it emits can be mistaken for a core event."""

    def __init__(self, name: str, declared: tuple[str, ...],
                 on_failure: Callable[[str], None]) -> None:
        self._name = name
        self._declared = frozenset(declared)
        self._on_failure = on_failure
        self._logger = logger_for(name)
        self.registered: list[tuple[str, Callable]] = []

    def subscribe(self, event: str, handler: Callable) -> None:
        def contained(**payload) -> None:
            try:
                handler(**payload)
            except Exception:
                self._logger.exception("Handling %s failed", event)
                self._on_failure(f"Failed while handling {event}")

        core_events.subscribe(event, contained)
        self.registered.append((event, contained))

    def publish(self, event: str, **payload) -> None:
        wanted = str(event or "").strip()
        if wanted not in self._declared:
            raise ContractError(f"{self._name} publishes {wanted!r}, which its manifest "
                                "does not declare")
        core_events.emit(f"{self._name}.{wanted}", **payload)


class ExtensionFiles:
    """The folders an extension works from, so core will accept a path inside one.

    Nothing here stops an extension reading a file - in-process Python cannot be
    prevented from opening one, and pretending otherwise would be theater. What it does
    is let core's own routes take a path the extension is working with: an importer
    converting somebody's old library has to hand core files that are nowhere near ours,
    and without this every one of them is refused.

    Declared rather than assumed, and only by an extension whose manifest asks for it, so
    what an install will read is something a person agreed to and can be shown.
    """

    def __init__(self, name: str, allowed: bool) -> None:
        self._name = name
        self._allowed = allowed
        self._roots: tuple[str, ...] = ()

    def roots(self) -> tuple[str, ...]:
        return self._roots

    def set_roots(self, paths) -> None:
        """Replace the set. The user moves a share or points somewhere else, and what
        core will accept has to follow rather than accumulate."""
        if not self._allowed:
            raise ContractError(f"{self._name} sets folders to read from, which needs "
                                "the fs:read capability its manifest does not declare")
        wanted = [str(one or "").strip() for one in paths]
        self._roots = tuple(str(Path(one).expanduser().resolve())
                            for one in wanted if one)


class ExtensionServices:
    """Things this extension answers for core, that are not about one game.

    A theme has been able to ask who is playing since before extensions existed, and
    published themes still call those methods - so the method stays in core and the
    answer moves here. Core asks by name and copes with nothing answering, which is what
    an extension being disabled has to look like.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def answer(self, service: str, run) -> None:
        """Answer this from now on. One extension per name."""
        from . import services

        services.provide(self._name, service, run)

    def answers(self) -> tuple[str, ...]:
        from . import services

        return tuple(name for name in services.provided()
                     if services.answered_by(name) == self._name)

    def withdraw(self) -> None:
        from . import services

        services.forget(self._name)


class ExtensionApps:
    """The programs this install can play a table with, as an extension may add to them.

    VPinFE plays Visual Pinball and, through the generic app, anything a person can point
    at a binary. An extension is how a format becomes first-class instead: something that
    claims its own suffixes, so a library of them can be imported and offered rather than
    read and dropped.
    """

    def __init__(self, name: str, scopes) -> None:
        self._name = name
        self._scopes = frozenset(scopes)
        self._mine: list[str] = []

    def provide(self, **described) -> str:
        """Add an app, described in plain data. Answers with the id it took.

        `id`, `name`, `suffixes`, and optionally `accepts_keys`, `companions`,
        `fields`, `kinds` and `command`. `command(entry, settings)` answers with a list
        of arguments, or with nothing to run the launcher's binary and arguments the way
        the generic app does.
        """
        from . import provided_apps

        if provided_apps.APPS_PROVIDE not in self._scopes:
            raise ContractError(
                f"{self._name} provides an app, which needs "
                f"{provided_apps.APPS_PROVIDE}, and its manifest does not declare it")
        from common import apps

        built = provided_apps.build(self._name, described)
        apps.contribute(built)
        self._mine.append(built.id)
        logger_for(self._name).info(
            "provides the %s app for %s", built.id,
            ", ".join(built.claim.suffixes) or "keyed entries")
        return built.id

    def suffixes(self) -> tuple[str, ...]:
        """Every file extension this install can play, its own and any provided.

        Ungated, unlike the library: this says what the build can do, not what the user
        has. An extension deciding whether a foreign library is worth importing needs it
        before it has been granted anything.
        """
        from common import apps

        found: list[str] = []
        for app in apps.all_apps():
            found.extend(app.claim.suffixes)
        return tuple(dict.fromkeys(found))

    def names(self) -> tuple[str, ...]:
        """What the apps here are called. For a source that says which program a system
        used but not which files it holds - a database found in a folder named after the
        program is often all there is."""
        from common import apps

        return tuple(one.name for one in apps.all_apps())

    def plays(self, name: str) -> bool:
        """Whether anything here plays a file of this name, or this bare suffix."""
        wanted = str(name or "").strip().lower()
        if not wanted:
            return False
        return any(wanted == one or wanted.endswith(one) for one in self.suffixes())

    def provided(self) -> tuple[str, ...]:
        """What this extension has added, which is what gets taken back with it."""
        return tuple(self._mine)

    def withdraw(self) -> None:
        """Take them all back. Called when the extension is unloaded, so a disabled
        extension does not leave a suffix claimed by something that is no longer here."""
        from common import apps

        for app_id in self._mine:
            apps.withdraw(app_id)
        self._mine.clear()


class ExtensionUI:
    """What an extension offers a person: its actions, and the page they sit on.

    Declared rather than drawn. An extension that painted its own page would tie the
    Console's look to whoever wrote it, and would stop working the moment that extension
    moved out of this process - where a task described as data still does. Core owns the
    treatment; the extension owns what is asked and what happens.

    An action is one call on the extension's own router. What varies is whether it takes
    input, whether it warrants confirming, and whether it finishes now or hands back a
    job - and core reads each of those off what the extension answers rather than from a
    mode it declares, because a declared mode is a second statement of the same thing and
    the two drift.

    A form with no fields is pressed and happens. A form with fields is filled in first.
    A form naming a confirm gets a step showing what would happen before it runs. The
    run answers with a job where it is slow and with the outcome where it is not.
    """

    def __init__(self, name: str, allowed: bool) -> None:
        self._name = name
        self._allowed = allowed
        self.actions: list[dict] = []
        self.settings_label = "Settings"
        self.state_label = ""
        self.settings_base = ""
        self.state_base = ""

    def action(self, key: str, label: str, base: str, description: str = "") -> None:
        """A verb somebody can press, in the vocabulary the rest of the app uses."""
        if not self._allowed:
            raise ContractError(f"{self._name} offers an action, which needs the "
                                "ui:mount capability its manifest does not declare")
        wanted = str(key or "").strip()
        if not wanted:
            raise ContractError(f"{self._name} offers an action with no key")
        self.actions.append({
            "key": wanted,
            "label": str(label or "").strip() or wanted,
            "description": str(description or "").strip(),
            "base": str(base or "").strip(),
        })


class ExtensionEntries:
    """What this extension adds to every entry a theme is handed.

    One key, filled in by core when the player moves to a game. A theme reads
    `entry.ext.<key>` and never learns which extension answered - which is the point: the
    surface a theme sees does not grow a method per connector.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def contribute(self, key: str, fetch) -> None:
        """Answer about one game at a time.

        `fetch` is given a plain description of the game - its ids and what is known
        about the machine - and returns whatever a theme should read, or None where there
        is nothing to say. It is called on core's thread when the wheel stops, so it may
        block; it must not raise for a game it simply has no answer about.
        """
        from . import contributions

        wanted = str(key or "").strip()
        if not wanted:
            raise ContractError(f"{self._name} contributes under no key")
        contributions.register(self._name, wanted, fetch)


    def settings(self, base: str, label: str = "Settings") -> None:
        """Say that this extension has settings, and where core may read and write them.

        Declared rather than drawn, like everything else here: the fields come back from
        that call and core renders them in the one grammar the rest of the application
        uses, so an extension's settings look like settings.
        """
        self._needs_ui("settings")
        self.settings_base = str(base or "").strip()
        self.settings_label = str(label or "").strip() or "Settings"

    def state(self, base: str, label: str) -> None:
        """Say that this extension holds something worth showing, and where to read it.

        A list of rows, each a label, a line under it, and at most two things you can do
        to it. Deliberately poor: it is enough for the accounts a connector is holding
        and not enough to become a page somebody draws, and the day a third extension
        needs more than this is the day to look again rather than to widen it now.
        """
        self._needs_ui("state")
        self.state_base = str(base or "").strip()
        self.state_label = str(label or "").strip()

    def _needs_ui(self, what: str) -> None:
        if not self._allowed:
            raise ContractError(f"{self._name} offers {what}, which needs the ui:mount "
                                "capability its manifest does not declare")


class ExtensionJobs:
    """Slow work, run the way core runs it.

    The kind carries the extension's name, so a job somebody is watching says which
    extension is doing it - the same reason the log namespace does. One at a time per
    kind, which is core's rule and is right here too: two imports of one library at once
    would race each other into the same folders.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def submit(self, kind: str, work):
        from common import jobs

        return jobs.submit(f"{self._name}.{str(kind or '').strip()}", work)

    def active(self) -> tuple[str, ...]:
        from common import jobs

        return tuple(job.id for job in jobs.active()
                     if job.kind.startswith(f"{self._name}."))


class ExtensionContext:
    """What `register(ctx)` is given."""

    def __init__(self, manifest: Manifest, store: ExtensionStore,
                 on_failure: Callable[[str], None]) -> None:
        self.name = manifest.name
        self.manifest = manifest
        self.logger = logger_for(manifest.name)
        self.config = ExtensionConfig(manifest.name, store)
        self.events = ExtensionEvents(manifest.name, manifest.events, on_failure)
        self.files = ExtensionFiles(manifest.name, "fs:read" in manifest.capabilities)
        self.jobs = ExtensionJobs(manifest.name)
        self.ui = ExtensionUI(manifest.name, "ui:mount" in manifest.capabilities)
        self.entries = ExtensionEntries(manifest.name)
        self.games = ExtensionGames(manifest.name, manifest.scopes, self.files)
        self.apps = ExtensionApps(manifest.name, manifest.scopes)
        self.serves = ExtensionServices(manifest.name)
        # Which program this is, for an extension that has to say so to somebody else.
        # Through the context rather than an import: the one module an extension may
        # import is the contract, and that is what makes the boundary checkable.
        from common.vpinfe_version import get_version

        self.host_version = get_version()
        self.routers: list[tuple[Any, str]] = []
        # Registration is a moment, not a phase: routers are mounted once, so one added
        # after `register` returned would never be reachable and silently answer nothing.
        self.open = True

    def scope(self, action: str) -> str:
        """The scope for one of this extension's own actions."""
        return f"ext:{self.name}:{str(action or '').strip()}"

    def add_router(self, router: Any, *, scope: str) -> None:
        """Offer routes under `/api/v1/ext/<name>/`, gated on a scope this extension
        declared. Core attaches the gate; the extension cannot choose to have none."""
        if not self.open:
            raise ContractError(f"{self.name} added a router after registering")
        allowed = {self.scope(action) for action in self.manifest.provides}
        if scope not in allowed:
            raise ContractError(
                f"{self.name} gates a router on {scope!r}, which its manifest does not "
                f"provide. Declared: {', '.join(sorted(allowed)) or 'none'}")
        self.routers.append((router, scope))
