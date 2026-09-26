"""A location or launcher just added: the grid drawn again lands on its row, and the
panel opens on it."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from console import launchers, locations


class LocationAdded(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.order: list[str] = []
        self.state: dict[str, Any] = {}
        self.landed = self.enterContext(patch.object(
            locations.grid, "land_on", side_effect=lambda *_: self.order.append("land")))
        self.enterContext(patch.object(locations.model, "mint_location_id",
                                       return_value="loc-new"))
        self.put = self.enterContext(patch.object(locations.run, "io_bound", new=AsyncMock()))
        self.enterContext(patch.object(locations.ui, "notify"))
        self.shown = AsyncMock(side_effect=lambda _row: self.order.append("show"))

    async def add(self) -> None:
        await locations._create(Mock(), self.state,
                                lambda: self.order.append("redraw"), self.shown,
                                "root", "/games")

    async def test_the_new_row_is_landed_on_before_the_grid_is_drawn_again(self) -> None:
        await self.add()
        self.landed.assert_called_once_with(locations.SCOPE, {"id": "loc-new"})
        self.assertEqual(self.order, ["land", "redraw", "show"])

    async def test_the_panel_opens_on_it(self) -> None:
        await self.add()
        self.shown.assert_awaited_once_with({"id": "loc-new"})
        self.assertEqual(self.state["location"], "loc-new")

    async def test_a_refused_add_lands_nowhere(self) -> None:
        self.put.side_effect = OSError("read-only")
        await self.add()
        self.landed.assert_not_called()
        self.shown.assert_not_awaited()
        self.assertEqual(self.order, [])


class LauncherAdded(unittest.IsolatedAsyncioTestCase):
    async def test_the_new_row_is_landed_on_and_opened(self) -> None:
        order: list[str] = []
        shown = AsyncMock(side_effect=lambda _row: order.append("show"))
        state: dict[str, Any] = {"show_launcher": shown}
        with patch.object(launchers.grid, "land_on",
                          side_effect=lambda *_: order.append("land")) as landed:
            await launchers._open(state, lambda: order.append("redraw"), "wide-copy")
        landed.assert_called_once_with(launchers.SCOPE, {"id": "wide-copy"})
        shown.assert_awaited_once_with({"id": "wide-copy"})
        self.assertEqual(order, ["land", "redraw", "show"])


if __name__ == "__main__":
    unittest.main()
