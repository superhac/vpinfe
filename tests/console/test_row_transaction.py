"""Putting one game's rows back on screen after a write, without rebuilding the page.

Rebuilding reads as the grid flashing: scroll position, focus and the open panel all go,
for a write that touched one game. AG Grid is already told the row's id, so a transaction
leaves all three alone - what this has to get right is which of add, update and remove
each row needs, and that nothing belonging to another game is touched.
"""

from __future__ import annotations

import unittest

from console.games import row_transaction


def _showing(*pairs):
    return {row_id: {"id": row_id, "game_id": game} for row_id, game in pairs}


def _fresh(*pairs):
    return [{"id": row_id, "game_id": game} for row_id, game in pairs]


class RowTransactionTests(unittest.TestCase):
    def test_a_table_that_arrived_is_added(self) -> None:
        got = row_transaction(_showing(), "g1", _fresh(("t1", "g1")))

        self.assertEqual([row["id"] for row in got["add"]], ["t1"])
        self.assertNotIn("update", got)
        self.assertNotIn("remove", got)

    def test_one_that_changed_is_updated(self) -> None:
        got = row_transaction(_showing(("t1", "g1")), "g1", _fresh(("t1", "g1")))

        self.assertEqual([row["id"] for row in got["update"]], ["t1"])
        self.assertNotIn("add", got)

    def test_one_that_went_is_removed(self) -> None:
        got = row_transaction(_showing(("t1", "g1")), "g1", [])

        self.assertEqual(got["remove"], [{"id": "t1"}])

    def test_a_write_can_do_two_at_once(self) -> None:
        """Giving a game its first table does exactly this: a row arrives and the
        default moves off whatever held it."""
        got = row_transaction(_showing(("t1", "g1")), "g1",
                              _fresh(("t1", "g1"), ("t2", "g1")))

        self.assertEqual([row["id"] for row in got["add"]], ["t2"])
        self.assertEqual([row["id"] for row in got["update"]], ["t1"])

    def test_another_game_s_rows_are_left_alone(self) -> None:
        """The one that would empty the grid: every row on screen that this write did
        not touch is not a removal."""
        got = row_transaction(_showing(("t1", "g1"), ("t9", "g2")), "g1",
                              _fresh(("t1", "g1")))

        self.assertNotIn("remove", got)
        self.assertEqual([row["id"] for row in got["update"]], ["t1"])

    def test_nothing_to_say_says_nothing(self) -> None:
        """An empty transaction is not sent, so a write that changed nothing does not
        make the grid do work."""
        self.assertEqual(row_transaction(_showing(("t9", "g2")), "g1", []), {})


if __name__ == "__main__":
    unittest.main()
