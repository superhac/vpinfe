"""Keeping the local catalog current, and knowing when a check is owed.

Everything VPS-shaped reads a file: matching, release lists, obtainability, what a kind
is offered from. Until this existed the only thing that downloaded it was a Manager UI
page, so a hub that never opened one answered from the snapshot it started with.
"""

from __future__ import annotations

import configparser
import unittest
from unittest.mock import patch

from common import timestamps
from common.online import vpsdb_sync


def _config(**vpsdb: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.add_section("vpsdb")
    for key, value in vpsdb.items():
        parser.set("vpsdb", key, value)
    return parser


def _ago(seconds: float) -> str:
    now = timestamps.iso_to_epoch(timestamps.utc_now_iso()) or 0
    return timestamps.epoch_to_iso(now - seconds)


class DueTests(unittest.TestCase):
    def test_never_checked_is_due(self) -> None:
        """A fresh install holding no catalog should not wait a day for one."""
        self.assertTrue(vpsdb_sync.due(_config(refresh="daily")))

    def test_never_is_not_an_interval(self) -> None:
        """It is a decision not to ask, not a very long wait - so even never having
        asked does not make it due."""
        self.assertFalse(vpsdb_sync.due(_config(refresh="never")))

    def test_inside_the_interval_is_not_due(self) -> None:
        self.assertFalse(vpsdb_sync.due(_config(refresh="daily", checked=_ago(3600))))

    def test_past_the_interval_is_due(self) -> None:
        self.assertTrue(vpsdb_sync.due(_config(refresh="daily", checked=_ago(90000))))

    def test_a_longer_schedule_holds_longer(self) -> None:
        day_old = _ago(90000)
        self.assertTrue(vpsdb_sync.due(_config(refresh="daily", checked=day_old)))
        self.assertFalse(vpsdb_sync.due(_config(refresh="weekly", checked=day_old)))

    def test_a_schedule_this_build_does_not_know_asks_nothing(self) -> None:
        """A config from a newer build must not be read as "every time"."""
        self.assertFalse(vpsdb_sync.due(_config(refresh="hourly")))


class SyncTests(unittest.TestCase):
    def test_not_due_does_not_download(self) -> None:
        config = _config(refresh="daily", checked=_ago(60))
        with patch("common.games.game_service.ensure_vpsdb_downloaded") as fetch:
            result = vpsdb_sync.sync(config)

        fetch.assert_not_called()
        self.assertFalse(result["checked"])

    def test_forced_ignores_the_schedule(self) -> None:
        """Asked for by a person. Answering "not due" would report a rule back to
        whoever is overriding it."""
        config = _config(refresh="never", checked=_ago(60))
        with patch("common.games.game_service.ensure_vpsdb_downloaded",
                   return_value=True) as fetch:
            result = vpsdb_sync.sync(config, force=True)

        fetch.assert_called_once()
        self.assertTrue(result["checked"])

    def test_a_check_that_found_nothing_new_says_so(self) -> None:
        config = _config(refresh="daily", last="1788355140571")
        with patch("common.games.game_service.ensure_vpsdb_downloaded",
                   return_value=True):
            result = vpsdb_sync.sync(config, force=True)

        self.assertTrue(result["ok"])
        self.assertFalse(result["changed"])

    def test_a_failed_check_still_stamps(self) -> None:
        """Or an unreachable catalog is re-asked on every draw."""
        config = _config(refresh="daily")
        with patch("common.games.game_service.ensure_vpsdb_downloaded",
                   return_value=False):
            vpsdb_sync.sync(config, force=True)

        self.assertTrue(vpsdb_sync.checked_at(config))
        self.assertFalse(vpsdb_sync.due(config))


if __name__ == "__main__":
    unittest.main()
