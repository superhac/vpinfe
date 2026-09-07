"""The configured ways this install runs an app, and which table uses which.

A launcher is user data: a name, the app it wraps, whether it is enabled, and a value
for each field that app declares. An install ships one, seeded from the configuration it
already had. Duplicating it and pointing the copy at another ini is the case this exists
for.

Follows `common/device_registry.py` and `common/games/collection_store.py` - a small JSON
file, written whole and atomically, carrying its own schema version. Not config sections:
a launcher is an object somebody creates, removes and duplicates, and the config file is
for what an install is set to. Every other collection of user objects here is a file of
its own, and `config_schema` has no dynamically named section for one to live in.

**Per install.** A binary path is a fact about one machine, so a launcher belongs to the
machine that runs it. Sharing across cabinets is a copy that keeps the id, not shared
storage - the same launcher then exists on every machine under one name, and a mapping
means the same thing everywhere.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from common import apps
from common.atomic_write import write_atomic
from common.install_identity import mint_id
from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.common.games.launchers")

LAUNCHERS_PATH = CONFIG_DIR / "launchers.json"
SCHEMA = 1
SCHEMA_KEY = "schema"
LAUNCHERS_KEY = "launchers"
MAPPINGS_KEY = "mappings"
MIGRATIONS_KEY = "migrations"


# What every launcher has, whatever app it wraps. Commands to run around a table are
# not an app's business - Visual Pinball has no opinion about mounting a share - but they
# are this launcher's, because they run only when this launcher is what plays the table.
# The install-wide pair is in Settings, and runs outside these.
OWN_FIELDS: tuple[apps.Field, ...] = (
    apps.Field("on_table_start", "When This Launcher Starts a Table", type="text",
               lines=3,
               description="One command per line, run after the install-wide ones and "
                           "before the program. For something only this way of playing "
                           "needs."),
    apps.Field("on_table_exit", "When This Launcher's Table Exits", type="text",
               lines=3,
               description="Run whenever the ones above ran, even if the program never "
                           "started."),
    apps.Field("on_start_required", "A Failure Stops the Launch", type="bool",
               default="false",
               description="On, a command that fails before the table starts stops it "
                           "launching. Off, the failure is noted and it starts anyway."),
)


def mint_launcher_id() -> str:
    """An id for a new launcher. The generator every id in this project uses, so an id
    minted here and one that arrives from another machine are indistinguishable - which
    is what lets a launcher be copied to a cabinet without being renumbered."""
    return mint_id()


@dataclass(frozen=True)
class Launcher:
    """One configured way of running an app.

    `settings` is keyed by the field names its app declares, so two launchers of the same
    app hold the same names and an editor can be generated rather than written.

    `owns_ini` says whether VPinFE created the file `ini_path` names. It is a field rather
    than something inferred from the path because removing a launcher offers to delete
    that file, and the shipped launcher points at Visual Pinball's own `VPinballX.ini` -
    guessing wrong there deletes a person's real configuration.
    """

    launcher_id: str
    app: str = ""
    display_name: str = ""
    enabled: bool = True
    owns_ini: bool = False
    settings: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def value(self, key: str) -> Any:
        """One setting, falling back to what its app declares. A launcher that does not
        carry a field is running on the default, so answering blank would say the
        opposite."""
        if key in self.settings:
            return self.settings[key]
        declared = next((f for f in self.fields() if f.key == key), None)
        return declared.default if declared is not None else ""

    def fields(self) -> tuple[apps.Field, ...]:
        """What configuring this launcher takes: what its app declares, and what every
        launcher has whatever it wraps."""
        found = apps.get(self.app)
        return (found.fields if found is not None else ()) + OWN_FIELDS

    def as_dict(self) -> dict[str, Any]:
        return {"launcher_id": self.launcher_id, "app": self.app,
                "display_name": self.display_name, "enabled": self.enabled,
                "owns_ini": self.owns_ini, "settings": dict(self.settings),
                **self.extra}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Launcher | None:
        launcher_id = str(raw.get("launcher_id", "") or "").strip()
        if not launcher_id:
            return None
        known = {"launcher_id", "app", "display_name", "enabled", "owns_ini", "settings"}
        return cls(
            launcher_id=launcher_id,
            app=str(raw.get("app", "") or ""),
            display_name=str(raw.get("display_name", "") or ""),
            # Absent reads as enabled: a file written before the flag existed described
            # launchers that were all in use.
            enabled=bool(raw.get("enabled", True)),
            owns_ini=bool(raw.get("owns_ini", False)),
            settings=dict(raw.get("settings") or {}),
            # Anything a newer build wrote is carried through rather than dropped, so a
            # downgrade does not silently strip fields it does not understand.
            extra={k: v for k, v in raw.items() if k not in known},
        )


class LauncherStore:
    """Every launcher this install has, and which table uses which."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else LAUNCHERS_PATH
        self._lock = threading.RLock()

    # -- reading -------------------------------------------------------------

    def launchers(self) -> list[Launcher]:
        """Every launcher, in the order the file holds them. An unreadable file is an
        empty set, never an error: a first run has none and that is not a fault."""
        with self._lock:
            return self._load()[0]

    def get(self, launcher_id: str) -> Launcher | None:
        wanted = (launcher_id or "").strip()
        if not wanted:
            return None
        return next((one for one in self.launchers()
                     if one.launcher_id == wanted), None)

    def mappings(self) -> dict[str, str]:
        """Table id to launcher id, and only for the tables that deviate.

        A table with no entry runs on the default, so changing the default re-points
        everything that never asked for anything else.
        """
        with self._lock:
            return self._load()[1]

    def mapped(self, table_id: str) -> str:
        return self.mappings().get(str(table_id or "").strip(), "")

    # -- writing -------------------------------------------------------------

    def save(self, launchers: list[Launcher], mappings: dict[str, str]) -> None:
        """The whole file, atomically. Written whole because it is small and because a
        partial write of a launcher that a mapping points at is a table that cannot
        launch."""
        with self._lock:
            self._write(launchers, mappings)

    def put(self, launcher: Launcher) -> Launcher:
        """Add one, or replace the one with its id.

        Replace rather than merge, and by id rather than by position: this is also how a
        launcher copied from another machine lands, and that copy is the whole launcher.
        """
        with self._lock:
            held, mappings = self._load()
            found = [one for one in held if one.launcher_id != launcher.launcher_id]
            at = next((i for i, one in enumerate(held)
                       if one.launcher_id == launcher.launcher_id), len(found))
            found.insert(at, launcher)
            self._write(found, mappings)
            return launcher

    def remove(self, launcher_id: str) -> bool:
        """Forget a launcher and every mapping to it.

        The mappings go with it rather than being left dangling: a table pointing at a
        launcher that is not there falls back at launch, which is right for a launcher
        that is switched off and wrong for one that was deleted - the second is not a
        state anybody chose to be in.
        """
        wanted = (launcher_id or "").strip()
        with self._lock:
            held, mappings = self._load()
            kept = [one for one in held if one.launcher_id != wanted]
            if len(kept) == len(held):
                return False
            self._write(kept, {table: to for table, to in mappings.items()
                               if to != wanted})
            return True

    def assign(self, table_id: str, launcher_id: str) -> None:
        """Point a table at a launcher, or clear it with an empty id.

        Clearing removes the row rather than storing a blank, because an absent mapping
        already means "the default" and two spellings of one state is what makes a
        reader ask which is which.
        """
        table = str(table_id or "").strip()
        if not table:
            return
        with self._lock:
            held, mappings = self._load()
            found = dict(mappings)
            wanted = str(launcher_id or "").strip()
            if wanted:
                found[table] = wanted
            else:
                found.pop(table, None)
            self._write(held, found)

    def migrations(self) -> list[str]:
        """Which one-time conversions have already run against this file."""
        with self._lock:
            return self._stored_migrations()

    def mark_migration(self, name: str) -> None:
        """Note that one has run, so it never runs twice."""
        wanted = str(name or "").strip()
        if not wanted:
            return
        with self._lock:
            names = self._stored_migrations()
            if wanted in names:
                return
            held, mappings = self._load()
            self._write(held, mappings, migrations=names + [wanted])

    # -- the file ------------------------------------------------------------

    def _stored_migrations(self) -> list[str]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                payload = json.load(handle) or {}
        except Exception:
            return []
        return [str(name) for name in payload.get(MIGRATIONS_KEY) or []
                if str(name).strip()]

    def _load(self) -> tuple[list[Launcher], dict[str, str]]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                payload = json.load(handle) or {}
        except FileNotFoundError:
            return [], {}
        except Exception:
            logger.exception("Could not read %s; treating it as empty", self.path)
            return [], {}

        held = [one for one in
                (Launcher.from_dict(raw) for raw in payload.get(LAUNCHERS_KEY) or []
                 if isinstance(raw, dict))
                if one is not None]
        ids = {one.launcher_id for one in held}
        # A mapping to a launcher that is not in the file leads nowhere, so it is dropped
        # on read rather than resolved at launch: the alternative is a table that reports
        # an override it does not have.
        mappings = {str(table): str(to) for table, to in
                    (payload.get(MAPPINGS_KEY) or {}).items()
                    if str(table).strip() and str(to) in ids}
        return held, mappings

    def _write(self, launchers: list[Launcher], mappings: dict[str, str],
               migrations: list[str] | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Read back rather than held: every other method here reads the file fresh, so
        # keeping the markers in memory would let two writers drop each other's.
        payload = {
            SCHEMA_KEY: SCHEMA,
            MIGRATIONS_KEY: (self._stored_migrations() if migrations is None
                             else migrations),
            LAUNCHERS_KEY: [one.as_dict() for one in launchers],
            MAPPINGS_KEY: dict(mappings),
        }
        write_atomic(self.path, lambda handle: json.dump(payload, handle, indent=2))


def default_for(app_id: str, launchers) -> Launcher | None:
    """The launcher a table of this app runs on when nothing says otherwise.

    The first enabled one, so the file's order answers "which is the default" rather than
    a flag that two launchers could carry at once.
    """
    return next((one for one in launchers
                 if one.app == app_id and one.enabled), None)


def launcher_for_table(filename: str, table_id: str, launchers, mappings) -> Launcher | None:
    """Which launcher plays this table: what it names, then the default for its app.

    One function, so the grid's effective-launcher column and the launch path can never
    disagree - that divergence is the bug the override mask has today, where what will
    actually happen at launch is not visible anywhere before it happens.

    A table naming a launcher that is switched off falls back rather than refusing, and
    the caller is expected to say so: the fallback is honest, and silence about it is
    what turns a configuration choice into a mystery.
    """
    app = apps.app_for(filename)
    if app is None:
        return None
    wanted = str(mappings.get(str(table_id or "").strip(), "") or "")
    if wanted:
        named = next((one for one in launchers if one.launcher_id == wanted), None)
        if named is not None and named.enabled:
            return named
    return default_for(app.id, launchers)


def seeded_from(values: dict[str, Any], app_id: str = "vpx") -> Launcher:
    """The launcher an install already had, from the values read out of its old config.

    Takes a plain mapping rather than a settings object: the seven keys it comes from are
    no longer in the schema, so nothing types them for us any more and the reader that
    finds them is the one that knows their old spellings.

    `owns_ini` is False - the ini those keys named is Visual Pinball's own, and nothing
    here created it.
    """
    return Launcher(
        launcher_id=mint_launcher_id(),
        app=app_id,
        display_name=apps.app_name(app_id),
        enabled=True,
        owns_ini=False,
        settings=dict(values),
    )


def default_launcher(app_id: str = "vpx") -> Launcher | None:
    """This install's launcher for an app, for anything that needs Visual Pinball without
    having a table in hand - a capability probe, or finding the ROM library beside it."""
    return default_for(app_id, get_launcher_store().launchers())


def default_value(key: str, app_id: str = "vpx") -> str:
    """One field of that launcher, or "" where the install has none. Answering blank for
    a missing launcher is right: nothing is configured, which is what the caller is
    usually about to report."""
    found = default_launcher(app_id)
    return str(found.value(key) or "") if found is not None else ""


def replace_settings(launcher: Launcher, **values: Any) -> Launcher:
    """A launcher with some of its settings changed, leaving the rest alone."""
    return replace(launcher, settings={**launcher.settings, **values})


_store: LauncherStore | None = None


def get_launcher_store() -> LauncherStore:
    """This install's launchers. One per process, the way the device registry is."""
    global _store
    if _store is None:
        _store = LauncherStore()
    return _store
