# tablelistfilters.py
import ast
from typing import List

class TableListFilters:
    """Filter tables by various criteria: starting letter, theme, and type."""

    def __init__(self, tables):
        """Initialize with a list of tables."""
        self.tables = tables

    def _get_meta_value(self, table, section, key, fallback=""):
        """Helper to safely extract metadata values."""
        meta = table.metaConfig
        cfg = meta.config if hasattr(meta, "config") else meta
        return cfg.get(section, key, fallback=fallback)

    def get_available_letters(self):
        """Return sorted list of unique starting letters from table names."""
        letters = set()
        for table in self.tables:
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
            table_type = self._get_meta_value(table, "VPSdb", "type", fallback="")
            if table_type:
                types.add(table_type)
        return sorted(types)

    def get_available_manufacturers(self):
        """Return sorted list of unique manufacturers."""
        manufacturers = set()
        for table in self.tables:
            manufacturer = self._get_meta_value(table, "VPSdb", "manufacturer", fallback="")
            if manufacturer:
                manufacturers.add(manufacturer)
        return sorted(manufacturers)

    def filter_by_letter(self, tables, letter):
        """Filter tables by starting letter of name."""
        if not letter or letter == "All":
            return tables

        filtered = []
        for table in tables:
            name = self._get_meta_value(table, "VPSdb", "name", fallback="")
            if name and name[0].upper() == letter.upper():
                filtered.append(table)
        return filtered

    def filter_by_theme(self, tables, theme):
        """Filter tables by theme."""
        if not theme or theme == "All":
            return tables

        filtered = []
        for table in tables:
            theme_str = self._get_meta_value(table, "VPSdb", "theme", fallback="")
            if theme_str:
                try:
                    theme_list = ast.literal_eval(theme_str)
                    if isinstance(theme_list, list):
                        if theme in theme_list:
                            filtered.append(table)
                    elif theme_str == theme:
                        filtered.append(table)
                except (ValueError, SyntaxError):
                    if theme_str == theme:
                        filtered.append(table)
        return filtered

    def filter_by_type(self, tables, table_type):
        """Filter tables by type (EM, SS, etc.)."""
        if not table_type or table_type == "All":
            return tables

        filtered = []
        for table in tables:
            current_type = self._get_meta_value(table, "VPSdb", "type", fallback="")
            if current_type == table_type:
                filtered.append(table)
        return filtered

    def filter_by_manufacturer(self, tables, manufacturer):
        """Filter tables by manufacturer."""
        if not manufacturer or manufacturer == "All":
            return tables

        filtered = []
        for table in tables:
            current_manufacturer = self._get_meta_value(table, "VPSdb", "manufacturer", fallback="")
            if current_manufacturer == manufacturer:
                filtered.append(table)
        return filtered

    def apply_filters(self, letter=None, theme=None, table_type=None, manufacturer=None):
        """
        Apply multiple filters in combination.
        Returns filtered and sorted list of tables.
        """
        result = self.tables

        # Apply each filter sequentially
        if letter and letter != "All":
            result = self.filter_by_letter(result, letter)

        if theme and theme != "All":
            result = self.filter_by_theme(result, theme)

        if table_type and table_type != "All":
            result = self.filter_by_type(result, table_type)

        if manufacturer and manufacturer != "All":
            result = self.filter_by_manufacturer(result, manufacturer)

        # Sort alphabetically by name
        result.sort(
            key=lambda t: self._get_meta_value(t, "VPSdb", "name", fallback="").lower()
        )

        return result
