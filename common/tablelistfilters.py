from common.table_metadata import (
    get_meta_value,
    is_truthy,
    normalize_rating,
    table_manufacturer,
    table_rating,
    table_themes,
    table_title,
    table_type,
    table_year,
)


class TableListFilters:
    """Filter tables by various criteria: starting letter, theme, type, and rating."""

    def __init__(self, tables=None):
        self.tables = list(tables or [])

    @staticmethod
    def _get_meta_value(table, section, key, fallback=""):
        """Helper to safely extract metadata values."""
        return get_meta_value(getattr(table, "metaConfig", {}), section, key, fallback)

    def get_available_letters(self):
        """Return sorted list of unique starting letters from table names."""
        letters = set()
        for table in self.tables:
            # Try Info.Title first (JSON format), then VPSdb.name (legacy)
            name = table_title(table)
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
            themes.update(table_themes(table))
        return sorted(themes)

    def get_available_types(self):
        """Return sorted list of unique table types."""
        types = set()
        for table in self.tables:
            current_type = table_type(table)
            if current_type:
                types.add(current_type)
        return sorted(types)

    def get_available_manufacturers(self):
        """Return sorted list of unique manufacturers."""
        manufacturers = set()
        for table in self.tables:
            manufacturer = table_manufacturer(table)
            if manufacturer:
                manufacturers.add(manufacturer)
        return sorted(manufacturers)

    def get_available_years(self):
        """Return sorted list of unique years."""
        years = set()
        for table in self.tables:
            year = table_year(table)
            if year:
                years.add(str(year))
        return sorted(years)

    def _get_table_name(self, table):
        """Get table name from either JSON or legacy format."""
        return table_title(table)

    def _get_table_theme(self, table):
        """Get table theme(s) from either JSON or legacy format."""
        return table_themes(table)

    def _get_table_type(self, table):
        """Get table type from either JSON or legacy format."""
        return table_type(table)

    def _get_table_manufacturer(self, table):
        """Get table manufacturer from either JSON or legacy format."""
        return table_manufacturer(table)

    def _get_table_year(self, table):
        """Get table year from either JSON or legacy format."""
        return table_year(table)

    @staticmethod
    def _normalize_rating(value):
        """Normalize rating values to an integer in the range 0..5."""
        return normalize_rating(value)

    @staticmethod
    def _is_truthy(value):
        """Convert common string/bool truthy values to bool."""
        return is_truthy(value)

    def _get_table_rating(self, table):
        """Get table rating from User.Rating metadata."""
        return table_rating(table)

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

    def filter_by_rating(self, tables, rating, rating_or_higher=False):
        """Filter tables by rating. Supports comma-separated values and optional 'or higher' mode."""
        if not rating or rating == "All":
            return tables

        selected_ratings = []
        for r in str(rating).split(','):
            try:
                selected_ratings.append(self._normalize_rating(r.strip()))
            except Exception:
                continue

        if not selected_ratings:
            return tables

        if self._is_truthy(rating_or_higher):
            min_rating = min(selected_ratings)
            return [table for table in tables if self._get_table_rating(table) >= min_rating]

        rating_set = set(selected_ratings)
        return [table for table in tables if self._get_table_rating(table) in rating_set]

    def apply_filters(self, letter=None, theme=None, table_type=None, manufacturer=None, year=None, rating=None, rating_or_higher=False):
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

        if rating and rating != "All":
            result = self.filter_by_rating(result, rating, rating_or_higher)

        # Sort alphabetically by name
        result.sort(
            key=lambda t: self._get_table_name(t).lower()
        )

        return result
