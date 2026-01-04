# collections.py
import configparser
from pathlib import Path

class VPXCollections:
    def __init__(self, ini_path: str):
        """Load and parse the ini file."""
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
        """Return a list of section names."""
        return self.config.sections()

    def is_filter_based(self, section: str):
        """Check if a collection is filter-based (vs VPS ID-based)."""
        if section not in self.config:
            return False
        return self.config[section].get("type", "vpsid") == "filter"

    def get_filters(self, section: str):
        """
        Get filter parameters for a filter-based collection.
        Returns dict with keys: letter, theme, table_type, manufacturer, year, sort_by
        Returns None if not a filter-based collection.
        """
        if not self.is_filter_based(section):
            return None

        return {
            'letter': self.config[section].get("letter", "All"),
            'theme': self.config[section].get("theme", "All"),
            'table_type': self.config[section].get("table_type", "All"),
            'manufacturer': self.config[section].get("manufacturer", "All"),
            'year': self.config[section].get("year", "All"),
            'sort_by': self.config[section].get("sort_by", "Alpha")
        }

    def get_vpsids(self, section: str):
        """Return list of vpsids for a given section."""
        if section not in self.config:
            raise KeyError(f"Section '{section}' not found")
        raw_value = self.config[section].get("vpsids", "")
        return [v.strip() for v in raw_value.split(",") if v.strip()]

    def get_all(self):
        """Return dict of section -> list of vpsids."""
        return {s: self.get_vpsids(s) for s in self.get_collections_name()}

    def add_collection(self, section: str, vpsids=None):
        """Add a new VPS ID-based collection (section)."""
        if self.config.has_section(section):
            raise ValueError(f"Section '{section}' already exists")
        self.config.add_section(section)
        self.config[section]["type"] = "vpsid"
        if vpsids:
            self.config[section]["vpsids"] = ",".join(vpsids)
        else:
            self.config[section]["vpsids"] = ""

    def add_filter_collection(self, section: str, letter="All", theme="All", table_type="All", manufacturer="All", year="All", sort_by="Alpha"):
        """Add a new filter-based collection."""
        if self.config.has_section(section):
            raise ValueError(f"Section '{section}' already exists")
        self.config.add_section(section)
        self.config[section]["type"] = "filter"
        self.config[section]["letter"] = letter
        self.config[section]["theme"] = theme
        self.config[section]["table_type"] = table_type
        self.config[section]["manufacturer"] = manufacturer
        self.config[section]["year"] = year
        self.config[section]["sort_by"] = sort_by

    def delete_collection(self, section: str):
        """Delete a collection (section)."""
        if not self.config.remove_section(section):
            raise KeyError(f"Section '{section}' not found")

    def add_vpsid(self, section: str, vpsid: str):
        """Add a vpsid to a section (ignores duplicates)."""
        vpsids = set(self.get_vpsids(section))
        vpsids.add(vpsid.strip())
        self.config[section]["vpsids"] = ",".join(sorted(vpsids))

    def remove_vpsid(self, section: str, vpsid: str):
        """Remove a vpsid from a section."""
        vpsids = self.get_vpsids(section)
        if vpsid not in vpsids:
            raise ValueError(f"vpsid '{vpsid}' not found in section '{section}'")
        vpsids.remove(vpsid)
        self.config[section]["vpsids"] = ",".join(vpsids)

    def save(self):
        """Write current state back to file."""
        with self.ini_path.open("w") as f:
            self.config.write(f)
            
    def filter_tables(self, tables, collection):
        filterList = []
        filterIDs = self.get_vpsids(collection)

        for fid in filterIDs:
            for table in tables:
                meta = table.metaConfig
                # handle both MetaConfig and plain ConfigParser
                cfg = meta.config if hasattr(meta, "config") else meta
                if cfg.get("VPSdb", "id", fallback="none") == fid:
                    filterList.append(table)

        # Sort alphabetically by VPSdb.name, handling both types
        filterList.sort(
            key=lambda t: (
                (t.metaConfig.config if hasattr(t.metaConfig, "config") else t.metaConfig)
                .get("VPSdb", "name", fallback="")
                .lower()
            )
        )

        return filterList


    