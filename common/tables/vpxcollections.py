# vpxcollections.py
import configparser
import logging
import os
from pathlib import Path

from common.tables.info_migration import (
    backup_names,
    copy_aside,
    write_atomic,
)
from common.tables.metaconfig import VPINFE_SECTION
from common.tables.table_identity import table_id
from common.tables.table_metadata import (
    base_game_vps_id,
    game_title,
    section,
    vpinfe_section,
)

logger = logging.getLogger("vpinfe.common.tables.vpxcollections")

# collections.ini is entirely ours, so it carries a version like the VPinFE section
# of a table's .info does. In an ini the sections are collection names, so the
# version lives in a reserved section that is filtered out of the collection list.
SCHEMA_SECTION = VPINFE_SECTION
SCHEMA_KEY = "schema"
#   0  membership keyed by VPS id. Implied when no version is recorded.
#   1  membership keyed by the table's own id (common/table_identity.py).
CURRENT_SCHEMA = 1

# The on-disk key and the non-filter type marker both still say "vpsid". They are
# file format, not meaning - see get_members().
MEMBERS_KEY = "vpsids"

_warned_newer_schema = set()


def _get_display_title(game):
    return game_title(game)


def _get_last_run_value(game):
    user = section(getattr(game, "metaConfig", {}), "User")
    raw = user.get("LastRun")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1


class VPXCollections:
    def __init__(self, ini_path: str):
        """Load and parse the collections ini file."""
        self.ini_path = Path(ini_path)
        self.config = configparser.ConfigParser()

        if self.ini_path.exists():
            self.config.read(self.ini_path)

    def reload(self):
        """Reload the ini file from disk (discard unsaved changes)."""
        self.config = configparser.ConfigParser()
        if self.ini_path.exists():
            self.config.read(self.ini_path)

    def get_collections_name(self):
        """Return a list of collection names."""
        return [s for s in self.config.sections() if s != SCHEMA_SECTION]

    def schema_version(self) -> int:
        if SCHEMA_SECTION not in self.config:
            return 0
        try:
            return int(self.config[SCHEMA_SECTION].get(SCHEMA_KEY, 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _stamp_schema(self, version: int = CURRENT_SCHEMA) -> None:
        if SCHEMA_SECTION not in self.config:
            self.config[SCHEMA_SECTION] = {}
        self.config[SCHEMA_SECTION][SCHEMA_KEY] = str(version)

    def is_filter_based(self, section: str):
        """Check if a collection is filter-based."""
        if section not in self.config:
            return False
        return self.config[section].get("type", "vpsid") == "filter"

    def get_filters(self, section: str):
        """Return filters for a filter-based collection."""
        if not self.is_filter_based(section):
            return None

        sec = self.config[section]
        return {
            "letter": sec.get("letter", "All"),
            "theme": sec.get("theme", "All"),
            "table_type": sec.get("table_type", "All"),
            "manufacturer": sec.get("manufacturer", "All"),
            "year": sec.get("year", "All"),
            "rating": sec.get("rating", "All"),
            "rating_or_higher": sec.get("rating_or_higher", "false"),
            "sort_by": sec.get("sort_by", "Alpha"),
            "order_by": sec.get("order_by", "Descending"),
        }

    def get_members(self, section: str):
        """Return the member ids of a collection.

        The key on disk is still `vpsids` even though the values are table ids now.
        Renaming it would strand every file written before the migration for no gain
        the user can see; the schema version already records which one it holds.
        """
        if section not in self.config:
            raise KeyError(f"Section '{section}' not found")

        raw = self.config[section].get(MEMBERS_KEY, "")
        return [v.strip() for v in raw.split(",") if v.strip()]

    def get_all(self):
        """Return dict of section -> member ids."""
        return {s: self.get_members(s) for s in self.get_collections_name()}

    def add_collection(self, section: str, members=None):
        """Add a collection whose membership is an explicit list of tables."""
        if self.config.has_section(section):
            raise ValueError(f"Section '{section}' already exists")

        self.config.add_section(section)
        self.config[section]["type"] = "vpsid"
        self.config[section][MEMBERS_KEY] = ",".join(members) if members else ""

    def add_filter_collection(
        self,
        section: str,
        letter="All",
        theme="All",
        table_type="All",
        manufacturer="All",
        year="All",
        rating="All",
        rating_or_higher="false",
        sort_by="Alpha",
        order_by="Descending",
    ):
        """Add a filter-based collection."""
        if self.config.has_section(section):
            raise ValueError(f"Section '{section}' already exists")

        self.config.add_section(section)
        sec = self.config[section]
        sec["type"] = "filter"
        sec["letter"] = letter
        sec["theme"] = theme
        sec["table_type"] = table_type
        sec["manufacturer"] = manufacturer
        sec["year"] = year
        sec["rating"] = rating
        sec["rating_or_higher"] = rating_or_higher
        sec["sort_by"] = sort_by
        sec["order_by"] = order_by or "Descending"

    def delete_collection(self, section: str):
        """Delete a collection."""
        if not self.config.remove_section(section):
            raise KeyError(f"Section '{section}' not found")

    def rename_collection(self, old_name: str, new_name: str):
        """Rename a collection."""
        if old_name not in self.config:
            raise KeyError(f"Section '{old_name}' not found")
        if new_name in self.config:
            raise ValueError(f"Section '{new_name}' already exists")
        if not new_name.strip():
            raise ValueError("New name cannot be empty")

        # Copy all items from old section to new section
        self.config.add_section(new_name)
        for key, value in self.config.items(old_name):
            self.config.set(new_name, key, value)

        # Remove old section
        self.config.remove_section(old_name)

    def add_member(self, section: str, member_id: str):
        """Add a table to a collection."""
        members = set(self.get_members(section))
        members.add(member_id.strip())
        self.config[section][MEMBERS_KEY] = ",".join(sorted(members))

    def remove_member(self, section: str, member_id: str):
        """Remove a table from a collection."""
        members = self.get_members(section)
        if member_id not in members:
            raise ValueError(f"'{member_id}' is not in collection '{section}'")

        members.remove(member_id)
        self.config[section][MEMBERS_KEY] = ",".join(members)

    def migrate_membership_to_game_ids(self, tables) -> int:
        """Move VPS-keyed membership onto table ids. Returns how many entries moved.

        Runs once: the file records that it has been through this, so later startups
        do not rescan. A file written by a newer VPinFE is left alone - an older
        build of VPinFE must not rewrite membership it does not understand.

        Entries that resolve to a table are rewritten; entries that do not are kept
        as they are, because the table may simply not be present right now and
        dropping it would lose that membership for good. The file converges as
        tables are seen.
        """
        version = self.schema_version()
        if version >= CURRENT_SCHEMA:
            if version > CURRENT_SCHEMA and version not in _warned_newer_schema:
                _warned_newer_schema.add(version)
                logger.warning(
                    "collections.ini uses schema %s, newer than this build's %s. "
                    "Leaving membership untouched.", version, CURRENT_SCHEMA)
            return 0

        names = self.get_collections_name()
        if not names:
            return 0

        by_vps: dict[str, str] = {}
        for game in tables:
            tid = table_id(game)
            if not tid:
                continue
            vpinfe = vpinfe_section(getattr(game, "metaConfig", {}))
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
            if rewritten != members:
                self.config[name][MEMBERS_KEY] = ",".join(rewritten)

        # Keep what was there before the ids move. This is the other file a newer
        # VPinFE rewrites, and until now it had no copy to go back to.
        if self.ini_path.exists():
            logger.info("Kept the pre-migration collections at %s",
                        copy_aside(str(self.ini_path)))
        self._stamp_schema()
        self.save()
        logger.info("Collection membership moved onto table ids: %s moved, %s left "
                    "as VPS ids because no table matched", moved, unresolved)
        return moved

    def save(self):
        """Write collections back to disk, atomically."""
        write_atomic(self.ini_path, self.config.write)

    # ------------------------------------------------------------------
    # NEW JSON METADATA AWARE FILTERING
    # ------------------------------------------------------------------

    def is_member(self, game, member_ids) -> bool:
        """Whether a table belongs to a collection whose membership is `member_ids`.

        Membership is the table's own id. VPS ids are still accepted because a file
        written before the migration, or an entry for a table that was not present
        when it ran, still holds one - and because a table with no VPSdb match has
        no VPS id at all, which is one of the reasons membership moved off it.
        """
        if table_id(game) and table_id(game) in member_ids:
            return True

        vpinfe = vpinfe_section(getattr(game, "metaConfig", {}))
        base_vpsid = base_game_vps_id(game)
        alt_vpsid = str(vpinfe.get("alt_vpsid", "") or "").strip()
        return bool(
            (base_vpsid and base_vpsid in member_ids)
            or (alt_vpsid and alt_vpsid in member_ids)
        )

    def filter_games(self, tables, collection):
        """Tables belonging to a collection, ordered for display."""
        filter_ids = set(self.get_members(collection))
        result = [t for t in tables if self.is_member(t, filter_ids)]

        if collection == "Last Played":
            # Automatic recents collection should surface the most recently run tables first.
            result.sort(
                key=lambda t: (-_get_last_run_value(t), _get_display_title(t).lower())
            )
        else:
            result.sort(key=lambda t: _get_display_title(t).lower())

        return result


COLLECTIONS_NAME = "collections.ini"


def collections_schema(path) -> int | None:
    """The schema a saved collections file declares, or None if it predates versioning."""
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if SCHEMA_SECTION not in parser:
        return None
    try:
        return int(parser[SCHEMA_SECTION].get(SCHEMA_KEY, 0) or 0) or None
    except (TypeError, ValueError):
        return None


def restorable_collections_backup(config_dir, max_schema: int = CURRENT_SCHEMA) -> str | None:
    """The saved collections file this build would put back, or None.

    Newest readable wins, same as a .info. A copy written by a newer build is stepped over.
    """
    config_dir = Path(config_dir)
    try:
        names = os.listdir(config_dir)
    except OSError:
        return None
    for name in backup_names(names, COLLECTIONS_NAME):
        candidate = config_dir / name
        try:
            schema = collections_schema(candidate)
        except (OSError, ValueError):
            logger.warning("Unreadable collections backup, skipping: %s", candidate)
            continue
        if schema is None or schema <= max_schema:
            return str(candidate)
    return None
