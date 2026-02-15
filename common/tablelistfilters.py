import ast
from typing import List, Optional


class TableListFilters:
    """Filter tables by various criteria: starting letter, theme, and type.

    Singleton pattern - shares cached filter data across all instances.
    """

    # Singleton instance
    _instance: Optional['TableListFilters'] = None
    _tables: list = []

    def __new__(cls, tables=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        if tables is not None:
            cls._tables = tables
        return cls._instance

    def __init__(self, tables=None):
        """Initialize with a list of tables (updates shared tables if provided)."""
        if tables is not None:
            TableListFilters._tables = tables

    @property
    def tables(self):
        return TableListFilters._tables

    @tables.setter
    def tables(self, value):
        TableListFilters._tables = value

    def _get_meta_value(self, table, section, key, fallback=""):
        """Helper to safely extract metadata values."""
        meta = table.metaConfig
        cfg = meta.config if hasattr(meta, "config") else meta

        # Handle both dicts and objects that might mimic configparser
        if isinstance(cfg, dict):
            section_dict = cfg.get(section, {})
            return section_dict.get(key, fallback)
        else:
            # fallback for objects that behave like configparser
            try:
                return cfg.get(section, key)
            except Exception:
                return fallback

    def get_available_letters(self):
        """Return sorted list of unique starting letters from table names."""
        letters = set()
        for table in self.tables:
            # Try Info.Title first (JSON format), then VPSdb.name (legacy)
            name = self._get_meta_value(table, "Info", "Title", fallback="")
            if not name:
                name = self._get_meta_value(table, "VPSdb", "name", fallback="")
            if name:
                first_char = name[0].upper()
                # Only include alphanumeric characters
                if first_char.isalnum():
                    letters.add(first_char)
        return sorted(letters)

    def get_available_themes(self):
        """Return sorted list of unique themes from all tables."""
        themes = set()
        for table in self.tables:
            # Try Info.Themes first (JSON format - already a list), then VPSdb.theme (legacy string)
            theme_val = self._get_meta_value(table, "Info", "Themes", fallback=None)
            if theme_val:
                if isinstance(theme_val, list):
                    themes.update(theme_val)
                else:
                    themes.add(theme_val)
            else:
                # Legacy format
                theme_str = self._get_meta_value(table, "VPSdb", "theme", fallback="")
                if theme_str:
                    try:
                        # Parse the string representation of list
                        theme_list = ast.literal_eval(theme_str)
                        if isinstance(theme_list, list):
                            themes.update(theme_list)
                    except (ValueError, SyntaxError):
                        # If it's not a list format, treat as single theme
                        themes.add(theme_str)
        return sorted(themes)

    def get_available_types(self):
        """Return sorted list of unique table types."""
        types = set()
        for table in self.tables:
            # Try Info.Type first (JSON format), then VPSdb.type (legacy)
            table_type = self._get_meta_value(table, "Info", "Type", fallback="")
            if not table_type:
                table_type = self._get_meta_value(table, "VPSdb", "type", fallback="")
            if table_type:
                types.add(table_type)
        return sorted(types)

    def get_available_manufacturers(self):
        """Return sorted list of unique manufacturers."""
        manufacturers = set()
        for table in self.tables:
            # Try Info.Manufacturer first (JSON format), then VPSdb.manufacturer (legacy)
            manufacturer = self._get_meta_value(table, "Info", "Manufacturer", fallback="")
            if not manufacturer:
                manufacturer = self._get_meta_value(table, "VPSdb", "manufacturer", fallback="")
            if manufacturer:
                manufacturers.add(manufacturer)
        return sorted(manufacturers)

    def get_available_years(self):
        """Return sorted list of unique years."""
        years = set()
        for table in self.tables:
            # Try Info.Year first (JSON format), then VPSdb.year (legacy)
            year = self._get_meta_value(table, "Info", "Year", fallback="")
            if not year:
                year = self._get_meta_value(table, "VPSdb", "year", fallback="")
            if year:
                years.add(str(year))
        return sorted(years)

    def _get_table_name(self, table):
        """Get table name from either JSON or legacy format."""
        name = self._get_meta_value(table, "Info", "Title", fallback="")
        if not name:
            name = self._get_meta_value(table, "VPSdb", "name", fallback="")
        return name

    def _get_table_theme(self, table):
        """Get table theme(s) from either JSON or legacy format."""
        theme_val = self._get_meta_value(table, "Info", "Themes", fallback=None)
        if theme_val:
            return theme_val if isinstance(theme_val, list) else [theme_val]
        # Legacy format
        theme_str = self._get_meta_value(table, "VPSdb", "theme", fallback="")
        if theme_str:
            try:
                theme_list = ast.literal_eval(theme_str)
                if isinstance(theme_list, list):
                    return theme_list
            except (ValueError, SyntaxError):
                pass
            return [theme_str]
        return []

    def _get_table_type(self, table):
        """Get table type from either JSON or legacy format."""
        table_type = self._get_meta_value(table, "Info", "Type", fallback="")
        if not table_type:
            table_type = self._get_meta_value(table, "VPSdb", "type", fallback="")
        return table_type

    def _get_table_manufacturer(self, table):
        """Get table manufacturer from either JSON or legacy format."""
        mfr = self._get_meta_value(table, "Info", "Manufacturer", fallback="")
        if not mfr:
            mfr = self._get_meta_value(table, "VPSdb", "manufacturer", fallback="")
        return mfr

    def _get_table_year(self, table):
        """Get table year from either JSON or legacy format."""
        year = self._get_meta_value(table, "Info", "Year", fallback="")
        if not year:
            year = self._get_meta_value(table, "VPSdb", "year", fallback="")
        return str(year) if year else ""

    def filter_by_letter(self, tables, letter):
        """Filter tables by starting letter of name. Supports comma-separated values."""
        if not letter or letter == "All":
            return tables

        letters = {l.strip().upper() for l in str(letter).split(',')}
        filtered = []
        for table in tables:
            name = self._get_table_name(table)
            if name and name[0].upper() in letters:
                filtered.append(table)
        return filtered

    def filter_by_theme(self, tables, theme):
        """Filter tables by theme. Supports comma-separated values."""
        if not theme or theme == "All":
            return tables

        themes = {t.strip() for t in str(theme).split(',')}
        filtered = []
        for table in tables:
            table_themes = self._get_table_theme(table)
            if themes & set(table_themes):
                filtered.append(table)
        return filtered

    def filter_by_type(self, tables, table_type):
        """Filter tables by type (EM, SS, etc.). Supports comma-separated values."""
        if not table_type or table_type == "All":
            return tables

        types = {t.strip() for t in str(table_type).split(',')}
        filtered = []
        for table in tables:
            current_type = self._get_table_type(table)
            if current_type in types:
                filtered.append(table)
        return filtered

    def filter_by_manufacturer(self, tables, manufacturer):
        """Filter tables by manufacturer. Supports comma-separated values."""
        if not manufacturer or manufacturer == "All":
            return tables

        manufacturers = {m.strip() for m in str(manufacturer).split(',')}
        filtered = []
        for table in tables:
            current_manufacturer = self._get_table_manufacturer(table)
            if current_manufacturer in manufacturers:
                filtered.append(table)
        return filtered

    def filter_by_year(self, tables, year):
        """Filter tables by year. Supports comma-separated values."""
        if not year or year == "All":
            return tables

        years = {y.strip() for y in str(year).split(',')}
        filtered = []
        for table in tables:
            current_year = self._get_table_year(table)
            if current_year in years:
                filtered.append(table)
        return filtered

    def apply_filters(self, letter=None, theme=None, table_type=None, manufacturer=None, year=None):
        """
        Apply multiple filters in combination.
        Returns filtered and sorted list of tables.
        """
        result = list(self.tables)  # Make a copy to avoid modifying original

        # Apply each filter sequentially
        if letter and letter != "All":
            result = self.filter_by_letter(result, letter)

        if theme and theme != "All":
            result = self.filter_by_theme(result, theme)

        if table_type and table_type != "All":
            result = self.filter_by_type(result, table_type)

        if manufacturer and manufacturer != "All":
            result = self.filter_by_manufacturer(result, manufacturer)

        if year and year != "All":
            result = self.filter_by_year(result, year)

        # Sort alphabetically by name
        result.sort(
            key=lambda t: self._get_table_name(t).lower()
        )

        return result
