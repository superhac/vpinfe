# vpxcollections.py
import configparser
import logging
from pathlib import Path

from common.table_metadata import base_table_vps_id, section, table_title

logger = logging.getLogger("vpinfe.common.vpxcollections")


def _get_display_title(table):
    return table_title(table)


def _get_last_run_value(table):
    user = section(getattr(table, "metaConfig", {}), "User")
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
        return self.config.sections()

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

    def get_vpsids(self, section: str):
        """Return list of VPSIds for a given collection."""
        if section not in self.config:
            raise KeyError(f"Section '{section}' not found")

        raw = self.config[section].get("vpsids", "")
        return [v.strip() for v in raw.split(",") if v.strip()]

    def get_all(self):
        """Return dict of section -> list of VPSIds."""
        return {s: self.get_vpsids(s) for s in self.get_collections_name()}

    def add_collection(self, section: str, vpsids=None):
        """Add a VPSId-based collection."""
        if self.config.has_section(section):
            raise ValueError(f"Section '{section}' already exists")

        self.config.add_section(section)
        self.config[section]["type"] = "vpsid"
        self.config[section]["vpsids"] = ",".join(vpsids) if vpsids else ""

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

    def add_vpsid(self, section: str, vpsid: str):
        """Add a VPSId to a collection."""
        vpsids = set(self.get_vpsids(section))
        vpsids.add(vpsid.strip())
        self.config[section]["vpsids"] = ",".join(sorted(vpsids))

    def remove_vpsid(self, section: str, vpsid: str):
        """Remove a VPSId from a collection."""
        vpsids = self.get_vpsids(section)
        if vpsid not in vpsids:
            raise ValueError(f"VPSId '{vpsid}' not found in section '{section}'")

        vpsids.remove(vpsid)
        self.config[section]["vpsids"] = ",".join(vpsids)

    def save(self):
        """Write collections back to disk."""
        with self.ini_path.open("w") as f:
            self.config.write(f)

    # ------------------------------------------------------------------
    # NEW JSON METADATA AWARE FILTERING
    # ------------------------------------------------------------------

    def filter_tables(self, tables, collection):
        """
        Filter tables by VPSId collection.

        Assumes:
        table.metaConfig is a DICT
        Base VPSId lives at metaConfig["Info"]["VPSId"]
        Optional override lives at metaConfig["VPinFE"]["altvpsid"]
        """
        filter_ids = set(self.get_vpsids(collection))
        result = []

        for table in tables:
            vpinfe = section(getattr(table, "metaConfig", {}), "VPinFE")
            base_vpsid = base_table_vps_id(table)
            alt_vpsid = str(vpinfe.get("altvpsid", "") or "").strip()

            # Collections may contain either the base VPS ID or an overridden altvpsid.
            if (
                (base_vpsid and base_vpsid in filter_ids)
                or (alt_vpsid and alt_vpsid in filter_ids)
            ):
                result.append(table)

        if collection == "Last Played":
            # Automatic recents collection should surface the most recently run tables first.
            result.sort(
                key=lambda t: (-_get_last_run_value(t), _get_display_title(t).lower())
            )
        else:
            result.sort(key=lambda t: _get_display_title(t).lower())

        return result
