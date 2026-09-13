"""Loading an extension, what it is handed, and what happens when it breaks.

Driven against the fixture extensions under `tests/fixtures/extensions/`, which is the
whole of the contract exercised by something that is not core.
"""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from common import events as core_events
from common.extensions import contract, host, store

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "extensions"


class HostCase(unittest.TestCase):
    """A registry with its own settings file, so nothing here touches this machine."""

    # Every refusal is logged, and the log is where attribution lives. Asserting on it
    # is what keeps a deliberate failure out of the suite's output as well.
    LOG = "vpinfe.common.extensions"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = store.ExtensionStore(self.root / "extensions.json")
        self.registry = host.Registry(self.store)
        self.addCleanup(self.registry.clear)
        self.addCleanup(core_events.clear)

    def load(self) -> None:
        self.registry.load_from(FIXTURES)

    def make(self, name: str, manifest: dict | None = None, body: str = "") -> Path:
        """An extension written for one test, where the shape under test is a broken
        one and a committed fixture would be a worked example of a mistake."""
        directory = self.root / "made" / name
        directory.mkdir(parents=True)
        raw = {"name": name, "version": "1.0.0",
               "requires_platform": contract.PLATFORM_ABI}
        raw.update(manifest or {})
        (directory / "extension.json").write_text(json.dumps(raw), encoding="utf-8")
        if body:
            (directory / "__init__.py").write_text(body, encoding="utf-8")
        return directory


class LoadTests(HostCase):
    def test_both_fixtures_load(self) -> None:
        self.load()

        self.assertEqual([one.name for one in self.registry.records()],
                         ["bystander", "sample"])
        self.assertTrue(all(one.running for one in self.registry.records()))

    def test_a_record_carries_what_the_manifest_declared(self) -> None:
        self.load()
        found = self.registry.get("sample").as_dict()

        self.assertEqual(found["state"], host.LOADED)
        self.assertEqual(found["scopes"], ["games:read"])
        self.assertEqual(found["routes"], ["ext:sample:read"])
        self.assertEqual(found["capabilities"], ["config:own", "ui:mount"])

    def test_a_directory_whose_name_is_not_the_manifests_is_refused(self) -> None:
        """The folder is the name. Two answers to what an extension is called would
        each address it somewhere - one in a URL, the other in a config file."""
        directory = self.make("elsewhere", {"name": "sample"}, "def register(ctx): pass\n")

        with self.assertLogs(self.LOG, "ERROR"):
            record = self.registry.load(directory)

        self.assertEqual(record.state, host.FAILED)
        self.assertIn("the folder is the name", record.reason)

    def test_a_package_with_no_register_is_refused(self) -> None:
        with self.assertLogs(self.LOG, "ERROR"):
            record = self.registry.load(self.make("silent", body="VALUE = 1\n"))

        self.assertEqual(record.state, host.FAILED)
        self.assertIn("register(ctx)", record.reason)

    def test_a_directory_with_no_package_is_refused(self) -> None:
        with self.assertLogs(self.LOG, "ERROR"):
            record = self.registry.load(self.make("empty"))

        self.assertEqual(record.state, host.FAILED)
        self.assertIn("__init__.py", record.reason)

    def test_a_register_that_raises_takes_only_that_extension(self) -> None:
        self.load()
        with self.assertLogs(self.LOG, "ERROR"):
            record = self.registry.load(self.make(
                "hostile", body='def register(ctx):\n    raise RuntimeError("no")\n'))

        self.assertEqual(record.state, host.FAILED)
        self.assertIn("no", record.reason)
        self.assertTrue(self.registry.running("sample"))

    def test_an_extension_the_user_switched_off_is_not_loaded(self) -> None:
        self.store.set_enabled("sample", False)

        self.load()

        self.assertEqual(self.registry.get("sample").state, host.OFF)
        self.assertTrue(self.registry.running("bystander"))

    def test_an_extension_for_another_platform_is_not_loaded(self) -> None:
        other = "windows" if host.this_platform() != "windows" else "linux"
        directory = self.make("elsewhere", {"platforms": [other]},
                              "def register(ctx): pass\n")

        record = self.registry.load(directory)

        self.assertEqual(record.state, host.OFF)
        self.assertIn(host.this_platform(), record.reason)

    def test_an_extension_needing_a_feature_this_install_lacks_is_not_loaded(self) -> None:
        directory = self.make("watcher", {"requires_features": ["overview"]},
                              "def register(ctx): pass\n")
        with unittest.mock.patch.object(host, "_features", return_value=("library",)):
            record = self.registry.load(directory)

        self.assertEqual(record.state, host.OFF)
        self.assertIn("overview", record.reason)


class ContextTests(HostCase):
    def test_the_logger_is_the_extensions_own_namespace(self) -> None:
        """The namespace is how "which extension did this?" stays answerable."""
        self.load()
        with self.assertLogs("vpinfe.ext.sample", level=logging.INFO) as caught:
            logging.getLogger("vpinfe.ext.sample").info("hello")

        self.assertIn("hello", caught.output[0])

    def test_settings_land_in_a_file_of_the_extensions_own(self) -> None:
        """A file each, not a namespace inside one. One bad write took every
        extension's settings with it, and the switched-off ones came back on."""
        self.store.set_setting("sample", "greeting", "good evening")

        path = self.root / "extension_settings" / "sample.json"

        self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                         {"greeting": "good evening"})

    def test_core_keeps_only_what_core_needs_to_know(self) -> None:
        """Whether it is switched off is core's record - it has to know before it loads
        anything. What it is configured with is nobody's business but its own."""
        self.store.set_setting("sample", "greeting", "good evening")
        self.store.set_enabled("sample", False)

        held = json.loads((self.root / "extensions.json").read_text(encoding="utf-8"))

        self.assertEqual(held["extensions"]["sample"], {"enabled": False})

    def test_one_extensions_unreadable_settings_cost_only_that_one(self) -> None:
        """The whole reason they are not in one file together."""
        self.store.set_setting("sample", "greeting", "good evening")
        self.store.set_setting("bystander", "greeting", "hello")
        (self.root / "extension_settings" / "sample.json").write_text("{", "utf-8")

        with self.assertLogs("vpinfe.common.extensions.store", "ERROR"):
            self.assertEqual(self.store.settings("sample"), {})

        self.assertEqual(self.store.settings("bystander"), {"greeting": "hello"})
        self.assertTrue(self.store.enabled("sample"))

    def test_settings_written_before_the_split_are_carried_over(self) -> None:
        """An install that ran a build where they lived together keeps them."""
        (self.root / "extensions.json").write_text(json.dumps({
            "schema": 1,
            "extensions": {"sample": {"enabled": True,
                                      "settings": {"greeting": "from before"}}},
        }), encoding="utf-8")

        self.assertEqual(self.store.settings("sample"), {"greeting": "from before"})
        held = json.loads((self.root / "extensions.json").read_text(encoding="utf-8"))
        self.assertNotIn("settings", held["extensions"]["sample"])

    def test_forgetting_one_takes_its_file_with_it(self) -> None:
        self.store.set_setting("sample", "greeting", "good evening")

        self.store.forget("sample")

        self.assertFalse((self.root / "extension_settings" / "sample.json").exists())

    def test_the_settings_follow_the_registry_rather_than_this_machine(self) -> None:
        """A store told where its registry is and left pointing at this machine's own
        settings is not isolated at all - which wrote into a real config directory
        before it was caught."""
        from common.extensions import store as store_module

        self.assertEqual(self.store.settings_dir, self.root / "extension_settings")
        self.assertNotEqual(self.store.settings_dir, store_module.SETTINGS_DIR)

    def test_a_router_gated_on_an_undeclared_scope_is_refused(self) -> None:
        body = ("from fastapi import APIRouter\n"
                "def register(ctx):\n"
                "    ctx.add_router(APIRouter(), scope='ext:sample:read')\n")
        with self.assertLogs(self.LOG, "ERROR"):
            record = self.registry.load(self.make("greedy", {"provides": ["read"]}, body))

        self.assertEqual(record.state, host.FAILED)
        self.assertIn("does not provide", record.reason)

    def test_publishing_an_undeclared_event_is_refused(self) -> None:
        body = ("def register(ctx):\n"
                "    ctx.events.publish('surprise')\n")
        with self.assertLogs(self.LOG, "ERROR"):
            record = self.registry.load(self.make("loud", body=body))

        self.assertEqual(record.state, host.FAILED)
        self.assertIn("does not declare", record.reason)

    def test_a_published_event_carries_the_extensions_namespace(self) -> None:
        self.load()
        heard = []
        core_events.subscribe("sample.noticed", lambda **payload: heard.append(payload))

        core_events.emit("game.selected", game_id="abc")

        self.assertEqual(heard, [{"game_id": "abc"}])


class FailureTests(HostCase):
    def test_a_subscriber_that_throws_disables_only_that_extension(self) -> None:
        self.load()

        with self.assertLogs(self.LOG, "ERROR"), \
                self.assertLogs("vpinfe.ext.sample", "ERROR") as blamed:
            core_events.emit("game.selected", game_id="fail")

        # The extension's own namespace carries the traceback: which extension did this
        # is the question the namespace exists to answer.
        self.assertIn("game.selected", blamed.output[0])
        self.assertEqual(self.registry.get("sample").state, host.DISABLED)
        self.assertIn("game.selected", self.registry.get("sample").reason)
        self.assertTrue(self.registry.running("bystander"))

    def test_a_disabled_extension_is_told_nothing_more(self) -> None:
        self.load()
        with self.assertLogs(self.LOG, "ERROR"), \
                self.assertLogs("vpinfe.ext.sample", "ERROR"):
            core_events.emit("game.selected", game_id="fail")

        heard = []
        core_events.subscribe("sample.noticed", lambda **payload: heard.append(payload))
        core_events.emit("game.selected", game_id="abc")

        self.assertEqual(heard, [])

    def test_disabling_takes_the_extensions_scopes_with_it(self) -> None:
        self.load()
        self.assertIn("ext:sample:read", self.registry.granted_scopes())

        with self.assertLogs(self.LOG, "ERROR"):
            self.registry.disable("sample", "asked to")

        self.assertNotIn("ext:sample:read", self.registry.granted_scopes())
        self.assertIn("ext:bystander:read", self.registry.granted_scopes())

    def test_a_disable_is_not_written_down(self) -> None:
        """A fault that happened once must not take the extension away until somebody
        notices a setting they never set."""
        self.load()
        with self.assertLogs(self.LOG, "ERROR"):
            self.registry.disable("sample", "asked to")

        self.assertTrue(self.store.enabled("sample"))


if __name__ == "__main__":
    unittest.main()
