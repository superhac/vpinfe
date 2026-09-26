"""What the Enabled switch does before it switches a launcher off."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from common.i18n import t
from console import workbench
from tests.support.clicks import press

LAUNCHER = {"launcher_id": "wide", "display_name": "VPX (4K)", "app_name": "Visual Pinball X"}


def _fallback(tables: int = 0, fallbacks: tuple = (), refused: str = "") -> dict:
    return {"tables": tables, "refused": refused,
            "fallbacks": [{"launcher_id": key, "display_name": name, "tables": count,
                           "has_program": True} for key, name, count in fallbacks]}


class SwitchingOff(unittest.IsolatedAsyncioTestCase):
    async def _switch_off(self, found: dict, answer: bool = True):
        ask = AsyncMock(return_value=answer)
        notify = Mock()
        with patch.object(workbench.offload, "io", new=AsyncMock(return_value=found)), \
                patch.object(workbench.confirm, "ask", new=ask), \
                patch.object(workbench.ui, "notify", new=notify):
            agreed = await press(workbench._agreed_to_switch_off, Mock(), LAUNCHER)
        return agreed, ask, notify

    async def test_one_no_table_uses_goes_off_without_asking(self) -> None:
        agreed, ask, notify = await self._switch_off(_fallback())

        self.assertTrue(agreed)
        ask.assert_not_awaited()
        notify.assert_not_called()

    async def test_a_refusal_is_shown_and_nothing_is_asked(self) -> None:
        refused = t("error.launchers.fallback_has_no_program", name="Visual Pinball X")
        agreed, ask, notify = await self._switch_off(
            _fallback(4, (("plain", "Visual Pinball X", 4),), refused))

        self.assertFalse(agreed)
        ask.assert_not_awaited()
        self.assertEqual(notify.call_args.args[0], refused)

    async def test_the_confirm_counts_the_tables_and_names_where_they_go(self) -> None:
        agreed, ask, _notify = await self._switch_off(
            _fallback(4, (("plain", "Visual Pinball X", 4),)))

        self.assertTrue(agreed)
        self.assertEqual(ask.call_args.args[0],
                         t("console.workbench.switch_off_name", name="VPX (4K)"))
        self.assertEqual(ask.call_args.kwargs["detail"],
                         t("console.workbench.switched_off_launch_with", count=4,
                           fallback="Visual Pinball X"))
        self.assertFalse(ask.call_args.kwargs["danger"])

    async def test_cancelling_leaves_it_on(self) -> None:
        agreed, _ask, _notify = await self._switch_off(
            _fallback(1, (("plain", "Visual Pinball X", 1),)), answer=False)

        self.assertFalse(agreed)

    async def test_tables_going_to_more_than_one_launcher_get_a_line_each(self) -> None:
        _agreed, ask, _notify = await self._switch_off(
            _fallback(4, (("plain", "Visual Pinball X", 3), ("fp", "Future Pinball", 1))))

        self.assertEqual(list(ask.call_args.kwargs["lines"]), [
            t("console.workbench.count_launch_with", count=3, name="Visual Pinball X"),
            t("console.workbench.count_launch_with", count=1, name="Future Pinball"),
        ])


if __name__ == "__main__":
    unittest.main()
