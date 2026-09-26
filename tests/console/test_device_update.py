"""The question put before a device replaces itself with the published build."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from common.i18n import t
from console import devices, verbs

UPDATE = {"latest_version": "v3.1.0"}


class UpdateConfirm(unittest.IsolatedAsyncioTestCase):
    async def _ask(self, playing: dict) -> AsyncMock:
        ask = AsyncMock(return_value=False)
        with patch.object(devices.offload, "io", new=AsyncMock(return_value=playing)), \
                patch.object(devices.confirm, "ask", new=ask), \
                patch.object(devices.ui, "notify", new=Mock()):
            await devices._confirm_update(Mock(), "Basement", UPDATE)
        return ask

    async def test_with_nothing_running_it_asks_to_update(self) -> None:
        ask = await self._ask({"launching": False})

        self.assertEqual(ask.call_args.kwargs["confirm"], t("console.devices.update"))
        self.assertEqual(ask.call_args.kwargs["icon"], verbs.UPDATE)
        self.assertFalse(ask.call_args.kwargs["danger"])

    async def test_with_a_table_running_it_asks_to_stop_it_first(self) -> None:
        ask = await self._ask({"launching": True, "game_name": "Medieval Madness"})

        self.assertEqual(ask.call_args.kwargs["confirm"],
                         t("console.devices.stop_table_update"))
        self.assertEqual(ask.call_args.kwargs["icon"], verbs.STOP)
        self.assertTrue(ask.call_args.kwargs["danger"])


if __name__ == "__main__":
    unittest.main()
