"""Remove selected on Locations: every location picked goes, and the list is drawn again."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from console import locations


async def _now(callback: Any, *args: Any, **kwargs: Any) -> Any:
    return callback(*args, **kwargs)


class RemoveSelected(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.library = Mock()
        self.library.delete_location.return_value = None
        self.redrawn = Mock()
        self.said = self.enterContext(patch.object(locations.ui, "notify"))
        self.enterContext(patch("nicegui.run.io_bound", new=_now))
        self.enterContext(patch.object(locations.confirm, "ask",
                                       new=AsyncMock(return_value=True)))

    async def remove(self, *ids: str) -> None:
        await locations._remove_many([{"id": one, "name": one} for one in ids],
                                     self.library, self.redrawn)

    async def test_every_location_picked_goes(self) -> None:
        await self.remove("first", "second", "third")
        self.assertEqual([one.args[0] for one in self.library.delete_location.call_args_list],
                         ["first", "second", "third"])

    async def test_the_list_is_drawn_again(self) -> None:
        await self.remove("first", "second")
        self.redrawn.assert_called_once_with()
        self.said.assert_not_called()

    async def test_a_refusal_stops_and_says_so(self) -> None:
        self.library.delete_location.side_effect = [None, OSError("busy"), None]
        await self.remove("first", "second", "third")
        self.assertEqual(self.library.delete_location.call_count, 2)
        self.said.assert_called_once()
        self.redrawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
