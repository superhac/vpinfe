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
    CONFIG_SCHEMA,
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
        """README.md walks a new user through these in the Manager UI."""
        store = ConfigStore(str(self.ini))

        for key in ("vpx_bin_path", "game_root_dir", "vpx_ini_path"):
            self.assertTrue(store.config.has_option("general", key))

    def test_a_second_run_is_not_a_first_run(self) -> None:
        ConfigStore(str(self.ini))
        self.assertFalse(ConfigStore(str(self.ini)).is_new)

    def test_the_file_carries_a_schema_version(self) -> None:
        ConfigStore(str(self.ini))
        self.assertEqual(self._payload()[SCHEMA_KEY], CONFIG_SCHEMA)


class TypedValueTests(ConfigStoreTests):
    def test_bools_and_ints_are_stored_as_bools_and_ints(self) -> None:
        ConfigStore(str(self.ini))
        settings = self._payload()[SETTINGS_KEY]

        self.assertIs(settings["displays"]["cab_mode"], False)
        self.assertEqual(settings["network"]["hub_port"], 8001)
        self.assertIsInstance(settings["network"]["hub_port"], int)

    def test_a_blank_int_stays_blank_rather_than_becoming_zero(self) -> None:
        """Blank means "no window on this one", which is not the same as screen 0."""
        ConfigStore(str(self.ini))
        self.assertEqual(
            self._payload()[SETTINGS_KEY]["windows"]["backglass"]["screen_id"], "")

    def test_an_empty_list_is_an_empty_list_rather_than_a_blank_string(self) -> None:
        """Unlike a blank int, which means something. A list setting is edited by hand,
        and "" would leave the user guessing what shape to put there."""
        ConfigStore(str(self.ini))
        self.assertEqual(self._payload()[SETTINGS_KEY]["themes"]["repositories"], [])

    def test_a_list_setting_round_trips_through_the_parser(self) -> None:
        first = ConfigStore(str(self.ini))
        first.config.set("themes", "repositories", "https://a.net/one,https://b.net/two")
        first.save()

        self.assertEqual(self._payload()[SETTINGS_KEY]["themes"]["repositories"],
                         ["https://a.net/one", "https://b.net/two"])
        second = ConfigStore(str(self.ini))
        self.assertEqual(second.config.get("themes", "repositories"),
                         "https://a.net/one,https://b.net/two")

    def test_values_survive_the_round_trip_as_text(self) -> None:
        first = ConfigStore(str(self.ini))
        first.config.set("displays", "cab_mode", "true")
        first.config.set("network", "hub_port", "9001")
        first.save()

        second = ConfigStore(str(self.ini))
        self.assertTrue(second.config.getboolean("displays", "cab_mode"))
        self.assertEqual(second.config.get("network", "hub_port"), "9001")


class IniConversionTests(ConfigStoreTests):
    def _write_ini(self, body: str) -> None:
        self.ini.write_text(body, encoding="utf-8")

    def test_an_existing_ini_converts_and_is_kept(self) -> None:
        self._write_ini("[Settings]\ngamerootdir = /my/tables\n")

        ConfigStore(str(self.ini))

        self.assertEqual(self._payload()[SETTINGS_KEY]["general"]["game_root_dir"],
                         "/my/tables")
        self.assertTrue(self.ini.exists(), "a downgrade needs the file 2.x reads")
        backups = [n for n in os.listdir(self.root) if n.startswith("vpinfe.ini.")]
        self.assertEqual(len(backups), 1, "the pre-JSON file is copied aside once")

    def test_converting_still_applies_the_key_renames(self) -> None:
        """tablerootdir became gamerootdir; an old ini must not lose the value."""
        self._write_ini("[Settings]\ntablerootdir = /old/tables\n")

        ConfigStore(str(self.ini))

        settings = self._payload()[SETTINGS_KEY]["general"]
        self.assertEqual(settings["game_root_dir"], "/old/tables")
        self.assertNotIn("tablerootdir", settings)

    def test_a_user_value_is_typed_on_the_way_in(self) -> None:
        self._write_ini("[Displays]\nplayfieldscreenid = 2\ncabmode = true\n")

        ConfigStore(str(self.ini))

        settings = self._payload()[SETTINGS_KEY]
        self.assertEqual(settings["windows"]["playfield"]["screen_id"], 2)
        self.assertIs(settings["displays"]["cab_mode"], True)

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

        self.assertNotEqual(store.config.get("general", "game_root_dir"), "/stale")

    def test_a_newer_schema_is_not_stamped_down(self) -> None:
        """A future VPinFE owns that number; claiming it would say we understood it."""
        ConfigStore(str(self.ini))
        payload = self._payload()
        payload[SCHEMA_KEY] = CONFIG_SCHEMA + 5
        self.json.write_text(json.dumps(payload), encoding="utf-8")

        store = ConfigStore(str(self.ini))
        store.save()

        self.assertEqual(self._payload()[SCHEMA_KEY], CONFIG_SCHEMA + 5)


if __name__ == "__main__":
    unittest.main()


class RetiredValueTests(ConfigStoreTests):
    """A key rename carried the key and left the value in the old vocabulary.

    It resolves either way on read, so this is about what the file says. The file is what
    the settings are served as, and saying `alpha` where the schema publishes
    `('sort', 'count')` is the file contradicting its own contract.
    """

    def test_an_ini_value_is_written_in_the_current_vocabulary(self) -> None:
        self.ini.write_text("[Input]\npagingtype = alpha\n", encoding="utf-8")

        ConfigStore(str(self.ini))

        self.assertEqual(self._payload()["settings"]["frontend"]["paging_group"], "sort")

    def test_a_json_written_before_the_rename_is_corrected_in_place(self) -> None:
        """The cab hit this: the key migrated, the value did not, and nothing was
        converting an ini any more so no migration was going to reach it."""
        store = ConfigStore(str(self.ini))
        store.config.set("frontend", "paging_group", "numeric")
        store.save()

        ConfigStore(str(self.ini))

        self.assertEqual(self._payload()["settings"]["frontend"]["paging_group"], "count")

    def test_a_current_value_is_left_alone(self) -> None:
        self.ini.write_text("[frontend]\npaging_group = count\n", encoding="utf-8")

        ConfigStore(str(self.ini))

        self.assertEqual(self._payload()["settings"]["frontend"]["paging_group"], "count")


class RetiredRoleTests(ConfigStoreTests):
    """`player` became `device`, and a list of roles had no migration.

    Worse than the value rename above, which still resolved on read: roles are filtered
    against a known set, so a retired word is dropped rather than understood - an install
    written before the rename quietly stopped claiming to be a device at all.
    """

    def _roles(self) -> list[str]:
        return self._payload()["settings"]["install"]["roles"]

    def test_a_json_written_before_the_rename_is_corrected_in_place(self) -> None:
        store = ConfigStore(str(self.ini))
        store.config.set("install", "roles", "hub,player")
        store.save()

        ConfigStore(str(self.ini))

        self.assertEqual(self._roles(), ["hub", "device"])

    def test_an_ini_is_converted_in_the_current_vocabulary(self) -> None:
        self.ini.write_text("[install]\nroles = player\n", encoding="utf-8")

        ConfigStore(str(self.ini))

        self.assertEqual(self._roles(), ["device"])

    def test_the_order_is_kept(self) -> None:
        """The schema's own default reads hub first, so a rename must not reshuffle."""
        self.ini.write_text("[install]\nroles = player,hub\n", encoding="utf-8")

        ConfigStore(str(self.ini))

        self.assertEqual(self._roles(), ["device", "hub"])

    def test_current_roles_are_left_alone(self) -> None:
        self.ini.write_text("[install]\nroles = hub,device\n", encoding="utf-8")

        ConfigStore(str(self.ini))

        self.assertEqual(self._roles(), ["hub", "device"])

    def test_a_renamed_role_survives_being_read_back(self) -> None:
        """The point of the migration: install_identity drops what it does not know, so
        before this the install reported one role where it had said two."""
        from common import install_identity

        self.ini.write_text("[install]\nroles = hub,player\n", encoding="utf-8")

        store = ConfigStore(str(self.ini))

        self.assertEqual(install_identity.roles(store), ["hub", "device"])


class ConfirmSwitchTests(ConfigStoreTests):
    """`frontend.confirm` was a list of scopes and is a switch.

    Anyone who had named a scope asked to be asked, so they stay asked. Letting the type
    conversion have "app,system" would read it as not-a-boolean and answer no - turning a
    setting off because its shape changed, which is the failure this whole file exists to
    catch.
    """

    def _confirm(self, stored):
        self.json.write_text(json.dumps({"schema": 2, "settings": {"lifecycle": stored}}),
                             encoding="utf-8")
        ConfigStore(str(self.ini))
        return self._payload()["settings"]["frontend"]["confirm"]

    def test_any_scope_named_means_keep_asking(self) -> None:
        for scopes in (["app", "system"], ["system"], ["frontend"]):
            with self.subTest(scopes=scopes):
                self.assertIs(self._confirm({"confirm": scopes}), True)

    def test_no_scopes_means_do_not_ask(self) -> None:
        self.assertIs(self._confirm({"confirm": []}), False)

    def test_a_fresh_install_does_not_ask(self) -> None:
        """Off is how VPinFE has always behaved."""
        ConfigStore(str(self.ini))
        self.assertIs(self._payload()["settings"]["frontend"]["confirm"], False)


class MovedSectionTests(ConfigStoreTests):
    """A setting that changes section takes its value with it, and leaves nothing behind.

    Declaring it in its new home and saying nothing about the old one loses whatever the
    user had: the new key falls back to its default while the real value sits orphaned
    under the old section - which the settings page then renders as a second control
    beside the new one. Both halves of that were live before this.
    """

    def _written(self, settings):
        self.json.write_text(json.dumps({"schema": 2, "settings": settings}),
                             encoding="utf-8")
        ConfigStore(str(self.ini))
        return self._payload()["settings"]

    def test_a_customised_value_moves_with_the_setting(self) -> None:
        after = self._written({"input": {"paging_group": "count", "paging_size": 25}})

        self.assertEqual(after["frontend"]["paging_group"], "count")
        self.assertEqual(after["frontend"]["paging_size"], 25)

    def test_the_old_entries_do_not_linger(self) -> None:
        """A leftover is not harmless: the settings page renders what the file holds."""
        after = self._written({"input": {"paging_group": "count", "paging_size": 25},
                               "lifecycle": {"confirm": ["app"]}})

        self.assertEqual([k for k in after.get("input", {}) if "paging" in k], [])
        self.assertNotIn("lifecycle", after)

    def test_a_setting_that_moved_and_changed_type_arrives(self) -> None:
        """confirm did both at once - lifecycle to frontend, and a scope list to a switch.
        Either step alone would have lost it."""
        after = self._written({"lifecycle": {"confirm": ["app", "system"]}})

        self.assertIs(after["frontend"]["confirm"], True)

    def test_a_file_that_never_had_them_gets_the_defaults(self) -> None:
        after = self._written({"general": {}})

        self.assertEqual(after["frontend"]["paging_size"], 10)
        self.assertIs(after["frontend"]["confirm"], False)

