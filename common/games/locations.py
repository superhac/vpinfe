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
from dataclasses import dataclass
from pathlib import Path

from common.atomic_write import write_atomic
from common.config_access import cfg_get
from common.install_identity import mint_id
from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.common.games.locations")

LOCATIONS_PATH = CONFIG_DIR / "locations.json"
SCHEMA = 1
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

    @property
    def name(self) -> str:
        """What to call it where the whole path will not fit.

        The last two segments, not the last one: a library is very often a folder called
        `tables` or `games`, and two of those side by side would draw the same row twice.
        """
        parts = [p for p in Path(self.path).parts if p not in ("/", "\\")]
        return "/".join(parts[-2:]) if len(parts) > 1 else (parts[0] if parts else self.path)

    def as_dict(self) -> dict[str, str]:
        return {"location_id": self.location_id, "path": self.path, "kind": self.kind}

    @classmethod
    def from_dict(cls, raw: dict) -> Location | None:
        location_id = str(raw.get("location_id", "") or "").strip()
        path = str(raw.get("path", "") or "").strip()
        if not location_id or not path:
            return None
        kind = str(raw.get("kind", "") or "").strip() or KIND_ROOT
        return cls(location_id=location_id, path=path,
                   kind=kind if kind in KINDS else KIND_ROOT)


@dataclass(frozen=True)
class LocationState:
    """What the disk says about a location right now."""

    reachable: bool
    writable: bool
    reason: str = ""


def state_of(location: Location) -> LocationState:
    """Asked of the disk every time. A late mount is the ordinary case here, and the
    honest report is "this location is unreachable" rather than every entry in it
    reading as gone."""
    # Resolved the same way `canonical` resolves it. Reading the raw string would call
    # `~/tables` unreachable while the scan happily walked it.
    path = Path(canonical(location.path) or location.path)
    if not path.exists():
        return LocationState(False, False, "Not reachable.")
    if not path.is_dir():
        return LocationState(False, False, "Not a folder.")
    if not os.access(path, os.W_OK):
        return LocationState(True, False, "Read-only.")
    return LocationState(True, True)


class LocationStore:
    """Every location this install looks in, and which one new entries are created in."""

    def __init__(self, path: Path | str | None = None):
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
        named = next((one for one in held if one.location_id == wanted), None)
        if named is not None and state_of(named).writable:
            return named
        return next((one for one in held
                     if one.kind == KIND_ROOT and state_of(one).writable), None)

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
                                    path=location.path, kind=location.kind)
            self._write([*kept, location], write_to)
        return location

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
        # two rows for one place would each report their own state.
        seen: set[str] = set()
        unique = []
        for one in held:
            key = canonical(one.path)
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


def configured() -> list[Location]:
    """Every location the scan walks.

    The store, and the configured root only when the store has nothing - which is an
    install that has not started since locations arrived, or one whose file was deleted.
    Falling back rather than reading empty means a library never disappears because a
    seed did not run.
    """
    held = get_location_store().locations()
    if held:
        return held

    from common.paths import get_games_path

    root = get_games_path()
    return [Location(location_id=CONFIGURED_ID, path=root, kind=KIND_ROOT)] if root else []


SEEDED = "seeded-from-config"


def seed(store: LocationStore, config) -> bool:
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


def ensure_seeded(config) -> None:
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
