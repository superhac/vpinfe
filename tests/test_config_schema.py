"""The schema is the same settings the config store already has.

It is introduced against the ini it will replace, so it can be checked rather than
trusted: every section, every key and every default has to match what a new install
writes today. Once this holds, the store can read its defaults from here and the
format underneath can change without either being a guess.
"""

from __future__ import annotations

import os
import unittest
from tempfile import TemporaryDirectory

from common import config_schema
from common.iniconfig import IniConfig


def _shipped_defaults() -> dict[str, dict[str, str]]:
    with TemporaryDirectory() as tmp:
        return IniConfig(os.path.join(tmp, "vpinfe.ini")).defaults


class SchemaMatchesTheStoreTests(unittest.TestCase):
    def test_the_schema_declares_the_same_defaults(self) -> None:
        self.assertEqual(config_schema.defaults(), _shipped_defaults())

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

        self.assertEqual(internal, {("VPSdb", "last"), ("State", "lastgame"),
                                    ("pinmame-score-parser", "romsupdatesha")})
        self.assertNotIn(("State", "lastgame"),
                         {(e.section, e.key) for e in config_schema.settable()})


class DocumentationCoverageTests(unittest.TestCase):
    def test_every_settable_option_has_a_label(self) -> None:
        """A label is what a person sees; an option without one cannot be presented."""
        missing = sorted(f"{e.section}.{e.key}" for e in config_schema.settable()
                         if not e.label)

        self.assertEqual(missing, ["Media.playfieldmediarotation",
                                   "Settings.chromeoptionsexclude"],
                         "either label the new option or update this list deliberately")


if __name__ == "__main__":
    unittest.main()
