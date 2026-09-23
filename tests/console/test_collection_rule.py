"""A collection's rule: the rows it is edited as, and the words its panel says it in."""

from __future__ import annotations

import unittest

from console import collection_rules as rules

AXES = [{"name": "letter", "kind": "letter", "label": "Letter"},
        {"name": "manufacturer", "kind": "choice", "label": "Manufacturer",
         "values": ["Bally", "Stern"], "counts": {"Bally": 22, "Stern": 3}},
        {"name": "year", "kind": "choice", "label": "Year"},
        {"name": "rating", "kind": "rating", "label": "Rating"},
        {"name": "rating_or_higher", "kind": "rating", "label": "Rating",
         "field": "rating"},
        {"name": "played", "kind": "flag", "label": "Played"},
        {"name": "favorite", "kind": "flag", "label": "Favorite"},
        {"name": "multiplayer", "kind": "flag", "label": "Multiplayer"},
        {"name": "year_range", "kind": "range", "label": "Year", "field": "year"}]
FIELDS = rules.fields(AXES)


def _said(filters: dict, added: int = 0, taken: int = 0) -> str:
    return rules.sentence(rules.rows_from(filters, FIELDS), FIELDS, added, taken)


def _round_trip(filters: dict) -> dict:
    return rules.filters_from(rules.rows_from(filters, FIELDS), FIELDS)


class Fields(unittest.TestCase):
    def test_an_axis_asked_under_another_is_not_a_field_of_its_own(self) -> None:
        self.assertEqual(["letter", "manufacturer", "year", "rating", "played", "favorite",
                          "multiplayer"], [one.name for one in FIELDS])

    def test_each_kind_asks_its_own_way_and_the_first_is_the_default(self) -> None:
        asked = {one.name: one.operators for one in FIELDS}

        self.assertEqual([rules.STARTS_WITH], asked["letter"])
        self.assertEqual([rules.ANY_OF], asked["manufacturer"])
        self.assertEqual([rules.BETWEEN, rules.BEFORE, rules.AFTER, rules.ANY_OF],
                         asked["year"])
        self.assertEqual([rules.AT_LEAST, rules.EXACTLY], asked["rating"])
        self.assertEqual([rules.YES, rules.NO], asked["played"])

    def test_a_flag_row_answers_yes_or_no_rather_than_naming_its_field_again(self) -> None:
        named = rules.by_name(FIELDS)
        for name in ("played", "favorite", "multiplayer"):
            with self.subTest(name):
                self.assertEqual(["Yes", "No"], [rules.operator_word(op)
                                                 for op in named[name].operators])

    def test_a_field_with_nothing_to_pick_cannot_be_asked(self) -> None:
        named = rules.by_name(FIELDS)

        self.assertFalse(named["letter"].askable)
        self.assertTrue(named["manufacturer"].askable)
        self.assertTrue(named["year"].askable, "a range needs no values")
        self.assertTrue(named["played"].askable)

    def test_a_field_carries_how_many_games_hold_each_value(self) -> None:
        self.assertEqual(22, rules.by_name(FIELDS)["manufacturer"].counts["Bally"])


class Rows(unittest.TestCase):
    def test_a_stored_rule_reads_back_as_it_was_written(self) -> None:
        for filters in ({"manufacturer": ["Bally", "Stern"]},
                        {"letter": ["A"]},
                        {"rating": "4", "rating_or_higher": True},
                        {"rating": "4", "rating_or_higher": False},
                        {"played": True}, {"favorite": False},
                        {"year": ["1995"]},
                        {"year_range": {"from": 1990, "to": 1999}},
                        {"year_range": {"to": 1979}},
                        {"year_range": {"from": 1991}}):
            with self.subTest(filters=filters):
                self.assertEqual(filters, _round_trip(filters))

    def test_all_asks_for_nothing(self) -> None:
        self.assertEqual({}, _round_trip({"manufacturer": ["All"], "rating": "All",
                                          "played": None, "year_range": None}))

    def test_before_and_after_are_said_as_the_year_named(self) -> None:
        before, after = rules.rows_from({"year_range": {"to": 1979}}, FIELDS) + \
            rules.rows_from({"year_range": {"from": 1991}}, FIELDS)

        self.assertEqual((rules.BEFORE, 1980), (before["op"], before["value"]))
        self.assertEqual((rules.AFTER, 1990), (after["op"], after["value"]))

    def test_between_is_stored_low_to_high(self) -> None:
        row = {"field": "year", "op": rules.BETWEEN, "value": {"from": 1999, "to": 1990}}

        self.assertEqual({"year_range": {"from": 1990, "to": 1999}},
                         rules.filters_from([row], FIELDS))

    def test_a_row_still_being_built_asks_for_nothing(self) -> None:
        for row in (rules.row_on(rules.by_name(FIELDS)["manufacturer"]),
                    {"field": "year", "op": rules.BETWEEN, "value": {"from": 1990}},
                    {"field": "year", "op": rules.BEFORE, "value": ""}):
            with self.subTest(row=row):
                self.assertFalse(rules.complete(row))
                self.assertEqual({}, rules.filters_from([row], FIELDS))

    def test_a_flag_row_is_whole_once_it_has_a_field(self) -> None:
        self.assertTrue(rules.complete(rules.row_on(rules.by_name(FIELDS)["played"])))


class RatingInTheSentence(unittest.TestCase):
    def test_at_least(self) -> None:
        self.assertEqual("Every game where Rating is at least 4 of 5",
                         _said({"rating": "4", "rating_or_higher": True}))

    def test_exactly(self) -> None:
        self.assertEqual("Every game where Rating is 4 of 5",
                         _said({"rating": "4", "rating_or_higher": False}))

    def test_a_floor_with_no_rating_says_nothing_about_rating(self) -> None:
        self.assertNotIn("Rating", _said({"rating": "All", "rating_or_higher": True}))


class YearsInTheSentence(unittest.TestCase):
    def test_a_range(self) -> None:
        self.assertEqual("Every game where Year is 1990 to 1999",
                         _said({"year_range": {"from": 1990, "to": 1999}}))

    def test_before_and_after(self) -> None:
        self.assertEqual("Every game where Year is before 1980",
                         _said({"year_range": {"to": 1979}}))
        self.assertEqual("Every game where Year is after 1990",
                         _said({"year_range": {"from": 1991}}))


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

    def test_a_letter_is_what_the_title_starts_with(self) -> None:
        self.assertEqual("Every game where the title starts with “A” or “B”",
                         _said({"letter": ["A", "B"]}))


class ConditionsInTheSentence(unittest.TestCase):
    def test_two_are_joined_by_and(self) -> None:
        self.assertEqual("Every game where Manufacturer is “Bally” and you have "
                         "played it", _said({"manufacturer": "Bally", "played": True}))

    def test_three_are_a_list_with_one_and(self) -> None:
        self.assertEqual("Every game where Manufacturer is “Bally”, you have "
                         "played it and you have marked it a favorite",
                         _said({"manufacturer": "Bally", "played": True,
                                "favorite": True}))

    def test_the_rows_are_said_in_the_order_they_stand(self) -> None:
        rows = [{"field": "played", "op": rules.YES, "value": None},
                {"field": "manufacturer", "op": rules.ANY_OF, "value": ["Bally"]}]

        self.assertEqual("Every game where you have played it and Manufacturer is “Bally”",
                         rules.sentence(rows, FIELDS))


class WhatTheRuleDoesNotSay(unittest.TestCase):
    def test_a_rule_with_nothing_set_asks_for_one(self) -> None:
        self.assertEqual("Add a rule to choose games", _said({}))

    def test_games_added_and_taken_out_are_counted_after_the_rule(self) -> None:
        self.assertEqual("Every game where you have played it, plus 1 you added, "
                         "minus 2 you took out", _said({"played": True}, 1, 2))

    def test_only_what_there_is_is_counted(self) -> None:
        self.assertEqual("Every game where you have played it, plus 1 you added",
                         _said({"played": True}, added=1))
        self.assertEqual("Every game where you have played it, minus 1 you took out",
                         _said({"played": True}, taken=1))


class UnsavedRules(unittest.TestCase):
    def test_only_a_draft_asking_something_else_is_unsaved(self) -> None:
        from console.workbench import unsaved

        stored = [{"name": "Same", "filters": {"manufacturer": ["Bally"]}},
                  {"name": "Grown", "filters": None},
                  {"name": "Half", "filters": None},
                  {"name": "Untouched", "filters": None}]
        drafts = {"Same": {"rules": rules.rows_from({"manufacturer": "Bally"}, FIELDS)},
                  "Grown": {"rules": [{"field": "played", "op": rules.YES, "value": None}]},
                  "Half": {"rules": [rules.row_on(rules.by_name(FIELDS)["manufacturer"])]},
                  "Untouched": {}, "Deleted": {"rules": []}}

        self.assertEqual({"Grown"}, unsaved(drafts, stored, FIELDS))


if __name__ == "__main__":
    unittest.main()
