"""The schema is the same settings the config store already has.

It is introduced against the ini it will replace, so it can be checked rather than
trusted: every section, every key and every default has to match what a new install
writes today. Once this holds, the store can read its defaults from here and the
format underneath can change without either being a guess.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common import config_schema
from common.config_store import ConfigStore

# What a new install wrote before the schema existed, captured once. The store reads its
# defaults from the schema now, so comparing the two would compare the schema to itself -
# this is the outside witness that keeps the check meaningful. Changing a default here is
# changing it for every user, so it should be a visible line in a diff.
FROZEN = Path(__file__).resolve().parent / "fixtures" / "config_defaults.json"


def _shipped_defaults() -> dict[str, dict[str, str]]:
    with TemporaryDirectory() as tmp:
        return ConfigStore(os.path.join(tmp, "vpinfe.ini")).defaults


class SchemaMatchesTheStoreTests(unittest.TestCase):
    def test_the_schema_declares_the_defaults_we_shipped(self) -> None:
        frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
        self.assertEqual(config_schema.defaults(), frozen,
                         "a default moved; if that is deliberate, update the fixture")

    def test_the_store_fills_a_new_file_from_the_schema(self) -> None:
        self.assertEqual(_shipped_defaults(), config_schema.defaults())

    def test_no_option_is_declared_twice(self) -> None:
        seen = [(entry.section, entry.key) for entry in config_schema.options()]
        duplicates = {pair for pair in seen if seen.count(pair) > 1}
        self.assertEqual(duplicates, set())


class SchemaShapeTests(unittest.TestCase):
    def test_every_option_states_a_type_we_can_read(self) -> None:
        kinds = {entry.type for entry in config_schema.options()}
        self.assertEqual(kinds - {"string", "bool", "int", "choice"}, set())

    def test_a_choice_defaults_to_one_of_its_choices(self) -> None:
        for entry in config_schema.options():
            if entry.type == "choice":
                self.assertIn(entry.default, entry.choices,
                              f"{entry.section}.{entry.key} defaults outside its choices")

    def test_only_choices_carry_choices(self) -> None:
        for entry in config_schema.options():
            if entry.type != "choice":
                self.assertEqual(entry.choices, (),
                                 f"{entry.section}.{entry.key} is not a choice")

    def test_a_bool_defaults_to_a_spelling_the_reader_accepts(self) -> None:
        for entry in config_schema.options():
            if entry.type == "bool":
                self.assertIn(entry.default, ("true", "false"),
                              f"{entry.section}.{entry.key} is not a bool default")

    def test_internal_state_is_not_offered_as_a_setting(self) -> None:
        """A last-played pointer and a cache marker live in the file nobody edits by
        hand, but they are not settings and should never reach a UI or the docs."""
        internal = {(e.section, e.key) for e in config_schema.options() if e.internal}

        self.assertEqual(internal, {("VPSdb", "last"), ("State", "last_game"),
                                    ("pinmame-score-parser", "roms_update_sha")})
        self.assertNotIn(("State", "last_game"),
                         {(e.section, e.key) for e in config_schema.settable()})


class AliasTests(unittest.TestCase):
    """Keys moved to snake_case at schema 2; every old spelling still has to resolve.

    The frozen fixture was regenerated for that rename, so it can no longer witness it.
    These do instead: each alias maps to a canonical key that exists and carries the
    same default, which is what makes an old file and an old call site both safe.
    """

    def test_every_alias_resolves_to_a_declared_option(self) -> None:
        for entry in config_schema.options():
            for alias in entry.aliases:
                self.assertEqual(config_schema.canonical(entry.section, alias), entry.key,
                                 f"{entry.section}.{alias} must resolve to {entry.key}")

    def test_no_alias_collides_with_a_real_key(self) -> None:
        keys = {(e.section, e.key.lower()) for e in config_schema.options()}
        for entry in config_schema.options():
            for alias in entry.aliases:
                self.assertNotIn((entry.section, alias.lower()), keys,
                                 f"{alias} is both an alias and a key")

    def test_the_renamed_keys_are_the_ones_we_meant(self) -> None:
        """A spot check in both directions, so a bad regeneration is visible."""
        self.assertEqual(config_schema.canonical("Settings", "gamerootdir"), "game_root_dir")
        self.assertEqual(config_schema.canonical("Displays", "cabmode"), "cab_mode")
        self.assertEqual(config_schema.canonical("Media", "defaultmissingmediaimg"),
                         "default_missing_media_image")
        self.assertEqual(config_schema.canonical("Settings", "game_root_dir"), "game_root_dir")

    def test_input_keys_are_untouched(self) -> None:
        """[Input] renames are the vocabulary work and want decisions first."""
        for entry in config_schema.options():
            if entry.section == "Input":
                self.assertEqual(entry.aliases, (), f"{entry.key} should not have moved yet")


class LookupTests(unittest.TestCase):
    def test_no_key_is_used_in_two_sections(self) -> None:
        """by_key() depends on this - the Manager UI holds keys without their section."""
        keys = [entry.key.lower() for entry in config_schema.options()]
        self.assertEqual({k for k in keys if keys.count(k) > 1}, set())

    def test_a_key_resolves_whatever_its_casing(self) -> None:
        """configparser lowercases option names, so a caller rarely has the original."""
        self.assertIsNotNone(config_schema.by_key("MMhideQuitButton"))
        self.assertIs(config_schema.by_key("mmhidequitbutton"),
                      config_schema.by_key("MMhideQuitButton"))

    def test_a_label_falls_back_to_a_readable_key(self) -> None:
        self.assertEqual(config_schema.label_for("gamerootdir"), "Tables Directory")
        self.assertEqual(config_schema.label_for("some_unknown_key"), "Some Unknown Key")

    def test_the_manager_ui_takes_its_labels_from_here(self) -> None:
        from managerui.pages.vpinfe_config import get_friendly_name

        for entry in config_schema.settable():
            if entry.label:
                self.assertEqual(get_friendly_name(entry.key), entry.label)

    def test_an_undescribed_setting_says_so_rather_than_guessing(self) -> None:
        self.assertEqual(config_schema.description_for("no_such_setting"), "")


class DocumentationCoverageTests(unittest.TestCase):
    def test_every_settable_option_has_a_label(self) -> None:
        """A label is what a person sees; an option without one cannot be presented."""
        missing = sorted(f"{e.section}.{e.key}" for e in config_schema.settable()
                         if not e.label)

        self.assertEqual(missing, ["Media.playfield_media_rotation",
                                   "Settings.chrome_options_exclude"],
                         "either label the new option or update this list deliberately")


if __name__ == "__main__":
    unittest.main()
