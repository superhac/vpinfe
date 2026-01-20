# vpxcollections.py
import configparser
from pathlib import Path


class VPXCollections:
    def __init__(self, ini_path: str):
        """Load and parse the collections ini file."""
        self.ini_path = Path(ini_path)
        self.config = configparser.ConfigParser()

        if self.ini_path.exists():
            self.config.read(self.ini_path)
            print("Found collections file...")

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
            "sort_by": sec.get("sort_by", "Alpha"),
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
        sort_by="Alpha",
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
        sec["sort_by"] = sort_by

    def delete_collection(self, section: str):
        """Delete a collection."""
        if not self.config.remove_section(section):
            raise KeyError(f"Section '{section}' not found")

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
        VPSId lives at metaConfig["Info"]["VPSId"]
        """
        filter_ids = set(self.get_vpsids(collection))
        result = []

        for table in tables:
            meta = table.metaConfig or {}
            info = meta.get("Info", {})
            vpsid = info.get("VPSId")

            if vpsid and vpsid in filter_ids:
                result.append(table)

        # Sort alphabetically by display title
        result.sort(
            key=lambda t: (
                (t.metaConfig or {})
                .get("Info", {})
                .get("Title", "")
                .lower()
            )
        )

        return result
