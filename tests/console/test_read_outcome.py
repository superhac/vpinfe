"""What Look for new tables and Auto-match say when they end, and where they lead."""

from __future__ import annotations

import unittest

from console.games import auto_match_outcome
from console.page import read_failure, read_outcome


def _result(games: int, matched: int, waiting: list[str]) -> dict:
    return {"new_games": games, "new_matched": matched, "new_unmatched": len(waiting),
            "new_unmatched_ids": waiting}


class ReadOutcomeTests(unittest.TestCase):
    def test_nothing_new_is_up_to_date(self) -> None:
        self.assertEqual(read_outcome(_result(0, 0, [])),
                         ("The library is up to date", []))

    def test_every_new_game_matched_leads_nowhere(self) -> None:
        self.assertEqual(read_outcome(_result(3, 3, [])), ("Matched 3 new games", []))
        self.assertEqual(read_outcome(_result(1, 1, [])), ("Matched 1 new game", []))

    def test_some_matched_says_how_many_are_left(self) -> None:
        self.assertEqual(read_outcome(_result(12, 10, ["g1", "g2"])),
                         ("Matched 10 of 12 new games. 2 need a match.", ["g1", "g2"]))
        self.assertEqual(read_outcome(_result(3, 2, ["g1"])),
                         ("Matched 2 of 3 new games. 1 needs a match.", ["g1"]))

    def test_none_matched_says_they_need_one(self) -> None:
        self.assertEqual(read_outcome(_result(2, 0, ["g1", "g2"])),
                         ("2 new games need a match", ["g1", "g2"]))
        self.assertEqual(read_outcome(_result(1, 0, ["g1"])),
                         ("1 new game needs a match", ["g1"]))

    def test_a_job_that_said_nothing_is_up_to_date(self) -> None:
        self.assertEqual(read_outcome({}), ("The library is up to date", []))

    def test_a_failed_read_puts_its_reason_under_the_lead(self) -> None:
        self.assertEqual(read_failure({"state": "failed", "error": "Nothing is at /tables"}),
                         ("The scan failed", "Nothing is at /tables"))

    def test_a_failed_read_with_no_reason_has_nothing_under_it(self) -> None:
        self.assertEqual(read_failure({"state": "failed", "error": None}),
                         ("The scan failed", ""))


class AutoMatchOutcomeTests(unittest.TestCase):
    def test_what_moved_and_what_waits(self) -> None:
        self.assertEqual(auto_match_outcome({"changed": 3, "unmatched": 2}),
                         ("Matched 3 games. 2 still need a match.", True))
        self.assertEqual(auto_match_outcome({"changed": 1, "unmatched": 1}),
                         ("Matched 1 game. 1 still needs a match.", True))

    def test_only_what_moved(self) -> None:
        self.assertEqual(auto_match_outcome({"changed": 1, "unmatched": 0}),
                         ("Matched 1 game", True))

    def test_only_what_waits(self) -> None:
        self.assertEqual(auto_match_outcome({"changed": 0, "unmatched": 2}),
                         ("2 still need a match", False))

    def test_nothing_moved_and_nothing_waits(self) -> None:
        self.assertEqual(auto_match_outcome({"changed": 0, "unmatched": 0, "yours": 4}),
                         ("Nothing changed", False))


if __name__ == "__main__":
    unittest.main()
