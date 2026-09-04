"""What a library collects, which is the library's answer and not a machine's.

These three lived in each install's config file. One machine, no problem; two devices
reading one hub and there were two answers to a question about one set of files, and
only the hub's ever did anything.
"""

from __future__ import annotations

import configparser
import json
import unittest

from common.games.library_policy import SCHEMA, SCHEMA_KEY, LibraryPolicy
from tests.support.library import TempTree


def _config(values: dict[tuple[str, str], str]) -> configparser.ConfigParser:
    """A config the accessors can read. A bare parser, which is what `cfg_get` unwraps a
    store down to - so this exercises the same read path the real one takes."""
    parser = configparser.ConfigParser()
    for (section, key), value in values.items():
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, key, value)
    return parser


class LibraryPolicyTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.policy = LibraryPolicy(self.root / "library.json")

    def test_a_library_nobody_has_narrowed_collects_everything(self) -> None:
        """Empty in all three, so a kind added in a later version arrives switched on."""
        self.assertEqual(self.policy.values(),
                         {"hidden_media_kinds": [], "hidden_asset_kinds": [],
                          "asset_sources": []})

    def test_what_is_set_is_what_is_read_back(self) -> None:
        self.policy.set("hidden_media_kinds", ["loading", "audio"])

        self.assertEqual(self.policy.get("hidden_media_kinds"), ["loading", "audio"])

    def test_setting_one_leaves_the_others(self) -> None:
        self.policy.set("hidden_media_kinds", ["loading"])
        self.policy.set("asset_sources", ["vpuniverse"])

        self.assertEqual(self.policy.get("hidden_media_kinds"), ["loading"])
        self.assertEqual(self.policy.get("asset_sources"), ["vpuniverse"])

    def test_clearing_one_is_an_answer_rather_than_a_missing_one(self) -> None:
        """Empty means everything, so storing empty is how "collect it all" is said."""
        self.policy.set("hidden_asset_kinds", ["rom"])
        self.policy.set("hidden_asset_kinds", [])

        self.assertEqual(self.policy.get("hidden_asset_kinds"), [])

    def test_a_comma_string_reads_as_a_list(self) -> None:
        """Which is how an ini held one, and what the adoption below hands over."""
        self.policy.set("hidden_media_kinds", "loading, audio")

        self.assertEqual(self.policy.get("hidden_media_kinds"), ["loading", "audio"])

    def test_it_refuses_a_key_that_is_not_a_library_policy(self) -> None:
        with self.assertRaises(ValueError):
            self.policy.set("game_root_dir", "/tables")

    def test_it_survives_being_reopened(self) -> None:
        self.policy.set("asset_sources", ["vpsdb"])

        self.assertEqual(LibraryPolicy(self.policy.path).get("asset_sources"),
                         ["vpsdb"])

    def test_the_file_carries_its_own_schema(self) -> None:
        self.policy.set("asset_sources", ["vpsdb"])

        payload = json.loads(self.policy.path.read_text(encoding="utf-8"))
        self.assertEqual(payload[SCHEMA_KEY], SCHEMA)

    def test_an_unreadable_file_collects_everything_rather_than_failing(self) -> None:
        """Empty means everything, so the library keeps working while somebody fixes it."""
        self.policy.path.write_text("{ not json", encoding="utf-8")

        with self.assertLogs("vpinfe.common.games.library_policy", level="WARNING"):
            self.assertEqual(self.policy.get("asset_sources"), [])


class AdoptionTests(TempTree):
    """The one-time move out of an install's config."""

    def setUp(self) -> None:
        super().setUp()
        self.policy = LibraryPolicy(self.root / "library.json")
        self.config = _config({
            ("general", "hidden_media_kinds"): "loading,audio",
            ("media", "asset_sources"): "vpuniverse",
        })

    def test_what_the_config_held_moves_across(self) -> None:
        self.assertTrue(self.policy.adopt_from_config(self.config))

        self.assertEqual(self.policy.get("hidden_media_kinds"), ["loading", "audio"])
        self.assertEqual(self.policy.get("asset_sources"), ["vpuniverse"])

    def test_a_config_that_narrowed_nothing_adopts_nothing(self) -> None:
        empty = LibraryPolicy(self.root / "other.json")

        self.assertTrue(empty.adopt_from_config(_config({})))
        self.assertEqual(empty.values(), {"hidden_media_kinds": [],
                                          "hidden_asset_kinds": [],
                                          "asset_sources": []})

    def test_it_runs_once_and_never_undoes_a_later_change(self) -> None:
        """The trap this exists to avoid: re-reading a config that still carries the old
        values would put them back over everything changed since."""
        self.policy.adopt_from_config(self.config)
        self.policy.set("hidden_media_kinds", [])

        self.assertFalse(self.policy.adopt_from_config(self.config))
        self.assertEqual(self.policy.get("hidden_media_kinds"), [])

    def test_the_config_is_left_alone(self) -> None:
        """A device downgrading to a build that reads them still finds what it had."""
        self.policy.adopt_from_config(self.config)

        self.assertEqual(self.config.get("general", "hidden_media_kinds"),
                         "loading,audio")


if __name__ == "__main__":
    unittest.main()
