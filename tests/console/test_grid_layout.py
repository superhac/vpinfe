"""A grid's saved layout, put back on the grid: the order a person left the columns in,
and the widths the grid declares wherever the person has not set one."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from console import grid

COLUMNS = [{"field": "name", "width": 240}, {"field": "year", "width": 90},
           {"field": "rating", "width": 130}, {"field": "plays", "width": 130}]


def _saved(*col_ids: str) -> dict[str, dict[str, Any]]:
    return {col_id: {"colId": col_id} for col_id in col_ids}


class _Grid:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    def run_grid_method(self, name: str, *args: Any) -> None:
        self.sent.append((name, *args))


class AppliedOrderTests(unittest.TestCase):
    def test_a_moved_column_goes_back_where_it_was_put(self) -> None:
        state = grid.applied_state(COLUMNS, _saved("plays", "name", "year", "rating"))

        self.assertEqual(["plays", "name", "year", "rating"],
                         [entry["colId"] for entry in state])

    def test_a_column_the_save_does_not_name_comes_after_the_ones_it_does(self) -> None:
        state = grid.applied_state(COLUMNS, _saved("rating", "name"))

        self.assertEqual(["rating", "name", "year", "plays"],
                         [entry["colId"] for entry in state])

    def test_a_saved_column_the_grid_no_longer_has_is_left_out(self) -> None:
        state = grid.applied_state(COLUMNS, _saved("gone", "year"))

        self.assertNotIn("gone", [entry["colId"] for entry in state])

    def test_nothing_saved_is_the_declared_order(self) -> None:
        state = grid.applied_state(COLUMNS, {})

        self.assertEqual(["name", "year", "rating", "plays"],
                         [entry["colId"] for entry in state])


class ApplyLayoutTests(unittest.IsolatedAsyncioTestCase):
    async def _applied(self, stored: dict[str, Any]) -> dict[str, Any]:
        table = _Grid()
        with patch("console.api.ApiClient"), \
                patch("console.grid.offload.io", new=AsyncMock(return_value=stored)):
            await grid.apply_layout(table, "test.grid", COLUMNS)  # type: ignore[arg-type]
        [(_, applied)] = [sent for sent in table.sent if sent[0] == "applyColumnState"]
        return applied

    async def test_the_order_is_applied_with_nothing_saved(self) -> None:
        """A view with no layout of its own shows the declared order, not the one the
        last view left on the grid."""
        applied = await self._applied({})

        self.assertTrue(applied["applyOrder"])

    async def test_a_saved_order_is_applied(self) -> None:
        applied = await self._applied(
            {"columns": [{"colId": "plays"}, {"colId": "name"}]})

        self.assertTrue(applied["applyOrder"])
        self.assertEqual(["plays", "name", "year", "rating"],
                         [entry["colId"] for entry in applied["state"]])


if __name__ == "__main__":
    unittest.main()
