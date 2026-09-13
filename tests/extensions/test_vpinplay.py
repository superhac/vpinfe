"""VPinPlay as an extension: the rating, contributed rather than fetched by the page.

What is pinned is the shape and the handover. The shape because twelve published themes
read `item.vpinplay` and would break on a change to no purpose; the handover because an
install already using VPinPlay must not be asked to say again where it is.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from common.config_store import ConfigStore
from common.extensions import contributions, handover, host, store

REPO = Path(__file__).resolve().parents[2]


def _extension():
    registry = host.Registry()
    record = registry.load(host.BUNDLED_DIR / "vpinplay")
    assert record.state == host.LOADED, record.reason
    import importlib

    return importlib.import_module("vpinfe_ext_vpinplay.client")


class ShapeTests(unittest.TestCase):
    """The answer a theme reads, which is the answer it read before."""

    def setUp(self) -> None:
        self.client = _extension()

    def test_the_payload_carries_the_fields_themes_already_read(self) -> None:
        found = self.client.normalize("vps-1", {
            "vpsId": "vps-1", "cumulativeRating": 4.5, "ratingCount": 12,
            "vpsdb": {"name": "Taxi", "authors": ["a"], "manufacturer": "Williams",
                      "year": 1988},
        })

        self.assertEqual(sorted(found),
                         ["cumulativeRating", "fetchedAt", "ratingCount", "vpsId",
                          "vpsdb"])
        self.assertEqual(sorted(found["vpsdb"]),
                         ["authors", "manufacturer", "name", "year"])

    def test_what_the_server_sends_is_coerced_rather_than_trusted(self) -> None:
        """A theme calling ratingCount.toFixed() should not be what discovers it was a
        string."""
        found = self.client.normalize("vps-1", {"cumulativeRating": "4.5",
                                                "ratingCount": "12", "vpsdb": "nonsense"})

        self.assertEqual(found["cumulativeRating"], 4.5)
        self.assertEqual(found["ratingCount"], 12)
        self.assertEqual(found["vpsdb"]["authors"], [])

    def test_a_year_is_a_whole_number(self) -> None:
        """The browser produced this, and JavaScript has one number type. Python would
        send 1995.0 to anything reading over REST, which is a different value to a
        reader that cares."""
        found = self.client.normalize("vps-1", {"vpsdb": {"year": 1995}})

        self.assertEqual(found["vpsdb"]["year"], 1995)
        self.assertNotIsInstance(found["vpsdb"]["year"], float)

    def test_a_year_that_is_not_one_falls_back_to_text(self) -> None:
        """A catalog says "1995-06" and it says "unknown", and both are years somebody
        wrote. Anything that is neither a number nor text is not a year in any reading,
        and passing it through leaves the field holding neither."""
        for raw, expected in (("1995-06", "1995-06"), ("unknown", "unknown"),
                              (True, ""), ([], ""), (None, "")):
            with self.subTest(raw=raw):
                found = self.client.normalize("v", {"vpsdb": {"year": raw}})

                self.assertEqual(found["vpsdb"]["year"], expected)

    def test_a_count_that_is_missing_is_none_rather_than_absent(self) -> None:
        found = self.client.normalize("vps-1", {})

        self.assertEqual(found["ratingCount"], 0)
        self.assertIsNone(found["cumulativeRating"])

    def test_an_answer_that_is_not_an_object_is_nothing(self) -> None:
        self.assertIsNone(self.client.normalize("vps-1", "down for maintenance"))

    def test_the_url_is_the_one_the_page_used_to_build(self) -> None:
        self.assertEqual(
            self.client.rating_url("https://api.example.com:8888/", "abc-1"),
            "https://api.example.com:8888/api/v1/tables/abc-1/cumulative-rating")

    def test_nothing_to_ask_about_is_no_url(self) -> None:
        self.assertEqual(self.client.rating_url("", "abc"), "")
        self.assertEqual(self.client.rating_url("https://x", ""), "")


class ContributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = store.ExtensionStore(self.root / "extensions.json")
        contributions.clear()
        self.addCleanup(contributions.clear)
        self.registry = host.Registry(self.store)
        self.addCleanup(self.registry.clear)
        self.record = self.registry.load(host.BUNDLED_DIR / "vpinplay")
        self.assertEqual(self.record.state, host.LOADED, self.record.reason)

    def test_it_contributes_under_the_key_a_theme_reads(self) -> None:
        self.assertIn("vpinplay", contributions.keys())

    def test_a_game_no_catalog_matched_is_never_asked_about(self) -> None:
        """It has no id VPinPlay knows it by, which is not a failure."""
        with patch("vpinfe_ext_vpinplay.client.fetch") as asked:
            found = contributions.refresh({"game_id": "abc", "vps_id": ""})

        asked.assert_not_called()
        self.assertEqual(found, {})

    def test_the_catalog_id_is_what_it_asks_about(self) -> None:
        with patch("vpinfe_ext_vpinplay.client.fetch",
                   return_value={"vpsId": "vps-1"}) as asked:
            contributions.refresh({"game_id": "abc", "vps_id": "vps-1"})

        self.assertEqual(asked.call_args.args[1], "vps-1")


class HandoverTests(unittest.TestCase):
    """An install already using VPinPlay must not be asked to say again where it is."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = store.ExtensionStore(self.root / "extensions.json")
        self.config = ConfigStore(str(self.root / "vpinfe.ini"))

    def test_what_core_was_configured_with_becomes_the_extensions_own(self) -> None:
        from common.config_access import cfg_set

        cfg_set(self.config, "vpinplay", "api_endpoint", "https://mine.example:9000")
        cfg_set(self.config, "vpinplay", "user_id", "chris")
        self.config.save()

        handover.seed(self.store, self.config)

        held = self.store.settings("vpinplay")
        self.assertEqual(held["endpoint"], "https://mine.example:9000")
        self.assertEqual(held["user_id"], "chris")

    def test_it_runs_once(self) -> None:
        from common.config_access import cfg_set

        cfg_set(self.config, "vpinplay", "api_endpoint", "https://mine.example:9000")
        self.config.save()
        handover.seed(self.store, self.config)
        self.store.set_setting("vpinplay", "endpoint", "https://moved.example")

        handover.seed(self.store, self.config)

        self.assertEqual(self.store.settings("vpinplay")["endpoint"],
                         "https://moved.example")

    def test_a_shared_default_is_not_handed_over(self) -> None:
        """A fresh config file holds every default, so "not empty" would hand over the
        whole section - and a default in an extension's file pins it to whatever core's
        was on the day it was installed, with the two free to drift after."""
        handover.seed(self.store, self.config)

        held = self.store.settings("vpinplay")

        self.assertNotIn("endpoint", held)
        self.assertNotIn("sync_on_exit", held)

    def test_an_identity_this_install_generated_is_handed_over(self) -> None:
        """Not a default even though nobody typed it: the machine id is minted per
        install, and an extracted VPinPlay has to keep being the same machine."""
        handover.seed(self.store, self.config)

        self.assertTrue(self.store.settings("vpinplay")["machine_id"])

    def test_the_old_section_is_left_where_it_is(self) -> None:
        """A reverted install has to still find what its user typed."""
        from common.config_access import cfg_get, cfg_set

        cfg_set(self.config, "vpinplay", "user_id", "chris")
        self.config.save()

        handover.seed(self.store, self.config)

        self.assertEqual(cfg_get(self.config, "vpinplay", "user_id"), "chris")


if __name__ == "__main__":
    unittest.main()
