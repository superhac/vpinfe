"""The filter registry, and the rule that keeps adding an axis free.

An axis is append-only and its meaning never changes. That is not a convention anyone
can hold in their head across releases, so the snapshot below fails if an existing
definition moves - a stored filter written against the old meaning would resolve to a
different membership, silently, on somebody's library.
"""

import unittest
from types import SimpleNamespace

from common.games import collection_filters as cf
from common.games.collection_filters import GameListFilters


def make_game(name="Example", manufacturer="", year="", game_type="",
              themes=None, rating=0):
    """A game as the metadata accessors read one: everything off meta_config."""
    return SimpleNamespace(
        gameDirName=name,
        meta_config={
            "Info": {"Title": name, "Manufacturer": manufacturer,
                     "Year": year, "Type": game_type, "Themes": themes or []},
            "User": {"Rating": rating},
        },
    )


# name -> (scope, kind). Add a line when an axis is added; never edit one.
AXIS_SNAPSHOT = {
    "letter": ("game", "letter"),
    "theme": ("game", "choice"),
    "game_type": ("game", "choice"),
    "manufacturer": ("game", "choice"),
    "year": ("game", "choice"),
    "rating": ("game", "rating"),
    "rating_or_higher": ("game", "rating"),
    "played": ("game", "flag"),
}


class RegistryShapeTests(unittest.TestCase):
    def test_no_axis_changed_its_scope_or_kind(self) -> None:
        """Editing one silently changes what every stored filter using it selects."""
        current = {a.name: (a.scope, a.kind) for a in cf.AXES}

        self.assertEqual(current, AXIS_SNAPSHOT,
                         "an axis moved; add a new one instead of changing this one")

    def test_the_axes_that_group_still_do(self) -> None:
        """Paging to the next boundary needs the extractor. An axis that loses it stops
        being pageable, and the press silently steps instead."""
        grouped = {name for name, axis in cf.AXES_BY_NAME.items() if axis.groups}

        self.assertEqual(grouped, {"letter", "year", "rating"})

    def test_every_axis_has_a_summary_and_a_matcher(self) -> None:
        for axis in cf.AXES:
            with self.subTest(axis=axis.name):
                self.assertTrue(axis.summary.strip())
                self.assertTrue(callable(axis.matches))

    def test_names_are_unique(self) -> None:
        names = [a.name for a in cf.AXES]
        self.assertEqual(len(names), len(set(names)))


class UnknownAxisTests(unittest.TestCase):
    """The property that makes adding an axis free: an older build can tell."""

    def test_an_axis_this_build_does_not_have_is_reported(self) -> None:
        self.assertEqual(cf.unknown_axes({"manufacturer": "Williams", "app": "VPX VR"}),
                         ["app"])

    def test_a_filter_this_build_understands_reports_nothing(self) -> None:
        self.assertEqual(cf.unknown_axes({"manufacturer": "Williams", "year": "1995"}), [])

    def test_the_old_spelling_of_game_type_still_resolves(self) -> None:
        """`table_type` was the game's type under the old vocabulary."""
        self.assertEqual(cf.unknown_axes({"table_type": "SS"}), [])


class MatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.afm = make_game(name="Attack from Mars", manufacturer="Bally",
                             year="1995", game_type="SS", themes=["Aliens"], rating=4)

    def test_a_digit_title_filters_under_the_hash_group(self) -> None:
        """Paging always bucketed `300` under `#`. The filter compared the first
        character literally, so no letter selected it and neither did `#`."""
        threehundred = make_game(name="300")

        self.assertTrue(cf.matches({"letter": "#"}, threehundred))
        self.assertFalse(cf.matches({"letter": "3"}, threehundred))

    def test_a_symbol_title_shares_that_group(self) -> None:
        self.assertTrue(cf.matches({"letter": "#"}, make_game(name="'Cuda")))

    def test_a_letter_filter_is_case_insensitive(self) -> None:
        self.assertTrue(cf.matches({"letter": "a"}, self.afm))

    def test_an_unconstrained_axis_matches_everything(self) -> None:
        for value in (None, "", "All"):
            with self.subTest(value=value):
                self.assertTrue(cf.matches({"manufacturer": value}, self.afm))

    def test_every_criterion_has_to_hold(self) -> None:
        self.assertTrue(cf.matches({"manufacturer": "Bally", "year": "1995"}, self.afm))
        self.assertFalse(cf.matches({"manufacturer": "Bally", "year": "1997"}, self.afm))

    def test_a_criterion_accepts_a_comma_separated_set(self) -> None:
        self.assertTrue(cf.matches({"manufacturer": "Williams, Bally"}, self.afm))

    def test_rating_is_a_set_unless_or_higher_is_set(self) -> None:
        self.assertFalse(cf.matches({"rating": "3"}, self.afm))
        self.assertTrue(cf.matches({"rating": "3", "rating_or_higher": "true"}, self.afm))

    def test_or_higher_without_a_rating_constrains_nothing(self) -> None:
        self.assertTrue(cf.matches({"rating_or_higher": "true"}, self.afm))

    def test_played_selects_the_games_with_a_date_on_record(self) -> None:
        never = make_game(name="Never Touched")
        played = make_game(name="Played Once")
        played.meta_config["User"]["LastRun"] = 1700000000

        self.assertTrue(cf.matches({"played": True}, played))
        self.assertFalse(cf.matches({"played": True}, never))

    def test_played_false_selects_the_ones_without(self) -> None:
        """The same axis answers "never played", which is why it is a flag and not a
        second axis that would have to be kept in step with this one."""
        never = make_game(name="Never Touched")
        played = make_game(name="Played Once")
        played.meta_config["User"]["LastRun"] = 1700000000

        self.assertTrue(cf.matches({"played": False}, never))
        self.assertFalse(cf.matches({"played": False}, played))

    def test_a_zero_or_unreadable_last_run_is_not_a_play(self) -> None:
        """A game carrying the key with nothing in it has not been played."""
        for value in (0, "", None, "not a date"):
            with self.subTest(value=value):
                game = make_game(name="Odd")
                game.meta_config["User"]["LastRun"] = value

                self.assertFalse(cf.matches({"played": True}, game))

    def test_an_unknown_axis_is_ignored_here_and_caught_by_the_caller(self) -> None:
        """matches() is not where refusal happens - unknown_axes() is, before this runs."""
        self.assertTrue(cf.matches({"app": "VPX VR"}, self.afm))


class DelegationTests(unittest.TestCase):
    """GameListFilters and a filter collection have to agree on what a criterion means,
    which they only do because there is one definition."""

    def test_a_criterion_reads_under_either_spelling(self) -> None:
        """A file 2.x wrote holds `table_type`; one written now holds `game_type`. Both
        have to answer, or a reader breaks on whichever it was not written against."""
        self.assertEqual(cf.criterion({"table_type": "SS"}, "game_type"), "SS")
        self.assertEqual(cf.criterion({"game_type": "EM"}, "game_type"), "EM")
        self.assertEqual(cf.criterion({}, "game_type", "All"), "All")

    def test_nothing_writes_the_retired_spelling_any_more(self) -> None:
        """It was still being minted into every new filter collection while the comment
        beside it said otherwise."""
        from common.games.collection_store import _FILTER_DEFAULTS

        self.assertIn("game_type", _FILTER_DEFAULTS)
        self.assertNotIn("table_type", _FILTER_DEFAULTS)

    def test_the_letters_offered_are_the_letters_that_select(self) -> None:
        """The picker listed the raw first character, so a library with `300` offered
        `3` and selecting it came back empty."""
        games = [make_game(name="300"), make_game(name="'Cuda"),
                 make_game(name="Attack from Mars")]

        offered = GameListFilters(games).get_available_letters()

        self.assertEqual(offered, ["#", "A"])
        for letter in offered:
            with self.subTest(letter=letter):
                self.assertTrue(any(cf.matches({"letter": letter}, g) for g in games))

    def test_the_list_filters_use_the_registry(self) -> None:
        games = [make_game(name="Attack from Mars", manufacturer="Bally"),
                 make_game(name="Medieval Madness", manufacturer="Williams")]
        engine = GameListFilters(games)

        by_list = engine.filter_by_manufacturer(games, "Bally")
        by_axis = [g for g in games if cf.matches({"manufacturer": "Bally"}, g)]

        self.assertEqual(by_list, by_axis)


if __name__ == "__main__":
    unittest.main()
