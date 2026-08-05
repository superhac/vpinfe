"""Every axis a filter collection can constrain, declared once.

One definition per axis drives four things that used to be written out separately: what
a stored filter may contain, how it matches, what control the Manager UI renders, and
what the API's schema says. Adding an axis is an entry here.

Because the registry is the only place that knows the axes, a stored filter naming one
this build does not have is *detectable*: the collection is refused by name instead of
silently resolving to a different membership. That is what makes adding an axis free -
an older build degrades loudly rather than quietly answering the wrong question.

The rule that keeps it free: **axes are append-only and their meaning never changes.**
Different semantics get a new axis. `tests/test_collection_filters.py` holds a snapshot
that fails if an existing definition moves.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from common.values import is_truthy
from common.games.game_metadata import (
    get_meta_value,

    game_manufacturer,
    game_rating,
    game_themes,
    game_title,
    game_type,
    game_year,
    normalize_rating,
)

# What a criterion says when it constrains nothing. The vocabulary the filter engine
# and the Manager UI already share, kept rather than translated.
UNCONSTRAINED = "All"

GAME_SCOPE = "game"
TABLE_SCOPE = "table"


def _values(criterion) -> set[str]:
    """A criterion as the set of values it accepts. Comma-separated throughout."""
    return {part.strip() for part in str(criterion).split(",") if part.strip()}


def _match_letter(criterion, game, table) -> bool:
    name = game_title(game)
    return bool(name) and name[0].upper() in {v.upper() for v in _values(criterion)}


def _match_theme(criterion, game, table) -> bool:
    return bool(_values(criterion) & set(game_themes(game)))


def _match_game_type(criterion, game, table) -> bool:
    return game_type(game) in _values(criterion)


def _match_manufacturer(criterion, game, table) -> bool:
    return game_manufacturer(game) in _values(criterion)


def _match_year(criterion, game, table) -> bool:
    return game_year(game) in _values(criterion)


def _match_rating(criterion, game, table) -> bool:
    wanted = {normalize_rating(v) for v in _values(criterion)}
    return game_rating(game) in wanted


def _match_rating_or_higher(criterion, game, table) -> bool:
    """Reads `rating` as a floor rather than a set. Declared as its own axis because
    that is how it is stored and how the UI presents it - a checkbox beside rating."""
    wanted = {normalize_rating(v) for v in _values(criterion)}
    return bool(wanted) and game_rating(game) >= min(wanted)


@dataclass(frozen=True)
class FilterAxis:
    """One thing a collection can filter on.

    `scope` says which object the criterion is about. It is what removes the ambiguity
    in `manufacturer`, `year` and `type`, which exist on a game *and* on each of its
    tables and were previously resolved by accident.
    """

    name: str
    scope: str
    kind: str
    summary: str
    matches: Callable

    @property
    def is_table_scoped(self) -> bool:
        return self.scope == TABLE_SCOPE


AXES: tuple[FilterAxis, ...] = (
    FilterAxis("letter", GAME_SCOPE, "letter",
               "First letter of the title, as sorted",
               _match_letter),
    FilterAxis("theme", GAME_SCOPE, "choice",
               "Any theme the game is tagged with",
               _match_theme),
    FilterAxis("game_type", GAME_SCOPE, "choice",
               "Solid state, electro-mechanical and so on",
               _match_game_type),
    FilterAxis("manufacturer", GAME_SCOPE, "choice",
               "Who made the machine",
               _match_manufacturer),
    FilterAxis("year", GAME_SCOPE, "choice",
               "Year the machine was released",
               _match_year),
    FilterAxis("rating", GAME_SCOPE, "rating",
               "The rating the user gave the game",
               _match_rating),
    FilterAxis("rating_or_higher", GAME_SCOPE, "rating",
               "Read `rating` as a floor instead of a set",
               _match_rating_or_higher),
)

AXES_BY_NAME = {axis.name: axis for axis in AXES}

# Stored beside the criteria but not criteria: they say how to order what matched, not
# what matches. Reserved so an older build does not read them as an axis it lacks and
# refuse a collection it can resolve perfectly well.
ORDERING_KEYS = frozenset({"sort_by", "order_by"})

# `table_type` was the game's type under the old vocabulary. Reading it keeps a stored
# filter working; nothing writes it.
LEGACY_AXIS_NAMES = {"table_type": "game_type"}


def canonical_axis(name: str) -> str:
    return LEGACY_AXIS_NAMES.get(name, name)


def is_unconstrained(criterion) -> bool:
    """Whether a criterion asks for nothing. Absent, empty and "All" all mean this."""
    return criterion in (None, "", UNCONSTRAINED) or not _values(criterion)


def unknown_axes(stored: dict | None) -> list[str]:
    """Axes in a stored filter that this build cannot resolve.

    A caller finding any must refuse the collection rather than resolve what is left:
    ignoring a constraint answers a different question, and does it silently.
    """
    return sorted(name for name in (stored or {})
                  if name not in ORDERING_KEYS
                  and canonical_axis(name) not in AXES_BY_NAME)


def matches(stored: dict | None, game, table: dict | None = None) -> bool:
    """Whether one game, optionally via one of its tables, satisfies every criterion.

    An axis that constrains nothing is skipped; `rating_or_higher` reads the `rating`
    criterion, so it is skipped when rating itself is unconstrained.
    """
    stored = stored or {}
    rating = stored.get("rating")
    for name, criterion in stored.items():
        axis = AXES_BY_NAME.get(canonical_axis(name))
        if axis is None or is_unconstrained(criterion):
            continue
        if axis.name == "rating_or_higher":
            if str(criterion).strip().lower() not in ("1", "true", "yes", "on"):
                continue
            criterion = rating
            if is_unconstrained(criterion):
                continue
        elif axis.name == "rating" and _reads_rating_as_a_floor(stored):
            continue
        if not axis.matches(criterion, game, table or {}):
            return False
    return True


def _reads_rating_as_a_floor(stored: dict) -> bool:
    value = str(stored.get("rating_or_higher", "") or "").strip().lower()
    return value in ("1", "true", "yes", "on")

# ---------------------------------------------------------------------------
# What there is to filter *on*, as opposed to whether a game matches. The Manager
# UI asks for the letters, themes, types, manufacturers and years its controls
# should offer, and the answer comes from the same axis definitions the matching
# uses - which is why this was folded in from game_list_filters.py.
# ---------------------------------------------------------------------------

class GameListFilters:
    """Filter games by various criteria: starting letter, theme, type, and rating."""

    def __init__(self, games=None):
        self.games = list(games or [])

    @staticmethod
    def _get_meta_value(game, section, key, fallback=""):
        """Helper to safely extract metadata values."""
        return get_meta_value(getattr(game, "meta_config", {}), section, key, fallback)

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
        if is_unconstrained(criterion):
            return games
        axis = AXES_BY_NAME[axis_name]
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
        if is_unconstrained(rating):
            return games
        axis = AXES_BY_NAME[
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
