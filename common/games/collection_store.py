# collection_store.py
import configparser
import json
import logging
import os
from pathlib import Path

from common import events
from common.games import collection_filters
from common.games.game_identity import game_id
from common.games.game_metadata import (
    base_game_vps_id,
    game_title,
    section,
    vpinfe_section,
)
from common.games.info_file import VPINFE_SECTION
from common.games.info_migration import (
    backup_names,
    copy_aside,
    write_atomic,
)

logger = logging.getLogger("vpinfe.common.games.collection_store")

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

# A member names a game, and optionally one of its tables:
#
#   {"game": "tuF3WogthK"}                        follow - every visible table
#   {"game": "tuF3WogthK", "table": "9kRm2QvT8x"} pin - exactly this one, frozen
#
# Two members may name the same game, which is how one game appears twice in a
# curated order with a different table each time. A bare id is read as a follow.
MEMBER_GAME_KEY = "game"
MEMBER_TABLE_KEY = "table"

# Same shape, opposite sign. An excluded ref naming only a game removes the game; one
# naming a table removes that table and leaves the rest of the game alone.
#
# Excluding a table is not the inverse of pinning one. A pin is frozen - a build added
# next month does not appear. An exclusion still follows - it does. Both are wanted,
# and neither substitutes for the other.
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


def _get_display_title(game):
    return game_title(game)


def _get_last_run_value(game):
    user = section(getattr(game, "meta_config", {}), "User")
    raw = user.get("LastRun")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1


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
        self.reload()

    def reload(self):
        """Load from disk, discarding unsaved changes."""
        self.records: list[dict] = []
        self._schema = COLLECTIONS_SCHEMA
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
        return None

    def _require(self, name: str) -> dict:
        record = self._record(name)
        if record is None:
            raise KeyError(f"Section '{name}' not found")
        return record

    def get_collections_name(self):
        return [r["name"] for r in self.records]

    def schema_version(self) -> int:
        return self._schema

    def _stamp_schema(self, version: int = COLLECTIONS_SCHEMA) -> None:
        self._schema = version

    def is_filter_based(self, section: str):
        record = self._record(section)
        return bool(record) and record.get("type") == "filter"

    def get_filters(self, section: str):
        if not self.is_filter_based(section):
            return None
        stored = self._require(section).get("filters") or {}
        return {key: stored.get(key, default) for key, default in _FILTER_DEFAULTS.items()}

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
        self._require(section)[ORDER_KEY] = {
            ORDER_BY_KEY: by,
            ORDER_DIRECTION_KEY: "desc" if str(direction).lower().startswith("desc")
                                 else "asc"}

    def get_excluded_refs(self, section: str) -> list[dict]:
        """What this collection removes, whatever put it there. Applied after members
        and filters, so it overrules both."""
        return [dict(ref) for ref in _member_refs(self._require(section).get(EXCLUDED_KEY))]

    def exclude(self, section: str, game_id: str, table_id: str = "") -> None:
        """Remove a game, or one of its tables, from this collection."""
        record = self._require(section)
        excluded = _member_refs(record.get(EXCLUDED_KEY))
        ref = _member_ref({MEMBER_GAME_KEY: game_id, MEMBER_TABLE_KEY: table_id})
        if ref and ref not in excluded:
            excluded.append(ref)
        record[EXCLUDED_KEY] = excluded

    def unexclude(self, section: str, game_id: str, table_id: str = "") -> None:
        """Undo an exclusion. Without a table, drops every exclusion naming this game -
        including the per-table ones, since the game is wanted back whole."""
        record = self._require(section)
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
    ):
        """Add a filter-based collection."""
        if self._record(section) is not None:
            raise ValueError(f"Section '{section}' already exists")
        self.records.append({
            "name": section, "type": "filter", "image": "",
            "filters": {
                "letter": letter, "theme": theme, "table_type": game_type,
                "manufacturer": manufacturer, "year": year, "rating": rating,
                "rating_or_higher": rating_or_higher, "sort_by": sort_by,
                "order_by": order_by or "Descending",
            },
        })

    def delete_collection(self, section: str):
        self.records.remove(self._require(section))

    def rename_collection(self, old_name: str, new_name: str):
        record = self._require(old_name)
        if self._record(new_name) is not None:
            raise ValueError(f"Section '{new_name}' already exists")
        if not new_name.strip():
            raise ValueError("New name cannot be empty")
        record["name"] = new_name

    def add_member(self, section: str, member_id: str, table_id: str = ""):
        """Add a game, or one specific table of it. Adding the same pairing twice is
        a no-op; adding a second table of a game already present is not."""
        record = self._require(section)
        members = _member_refs(record.get("members"))
        ref = _member_ref({MEMBER_GAME_KEY: member_id, MEMBER_TABLE_KEY: table_id})
        if ref and ref not in members:
            members.append(ref)
        record["members"] = members

    def remove_member(self, section: str, member_id: str, table_id: str = ""):
        """Remove a pairing, or every ref naming this game when no table is given."""
        record = self._require(section)
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
        """Replace the membership outright, taking game ids or refs. For the callers
        where order is the point - Last Played writes most-recent-first, and the
        Manager UI saves a whole edit.

        A caller passing bare ids is saying "these games, following each", so any pin
        this collection held is gone. That is the right meaning for an editor that
        cannot show pins, but it is not something to lose quietly.
        """
        record = self._require(section)
        replacement = _member_refs(members)
        pinned = {m[MEMBER_GAME_KEY] for m in _member_refs(record.get("members"))
                  if MEMBER_TABLE_KEY in m}
        lost = pinned - {m[MEMBER_GAME_KEY] for m in replacement if MEMBER_TABLE_KEY in m}
        if lost:
            logger.warning(
                "Collection %r: replacing membership dropped the table pinned for %s; "
                "those games follow every visible table now",
                section, ", ".join(sorted(lost)))
        record["members"] = replacement

    def __contains__(self, section: str) -> bool:
        return self._record(section) is not None

    def get_image(self, section: str) -> str:
        record = self._record(section)
        return str((record or {}).get(COLLECTION_IMAGE_KEY, "") or "").strip()

    def set_image(self, section: str, filename: str | None) -> None:
        """Set the collection's icon, or clear it when given nothing."""
        record = self._require(section)
        if filename:
            record[COLLECTION_IMAGE_KEY] = filename
        else:
            record.pop(COLLECTION_IMAGE_KEY, None)

    def set_filter(self, section: str, key: str, value) -> None:
        """One criterion on a filter collection."""
        self._require(section).setdefault("filters", {})[key] = value

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

    def save(self):
        """Write collections back to disk, atomically.

        The first save after reading an ini keeps a copy of it and leaves the original
        in place: a user who goes back to 2.x needs the file 2.x reads.
        """
        if self._converted_from_ini and self.ini_path.exists():
            logger.info("Kept the pre-JSON collections at %s",
                        copy_aside(str(self.ini_path)))
            self._converted_from_ini = False
        # Never stamp a newer file down to what this build writes. A newer VPinFE owns
        # that number, and claiming it would tell the next reader we understood the file.
        payload = {SCHEMA_KEY: max(self._schema, COLLECTIONS_SCHEMA),
                   COLLECTIONS_KEY: self.records}
        write_atomic(self.path,
                     lambda handle: json.dump(payload, handle, indent=2, ensure_ascii=False))
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

    def filter_games(self, games, collection):
        """Games belonging to a collection, ordered for display."""
        filter_ids = set(self.get_members(collection))
        result = [t for t in games if self.is_member(t, filter_ids)]

        if collection == "Last Played":
            # Automatic recents collection should surface the most recently run games first.
            result.sort(
                key=lambda t: (-_get_last_run_value(t), _get_display_title(t).lower())
            )
        else:
            result.sort(key=lambda t: _get_display_title(t).lower())

        return result


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
