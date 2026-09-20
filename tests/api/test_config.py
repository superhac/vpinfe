"""Settings: what this install has, what it is set to, and what it refuses.

The refusals are the part worth pinning. A settings write that half-applies leaves an
install in a state nobody asked for, and a theme source is a URL this install fetches
code from - so an unknown key fails the whole request and a theme source is not settable
over HTTP at all.

Split by what it tests. The rules are the service's and are tested against it; the route
is tested for the one thing only it does, which is turning a refusal into a status code.
"""

from __future__ import annotations

import unittest
import unittest.mock

from fastapi.testclient import TestClient

import httpapi
from common import config_schema, config_service


class Store:
    """Enough ConfigStore for the service: typed reads, staged writes, one save."""

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


class ConfigServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self._real = config_service.get_ini_config
        config_service.get_ini_config = lambda: self.store

    def tearDown(self):
        config_service.get_ini_config = self._real

    # --- schema ---------------------------------------------------------------

    def test_schema_describes_every_settable_option(self):
        schema = config_service.schema()
        served = sum(len(s["options"]) for s in schema["sections"])
        self.assertEqual(schema["count"], served)
        self.assertEqual(served, len(config_schema.settable()))

    def test_schema_leaves_out_internal_options(self):
        """Runtime state that happens to live in the file is not a setting. Offering a
        last-played pointer invites someone to set it."""
        served = {(o["section"], o["key"]) for s in config_service.schema()["sections"]
                  for o in s["options"]}
        internal = {(o.section, o.key) for o in config_schema.options() if o.internal}
        self.assertTrue(internal, "expected some internal options to exist")
        self.assertFalse(served & internal)

    def test_theme_sources_are_writable(self):
        sections = {s["name"]: s for s in config_service.schema()["sections"]}
        self.assertIn("themes", sections)
        self.assertTrue(sections["themes"]["writable"])
        self.assertTrue(all(o["writable"] for o in sections["themes"]["options"]))

    # --- writes ---------------------------------------------------------------

    def test_a_known_setting_is_written_and_saved(self):
        config_service.set_values({"logger": {"terminal": False}})
        self.assertEqual(self.store.written[("logger", "terminal")], False)
        self.assertEqual(self.store.saves, 1)

    def test_a_retired_spelling_writes_to_the_current_key(self):
        """`console` named terminal logging before it named the web UI. A client written
        against the old name must not write a second, dead key beside the live one."""
        config_service.set_values({"logger": {"console": False}})
        self.assertEqual(self.store.written[("logger", "terminal")], False)
        self.assertNotIn(("logger", "console"), self.store.written)

    def test_an_unknown_key_fails_the_whole_request(self):
        """Not just the bad key - the good one must not land either, or a save is
        half-applied and no screen reflects the result."""
        with self.assertRaises(config_service.UnknownSettingsError) as caught:
            config_service.set_values({"logger": {"terminal": False},
                                       "general": {"not_a_setting": "x"}})
        self.assertEqual(caught.exception.keys, ["general.not_a_setting"])
        self.assertEqual(self.store.written, {})
        self.assertEqual(self.store.saves, 0)

    def test_a_theme_source_is_written(self):
        config_service.set_values({"themes": {"registries": "http://elsewhere"}})
        self.assertIn(("themes", "registries"), self.store.written)

    def test_nothing_is_read_only_and_the_refusal_still_works(self):
        """The set is empty, not gone: the path that refuses a write is what a later
        origin check reuses, so it is exercised rather than left to rot."""
        self.assertEqual(config_service.READ_ONLY_SECTIONS, frozenset())
        with unittest.mock.patch.object(config_service, "READ_ONLY_SECTIONS",
                                        frozenset({"themes"})):
            with self.assertRaises(config_service.ReadOnlySettingsError) as caught:
                config_service.set_values({"themes": {"registries": "http://elsewhere"}})
        self.assertEqual(caught.exception.keys, ["themes.registries"])
        self.assertEqual(self.store.written, {})

    def test_an_empty_patch_writes_nothing(self):
        config_service.set_values({})
        self.assertEqual(self.store.saves, 0)

    def test_a_former_spelling_lands_on_the_canonical_key(self):
        """Keys moved to snake_case and the old ones stay aliases, so a client written
        against an older name keeps working and the file still gets one spelling."""
        aliased = next((o for o in config_schema.settable()
                        if o.aliases
                        and o.section not in config_service.READ_ONLY_SECTIONS),
                       None)
        if aliased is None:
            self.skipTest("no aliased option in the schema")
        config_service.set_values({aliased.section: {aliased.aliases[0]: "1"}})
        self.assertIn((aliased.section, aliased.key), self.store.written)


class ConfigRouteTests(unittest.TestCase):
    """What the route adds: a refusal becomes a status code and a message."""

    def setUp(self):
        self.store = Store()
        self._real = config_service.get_ini_config
        config_service.get_ini_config = lambda: self.store
        self.client = TestClient(httpapi.create_api_app(),
                                 raise_server_exceptions=False)

    def tearDown(self):
        config_service.get_ini_config = self._real

    def test_the_schema_is_served(self):
        body = self.client.get("/config/schema").json()
        self.assertEqual(body["count"], len(config_schema.settable()))

    def test_an_unknown_key_is_a_bad_request_naming_it(self):
        response = self.client.put("/config",
                                   json={"general": {"not_a_setting": "x"}})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("not_a_setting", response.text)

    def test_a_theme_source_is_accepted(self):
        response = self.client.put("/config",
                                   json={"themes": {"registries": "http://elsewhere"}})
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()
