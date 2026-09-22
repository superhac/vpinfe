"""Which of the two places holding VPinPlay's address answers a theme."""

from __future__ import annotations

import configparser
import contextlib
import unittest
from unittest import mock

from frontend import config_api


@contextlib.contextmanager
def _endpoint_held_by(extension: str = "", config: str = ""):
    store = type("_Store", (), {
        "settings": lambda _self, _name: {"endpoint": extension} if extension else {},
    })()
    with mock.patch.object(config_api, "get_extension_store", lambda: store):
        parser = configparser.ConfigParser()
        if config:
            parser.read_dict({"vpinplay": {"api_endpoint": config}})
        yield parser


class WhichAnswerAThemeGets(unittest.TestCase):
    def test_the_extension_holds_it_once_the_handover_has_run(self) -> None:
        with _endpoint_held_by(extension="https://mine.example:9000",
                               config="https://stale.example") as parser:
            self.assertEqual(config_api.get_vpinplay_endpoint(parser),
                             "https://mine.example:9000")

    def test_the_config_answers_where_the_extension_holds_none(self) -> None:
        """VPinPlay switched off, never installed, or the handover not yet run."""
        with _endpoint_held_by(config="https://stale.example") as parser:
            self.assertEqual(config_api.get_vpinplay_endpoint(parser),
                             "https://stale.example")

    def test_nobody_holding_one_is_blank(self) -> None:
        with _endpoint_held_by() as parser:
            self.assertEqual(config_api.get_vpinplay_endpoint(parser), "")


if __name__ == "__main__":
    unittest.main()
