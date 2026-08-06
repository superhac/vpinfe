"""Settings are stored as JSON, and an ini is read once and kept.

Two things this has to get right, because both are somebody's install. A fresh one has
to come up with no file and no hand-editing at all - the whole first-run path had no
test before this. And an existing `vpinfe.ini` has to convert without losing a value,
without being deleted, and without converting twice.
"""

from __future__ import annotations

import json
import os
import unittest

from common import config_schema
from common.config_store import (
    CURRENT_SCHEMA,
    SCHEMA_KEY,
    SETTINGS_KEY,
    ConfigStore,
    _flatten,
)
from tests.support.library import TempTree


class ConfigStoreTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.ini = self.root / "vpinfe.ini"
        self.json = self.root / "vpinfe.json"

    def _payload(self) -> dict:
        return json.loads(self.json.read_text(encoding="utf-8"))


class FirstRunTests(ConfigStoreTests):
    """Chris's acceptance criterion: a fresh install never needs the file opened."""

    def test_a_fresh_install_writes_a_complete_config(self) -> None:
        store = ConfigStore(str(self.ini))

        self.assertTrue(store.is_new, "first run has to announce itself - main.py "
                                      "uses this to open the Manager UI")
        self.assertTrue(self.json.exists())
        self.assertFalse(self.ini.exists(), "nothing writes an ini any more")

        # Flattened first: on disk a window is a nested object, in the schema it is a
        # dotted section name. Case-folded because configparser lowercases option names
        # and always did - MMhideQuitButton reached the old ini lowercase too.
        settings = _flatten(self._payload()[SETTINGS_KEY])
        self.assertEqual(
            {s: {k.lower() for k in v} for s, v in settings.items()},
            {s: {k.lower() for k in v} for s, v in config_schema.defaults().items()})

    def test_the_three_settings_the_readme_asks_for_are_present(self) -> None:
        """readme.md walks a new user through these in the Manager UI."""
        store = ConfigStore(str(self.ini))

        for key in ("vpx_bin_path", "game_root_dir", "vpx_ini_path"):
            self.assertTrue(store.config.has_option("Settings", key))

    def test_a_second_run_is_not_a_first_run(self) -> None:
        ConfigStore(str(self.ini))
        self.assertFalse(ConfigStore(str(self.ini)).is_new)

    def test_the_file_carries_a_schema_version(self) -> None:
        ConfigStore(str(self.ini))
        self.assertEqual(self._payload()[SCHEMA_KEY], CURRENT_SCHEMA)


class TypedValueTests(ConfigStoreTests):
    def test_bools_and_ints_are_stored_as_bools_and_ints(self) -> None:
        ConfigStore(str(self.ini))
        settings = self._payload()[SETTINGS_KEY]

        self.assertIs(settings["Displays"]["cab_mode"], False)
        self.assertEqual(settings["Network"]["manager_ui_port"], 8001)
        self.assertIsInstance(settings["Network"]["manager_ui_port"], int)

    def test_a_blank_int_stays_blank_rather_than_becoming_zero(self) -> None:
        """Blank means "no window on this one", which is not the same as screen 0."""
        ConfigStore(str(self.ini))
        self.assertEqual(
            self._payload()[SETTINGS_KEY]["windows"]["backglass"]["screen_id"], "")

    def test_values_survive_the_round_trip_as_text(self) -> None:
        first = ConfigStore(str(self.ini))
        first.config.set("Displays", "cab_mode", "true")
        first.config.set("Network", "manager_ui_port", "9001")
        first.save()

        second = ConfigStore(str(self.ini))
        self.assertTrue(second.config.getboolean("Displays", "cab_mode"))
        self.assertEqual(second.config.get("Network", "manager_ui_port"), "9001")


class IniConversionTests(ConfigStoreTests):
    def _write_ini(self, body: str) -> None:
        self.ini.write_text(body, encoding="utf-8")

    def test_an_existing_ini_converts_and_is_kept(self) -> None:
        self._write_ini("[Settings]\ngamerootdir = /my/tables\n")

        ConfigStore(str(self.ini))

        self.assertEqual(self._payload()[SETTINGS_KEY]["Settings"]["game_root_dir"],
                         "/my/tables")
        self.assertTrue(self.ini.exists(), "a downgrade needs the file 2.x reads")
        backups = [n for n in os.listdir(self.root) if n.startswith("vpinfe.ini.")]
        self.assertEqual(len(backups), 1, "the pre-JSON file is copied aside once")

    def test_converting_still_applies_the_key_renames(self) -> None:
        """tablerootdir became gamerootdir; an old ini must not lose the value."""
        self._write_ini("[Settings]\ntablerootdir = /old/tables\n")

        ConfigStore(str(self.ini))

        settings = self._payload()[SETTINGS_KEY]["Settings"]
        self.assertEqual(settings["game_root_dir"], "/old/tables")
        self.assertNotIn("tablerootdir", settings)

    def test_a_user_value_is_typed_on_the_way_in(self) -> None:
        self._write_ini("[Displays]\nplayfieldscreenid = 2\ncabmode = true\n")

        ConfigStore(str(self.ini))

        settings = self._payload()[SETTINGS_KEY]
        self.assertEqual(settings["windows"]["playfield"]["screen_id"], 2)
        self.assertIs(settings["Displays"]["cab_mode"], True)

    def test_conversion_happens_once(self) -> None:
        self._write_ini("[Settings]\ngamerootdir = /my/tables\n")
        ConfigStore(str(self.ini))
        after_first = sorted(os.listdir(self.root))

        ConfigStore(str(self.ini))

        self.assertEqual(sorted(os.listdir(self.root)), after_first,
                         "a second run must not back the ini up again")

    def test_json_wins_when_both_exist(self) -> None:
        """The ini is left in place, so it must not overwrite newer settings."""
        ConfigStore(str(self.ini))
        self._write_ini("[Settings]\ngamerootdir = /stale\n")

        store = ConfigStore(str(self.ini))

        self.assertNotEqual(store.config.get("Settings", "game_root_dir"), "/stale")

    def test_a_newer_schema_is_not_stamped_down(self) -> None:
        """A future VPinFE owns that number; claiming it would say we understood it."""
        ConfigStore(str(self.ini))
        payload = self._payload()
        payload[SCHEMA_KEY] = CURRENT_SCHEMA + 5
        self.json.write_text(json.dumps(payload), encoding="utf-8")

        store = ConfigStore(str(self.ini))
        store.save()

        self.assertEqual(self._payload()[SCHEMA_KEY], CURRENT_SCHEMA + 5)


if __name__ == "__main__":
    unittest.main()
