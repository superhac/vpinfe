"""A collection's rule, in the words its panel says it in."""

from __future__ import annotations

import unittest

from console.workbench import _rule_sentence

_AXES = [{"name": "manufacturer", "kind": "choice", "label": "Manufacturer"},
         {"name": "rating", "kind": "rating", "label": "Rating"},
         {"name": "rating_or_higher", "kind": "rating", "label": "Rating"},
         {"name": "played", "kind": "flag", "label": "Played"},
         {"name": "favorite", "kind": "flag", "label": "Favorite"},
         {"name": "multiplayer", "kind": "flag", "label": "Multiplayer"}]


def _said(filters: dict, members: list[dict] | None = None) -> str:
    return _rule_sentence({"axes": _AXES, "draft": {},
                           "membership": {"members": members or []}},
                          {"filters": filters})


class RatingInTheSentence(unittest.TestCase):
    def test_at_least(self) -> None:
        self.assertEqual("Every game where Rating is at least 4 of 5",
                         _said({"rating": "4", "rating_or_higher": True}))

    def test_exactly(self) -> None:
        self.assertEqual("Every game where Rating is 4 of 5",
                         _said({"rating": "4", "rating_or_higher": False}))

    def test_a_floor_with_no_rating_says_nothing_about_rating(self) -> None:
        self.assertNotIn("Rating", _said({"rating": "All", "rating_or_higher": True}))


class FlagsInTheSentence(unittest.TestCase):
    def test_played_is_something_you_did(self) -> None:
        self.assertEqual("Every game where you have played it", _said({"played": True}))
        self.assertEqual("Every game where you have never played it",
                         _said({"played": False}))

    def test_favorite_reads_like_played(self) -> None:
        self.assertEqual("Every game where you have marked it a favorite",
                         _said({"favorite": True}))

    def test_not_a_favorite_is_said_rather_than_dropped(self) -> None:
        self.assertEqual("Every game where you have not marked it a favorite",
                         _said({"favorite": False}))

    def test_a_flag_with_no_words_of_its_own_reads_as_yes_or_no(self) -> None:
        self.assertEqual("Every game where Multiplayer is Yes", _said({"multiplayer": True}))


class ValuesInTheSentence(unittest.TestCase):
    def test_one(self) -> None:
        self.assertEqual("Every game where Manufacturer is “Bally”",
                         _said({"manufacturer": "Bally"}))

    def test_two(self) -> None:
        self.assertEqual("Every game where Manufacturer is “Bally” or “Stern”",
                         _said({"manufacturer": "Bally,Stern"}))

    def test_three_are_a_list_with_one_or(self) -> None:
        self.assertEqual(
            "Every game where Manufacturer is “Bally”, “Stern” or "
            "“Williams”",
            _said({"manufacturer": ["Bally", "Stern", "Williams"]}))


class ConditionsInTheSentence(unittest.TestCase):
    def test_two_are_joined_by_and(self) -> None:
        self.assertEqual("Every game where Manufacturer is “Bally” and you have "
                         "played it", _said({"manufacturer": "Bally", "played": True}))

    def test_three_are_a_list_with_one_and(self) -> None:
        self.assertEqual("Every game where Manufacturer is “Bally”, you have "
                         "played it and you have marked it a favorite",
                         _said({"manufacturer": "Bally", "played": True,
                                "favorite": True}))


class WhatTheRuleDoesNotSay(unittest.TestCase):
    def test_a_rule_with_nothing_set_asks_for_one(self) -> None:
        self.assertEqual("Add a rule to choose games", _said({}))

    def test_games_added_and_taken_out_are_counted_after_the_rule(self) -> None:
        members = [{"game": "a", "origin": "named"},
                   {"game": "b", "origin": "filter"},
                   {"game": "c", "origin": "excluded"},
                   {"game": "d", "origin": "excluded"}]
        self.assertEqual("Every game where you have played it, plus 1 you added, "
                         "minus 2 you took out", _said({"played": True}, members))

    def test_only_what_there_is_is_counted(self) -> None:
        self.assertEqual("Every game where you have played it, plus 1 you added",
                         _said({"played": True}, [{"game": "a", "origin": "named"}]))
        self.assertEqual("Every game where you have played it, minus 1 you took out",
                         _said({"played": True}, [{"game": "a", "origin": "excluded"}]))

    def test_a_game_held_on_two_tables_is_one_game(self) -> None:
        members = [{"game": "a", "origin": "named"}, {"game": "a", "origin": "named"}]
        self.assertIn("plus 1 you added", _said({"played": True}, members))


if __name__ == "__main__":
    unittest.main()
