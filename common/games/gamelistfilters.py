from common.games import collection_filters
from common.games.game_metadata import (
    game_manufacturer,
    game_rating,
    game_themes,
    game_title,
    game_type,
    game_year,
    get_meta_value,
    normalize_rating,
)
from common.values import is_truthy


class GameListFilters:
    """Filter games by various criteria: starting letter, theme, type, and rating."""

    def __init__(self, games=None):
        self.games = list(games or [])

    @staticmethod
    def _get_meta_value(game, section, key, fallback=""):
        """Helper to safely extract metadata values."""
        return get_meta_value(getattr(game, "metaConfig", {}), section, key, fallback)

    def get_available_letters(self):
        """Return sorted list of unique starting letters from game names."""
        letters = set()
        for game in self.games:
            # Try Info.Title first (JSON format), then VPSdb.name (legacy)
            name = game_title(game)
            if name:
                first_char = name[0].upper()
                # Only include alphanumeric characters
                if first_char.isalnum():
                    letters.add(first_char)
        return sorted(letters)

    def get_available_themes(self):
        """Return sorted list of unique themes from all games."""
        themes = set()
        for game in self.games:
            themes.update(game_themes(game))
        return sorted(themes)

    def get_available_types(self):
        """Return sorted list of unique game types."""
        types = set()
        for game in self.games:
            current_type = game_type(game)
            if current_type:
                types.add(current_type)
        return sorted(types)

    def get_available_manufacturers(self):
        """Return sorted list of unique manufacturers."""
        manufacturers = set()
        for game in self.games:
            manufacturer = game_manufacturer(game)
            if manufacturer:
                manufacturers.add(manufacturer)
        return sorted(manufacturers)

    def get_available_years(self):
        """Return sorted list of unique years."""
        years = set()
        for game in self.games:
            year = game_year(game)
            if year:
                years.add(str(year))
        return sorted(years)

    def _get_game_name(self, game):
        """Get game name from either JSON or legacy format."""
        return game_title(game)

    def _get_game_theme(self, game):
        """Get game theme(s) from either JSON or legacy format."""
        return game_themes(game)

    def _get_game_type(self, game):
        """Get game type from either JSON or legacy format."""
        return game_type(game)

    def _get_game_manufacturer(self, game):
        """Get game manufacturer from either JSON or legacy format."""
        return game_manufacturer(game)

    def _get_game_year(self, game):
        """Get game year from either JSON or legacy format."""
        return game_year(game)

    @staticmethod
    def _normalize_rating(value):
        """Normalize rating values to an integer in the range 0..5."""
        return normalize_rating(value)

    def _get_game_rating(self, game):
        """Get game rating from User.Rating metadata."""
        return game_rating(game)

    # The predicates live in collection_filters, so a filter collection and this class
    # cannot disagree about what "manufacturer = Williams" selects. These stay because
    # the Manager UI and the frontend both call them one axis at a time.

    def _by_axis(self, games, axis_name, criterion):
        if collection_filters.is_unconstrained(criterion):
            return games
        axis = collection_filters.AXES_BY_NAME[axis_name]
        return [game for game in games if axis.matches(criterion, game, {})]

    def filter_by_letter(self, games, letter):
        """Filter games by starting letter of name. Supports comma-separated values."""
        return self._by_axis(games, "letter", letter)

    def filter_by_theme(self, games, theme):
        """Filter games by theme. Supports comma-separated values."""
        return self._by_axis(games, "theme", theme)

    def filter_by_type(self, games, game_type):
        """Filter games by type (EM, SS, etc.). Supports comma-separated values."""
        return self._by_axis(games, "game_type", game_type)

    def filter_by_manufacturer(self, games, manufacturer):
        """Filter games by manufacturer. Supports comma-separated values."""
        return self._by_axis(games, "manufacturer", manufacturer)

    def filter_by_year(self, games, year):
        """Filter games by year. Supports comma-separated values."""
        return self._by_axis(games, "year", year)

    def filter_by_rating(self, games, rating, rating_or_higher=False):
        """Filter games by rating, optionally reading it as a floor."""
        if collection_filters.is_unconstrained(rating):
            return games
        axis = collection_filters.AXES_BY_NAME[
            "rating_or_higher" if is_truthy(rating_or_higher) else "rating"]
        return [game for game in games if axis.matches(rating, game, {})]

    def apply_filters(self, letter=None, theme=None, game_type=None, manufacturer=None, year=None, rating=None, rating_or_higher=False):
        """
        Apply multiple filters in combination.
        Returns filtered and sorted list of games.
        """
        result = list(self.games)  # Make a copy to avoid modifying original

        # Apply each filter sequentially
        if letter and letter != "All":
            result = self.filter_by_letter(result, letter)

        if theme and theme != "All":
            result = self.filter_by_theme(result, theme)

        if game_type and game_type != "All":
            result = self.filter_by_type(result, game_type)

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
