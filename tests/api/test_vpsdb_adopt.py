"""The catalog sweep: when it is owed, and when it must not run."""

from __future__ import annotations

import configparser
import unittest

from common.online import vpsdb_sync


class _Config:
    """A ConfigStore's surface, as much of it as this reads."""

    def __init__(self, **vpsdb: str) -> None:
        self.config = configparser.ConfigParser()
        self.config.add_section("vpsdb")
        for key, value in vpsdb.items():
            self.config.set("vpsdb", key, value)
        self.saved = 0

    def save(self) -> None:
        self.saved += 1


def _config(**vpsdb: str) -> _Config:
    return _Config(**vpsdb)


class WhenASweepIsOwed(unittest.TestCase):
    def test_off_by_default(self) -> None:
        """Read off the schema, which is where the default actually lives. A config
        object that has never had the key set falls back to whatever the caller passed,
        so asking one of those proves nothing."""
        from common.config_schema import options

        declared = next(one for one in options()
                        if one.section == "vpsdb" and one.key == "update_matched_games")
        self.assertEqual("never", declared.default)

    def test_a_config_with_nothing_set_is_owed_nothing(self) -> None:
        self.assertFalse(vpsdb_sync.adopt_due(_config(last="2026-09-22")))

    def test_never_is_never_even_with_a_new_catalog(self) -> None:
        self.assertFalse(vpsdb_sync.adopt_due(
            _config(update_matched_games="never", last="2026-09-22",
                    games_updated_to="2026-01-01")))

    def test_a_catalog_that_moved_is_owed_one(self) -> None:
        self.assertTrue(vpsdb_sync.adopt_due(
            _config(update_matched_games="daily", last="2026-09-22",
                    games_updated_to="2026-01-01")))

    def test_a_catalog_that_has_not_moved_is_not(self) -> None:
        self.assertFalse(vpsdb_sync.adopt_due(
            _config(update_matched_games="daily", last="2026-09-22",
                    games_updated_to="2026-09-22")))

    def test_never_swept_and_a_catalog_in_hand_is_owed_one(self) -> None:
        self.assertTrue(vpsdb_sync.adopt_due(
            _config(update_matched_games="weekly", last="2026-09-22")))

    def test_no_catalog_yet_is_not(self) -> None:
        self.assertFalse(vpsdb_sync.adopt_due(_config(update_matched_games="daily", last="")))

    def test_a_typo_reads_as_off_rather_than_as_daily(self) -> None:
        self.assertFalse(vpsdb_sync.adopt_due(
            _config(update_matched_games="dayly", last="2026-09-22",
                    games_updated_to="2026-01-01")))


class TheTwoSchedulesAreSeparate(unittest.TestCase):
    def test_fetching_daily_does_not_sweep(self) -> None:
        held = _config(download="daily", last="2026-09-22", games_updated_to="2026-01-01")
        self.assertFalse(vpsdb_sync.adopt_due(held))

    def test_sweeping_does_not_require_fetching(self) -> None:
        held = _config(download="never", update_matched_games="daily",
                       last="2026-09-22", games_updated_to="2026-01-01")
        self.assertTrue(vpsdb_sync.adopt_due(held))


if __name__ == "__main__":
    unittest.main()
