from common.tables.game_metadata import (
    game_manufacturer,
    game_rating,
    game_themes,
    game_title,
    game_year,
    get_meta_value,
    normalize_rating,
    table_type,
)
from common.values import is_truthy


class GameListFilters:
    """Filter tables by various criteria: starting letter, theme, type, and rating."""

    def __init__(self, tables=None):
        self.tables = list(tables or [])

    @staticmethod
    def _get_meta_value(game, section, key, fallback=""):
        """Helper to safely extract metadata values."""
        return get_meta_value(getattr(game, "metaConfig", {}), section, key, fallback)

    def get_available_letters(self):
        """Return sorted list of unique starting letters from table names."""
        letters = set()
        for game in self.tables:
            # Try Info.Title first (JSON format), then VPSdb.name (legacy)
            name = game_title(game)
            if name:
                first_char = name[0].upper()
                # Only include alphanumeric characters
                if first_char.isalnum():
                    letters.add(first_char)
        return sorted(letters)

    def get_available_themes(self):
        """Return sorted list of unique themes from all tables."""
        themes = set()
        for game in self.tables:
            themes.update(game_themes(game))
        return sorted(themes)

    def get_available_types(self):
        """Return sorted list of unique table types."""
        types = set()
        for game in self.tables:
            current_type = table_type(game)
            if current_type:
                types.add(current_type)
        return sorted(types)

    def get_available_manufacturers(self):
        """Return sorted list of unique manufacturers."""
        manufacturers = set()
        for game in self.tables:
            manufacturer = game_manufacturer(game)
            if manufacturer:
                manufacturers.add(manufacturer)
        return sorted(manufacturers)

    def get_available_years(self):
        """Return sorted list of unique years."""
        years = set()
        for game in self.tables:
            year = game_year(game)
            if year:
                years.add(str(year))
        return sorted(years)

    def _get_game_name(self, game):
        """Get table name from either JSON or legacy format."""
        return game_title(game)

    def _get_game_theme(self, game):
        """Get table theme(s) from either JSON or legacy format."""
        return game_themes(game)

    def _get_game_type(self, game):
        """Get table type from either JSON or legacy format."""
        return table_type(game)

    def _get_game_manufacturer(self, game):
        """Get table manufacturer from either JSON or legacy format."""
        return game_manufacturer(game)

    def _get_game_year(self, game):
        """Get table year from either JSON or legacy format."""
        return game_year(game)

    @staticmethod
    def _normalize_rating(value):
        """Normalize rating values to an integer in the range 0..5."""
        return normalize_rating(value)

    def _get_game_rating(self, game):
        """Get table rating from User.Rating metadata."""
        return game_rating(game)

    def filter_by_letter(self, tables, letter):
        """Filter tables by starting letter of name. Supports comma-separated values."""
        if not letter or letter == "All":
            return tables

        letters = {l.strip().upper() for l in str(letter).split(',')}
        filtered = []
        for game in tables:
            name = self._get_game_name(game)
            if name and name[0].upper() in letters:
                filtered.append(game)
        return filtered

    def filter_by_theme(self, tables, theme):
        """Filter tables by theme. Supports comma-separated values."""
        if not theme or theme == "All":
            return tables

        themes = {t.strip() for t in str(theme).split(',')}
        filtered = []
        for game in tables:
            game_themes = self._get_game_theme(game)
            if themes & set(game_themes):
                filtered.append(game)
        return filtered

    def filter_by_type(self, tables, table_type):
        """Filter tables by type (EM, SS, etc.). Supports comma-separated values."""
        if not table_type or table_type == "All":
            return tables

        types = {t.strip() for t in str(table_type).split(',')}
        filtered = []
        for game in tables:
            current_type = self._get_game_type(game)
            if current_type in types:
                filtered.append(game)
        return filtered

    def filter_by_manufacturer(self, tables, manufacturer):
        """Filter tables by manufacturer. Supports comma-separated values."""
        if not manufacturer or manufacturer == "All":
            return tables

        manufacturers = {m.strip() for m in str(manufacturer).split(',')}
        filtered = []
        for game in tables:
            current_manufacturer = self._get_game_manufacturer(game)
            if current_manufacturer in manufacturers:
                filtered.append(game)
        return filtered

    def filter_by_year(self, tables, year):
        """Filter tables by year. Supports comma-separated values."""
        if not year or year == "All":
            return tables

        years = {y.strip() for y in str(year).split(',')}
        filtered = []
        for game in tables:
            current_year = self._get_game_year(game)
            if current_year in years:
                filtered.append(game)
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

        if is_truthy(rating_or_higher):
            min_rating = min(selected_ratings)
            return [game for game in tables if self._get_game_rating(game) >= min_rating]

        rating_set = set(selected_ratings)
        return [game for game in tables if self._get_game_rating(game) in rating_set]

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
            key=lambda t: self._get_game_name(t).lower()
        )

        return result
