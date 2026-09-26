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

from common import apps, i18n
from common import events as core_events
from common.extensions import contract, host, provided_apps, services, store

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
        self.assertEqual(record.as_dict()["reason_key"],
                         "extension.reason.manifest_names_another")
        self.assertEqual(record.reason,
                         i18n.t("extension.reason.manifest_names_another", name="sample"))

    def test_a_refused_manifest_is_read_in_the_language_set_when_it_is_shown(self) -> None:
        directory = self.make("unreadable")
        (directory / "extension.json").write_text("{", encoding="utf-8")
        with self.assertLogs(self.LOG, "ERROR") as logged:
            record = self.registry.load(directory)
        english = record.reason

        self.addCleanup(i18n.set_language, i18n.language())
        i18n.set_language("qps")

        self.assertEqual(english, "Its manifest cannot be read")
        self.assertIn("JSONDecodeError", logged.output[0])
        self.assertNotEqual(record.reason, english)

    def test_a_package_with_no_register_is_refused(self) -> None:
        with self.assertLogs(self.LOG, "ERROR") as logged:
            record = self.registry.load(self.make("silent", body="VALUE = 1\n"))

        self.assertEqual(record.state, host.FAILED)
        self.assertIn("register(ctx)", logged.output[0])

    def test_a_directory_with_no_package_is_refused(self) -> None:
        with self.assertLogs(self.LOG, "ERROR") as logged:
            record = self.registry.load(self.make("empty"))

        self.assertEqual(record.state, host.FAILED)
        self.assertIn("__init__.py", logged.output[0])

    def test_a_register_that_raises_takes_only_that_extension(self) -> None:
        self.load()
        with self.assertLogs(self.LOG, "ERROR") as logged:
            record = self.registry.load(self.make(
                "hostile", body='def register(ctx):\n    raise RuntimeError("halted")\n'))

        self.assertEqual(record.state, host.FAILED)
        self.assertIn("RuntimeError('halted')", logged.output[0])
        self.assertTrue(self.registry.running("sample"))

    def test_what_its_code_raised_stays_off_the_screen(self) -> None:
        with self.assertLogs(self.LOG, "ERROR"):
            record = self.registry.load(self.make(
                "hostile", body='def register(ctx):\n    raise KeyError("token")\n'))

        self.assertNotIn("token", record.reason)
        self.assertEqual(record.reason, "The log says why it did not start")

    def test_why_is_read_in_the_language_set_when_it_is_shown(self) -> None:
        self.store.set_enabled("sample", False)
        self.load()
        record = self.registry.get("sample")
        self.assertEqual(record.reason, "Switched off")

        self.addCleanup(i18n.set_language, i18n.language())
        i18n.set_language("qps")

        self.assertNotIn("Switched", record.reason)
        self.assertNotIn("Switched", record.as_dict()["reason"])

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
        self.assertIn(i18n.t(host.PLATFORM_NAMES[host.this_platform()]), record.reason)

    def test_a_platform_reads_as_its_name(self) -> None:
        directory = self.make("elsewhere", {"platforms": ["windows"]},
                              "def register(ctx): pass\n")
        with unittest.mock.patch.object(host, "this_platform", return_value="macos"):
            record = self.registry.load(directory)

        self.assertEqual(record.reason, "Not for macOS")

    def test_a_platform_with_no_name_is_shown_as_it_arrived(self) -> None:
        directory = self.make("elsewhere", {"platforms": ["windows"]},
                              "def register(ctx): pass\n")
        with unittest.mock.patch.object(host, "this_platform", return_value="freebsd"):
            record = self.registry.load(directory)

        self.assertEqual(record.reason, "Not for freebsd")

    def test_an_extension_needing_a_feature_this_install_lacks_is_not_loaded(self) -> None:
        directory = self.make("watcher", {"requires_features": ["overview", "devices"]},
                              "def register(ctx): pass\n")
        with unittest.mock.patch.object(host, "_features", return_value=("library",)):
            record = self.registry.load(directory)

        self.assertEqual(record.state, host.OFF)
        self.assertEqual(record.reason,
                         "This device does not do Device Management, Overview")

    def test_the_names_follow_the_language_set(self) -> None:
        directory = self.make("elsewhere", {"platforms": ["windows"]},
                              "def register(ctx): pass\n")
        with unittest.mock.patch.object(host, "this_platform", return_value="macos"):
            record = self.registry.load(directory)
        self.addCleanup(i18n.set_language, i18n.language())
        i18n.set_language("qps")

        self.assertNotIn("macOS", record.reason)


class WordsTests(HostCase):
    """What an extension says is looked up in its own `i18n/`, when it is read."""

    OFFERS = ('def register(ctx):\n'
              '    ctx.ui.action("sync", "/sync")\n'
              '    ctx.ui.settings("/settings")\n'
              '    ctx.ui.community("tables", "/t", columns=[{"field": "name"}],\n'
              '                     views=[{"key": "top", "columns": ["name"]}])\n')

    def worded(self, name: str, words: dict, manifest: dict | None = None,
               body: str = "def register(ctx): pass\n") -> Path:
        directory = self.make(name, manifest, body)
        (directory / "i18n").mkdir()
        (directory / "i18n" / "en.json").write_text(json.dumps(words), encoding="utf-8")
        self.addCleanup(i18n.disown, f"ext.{name}")
        return directory

    def test_a_name_left_out_is_its_folder_name(self) -> None:
        record = self.registry.load(self.make("plain", body="def register(ctx): pass\n"))

        self.assertEqual(record.display_name, "plain")
        self.assertEqual(record.as_dict()["description"], "")

    def test_its_catalog_names_it(self) -> None:
        record = self.registry.load(self.worded(
            "named", {"name": "Named", "description": "Does one thing"}))

        self.assertEqual(record.as_dict()["display_name"], "Named")
        self.assertEqual(record.as_dict()["description"], "Does one thing")

    def test_a_name_in_the_manifest_is_shown_as_written(self) -> None:
        """A product name, which is the same in every language."""
        record = self.registry.load(self.worded(
            "branded", {"name": "Translated"}, {"display_name": "VPinThing"}))

        self.assertEqual(record.display_name, "VPinThing")

    def test_one_switched_off_is_still_named_by_its_catalog(self) -> None:
        """It is still listed, and switching it back on is done by name."""
        self.store.set_enabled("named", False)

        record = self.registry.load(self.worded("named", {"name": "Named"}))

        self.assertEqual(record.state, host.OFF)
        self.assertEqual(record.display_name, "Named")

    def test_what_it_offers_is_worded_by_its_catalog(self) -> None:
        record = self.registry.load(self.worded("worded", {
            "action.sync.label": "Sync now",
            "action.sync.description": "Sends what was played",
            "settings.label": "Account",
            "community.tables.title": "Top tables",
            "community.tables.column.name.header": "Table",
            "community.tables.view.top.name": "Most played",
        }, {"capabilities": ["ui:mount"]}, self.OFFERS))
        found = record.as_dict()

        self.assertEqual(found["actions"][0]["label"], "Sync now")
        self.assertEqual(found["actions"][0]["label_key"], "ext.worded.action.sync.label")
        self.assertEqual(found["actions"][0]["description"], "Sends what was played")
        self.assertEqual(found["surfaces"]["settings_label"], "Account")
        listing = found["community"][0]
        self.assertEqual(listing["title"], "Top tables")
        self.assertEqual(listing["columns"][0]["header"], "Table")
        self.assertEqual(listing["views"][0]["name"], "Most played")

    def test_what_its_catalog_leaves_out_is_called_by_its_key(self) -> None:
        """The Console has its own word for a settings page with none."""
        record = self.registry.load(self.worded(
            "bare", {}, {"capabilities": ["ui:mount"]}, self.OFFERS))
        found = record.as_dict()

        self.assertEqual(found["actions"][0]["label"], "sync")
        self.assertEqual(found["actions"][0]["label_key"], "")
        self.assertEqual(found["surfaces"]["settings_label"], "")
        listing = found["community"][0]
        self.assertEqual(listing["title"], "tables")
        self.assertEqual(listing["columns"][0]["header"], "name")
        self.assertEqual(listing["views"][0]["name"], "top")

    def test_it_reads_its_own_words_by_key(self) -> None:
        directory = self.worded("speaker", {"greeting": "Hello, {who}"}, body=(
            'from pathlib import Path\n'
            'def register(ctx):\n'
            '    Path(__file__).with_name("said.txt").write_text(ctx.t("greeting", who="Pat"))\n'))

        self.registry.load(directory)

        self.assertEqual((directory / "said.txt").read_text(), "Hello, Pat")
        self.assertEqual(contract.words("speaker")("greeting", who="Sam"), "Hello, Sam")


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
        with self.assertLogs(self.LOG, "ERROR") as logged:
            record = self.registry.load(self.make("greedy", {"provides": ["read"]}, body))

        self.assertEqual(record.state, host.FAILED)
        self.assertIn("does not provide", logged.output[0])

    def test_publishing_an_undeclared_event_is_refused(self) -> None:
        body = ("def register(ctx):\n"
                "    ctx.events.publish('surprise')\n")
        with self.assertLogs(self.LOG, "ERROR") as logged:
            record = self.registry.load(self.make("loud", body=body))

        self.assertEqual(record.state, host.FAILED)
        self.assertIn("does not declare", logged.output[0])

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


class SwitchTests(HostCase):
    def heard(self) -> list[dict]:
        heard: list[dict] = []
        core_events.subscribe("sample.noticed", lambda **payload: heard.append(payload))
        core_events.emit("game.selected", game_id="abc")
        return heard

    def test_off_takes_it_out_now_and_writes_it_down(self) -> None:
        self.load()

        with self.assertLogs(self.LOG, "INFO"):
            record = self.registry.switch("sample", False)

        self.assertIs(record, self.registry.get("sample"))
        self.assertEqual((record.state, record.why), (host.OFF, host.SWITCHED_OFF))
        self.assertFalse(record.enabled)
        self.assertFalse(self.store.enabled("sample"))
        self.assertNotIn("ext:sample:read", self.registry.granted_scopes())
        self.assertEqual(self.heard(), [])
        self.assertTrue(self.registry.running("bystander"))

    def test_off_is_not_reported_as_a_fault(self) -> None:
        self.load()

        with self.assertLogs(self.LOG, "INFO") as said:
            self.registry.switch("sample", False)

        self.assertEqual([line for line in said.records if line.levelno > logging.INFO],
                         [])

    def test_on_writes_it_down_and_waits_for_the_next_start(self) -> None:
        self.store.set_enabled("sample", False)
        self.load()

        with self.assertLogs(self.LOG, "INFO"):
            record = self.registry.switch("sample", True)

        self.assertTrue(self.store.enabled("sample"))
        self.assertTrue(record.enabled)
        self.assertEqual((record.state, record.why), (host.OFF, host.STARTS_AT_RESTART))
        self.assertEqual(record.as_dict()["reason"], "Starts at the next restart")
        self.assertNotIn("ext:sample:read", self.registry.granted_scopes())

        again = host.Registry(self.store)
        self.addCleanup(again.clear)
        again.load_from(FIXTURES)
        self.assertTrue(again.running("sample"))

    def test_off_again_before_the_restart_says_switched_off(self) -> None:
        self.store.set_enabled("sample", False)
        self.load()

        with self.assertLogs(self.LOG, "INFO"):
            self.registry.switch("sample", True)
            record = self.registry.switch("sample", False)

        self.assertEqual(record.why, host.SWITCHED_OFF)

    def test_one_this_device_cannot_run_keeps_saying_why(self) -> None:
        other = "windows" if host.this_platform() != "windows" else "linux"
        self.registry.load(self.make("elsewhere", {"platforms": [other]},
                                     "def register(ctx): pass\n"))

        with self.assertLogs(self.LOG, "INFO"):
            self.assertEqual(self.registry.switch("elsewhere", False).why,
                             host.SWITCHED_OFF)
            record = self.registry.switch("elsewhere", True)

        self.assertEqual(record.why, "extension.reason.not_for_platform")

    def test_switching_off_one_a_fault_stopped_reads_as_switched_off(self) -> None:
        self.load()
        with self.assertLogs(self.LOG, "ERROR"):
            self.registry.disable("sample", "asked to")

        with self.assertLogs(self.LOG, "INFO"):
            record = self.registry.switch("sample", False)

        self.assertEqual((record.state, record.why), (host.OFF, host.SWITCHED_OFF))

    def test_on_leaves_a_running_one_running(self) -> None:
        self.load()

        with self.assertLogs(self.LOG, "INFO"):
            record = self.registry.switch("sample", True)

        self.assertEqual(record.state, host.LOADED)
        self.assertIn("ext:sample:read", self.registry.granted_scopes())

    def test_a_name_nothing_answers_to_is_not_written(self) -> None:
        self.assertIsNone(self.registry.switch("nothing", False))
        self.assertTrue(self.store.enabled("nothing"))

    def test_the_listing_says_what_the_switch_is_set_to(self) -> None:
        self.store.set_enabled("sample", False)
        self.load()

        self.assertFalse(self.registry.get("sample").as_dict()["enabled"])
        self.assertTrue(self.registry.get("bystander").as_dict()["enabled"])


class WithdrawTests(HostCase):
    """What an extension offered goes with it, whether it stops or never finished."""

    OFFERS = ('def register(ctx):\n'
              '    ctx.events.subscribe("game.selected", lambda **_: ctx.events.publish("heard"))\n'
              '    ctx.apps.provide(id="fp", name="Future Pinball", suffixes=(".fpt",))\n'
              '    ctx.serves.answer("offers.state", lambda: "somebody")\n')
    MANIFEST = {"scopes": [provided_apps.APPS_PROVIDE], "events": ["heard"]}

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(apps.withdraw_all)
        self.addCleanup(services.forget_all)

    def heard(self) -> list[dict]:
        heard: list[dict] = []
        core_events.subscribe("offers.heard", lambda **payload: heard.append(payload))
        core_events.emit("game.selected", game_id="abc")
        return heard

    def test_a_stopped_one_takes_back_its_app_and_its_answers(self) -> None:
        self.registry.load(self.make("offers", self.MANIFEST, self.OFFERS))
        self.assertEqual(apps.app_for("Big Bang Bar.fpt").id, "fp")
        self.assertEqual(services.ask("offers.state"), "somebody")

        with self.assertLogs(self.LOG, "ERROR"):
            self.registry.disable("offers", "asked to")

        self.assertIsNone(apps.app_for("Big Bang Bar.fpt"))
        self.assertIsNone(services.ask("offers.state"))
        self.assertEqual(self.heard(), [])

    def test_its_apps_words_go_with_it(self) -> None:
        directory = self.make("offers", self.MANIFEST, self.OFFERS)
        (directory / "i18n").mkdir()
        (directory / "i18n" / "en.json").write_text(
            json.dumps({"app.fp.name": "Future Pinball"}), encoding="utf-8")
        self.addCleanup(i18n.disown, "ext.offers")
        self.addCleanup(i18n.disown, "app.fp")
        self.registry.load(directory)
        self.assertEqual(i18n.first_key("app.fp.name"), "app.fp.name")

        with self.assertLogs(self.LOG, "ERROR"):
            self.registry.disable("offers", "asked to")

        self.assertEqual(i18n.first_key("app.fp.name"), "")

    def test_a_register_that_raises_part_way_takes_back_what_it_had_offered(self) -> None:
        body = self.OFFERS + '    raise RuntimeError("halfway")\n'
        with self.assertLogs(self.LOG, "ERROR"):
            record = self.registry.load(self.make("offers", self.MANIFEST, body))

        self.assertEqual(record.state, host.FAILED)
        self.assertIsNone(apps.app_for("Big Bang Bar.fpt"))
        self.assertIsNone(services.ask("offers.state"))
        self.assertEqual(self.heard(), [])


if __name__ == "__main__":
    unittest.main()
