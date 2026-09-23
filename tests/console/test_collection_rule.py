"""A collection's rule, in the words its panel says it in."""

from __future__ import annotations

import unittest

from console.workbench import _rule_sentence

_AXES = [{"name": "rating", "kind": "rating", "label": "Rating"},
         {"name": "rating_or_higher", "kind": "rating", "label": "Rating"}]


def _said(filters: dict) -> str:
    return _rule_sentence({"axes": _AXES, "draft": {}}, {"filters": filters})


class RatingInTheSentence(unittest.TestCase):
    def test_at_least(self) -> None:
        self.assertEqual("Every game where Rating is at least 4 of 5.",
                         _said({"rating": "4", "rating_or_higher": True}))

    def test_exactly(self) -> None:
        self.assertEqual("Every game where Rating is 4 of 5.",
                         _said({"rating": "4", "rating_or_higher": False}))

    def test_a_floor_with_no_rating_says_nothing_about_rating(self) -> None:
        self.assertNotIn("Rating", _said({"rating": "All", "rating_or_higher": True}))


if __name__ == "__main__":
    unittest.main()
