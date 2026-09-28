"""Where this install looks for entries.

A location is either a **root**, whose children are game folders, or a **single game
folder**. Both kinds coexist in one list, so a library can be a share plus the two
folders somebody keeps elsewhere without either being second class.

Follows `common/games/launchers.py`: a small JSON file, written whole and atomically,
carrying its own schema version. **Per install, not per library** - a path is a fact
about one machine, and a share reachable from the cabinet may not be reachable from the
laptop reading the same library. That is why this is not in `library.json`, which holds
what the library itself collects.

Whether a location is reachable and whether it can be written to are asked of the disk
when somebody looks, never stored. A stored answer is wrong the moment a mount drops,
and a mount dropping is the ordinary case this exists to report well.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from common import mounts
from common.atomic_write import write_atomic
from common.config_access import cfg_get
from common.config_store import ConfigStore
from common.failures import why
from common.i18n import t
from common.install_identity import mint_id
from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.common.games.locations")

LOCATIONS_PATH = CONFIG_DIR / "locations.json"
SCHEMA = 2
SCHEMA_KEY = "schema"
LOCATIONS_KEY = "locations"
WRITE_TO_KEY = "write_to"
MIGRATIONS_KEY = "migrations"

# Its children are game folders.
KIND_ROOT = "root"
# It is one game folder.
KIND_GAME = "game"
KINDS = (KIND_ROOT, KIND_GAME)


def mint_location_id() -> str:
    return mint_id()


def canonical(path: str) -> str:
    """One spelling per place on disk, so a folder reached directly and through a parent
    root is recognized as the same one. Symlinks resolved, case left alone: a
    case-insensitive filesystem is not a reason to rewrite what somebody typed."""
    wanted = str(path or "").strip()
    if not wanted:
        return ""
    return os.path.normpath(os.path.realpath(os.path.expanduser(wanted)))


@dataclass(frozen=True)
class Location:
    location_id: str
    path: str
    kind: str = KIND_ROOT
    # The share it was last seen on.
    origin: mounts.Origin | None = None

    @property
    def name(self) -> str:
        """What to call it where the whole path will not fit.

        The last two segments, not the last one: a library is very often a folder called
        `tables` or `games`, and two of those side by side would draw the same row twice.
        """
        parts = [p for p in Path(self.path).parts if p not in ("/", "\\")]
        return "/".join(parts[-2:]) if len(parts) > 1 else (parts[0] if parts else self.path)

    def as_dict(self) -> dict[str, Any]:
        held: dict[str, Any] = {"location_id": self.location_id, "path": self.path,
                                "kind": self.kind}
        if self.origin is not None:
            held["origin"] = self.origin.as_dict()
        return held

    @classmethod
    def from_dict(cls, raw: dict) -> Location | None:
        location_id = str(raw.get("location_id", "") or "").strip()
        path = str(raw.get("path", "") or "").strip()
        if not location_id or not path:
            return None
        kind = str(raw.get("kind", "") or "").strip() or KIND_ROOT
        return cls(location_id=location_id, path=path,
                   kind=kind if kind in KINDS else KIND_ROOT,
                   origin=mounts.Origin.from_dict(raw.get("origin")))


READY = "ready"
READ_ONLY = "read_only"
NOT_CONNECTED = "not_connected"
NOT_FOUND = "not_found"
NOT_ANSWERING = "not_answering"

# How long a caller waits for the disk before calling a location Not answering.
PROBE_SECONDS = 2.0
# How long the scan and a launch wait for a folder.
MOUNT_SECONDS = 30.0


@dataclass(frozen=True)
class LocationState:
    """What the disk says about a location right now."""

    state: str
    reason: str = ""
    # The share it is on, or None on this device or when it did not answer.
    origin: mounts.Origin | None = None

    @property
    def reachable(self) -> bool:
        return self.state in (READY, READ_ONLY)

    @property
    def writable(self) -> bool:
        return self.state == READY


def _look(raw_path: str, recorded: mounts.Origin | None = None) -> LocationState:
    # Resolved the same way `canonical` resolves it. Reading the raw string would call
    # `~/tables` unreachable while the scan happily walked it.
    path = Path(canonical(raw_path) or raw_path)
    there = path.exists()
    where = mounts.where(str(path), recorded)
    origin = where.origin
    if origin is not None and not where.connected:
        return LocationState(NOT_CONNECTED, t("error.locations.not_connected",
                                              share=origin.source), origin)
    if not there:
        return LocationState(NOT_FOUND, t("error.locations.nothing_at_path"), origin)
    if not path.is_dir():
        return LocationState(NOT_FOUND, t("error.locations.not_a_folder"), origin)
    if not os.access(path, os.W_OK):
        return LocationState(READ_ONLY, t("error.locations.nothing_can_be_written"),
                             origin)
    return LocationState(READY, origin=origin)


class _Probe:
    def __init__(self, raw_path: str, recorded: mounts.Origin | None) -> None:
        self.raw_path = raw_path
        self.recorded = recorded
        self.started = time.monotonic()
        self.done = threading.Event()
        self.answer = LocationState(NOT_ANSWERING, t("error.locations.not_answering"))

    def run(self) -> None:
        try:
            self.answer = _look(self.raw_path, self.recorded)
        except (OSError, ValueError) as exc:
            self.answer = LocationState(NOT_FOUND, why(exc, self.raw_path))
        finally:
            with _PROBES_LOCK:
                if _PROBES.get(self.raw_path) is self:
                    del _PROBES[self.raw_path]
            self.done.set()


_PROBES: dict[str, _Probe] = {}
_PROBES_LOCK = threading.Lock()


def _probe(location: Location) -> _Probe:
    """The question in flight for this path, or a new one. Nothing cancels a stat on a
    dead mount, so a second question would be a second thread lost to it."""
    with _PROBES_LOCK:
        probe = _PROBES.get(location.path)
        if probe is None:
            probe = _PROBES[location.path] = _Probe(location.path, location.origin)
            threading.Thread(target=probe.run, daemon=True,
                             name="location-probe").start()
    return probe


def states_of(held: list[Location],
              wait: float | None = None) -> dict[str, LocationState]:
    """What the disk says about each location, keyed by id, asked of all of them at once.

    `wait` counts from when the question was first asked, not from this call, so a
    question already out that long answers Not answering at once.
    """
    limit = PROBE_SECONDS if wait is None else wait
    probes = {one.location_id: _probe(one) for one in held}
    for probe in probes.values():
        probe.done.wait(max(0.0, probe.started + limit - time.monotonic()))
    answers = {location_id: probe.answer for location_id, probe in probes.items()}
    seen = {one.location_id: origin for one in held
            if (origin := answers[one.location_id].origin) is not None
            and answers[one.location_id].state != NOT_CONNECTED and origin != one.origin}
    if seen:
        get_location_store().record_origins(seen)
    return answers


def state_of(location: Location) -> LocationState:
    return states_of([location])[location.location_id]


class LocationStore:
    """Every location this install looks in, and which one new entries are created in."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else LOCATIONS_PATH
        self._lock = threading.RLock()

    # -- reading -------------------------------------------------------------

    def locations(self) -> list[Location]:
        """Every location, in the order the file holds them. An unreadable file is an
        empty set, never an error: a first run has none and that is not a fault."""
        with self._lock:
            return self._load()[0]

    def get(self, location_id: str) -> Location | None:
        wanted = str(location_id or "").strip()
        if not wanted:
            return None
        return next((one for one in self.locations()
                     if one.location_id == wanted), None)

    def write_to(self) -> Location | None:
        """Where a new entry's folder is created. A user choice, so it is stored rather
        than derived - but it falls back to the first writable one, because an install
        that has never been asked still has to be able to create something."""
        with self._lock:
            held, wanted = self._load()
        states = states_of(held)
        named = next((one for one in held if one.location_id == wanted), None)
        if named is not None and states[named.location_id].writable:
            return named
        return next((one for one in held
                     if one.kind == KIND_ROOT and states[one.location_id].writable), None)

    # -- writing -------------------------------------------------------------

    def save(self, locations: list[Location], write_to: str = "") -> None:
        with self._lock:
            self._write(locations, write_to)

    def put(self, location: Location) -> Location:
        """Add one, or replace the one that already names this place.

        Matched on the canonical path rather than the id, because adding a folder twice
        is a thing a person does and two rows for one place would each report their own
        state.
        """
        wanted = canonical(location.path)
        with self._lock:
            held, write_to = self._load()
            kept = [one for one in held if canonical(one.path) != wanted]
            existing = next((one for one in held if canonical(one.path) == wanted), None)
            if existing is not None:
                location = Location(location_id=existing.location_id,
                                    path=location.path, kind=location.kind,
                                    origin=existing.origin)
            self._write([*kept, location], write_to)
        return location

    def record_origins(self, origins: dict[str, mounts.Origin]) -> None:
        """Note the share each location was just seen on. Ids it does not hold are
        ignored, and nothing is written when nothing changed."""
        with self._lock:
            held, write_to = self._load()
            updated = [replace(one, origin=origins[one.location_id])
                       if one.location_id in origins else one for one in held]
            if updated != held:
                self._write(updated, write_to)

    def remove(self, location_id: str) -> bool:
        """Forget a location. The records inside it go with it, because a contained
        entry keeps its record in its own folder - that is where it lives, and it is
        still there if the location comes back."""
        wanted = str(location_id or "").strip()
        with self._lock:
            held, write_to = self._load()
            kept = [one for one in held if one.location_id != wanted]
            if len(kept) == len(held):
                return False
            self._write(kept, "" if write_to == wanted else write_to)
        return True

    def chosen_write_to(self) -> str:
        """The location somebody actually chose, or "".

        `write_to` answers the fallback as well, which is right when something has to
        create a folder now. This is right when the question is what they asked for -
        so a destination that has gone read-only can be refused by name rather than
        quietly becoming a different folder.
        """
        with self._lock:
            return self._load()[1]

    def reorder(self, order: list[str]) -> bool:
        """Put the locations in the order given. **The order is the priority.**

        A game folder carries its id, so one library reached through two locations has
        every id twice - and which folder answers is decided by which location is
        higher. That has to be somebody's to set, which is what this is.

        Any location the caller does not name keeps its place after the ones that were,
        in the order it already had. A caller working from a stale list therefore
        rearranges what it knew about and loses nothing it did not.
        """
        with self._lock:
            held, write_to = self._load()
            by_id = {one.location_id: one for one in held}
            wanted = [by_id[one] for one in
                      dict.fromkeys(str(x or "").strip() for x in order)
                      if one in by_id]
            if not wanted:
                return False
            named = {one.location_id for one in wanted}
            self._write(wanted + [one for one in held
                                  if one.location_id not in named], write_to)
        return True

    def set_write_to(self, location_id: str) -> bool:
        wanted = str(location_id or "").strip()
        with self._lock:
            held, _ = self._load()
            if not any(one.location_id == wanted for one in held):
                return False
            self._write(held, wanted)
        return True

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
            held, write_to = self._load()
            self._write(held, write_to, migrations=names + [wanted])

    # -- the file ------------------------------------------------------------

    def _load(self) -> tuple[list[Location], str]:
        payload = self._payload()
        held = [one for one in
                (Location.from_dict(raw) for raw in payload.get(LOCATIONS_KEY) or []
                 if isinstance(raw, dict))
                if one is not None]
        # One row per place. A file edited by hand can hold the same folder twice, and
        # two rows for one place would each report their own state. Compared as spelled,
        # not through canonical(): resolving a path on a dead mount blocks.
        seen: set[str] = set()
        unique = []
        for one in held:
            key = os.path.normpath(os.path.expanduser(one.path))
            if key in seen:
                logger.warning("Ignoring a second location for %s", one.path)
                continue
            seen.add(key)
            unique.append(one)
        write_to = str(payload.get(WRITE_TO_KEY, "") or "").strip()
        return unique, write_to

    def _payload(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as handle:
                return json.load(handle) or {}
        except FileNotFoundError:
            return {}
        except Exception:
            logger.exception("Could not read %s; treating it as empty", self.path)
            return {}

    def _stored_migrations(self) -> list[str]:
        return [str(name) for name in self._payload().get(MIGRATIONS_KEY) or []
                if str(name).strip()]

    def _write(self, locations: list[Location], write_to: str,
               migrations: list[str] | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            SCHEMA_KEY: SCHEMA,
            MIGRATIONS_KEY: (self._stored_migrations() if migrations is None
                             else migrations),
            LOCATIONS_KEY: [one.as_dict() for one in locations],
            WRITE_TO_KEY: str(write_to or ""),
        }
        write_atomic(self.path, lambda handle: json.dump(payload, handle, indent=2))


# The id every row carries while the scan still walks the configured root. Runtime
# only: nothing stores a location id yet.
CONFIGURED_ID = "configured"


@dataclass(frozen=True)
class Destination:
    """Where a new game folder would be created, or why it would not be.

    Both, because the answer a caller needs on a refusal is not only that it failed: it
    is which other places would work, so somebody can send this one there instead.
    """

    location: Location | None = None
    # Empty when there is somewhere to write. A sentence when there is not.
    reason: str = ""
    # Every writable root other than the one that was wanted, for a one-time override.
    alternatives: tuple[Location, ...] = ()

    @property
    def path(self) -> str:
        return self.location.path if self.location is not None else ""


def _writable_roots(held: list[Location],
                    states: dict[str, LocationState]) -> tuple[Location, ...]:
    return tuple(one for one in held
                 if one.kind == KIND_ROOT and states[one.location_id].writable)


def destination(location_id: str = "") -> Destination:
    """Where a new game goes, or the reason it cannot go anywhere.

    **Refuses rather than quietly landing somewhere else.** The location marked "create
    new games here" is a choice somebody made and a row on screen says so; writing to a
    different one because that row went read-only makes the screen a lie, and they find
    out by looking for a game where they expected it.

    `location_id` names a one-time override, which is checked the same way - an override
    that cannot be written to is refused rather than falling back in its turn.
    """
    store = get_location_store()
    held = store.locations()
    states = states_of(held)
    writable = _writable_roots(held, states)
    wanted = str(location_id or "").strip() or store.chosen_write_to()

    if not wanted:
        # Nothing chosen. The first writable root is the honest default rather than a
        # refusal: an install that has never been asked still has to be able to create.
        if writable:
            return Destination(location=writable[0])
        return Destination(reason=t("error.locations.nowhere_to_create"))

    named = next((one for one in held if one.location_id == wanted), None)
    others = tuple(one for one in writable if one.location_id != wanted)
    if named is None:
        return Destination(reason=t("error.locations.new_games_location_gone"),
                           alternatives=others)
    state = states[named.location_id]
    if named.kind != KIND_ROOT:
        return Destination(reason=t("error.locations.single_game_folder", name=named.name),
                           alternatives=others)
    if not state.reachable:
        return Destination(reason=t("error.locations.not_reachable", name=named.name,
                                    reason=state.reason),
                           alternatives=others)
    if not state.writable:
        return Destination(reason=t("error.locations.read_only", name=named.name),
                           alternatives=others)
    return Destination(location=named, alternatives=others)


def portable_reference(game_dir: str, target: str) -> str:
    """How to store a path to a file outside a game folder, so a library survives being
    moved.

    Relative where the target is inside the same configured location as the game,
    because moving or sharing that whole tree then keeps the reference pointing at the
    same file. Absolute otherwise: a relative path out of the library would be a chain
    of `..` that means nothing once the library has moved, which is worse than an
    absolute path that at least fails honestly.
    """
    from common.games.tables import stored_reference

    wanted = canonical(target)
    home = canonical(game_dir)
    if not wanted or not home:
        return stored_reference(target)
    for location in configured():
        root = canonical(location.path)
        if not root:
            continue
        # Compared canonically, because two spellings of one place have to be recognized
        # as one - but the relative form is computed from those same canonical ends, so
        # what it walks is real rather than through whichever alias was typed.
        if _inside(root, wanted) and _inside(root, home):
            return Path(os.path.relpath(wanted, home)).as_posix()
    # Stored as given, not as resolved. Somebody who points through a symlink means the
    # symlink: baking today's target in would stop the reference following it, and a
    # mount point is exactly the kind of path that gets repointed.
    return stored_reference(os.path.normpath(os.path.expanduser(str(target or ""))))


def _inside(root: str, path: str) -> bool:
    """Whether a path is at or under a root, compared as paths rather than as text -
    `/games2` starts with `/games` and is not in it."""
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def configured() -> list[Location]:
    """Every location the scan walks.

    The store, and the configured root only while the store has nothing and the seed has
    not run - an install that has not started since locations arrived, or one whose file
    was deleted. Falling back rather than reading empty means a library never disappears
    because a seed did not run; after it has, an empty store is no locations.
    """
    store = get_location_store()
    held = store.locations()
    if held or SEEDED in store.migrations():
        return held

    from common.paths import get_games_path

    root = get_games_path(default="")
    return [Location(location_id=CONFIGURED_ID, path=root, kind=KIND_ROOT)] if root else []


SEEDED = "seeded-from-config"


def seed(store: LocationStore, config: ConfigStore) -> bool:
    """Give an install its locations, once, from the single root it was configured with.

    Marked so it never runs twice: somebody who removes a location should not find it
    back on the next start. An install with no root configured is not marked, so the
    first one it is given still seeds.
    """
    if SEEDED in store.migrations():
        return False
    configured = str(cfg_get(config, "general", "game_root_dir", "") or "").strip()
    if not configured:
        return False

    location = store.put(Location(location_id=mint_location_id(), path=configured,
                                  kind=KIND_ROOT))
    store.set_write_to(location.location_id)
    store.mark_migration(SEEDED)
    logger.info("Seeded the library location from the configured root: %s", configured)
    return True


def ensure_seeded(config: ConfigStore) -> None:
    """Seed at startup, and never let it be the thing that stops an install starting."""
    try:
        seed(get_location_store(), config)
    except Exception:
        logger.exception("Could not seed locations from the configuration")


_store: LocationStore | None = None


def get_location_store() -> LocationStore:
    global _store
    if _store is None:
        _store = LocationStore()
    return _store
