from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from screeninfo import Monitor

from common import config_schema, config_service
from common.host import display_service
from common.i18n import t
from console import panel, settings
from frontend.chromium_manager import MonitorInfo

WINDOWS = ("windows.playfield", "windows.backglass", "windows.score_view")

# As screeninfo reports them, which is the list the frontend opens windows by on Linux and
# Windows...
WIDE = Monitor(x=0, y=0, width=2560, height=1440, width_mm=597, height_mm=336,
               name="DP-1", is_primary=True)
TALL = Monitor(x=2560, y=0, width=1080, height=1920, width_mm=336, height_mm=597,
               name="HDMI-1", is_primary=False)
# ...and as the frontend reads them for itself on macOS.
BUILT_IN = MonitorInfo(x=0, y=0, width=1728, height=1117)
BESIDE = MonitorInfo(x=1728, y=-200, width=1920, height=1080)


def _option(section: str) -> dict[str, Any]:
    return next(option for block in config_service.schema()["sections"]
                if block["name"] == section
                for option in block["options"] if option["key"] == "screen_id")


class PickedFromTheScreensTests(unittest.TestCase):
    def _drawn(self, section: str, value: Any, screens: list[Any]) -> tuple[Mock, Mock, Mock]:
        save = Mock()
        with patch.object(panel, "select") as select, patch.object(panel, "number") as number:
            settings.control_for(_option(section), value, save,
                                 suggestions={config_schema.SUGGEST_SCREENS: screens})
        return select, number, save

    def test_each_window_s_screen_is_one_of_the_screens_and_not_a_number(self) -> None:
        for section in WINDOWS:
            with self.subTest(section=section):
                select, number, _ = self._drawn(section, 0, [WIDE, TALL])

                number.assert_not_called()
                self.assertEqual(select.call_args.args[1], "0")
                self.assertEqual(
                    {key: label for key, label in select.call_args.args[0].items() if key},
                    {"0": t("console.screens.at", width=2560, height=1440, x=0, y=0),
                     "1": t("console.screens.at", width=1080, height=1920, x=2560, y=0)})

    def test_the_frontend_s_own_list_on_macos_is_described_the_same_way(self) -> None:
        select, _, _ = self._drawn("windows.playfield", 0, [BUILT_IN, BESIDE])

        self.assertEqual(select.call_args.args[0],
                         {"0": "1728 x 1117 at 0, 0", "1": "1920 x 1080 at 1728, -200"})

    def test_none_is_offered_where_no_window_is_the_default(self) -> None:
        playfield, _, _ = self._drawn("windows.playfield", 0, [WIDE])
        backglass, _, _ = self._drawn("windows.backglass", "", [WIDE])

        self.assertNotIn("", playfield.call_args.args[0])
        self.assertEqual(backglass.call_args.args[0][""], t("word.none"))
        self.assertEqual(backglass.call_args.args[1], "")

    def test_a_pick_stores_the_screen_s_number(self) -> None:
        select, _, save = self._drawn("windows.backglass", "", [WIDE, TALL])
        pick = select.call_args.args[2]

        pick(SimpleNamespace(value="1"))
        pick(SimpleNamespace(value=""))

        self.assertEqual([one.args for one in save.call_args_list], [(1,), ("",)])

    def test_a_stored_screen_that_is_not_connected_stays_chosen_and_is_marked(self) -> None:
        with patch.object(panel, "value_state") as value_state:
            select, _, _ = self._drawn("windows.backglass", 2, [WIDE])

        self.assertEqual(select.call_args.args[1], "2")
        self.assertEqual(select.call_args.args[0]["2"],
                         t("console.screens.numbered", number="2"))
        value_state.assert_called_with("missing", t("console.screens.not_connected"))

    def test_a_connected_screen_or_none_is_not_marked(self) -> None:
        for value in (1, ""):
            with self.subTest(value=value), \
                    patch.object(panel, "value_state") as value_state:
                self._drawn("windows.backglass", value, [WIDE, TALL])

                self.assertEqual({one.args for one in value_state.call_args_list}, {("", "")})

    def test_where_the_screens_cannot_be_read_it_is_the_number_it_was(self) -> None:
        select, number, _ = self._drawn("windows.backglass", 2, [])

        select.assert_not_called()
        number.assert_called_once()


class TheScreensAreReadForThePageTests(unittest.IsolatedAsyncioTestCase):
    def test_every_window_the_schema_declares_offers_the_screens(self) -> None:
        self.assertEqual({section: _option(section)["suggest"] for section in WINDOWS},
                         dict.fromkeys(WINDOWS, config_schema.SUGGEST_SCREENS))

    async def test_they_are_read_again_off_the_loop_for_a_page_that_picks_one(self) -> None:
        blocks = config_service.schema()["sections"]
        self.enterContext(patch.object(
            settings.run, "io_bound",
            new=AsyncMock(side_effect=lambda call, *args, **kwargs: call(*args, **kwargs))))
        read = self.enterContext(patch.object(display_service, "get_display_monitors",
                                              return_value=[WIDE, TALL]))

        offered = await settings._suggestions(Mock(), blocks, WINDOWS)

        self.assertEqual(offered[config_schema.SUGGEST_SCREENS], [WIDE, TALL])
        read.assert_called_once_with(refresh=True)


if __name__ == "__main__":
    unittest.main()
