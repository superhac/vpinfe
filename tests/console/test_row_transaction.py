"""Putting one game's rows back on screen after a write, without rebuilding the page.

Rebuilding reads as the grid flashing: scroll position, focus and the open panel all go,
for a write that touched one game. AG Grid is already told the row's id, so a transaction
leaves all three alone - what this has to get right is which of add, update and remove
each row needs, and that nothing belonging to another game is touched.
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from console import grid, stars
from console.games import add_index, row_transaction


def _showing(*pairs):
    return {row_id: {"id": row_id, "game_id": game} for row_id, game in pairs}


def _fresh(*pairs):
    return [{"id": row_id, "game_id": game} for row_id, game in pairs]


class _Grid:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    def run_grid_method(self, name: str, *args: object) -> None:
        self.sent.append((name, *args))


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


class InPlaceTests(unittest.TestCase):
    """Where an added row goes, and the rows the count reads once it has."""

    BUILT = _fresh(("a1", "ga"), ("b1", "gb"), ("b2", "gb"), ("c1", "gc"))

    def _apply(self, fresh):
        showing = {row["id"]: row for row in self.BUILT}
        transaction = row_transaction(showing, "gb", fresh)
        built = list(self.BUILT)
        add_index(built, "gb", transaction)
        grid.transact(_Grid(), built, transaction)
        return transaction, built

    def test_an_added_row_follows_its_game_s_rows(self) -> None:
        transaction, built = self._apply(_fresh(("b1", "gb"), ("b2", "gb"), ("b3", "gb")))

        self.assertEqual(transaction["addIndex"], 3)
        self.assertEqual([row["id"] for row in built], ["a1", "b1", "b2", "b3", "c1"])

    def test_a_removal_leaves_the_rest_in_order(self) -> None:
        transaction, built = self._apply(_fresh(("b2", "gb")))

        self.assertNotIn("addIndex", transaction)
        self.assertEqual([row["id"] for row in built], ["a1", "b2", "c1"])

    def test_an_add_and_a_removal_at_once_count_what_stayed(self) -> None:
        transaction, built = self._apply(_fresh(("b2", "gb"), ("b3", "gb")))

        self.assertEqual(transaction["addIndex"], 2)
        self.assertEqual([row["id"] for row in built], ["a1", "b2", "b3", "c1"])


class TransactTests(unittest.TestCase):
    """The rows a grid holds, which a selection is read against, follow its screen."""

    def setUp(self) -> None:
        self.held = [{"id": "a", "v": 1}, {"id": "b", "v": 1}, {"id": "c", "v": 1}]
        self.by_id = {row["id"]: row for row in self.held}
        self.screen = _Grid()

    def test_an_edited_row_is_held_as_edited(self) -> None:
        grid.transact(self.screen, self.held, {"update": [{"id": "b", "v": 2}]}, self.by_id)

        self.assertEqual([row["v"] for row in self.held], [1, 2, 1])
        self.assertIs(self.by_id["b"], self.held[1])

    def test_a_removed_row_is_not_held(self) -> None:
        grid.transact(self.screen, self.held, {"remove": [{"id": "a"}]}, self.by_id)

        self.assertEqual([row["id"] for row in self.held], ["b", "c"])
        self.assertNotIn("a", self.by_id)

    def test_an_add_goes_where_the_screen_puts_it(self) -> None:
        grid.transact(self.screen, self.held, {"add": [{"id": "d"}], "addIndex": 1})
        grid.transact(self.screen, self.held, {"add": [{"id": "e"}]})

        self.assertEqual([row["id"] for row in self.held], ["a", "d", "b", "c", "e"])

    def test_the_screen_is_sent_the_same_transaction(self) -> None:
        transaction = {"update": [{"id": "c", "v": 3}]}
        grid.transact(self.screen, self.held, transaction)

        self.assertEqual(self.screen.sent, [("applyTransaction", transaction)])


class MovedTests(unittest.TestCase):
    def _replace(self, held: list[dict], fresh: list[dict], game: str | None = None):
        by_id = {row["id"]: row for row in held}
        screen = _Grid()
        grid.replace_rows(screen, held, by_id, fresh,
                          lambda row: game is None or row.get("game_id") == game)
        return screen, by_id

    def test_an_update_whose_place_changed_moves(self) -> None:
        held = [{"id": "a", "v": 1}, {"id": "b", "v": 1}, {"id": "c", "v": 1}]

        screen, by_id = self._replace(held, [{"id": "c", "v": 2}, {"id": "a", "v": 1},
                                             {"id": "b", "v": 1}])

        self.assertEqual([row["id"] for row in held], ["c", "a", "b"])
        (method, option, rows), = screen.sent
        self.assertEqual((method, option), ("setGridOption", "rowData"))
        self.assertEqual([row["id"] for row in rows], ["c", "a", "b"])
        self.assertEqual(by_id["c"]["v"], 2)

    def test_rows_another_game_holds_keep_their_slots(self) -> None:
        held = _fresh(("a1", "ga"), ("b1", "gb"), ("a2", "ga"))

        self._replace(held, _fresh(("a2", "ga"), ("a1", "ga")), game="ga")

        self.assertEqual([row["id"] for row in held], ["a2", "b1", "a1"])

    def test_a_move_takes_what_went_and_what_came_with_it(self) -> None:
        held = [{"id": "a"}, {"id": "b"}, {"id": "c"}]

        _screen, by_id = self._replace(held, [{"id": "c"}, {"id": "a"}, {"id": "d"}])

        self.assertEqual([row["id"] for row in held], ["c", "a", "d"])
        self.assertEqual(set(by_id), {"a", "c", "d"})

    def test_an_update_in_its_place_is_a_transaction(self) -> None:
        held = [{"id": "a", "v": 1}, {"id": "b", "v": 1}]

        screen, _by_id = self._replace(held, [{"id": "a", "v": 1}, {"id": "b", "v": 2}])

        self.assertEqual(screen.sent[0][0], "applyTransaction")
        self.assertEqual([row["v"] for row in held], [1, 2])


class RatingTests(unittest.TestCase):
    def test_a_rated_row_is_held_with_its_rating(self) -> None:
        held = [{"id": "g1", "rating": 0}, {"id": "g2", "rating": 4}]
        by_id = {row["id"]: row for row in held}
        screen = _Grid()

        class _Client:
            def rate(self, game_id: str, value: int) -> None:
                pass

        rate = stars.rating_handler(held, by_id, lambda: screen, _Client)
        asyncio.run(rate(SimpleNamespace(args={"game": "g1", "value": 3})))

        self.assertEqual([row["rating"] for row in held], [3, 4])
        self.assertEqual(by_id["g1"]["rating"], 3)
        self.assertEqual(screen.sent[0][1], {"update": [{"id": "g1", "rating": 3}]})


if __name__ == "__main__":
    unittest.main()
