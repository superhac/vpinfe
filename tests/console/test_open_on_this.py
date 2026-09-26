"""A collection's Open on This: the one setting the frontend opens on, from its panel."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from common.i18n import t
from console import workbench
from tests.support.clicks import press


async def _now(callback: Any, *args: Any, **kwargs: Any) -> Any:
    return callback(*args, **kwargs)


class OpenOnThis(unittest.IsolatedAsyncioTestCase):
    def _drawn(self, name: str, opens_on: str) -> tuple[bool, Any, str, dict[str, Any]]:
        context = {"library": Mock(), "state": {},
                   "settings": {"behavior": {"startup_collection": opens_on}}}
        drawn: dict[str, Any] = {}

        def switch(value: bool, on_change: Any, *, hint: str = "", **_: Any) -> Any:
            drawn.update(value=value, on_change=on_change, hint=hint)
            return lambda: None

        with patch.object(workbench.panel, "switch", new=switch):
            workbench._opens_on_switch(context, {"name": name})
        return drawn["value"], drawn["on_change"], drawn["hint"], context

    async def _turned(self, name: str, opens_on: str, value: bool) -> dict[str, Any]:
        _, changed, _, context = self._drawn(name, opens_on)
        with patch.object(workbench.run, "io_bound", new=_now), \
                patch.object(workbench, "_written", new=AsyncMock()) as written:
            await press(changed, SimpleNamespace(value=value))
        context["written"] = written
        return context

    def test_on_where_the_frontend_opens_on_it_and_off_saying_so(self) -> None:
        value, _, hint, _ = self._drawn("Friday Night", "Friday Night")

        self.assertEqual((True, t("console.workbench.open_on_this.here")), (value, hint))

    def test_off_names_the_collection_it_would_take_over_from(self) -> None:
        value, _, hint, _ = self._drawn("90s Bally", "Friday Night")

        self.assertEqual(
            (False, t("console.workbench.open_on_this.elsewhere", name="Friday Night")),
            (value, hint))

    def test_off_with_nothing_set_says_all_games(self) -> None:
        self.assertEqual(t("console.workbench.open_on_this.everything"),
                         self._drawn("90s Bally", "")[2])

    async def test_on_writes_the_setting_settings_writes(self) -> None:
        context = await self._turned("90s Bally", "Friday Night", True)

        context["library"].put_config.assert_called_once_with(
            {"behavior": {"startup_collection": "90s Bally"}})
        context["written"].assert_awaited_once()

    async def test_off_opens_the_frontend_on_all_games(self) -> None:
        context = await self._turned("Friday Night", "Friday Night", False)

        context["library"].put_config.assert_called_once_with(
            {"behavior": {"startup_collection": ""}})

    async def test_the_value_it_already_has_writes_nothing(self) -> None:
        context = await self._turned("Friday Night", "Friday Night", True)

        context["library"].put_config.assert_not_called()
        context["written"].assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
