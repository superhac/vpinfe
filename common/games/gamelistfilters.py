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

    def filter_by_letter(self, games, letter):
        """Filter games by starting letter of name. Supports comma-separated values."""
        if not letter or letter == "All":
            return games

        letters = {l.strip().upper() for l in str(letter).split(',')}
        filtered = []
        for game in games:
            name = self._get_game_name(game)
            if name and name[0].upper() in letters:
                filtered.append(game)
        return filtered

    def filter_by_theme(self, games, theme):
        """Filter games by theme. Supports comma-separated values."""
        if not theme or theme == "All":
            return games

        themes = {t.strip() for t in str(theme).split(',')}
        filtered = []
        for game in games:
            game_themes = self._get_game_theme(game)
            if themes & set(game_themes):
                filtered.append(game)
        return filtered

    def filter_by_type(self, games, game_type):
        """Filter games by type (EM, SS, etc.). Supports comma-separated values."""
        if not game_type or game_type == "All":
            return games

        types = {t.strip() for t in str(game_type).split(',')}
        filtered = []
        for game in games:
            current_type = self._get_game_type(game)
            if current_type in types:
                filtered.append(game)
        return filtered

    def filter_by_manufacturer(self, games, manufacturer):
        """Filter games by manufacturer. Supports comma-separated values."""
        if not manufacturer or manufacturer == "All":
            return games

        manufacturers = {m.strip() for m in str(manufacturer).split(',')}
        filtered = []
        for game in games:
            current_manufacturer = self._get_game_manufacturer(game)
            if current_manufacturer in manufacturers:
                filtered.append(game)
        return filtered

    def filter_by_year(self, games, year):
        """Filter games by year. Supports comma-separated values."""
        if not year or year == "All":
            return games

        years = {y.strip() for y in str(year).split(',')}
        filtered = []
        for game in games:
            current_year = self._get_game_year(game)
            if current_year in years:
                filtered.append(game)
        return filtered

    def filter_by_rating(self, games, rating, rating_or_higher=False):
        """Filter games by rating. Supports comma-separated values and optional 'or higher' mode."""
        if not rating or rating == "All":
            return games

        selected_ratings = []
        for r in str(rating).split(','):
            try:
                selected_ratings.append(self._normalize_rating(r.strip()))
            except Exception:
                continue

        if not selected_ratings:
            return games

        if is_truthy(rating_or_higher):
            min_rating = min(selected_ratings)
            return [game for game in games if self._get_game_rating(game) >= min_rating]

        rating_set = set(selected_ratings)
        return [game for game in games if self._get_game_rating(game) in rating_set]

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
