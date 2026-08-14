"""Collections on disk: what is in each one, and what a collection is allowed to be."""

# collection_store.py
import configparser
import contextlib
import json
import logging
import os
import threading
from pathlib import Path

from common import events
from common.games import collection_filters
from common.games.game_identity import game_id
from common.games.game_metadata import (
    base_game_vps_id,
    vpinfe_section,
)
from common.games.info_file import VPINFE_SECTION
from common.games.info_migration import (
    backup_names,
    copy_aside,
    write_atomic,
)

logger = logging.getLogger("vpinfe.common.games.collection_store")

# Every writer holds a whole copy of the file and `save` writes all of it, so two that
# read before either saved lose one of the two edits. Callers each build their own store
# - the theme's collection menu and the API are different objects reading the same path -
# so the lock is the module's rather than any one store's.
_write_lock = threading.RLock()

# Generations of the collections file, counting from the first one that shipped.
#   1  ini, membership keyed by VPS id. Implied when no version is recorded.
#   2  JSON, membership keyed by the game's own id (common/games/game_identity.py).
#      Members and filters are nested and ordered, which an ini cannot encode.
#
# 3.0 development also numbered an ini keyed by game id, between the two. It never
# shipped, and anything below the current version migrates the same way, so it collapses
# into the JSON generation rather than leaving a gap.
COLLECTIONS_SCHEMA = 2

# Schema 0/1 only: in an ini the sections are collection names, so the version lived
# in a reserved section filtered out of the collection list. Both spellings are
# reserved - real files carry `[VPinFE]` and `[vpinfe]` side by side, because the
# section was renamed without the old one being removed. Reading only the new name
# turns the old one into a collection called "VPinFE".
SCHEMA_SECTION = VPINFE_SECTION
SCHEMA_SECTIONS = (VPINFE_SECTION, "VPinFE")
SCHEMA_KEY = "schema"

# The ini's membership key. Kept for reading a schema 0/1 file - see get_members().
MEMBERS_KEY = "vpsids"

COLLECTIONS_KEY = "collections"
COLLECTION_IMAGE_KEY = "image"

# One-time conversions this file has been through, by name. Not the schema number:
# whichever conversion stamped that first would tell the others they had already run.
MIGRATIONS_KEY = "migrations"

# A member names a game, and optionally one of its tables:
#
#   {"game": "tuF3WogthK"}                        the game - its default table
#   {"game": "tuF3WogthK", "table": "9kRm2QvT8x"} exactly this table, frozen
#
# Two members may name the same game, which is how one game appears twice in a
# curated order with a different table each time. A bare id names the game.
MEMBER_GAME_KEY = "game"
MEMBER_TABLE_KEY = "table"

# Same shape, opposite sign. An excluded ref naming only a game removes the game; one
# naming a table removes that table and leaves the rest of the game alone.
#
# Excluding a table is not the inverse of naming one. A named table is frozen - a table
# added next month does not appear. An exclusion still tracks - it does. Both are
# wanted, and neither substitutes for the other.
EXCLUDED_KEY = "excluded"

# How a collection is ordered, as its own block rather than mixed in with the criteria.
#
#   {"by": "title", "direction": "asc"}
#
# `manual` means the member array is the order. It is never the default: a collection
# curated before curated order existed was displayed alphabetically, and honouring its
# insertion order would silently reshuffle a list the user is used to. The editor sets
# it when somebody actually arranges one.
ORDER_KEY = "order"
ORDER_BY_KEY = "by"
ORDER_DIRECTION_KEY = "direction"
DEFAULT_ORDER_BY = "title"
DEFAULT_DIRECTION = "asc"
MANUAL_ORDER = "manual"

# How many rows to keep, applied last so it caps an ordered list rather than choosing
# which rows are in it. Absent means all of them, which is every collection written
# before this key existed - so it is an addition to schema 2, not a new version.
# "Last 20 played" is an order plus this and nothing else.
LIMIT_KEY = "limit"

# The whole library, as a collection. Synthesized: the store answers for it and `save()`
# never writes it, so no user's file gains a row to say what absence already said. It
# constrains nothing, which is why the resolver needs no case for it - empty criteria
# match every game, so the library comes back through the ordinary path.
BUILTIN_ALL = "builtin:all"

BUILTIN_RECORDS = {
    BUILTIN_ALL: {"name": BUILTIN_ALL, "label": "All Games", "type": "filter",
                  "builtin": True, "image": "", "filters": {}},
}


def public_name(name: str | None) -> str:
    """What a collection is called outside core. The whole library is no collection at
    all out there - in the payload, in `get_current_collection`, in the hub's URL - and
    the `builtin:` prefix reaches nobody."""
    return "" if not name or name == BUILTIN_ALL else str(name)

# The stored sort names, in the vocabulary the rest of 3.0 uses. Nothing writes the old
# spellings any more; a file written before this block existed still holds them.
ORDER_ALIASES = {
    "Alpha": "title",
    "Newest": "added",
    "LastRun": "last_played",
    "Highest StartCount": "play_count",
    "RunTime": "play_time",
}


def _member_ref(value) -> dict | None:
    """One stored member as a ref, or None if there is nothing addressable in it."""
    if isinstance(value, str):
        value = value.strip()
        return {MEMBER_GAME_KEY: value} if value else None
    if not isinstance(value, dict):
        return None
    game = str(value.get(MEMBER_GAME_KEY, "") or "").strip()
    if not game:
        return None
    ref = {MEMBER_GAME_KEY: game}
    table = str(value.get(MEMBER_TABLE_KEY, "") or "").strip()
    if table:
        ref[MEMBER_TABLE_KEY] = table
    return ref


def _member_refs(values) -> list[dict]:
    return [ref for ref in (_member_ref(v) for v in (values or [])) if ref]

# What a filter collection stores, with the value meaning "unconstrained on this axis".
_FILTER_DEFAULTS = {
    "letter": "All", "theme": "All", "table_type": "All", "manufacturer": "All",
    "year": "All", "rating": "All", "rating_or_higher": "false",
    "sort_by": "Alpha", "order_by": "Descending",
}


def _ini_schema(parser) -> int:
    """The highest version either reserved section declares, or 0 if none does.

    0 means "declares nothing", which `collections_schema` turns into None for a caller
    choosing a backup to restore. The store reads an unstamped ini as generation 1.
    """
    found = []
    for name in SCHEMA_SECTIONS:
        if name in parser:
            try:
                found.append(int(parser[name].get(SCHEMA_KEY, 0) or 0))
            except (TypeError, ValueError):
                pass
    return max(found, default=0)

_warned_newer_schema = set()


class CollectionStore:
    """The user's collections, stored as JSON.

    Records are dicts in a list, so their order is the order they are shown in and a
    filter collection's criteria nest instead of being flattened into ini keys. A
    schema 0/1 `collections.ini` beside the JSON is read once and converted on save.
    """

    def __init__(self, path: str):
        # Either name is accepted: the JSON file is what we read and write, and a
        # caller still holding the ini path - a script, an old config - gets the same
        # collections rather than an empty list.
        path = Path(path)
        if path.suffix == ".ini":
            self.ini_path, self.path = path, path.with_name(COLLECTIONS_NAME)
        else:
            self.path, self.ini_path = path, path.with_name(COLLECTIONS_NAME_INI)
        self._converted_from_ini = False
        # This store's own copies: `set_view_filters` writes into `builtin:all`, and one
        # caller's view must not become another's.
        self._builtins = {name: dict(record) for name, record in BUILTIN_RECORDS.items()}
        self.reload()

    def reload(self):
        """Load from disk, discarding unsaved changes."""
        self.records: list[dict] = []
        self._schema = COLLECTIONS_SCHEMA
        self._migrations: list[str] = []
        self._converted_from_ini = False

        if self.path.exists():
            self._load_json()
        elif self.ini_path.exists():
            self._load_ini()
            self._converted_from_ini = True

    def _load_json(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.exception("Could not read %s; starting from no collections", self.path)
            return
        if not isinstance(data, dict):
            return
        self._schema = int(data.get(SCHEMA_KEY, COLLECTIONS_SCHEMA) or COLLECTIONS_SCHEMA)
        self._migrations = [str(name) for name in data.get(MIGRATIONS_KEY) or []
                            if isinstance(name, str)]
        records = data.get(COLLECTIONS_KEY)
        if not isinstance(records, list):
            return
        for record in records:
            if not isinstance(record, dict) or not record.get("name"):
                continue
            for key in ("members", EXCLUDED_KEY):
                if key in record:
                    record[key] = _member_refs(record[key])
            self.records.append(record)

    def _load_ini(self) -> None:
        """Read a schema 0/1 file into the current shape. Nothing is written here -
        the conversion reaches disk on the next save, which keeps reading side-effect
        free for the callers that only ever look."""
        parser = configparser.ConfigParser()
        parser.read(self.ini_path, encoding="utf-8")
        # No stamp means the shape 2.x shipped, which is generation 1.
        self._schema = _ini_schema(parser) or 1
        for name in parser.sections():
            if name in SCHEMA_SECTIONS:
                continue
            sec = parser[name]
            record = {"name": name, "image": sec.get("image", "")}
            if sec.get("type", "vpsid") == "filter":
                record["type"] = "filter"
                record["filters"] = {k: sec.get(k, d) for k, d in _FILTER_DEFAULTS.items()}
            else:
                record["type"] = "manual"
                record["members"] = _member_refs(
                    sec.get(MEMBERS_KEY, "").split(","))
            self.records.append(record)

    def _record(self, name: str) -> dict | None:
        for record in self.records:
            if record.get("name") == name:
                return record
        # A fresh copy, so a reader that mutates what it is handed cannot make a builtin
        # differ between two calls. Writers go through _require_mutable, which refuses.
        builtin = self._builtins.get(name)
        return dict(builtin) if builtin else None

    def _require(self, name: str) -> dict:
        record = self._record(name)
        if record is None:
            raise KeyError(f"Section '{name}' not found")
        return record

    def _require_mutable(self, name: str) -> dict:
        """The stored record to write to. A builtin has none - it is synthesized on read,
        so an edit would be accepted and then vanish at the next call."""
        record = self._require(name)
        if record.get("builtin") is True:
            raise ValueError(f"Collection {name!r} is builtin and cannot be edited")
        return record

    def get_collections_name(self):
        return [r["name"] for r in self.records]

    def schema_version(self) -> int:
        return self._schema

    def has_migrated(self, name: str) -> bool:
        """Whether this file has already been through the named one-time conversion."""
        return name in self._migrations

    def record_migration(self, name: str) -> None:
        """Say it has, so it is not done to the user's file a second time. Written by
        the next `save`, which is what makes it survive a restart."""
        if name not in self._migrations:
            self._migrations.append(name)

    def _stamp_schema(self, version: int = COLLECTIONS_SCHEMA) -> None:
        self._schema = version

    def is_filter_based(self, section: str):
        record = self._record(section)
        return bool(record) and record.get("type") == "filter"

    def get_filters(self, section: str):
        if not self.is_filter_based(section):
            return None
        stored = self._require(section).get("filters") or {}
        # Defaults underneath, the file on top: the defaults are the nine criteria an ini
        # could hold, and an axis added since - `played` is the first - is only in the file.
        return {**_FILTER_DEFAULTS, **stored}

    def set_view_filters(self, criteria: dict | None) -> None:
        """Constrain `builtin:all` by criteria that are stored nowhere - the frontend's
        filter controls, which make a collection out of the library rather than narrowing
        the one on screen. Around `_require_mutable` on purpose: there is no record to
        write to, and this lasts as long as the store object."""
        self._builtins[BUILTIN_ALL]["filters"] = dict(criteria or {})

    def get_order(self, section: str) -> dict:
        """How to order this collection: {"by": ..., "direction": "asc"|"desc"}.

        Falls back to the sort a filter collection stored beside its criteria, and then
        to title. Never falls back to `manual` - see ORDER_KEY.
        """
        record = self._require(section)
        stored = record.get(ORDER_KEY)
        if isinstance(stored, dict) and str(stored.get(ORDER_BY_KEY, "") or "").strip():
            by = str(stored[ORDER_BY_KEY]).strip()
            direction = str(stored.get(ORDER_DIRECTION_KEY, "") or DEFAULT_DIRECTION)
        else:
            criteria = record.get("filters") or {}
            raw = str(criteria.get("sort_by", "") or "").strip()
            by = ORDER_ALIASES.get(raw, raw) or DEFAULT_ORDER_BY
            direction = str(criteria.get("order_by", "") or DEFAULT_DIRECTION)
        return {ORDER_BY_KEY: by,
                ORDER_DIRECTION_KEY: "desc" if direction.lower().startswith("desc")
                                     else "asc"}

    def set_order(self, section: str, by: str, direction: str = DEFAULT_DIRECTION) -> None:
        """Record how this collection is ordered. `manual` means the member array."""
        self._require_mutable(section)[ORDER_KEY] = {
            ORDER_BY_KEY: by,
            ORDER_DIRECTION_KEY: "desc" if str(direction).lower().startswith("desc")
                                 else "asc"}

    def get_limit(self, section: str) -> int | None:
        """How many rows this collection keeps, or None for all of them."""
        raw = self._require(section).get(LIMIT_KEY)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def set_limit(self, section: str, limit: int | None) -> None:
        """Cap this collection, or lift the cap with None.

        Refused on a builtin: a limit on the whole library hides most of it with nothing
        on screen to say why, and `builtin:all` is what everything else falls back to.
        """
        record = self._require_mutable(section)
        if limit is None:
            record.pop(LIMIT_KEY, None)
            return
        value = int(limit)
        if value <= 0:
            raise ValueError("A limit must be a positive number of rows")
        record[LIMIT_KEY] = value

    def get_excluded_refs(self, section: str) -> list[dict]:
        """What this collection removes, whatever put it there. Applied after members
        and filters, so it overrules both."""
        return [dict(ref) for ref in _member_refs(self._require(section).get(EXCLUDED_KEY))]

    def exclude(self, section: str, game_id: str, table_id: str = "") -> None:
        """Remove a game, or one of its tables, from this collection."""
        record = self._require_mutable(section)
        excluded = _member_refs(record.get(EXCLUDED_KEY))
        ref = _member_ref({MEMBER_GAME_KEY: game_id, MEMBER_TABLE_KEY: table_id})
        if ref and ref not in excluded:
            excluded.append(ref)
        record[EXCLUDED_KEY] = excluded

    def unexclude(self, section: str, game_id: str, table_id: str = "") -> None:
        """Undo an exclusion. Without a table, drops every exclusion naming this game -
        including the per-table ones, since the game is wanted back whole."""
        record = self._require_mutable(section)
        excluded = _member_refs(record.get(EXCLUDED_KEY))
        if table_id:
            keep = [e for e in excluded
                    if not (e[MEMBER_GAME_KEY] == game_id
                            and e.get(MEMBER_TABLE_KEY) == table_id)]
        else:
            keep = [e for e in excluded if e[MEMBER_GAME_KEY] != game_id]
        if keep:
            record[EXCLUDED_KEY] = keep
        else:
            # Nothing left to say; an empty list in every record is noise in the file.
            record.pop(EXCLUDED_KEY, None)

    def get_member_refs(self, section: str) -> list[dict]:
        """Membership as stored: an ordered list of refs, each naming a game and
        optionally one of its tables. This is the list the resolver walks."""
        return [dict(ref) for ref in _member_refs(self._require(section).get("members"))]

    def unknown_filter_axes(self, section: str) -> list[str]:
        """Criteria in this collection that this build cannot resolve.

        Non-empty means refuse the collection rather than resolve what is left: skipping
        a constraint answers a different question and does it silently. Every other
        collection in the file is unaffected, which is what lets an axis be added
        without a schema bump.
        """
        record = self._record(section)
        if not record:
            return []
        return collection_filters.unknown_axes(record.get("filters"))

    def get_members(self, section: str):
        """The game ids a collection contains, in order and de-duplicated.

        The same game can appear more than once - two tables of it, at two positions -
        so this is not the same length as the stored list. Callers that need to know
        which table want get_member_refs().
        """
        seen = []
        for ref in _member_refs(self._require(section).get("members")):
            if ref[MEMBER_GAME_KEY] not in seen:
                seen.append(ref[MEMBER_GAME_KEY])
        return seen

    def get_all(self):
        return {name: self.get_members(name) for name in self.get_collections_name()}

    def add_collection(self, section: str, members=None):
        """Add a collection whose membership is an explicit list of games."""
        if self._record(section) is not None:
            raise ValueError(f"Section '{section}' already exists")
        self.records.append({"name": section, "type": "manual",
                             "image": "", "members": list(members or [])})

    def add_filter_collection(
        self,
        section: str,
        letter="All",
        theme="All",
        game_type="All",
        manufacturer="All",
        year="All",
        rating="All",
        rating_or_higher="false",
        sort_by="Alpha",
        order_by="Descending",
        played=None,
    ):
        """Add a filter-based collection."""
        if self._record(section) is not None:
            raise ValueError(f"Section '{section}' already exists")
        criteria = {
            "letter": letter, "theme": theme, "table_type": game_type,
            "manufacturer": manufacturer, "year": year, "rating": rating,
            "rating_or_higher": rating_or_higher, "sort_by": sort_by,
            "order_by": order_by or "Descending",
        }
        # Only when asked for. Written as false it would read as "never played" rather
        # than as saying nothing about play at all.
        if played is not None:
            criteria["played"] = bool(played)
        self.records.append({"name": section, "type": "filter", "image": "",
                             "filters": criteria})

    def make_filter_collection(self, section: str, filters: dict,
                               order: dict | None = None,
                               limit: int | None = None) -> None:
        """Turn a collection into one that filters, keeping its name, icon and position.

        Hand-picked membership goes with it: a named game overrides the criteria, so
        one left behind would stay in the collection whatever the filter selects.
        """
        record = self._require_mutable(section)
        record["type"] = "filter"
        record["filters"] = dict(filters)
        record.pop("members", None)
        if order:
            self.set_order(section, order.get(ORDER_BY_KEY, DEFAULT_ORDER_BY),
                           order.get(ORDER_DIRECTION_KEY, DEFAULT_DIRECTION))
        self.set_limit(section, limit)

    def delete_collection(self, section: str):
        self.records.remove(self._require_mutable(section))

    def rename_collection(self, old_name: str, new_name: str):
        record = self._require_mutable(old_name)
        if self._record(new_name) is not None:
            raise ValueError(f"Section '{new_name}' already exists")
        if not new_name.strip():
            raise ValueError("New name cannot be empty")
        record["name"] = new_name

    def add_member(self, section: str, member_id: str, table_id: str = ""):
        """Add a game, or one specific table of it. Adding the same pairing twice is
        a no-op; adding a second table of a game already present is not."""
        record = self._require_mutable(section)
        members = _member_refs(record.get("members"))
        ref = _member_ref({MEMBER_GAME_KEY: member_id, MEMBER_TABLE_KEY: table_id})
        if ref and ref not in members:
            members.append(ref)
        record["members"] = members

    def remove_member(self, section: str, member_id: str, table_id: str = ""):
        """Remove a pairing, or every ref naming this game when no table is given."""
        record = self._require_mutable(section)
        members = _member_refs(record.get("members"))
        if table_id:
            keep = [m for m in members
                    if not (m[MEMBER_GAME_KEY] == member_id
                            and m.get(MEMBER_TABLE_KEY) == table_id)]
        else:
            keep = [m for m in members if m[MEMBER_GAME_KEY] != member_id]
        if len(keep) == len(members):
            raise ValueError(f"'{member_id}' is not in collection '{section}'")
        record["members"] = keep

    def set_members(self, section: str, members) -> None:
        """Replace the membership outright, taking game ids or refs. For a caller where
        the order is the point, which is the Manager UI saving a whole edit.

        A caller passing bare ids is naming games rather than tables, so a table this
        collection had named is gone. That is the right meaning for an editor that can
        only show games, but it is not something to lose quietly.
        """
        record = self._require_mutable(section)
        replacement = _member_refs(members)
        named = {m[MEMBER_GAME_KEY] for m in _member_refs(record.get("members"))
                 if MEMBER_TABLE_KEY in m}
        lost = named - {m[MEMBER_GAME_KEY] for m in replacement if MEMBER_TABLE_KEY in m}
        if lost:
            logger.warning(
                "Collection %r: replacing membership dropped the table named for %s; "
                "those games contribute their default table now",
                section, ", ".join(sorted(lost)))
        record["members"] = replacement

    def __contains__(self, section: str) -> bool:
        return self._record(section) is not None

    def get_image(self, section: str) -> str:
        record = self._record(section)
        return str((record or {}).get(COLLECTION_IMAGE_KEY, "") or "").strip()

    def set_image(self, section: str, filename: str | None) -> None:
        """Set the collection's icon, or clear it when given nothing."""
        record = self._require_mutable(section)
        if filename:
            record[COLLECTION_IMAGE_KEY] = filename
        else:
            record.pop(COLLECTION_IMAGE_KEY, None)

    def set_filter(self, section: str, key: str, value) -> None:
        """One criterion on a filter collection."""
        self._require_mutable(section).setdefault("filters", {})[key] = value

    def migrate_membership_to_game_ids(self, games) -> int:
        """Move VPS-keyed membership onto game ids. Returns how many entries moved.

        Runs once: the file records that it has been through this, so later startups
        do not rescan. A file written by a newer VPinFE is left alone - an older
        build of VPinFE must not rewrite membership it does not understand.

        Entries that resolve to a game are rewritten; entries that do not are kept
        as they are, because the game may simply not be present right now and
        dropping it would lose that membership for good. The file converges as
        tables are seen.
        """
        version = self.schema_version()
        if version >= COLLECTIONS_SCHEMA:
            if version > COLLECTIONS_SCHEMA and version not in _warned_newer_schema:
                _warned_newer_schema.add(version)
                logger.warning(
                    "collections.ini uses schema %s, newer than this build's %s. "
                    "Leaving membership untouched.", version, COLLECTIONS_SCHEMA)
            return 0

        names = self.get_collections_name()
        if not names:
            return 0

        # Which collection, and which ids. The count alone said 19 members had not
        # resolved and gave no way to find them - and the UI renders an unresolved
        # member as raw hex, so the file is the only place to look.
        unresolved_by_collection: dict[str, list[str]] = {}

        by_vps: dict[str, str] = {}
        for game in games:
            tid = game_id(game)
            if not tid:
                continue
            vpinfe = vpinfe_section(getattr(game, "meta_config", {}))
            for candidate in (base_game_vps_id(game),
                              str(vpinfe.get("alt_vpsid", "") or "").strip()):
                if candidate:
                    by_vps.setdefault(candidate, tid)

        known_ids = set(by_vps.values())
        moved = unresolved = 0
        for name in names:
            if self.is_filter_based(name):
                continue
            members = self.get_members(name)
            rewritten = []
            for member in members:
                if member in known_ids:
                    rewritten.append(member)
                elif member in by_vps:
                    rewritten.append(by_vps[member])
                    moved += 1
                else:
                    rewritten.append(member)
                    unresolved += 1
                    unresolved_by_collection.setdefault(name, []).append(member)
            if rewritten != members:
                self._require(name)["members"] = rewritten

        self._stamp_schema()
        self.save()
        logger.info("Collection membership moved onto game ids: %s moved, %s left "
                    "as VPS ids because no game matched", moved, unresolved)
        for name, ids in sorted(unresolved_by_collection.items()):
            # Not an error: the game may simply not be present right now, and the file
            # converges as tables are seen. But a member nothing matches shows in the UI
            # as raw hex, so say where it is rather than leaving it to be found.
            logger.warning("Collection %r keeps %s member(s) no game matched: %s",
                           name, len(ids), ", ".join(sorted(ids)[:10])
                           + (", ..." if len(ids) > 10 else ""))
        return moved

    @contextlib.contextmanager
    def mutate(self):
        """Read the file, change it, write it back, with no other writer in between.

        `write_atomic` already stops a reader seeing half a file. What it cannot stop is
        the edit made against a copy that went stale while it was being made: the theme's
        collection menu and the API write the same file through different stores, and
        without this the second `save` drops the first one's collection and reports
        success. Reloading inside the lock is what makes the copy current.

        Raising inside the block writes nothing, which is what lets a caller validate
        against the just-reloaded file and refuse.
        """
        with _write_lock:
            self.reload()
            yield self
            self.save()

    def save(self):
        """Write collections back to disk, atomically.

        Prefer `mutate` for a read-modify-write; calling this alone writes whatever this
        store last read, which may no longer be what is on disk.

        The first save after reading an ini keeps a copy of it and leaves the original
        in place: a user who goes back to 2.x needs the file 2.x reads.
        """
        with _write_lock:
            if self._converted_from_ini and self.ini_path.exists():
                logger.info("Kept the pre-JSON collections at %s",
                            copy_aside(str(self.ini_path)))
                self._converted_from_ini = False
            # Never stamp a newer file down to what this build writes. A newer VPinFE
            # owns that number, and claiming it would tell the next reader we understood
            # the file.
            payload = {SCHEMA_KEY: max(self._schema, COLLECTIONS_SCHEMA),
                       COLLECTIONS_KEY: self.records}
            if self._migrations:
                payload[MIGRATIONS_KEY] = self._migrations
            write_atomic(self.path,
                         lambda handle: json.dump(payload, handle, indent=2,
                                                  ensure_ascii=False))
        # Same reason game_repository announces a refreshed game: a wheel showing a
        # collection is showing this file, and nothing else would tell it.
        events.emit(events.COLLECTIONS_CHANGED, path=str(self.path))

    # ------------------------------------------------------------------
    # NEW JSON METADATA AWARE FILTERING
    # ------------------------------------------------------------------

    def is_member(self, game, member_ids) -> bool:
        """Whether a game belongs to a collection whose membership is `member_ids`.

        Membership is the game's own id. VPS ids are still accepted because a file
        written before the migration, or an entry for a game that was not present
        when it ran, still holds one - and because a game with no VPSdb match has
        no VPS id at all, which is one of the reasons membership moved off it.
        """
        if game_id(game) and game_id(game) in member_ids:
            return True

        vpinfe = vpinfe_section(getattr(game, "meta_config", {}))
        base_vpsid = base_game_vps_id(game)
        alt_vpsid = str(vpinfe.get("alt_vpsid", "") or "").strip()
        return bool(
            (base_vpsid and base_vpsid in member_ids)
            or (alt_vpsid and alt_vpsid in member_ids)
        )


COLLECTIONS_NAME = "collections.json"
COLLECTIONS_NAME_INI = "collections.ini"


def collections_schema(path) -> int | None:
    """The schema a saved collections file declares, or None if it predates versioning.

    Reads either format, because backups of both exist: a restore has to be able to
    look at a `collections.ini` copy written before the move to JSON.
    """
    path = Path(path)
    if COLLECTIONS_NAME_INI in path.name:
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        return _ini_schema(parser) or None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return int(data.get(SCHEMA_KEY, 0) or 0) or None if isinstance(data, dict) else None


def restorable_collections_backup(config_dir, max_schema: int = COLLECTIONS_SCHEMA) -> str | None:
    """The saved collections file this build would put back, or None.

    Newest readable wins, same as a .info. A copy written by a newer build is stepped over.
    """
    config_dir = Path(config_dir)
    try:
        names = os.listdir(config_dir)
    except OSError:
        return None
    candidates = backup_names(names, COLLECTIONS_NAME) + backup_names(names, COLLECTIONS_NAME_INI)
    for name in sorted(candidates, reverse=True):
        candidate = config_dir / name
        try:
            schema = collections_schema(candidate)
        except (OSError, ValueError):
            logger.warning("Unreadable collections backup, skipping: %s", candidate)
            continue
        if schema is None or schema <= max_schema:
            return str(candidate)
    return None
