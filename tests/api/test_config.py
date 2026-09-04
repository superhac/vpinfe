"""The config API: what this install has, what it is set to, and what it refuses.

The refusals are the part worth pinning. A settings write that half-applies leaves an
install in a state nobody asked for, and a theme source is a URL this install fetches
code from - so an unknown key fails the whole request and a theme source is not settable
over HTTP at all.
"""

from __future__ import annotations

import unittest

from common import config_schema
from httpapi import config as config_api


class Store:
    """Enough ConfigStore for the router: typed reads, staged writes, one save."""

    def __init__(self):
        self.written: dict[tuple[str, str], object] = {}
        self.saves = 0

    def value(self, section, key):
        entry = config_schema.option(section, key)
        return self.written.get((section, key), entry.default if entry else "")

    def set_value(self, section, key, value):
        self.written[(section, key)] = value

    def save(self):
        self.saves += 1


class ConfigApiTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self._real = config_api.get_ini_config
        config_api.get_ini_config = lambda: self.store

    def tearDown(self):
        config_api.get_ini_config = self._real

    # --- schema ---------------------------------------------------------------

    def test_schema_describes_every_settable_option(self):
        schema = config_api.get_schema()
        served = sum(len(s["options"]) for s in schema["sections"])
        self.assertEqual(schema["count"], served)
        self.assertEqual(served, len(config_schema.settable()))

    def test_schema_leaves_out_internal_options(self):
        """Runtime state that happens to live in the file is not a setting. Offering a
        last-played pointer invites someone to set it."""
        served = {(o["section"], o["key"]) for s in config_api.get_schema()["sections"]
                  for o in s["options"]}
        internal = {(o.section, o.key) for o in config_schema.options() if o.internal}
        self.assertTrue(internal, "expected some internal options to exist")
        self.assertFalse(served & internal)

    def test_theme_sources_are_described_but_not_writable(self):
        sections = {s["name"]: s for s in config_api.get_schema()["sections"]}
        self.assertIn("themes", sections, "a client should still see they exist")
        self.assertFalse(sections["themes"]["writable"])
        self.assertTrue(all(not o["writable"] for o in sections["themes"]["options"]))

    # --- writes ---------------------------------------------------------------

    def test_a_known_setting_is_written_and_saved(self):
        config_api.put_values({"logger": {"terminal": False}})
        self.assertEqual(self.store.written[("logger", "terminal")], False)
        self.assertEqual(self.store.saves, 1)

    def test_a_retired_spelling_writes_to_the_current_key(self):
        """`console` named terminal logging before it named the web UI. A client written
        against the old name must not write a second, dead key beside the live one."""
        config_api.put_values({"logger": {"console": False}})
        self.assertEqual(self.store.written[("logger", "terminal")], False)
        self.assertNotIn(("logger", "console"), self.store.written)

    def test_an_unknown_key_fails_the_whole_request(self):
        """Not just the bad key - the good one must not land either, or a save is
        half-applied and no screen reflects the result."""
        with self.assertRaises(Exception) as caught:
            config_api.put_values({"logger": {"terminal": False},
                                   "general": {"not_a_setting": "x"}})
        self.assertIn("not_a_setting", str(caught.exception))
        self.assertEqual(self.store.written, {})
        self.assertEqual(self.store.saves, 0)

    def test_a_theme_source_is_refused(self):
        with self.assertRaises(Exception) as caught:
            config_api.put_values({"themes": {"registries": "http://elsewhere"}})
        self.assertIn("Read-only", str(caught.exception))
        self.assertEqual(self.store.written, {})
        self.assertEqual(self.store.saves, 0)

    def test_an_empty_patch_writes_nothing(self):
        config_api.put_values({})
        self.assertEqual(self.store.saves, 0)

    def test_a_former_spelling_lands_on_the_canonical_key(self):
        """Keys moved to snake_case and the old ones stay aliases, so a client written
        against an older name keeps working and the file still gets one spelling."""
        aliased = next((o for o in config_schema.settable()
                        if o.aliases and o.section not in config_api.READ_ONLY_SECTIONS),
                       None)
        if aliased is None:
            self.skipTest("no aliased option in the schema")
        config_api.put_values({aliased.section: {aliased.aliases[0]: "1"}})
        self.assertIn((aliased.section, aliased.key), self.store.written)


if __name__ == "__main__":
    unittest.main()
