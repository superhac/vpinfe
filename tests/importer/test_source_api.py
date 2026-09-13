"""The importer over its own routes, and what pointing it at a folder does to core.

The part worth pinning is the last one: an importer converting somebody's old library
has to hand core files that are nowhere near ours, and until it says where it is working
every one of them is refused.
"""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from fastapi.testclient import TestClient

import httpapi
from common import extensions
from common.extensions import host, store
from httpapi import filesystem

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "pinballx"
BASE = "/ext/library_importer"


class ImporterApiCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

        self.store = store.ExtensionStore(self.root / "extensions.json")
        self.registry = host.Registry(self.store)
        extensions.set_registry(self.registry)
        self.addCleanup(extensions.set_registry, host.Registry())
        self.addCleanup(self.registry.clear)

        record = self.registry.load(host.BUNDLED_DIR / "library_importer")
        self.assertEqual(record.state, host.LOADED, record.reason)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def point_at(self, path) -> dict:
        return self.client.put(f"{BASE}/source", json={"path": str(path)}).json()


class SourceTests(ImporterApiCase):
    def test_an_install_that_has_not_been_asked_says_so(self) -> None:
        found = self.client.get(f"{BASE}/source").json()

        self.assertEqual(found["path"], "")
        self.assertFalse(found["reachable"])
        self.assertIn("No source", found["reason"])

    def test_pointing_at_a_source_names_what_can_read_it(self) -> None:
        found = self.point_at(FIXTURE)

        self.assertTrue(found["reachable"])
        self.assertEqual(found["source_id"], "pinballx")
        self.assertEqual(found["reason"], "")

    def test_a_folder_that_is_not_there_is_reported_rather_than_refused(self) -> None:
        """A share that has not mounted yet is the ordinary case, and the setting is
        still what somebody chose."""
        found = self.point_at(self.root / "not-mounted")

        self.assertFalse(found["reachable"])
        self.assertIn("not reachable", found["reason"])

    def test_a_folder_holding_nothing_we_read_says_which_problem_it_is(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()

        found = self.point_at(empty)

        self.assertTrue(found["reachable"])
        self.assertEqual(found["source_id"], "")
        self.assertIn("Nothing this build can read", found["reason"])

    def test_the_setting_survives_and_is_the_extensions_own(self) -> None:
        self.point_at(FIXTURE)

        self.assertEqual(self.store.settings("library_importer"),
                         {"source_root": str(FIXTURE)})


class PreviewTests(ImporterApiCase):
    def test_a_preview_counts_what_would_come_across(self) -> None:
        self.point_at(FIXTURE)

        found = self.client.get(f"{BASE}/preview").json()
        systems = {one["name"]: one for one in found["systems"]}

        self.assertEqual(systems["Visual Pinball X"]["games"], 3)
        self.assertEqual(systems["Visual Pinball X"]["with_artwork"], 3)
        self.assertEqual(systems["Visual Pinball X"]["already_matched"], 1)

    def test_a_preview_carries_what_the_read_could_not_do(self) -> None:
        """Counting without the notes would report a clean import of a library whose
        tables are on a machine that is not here."""
        self.point_at(FIXTURE)

        notes = self.client.get(f"{BASE}/preview").json()["notes"]

        self.assertTrue(any("not reachable from here" in note for note in notes))

    def test_a_preview_with_no_source_says_so_rather_than_failing(self) -> None:
        found = self.client.get(f"{BASE}/preview").json()

        self.assertEqual(found["systems"], [])
        self.assertIn("No source", found["notes"][0])


class ReadRootTests(ImporterApiCase):
    def setUp(self) -> None:
        super().setUp()
        # No browse roots of this machine's own, so what is allowed here is only ever
        # what the extension contributed. Unpatched, a developer whose library happens
        # to sit above the fixture would make the first of these pass for the wrong
        # reason.
        roots = unittest.mock.patch("httpapi.filesystem.roots", return_value=[])
        roots.start()
        self.addCleanup(roots.stop)

    def _may_read(self, path) -> bool:
        try:
            filesystem.within_roots(str(path))
        except Exception:
            return False
        return True

    def test_core_will_not_read_a_foreign_folder_until_it_is_chosen(self) -> None:
        self.assertFalse(self._may_read(FIXTURE / "Config" / "PinballX.ini"))

    def test_choosing_a_source_is_what_lets_core_take_a_file_from_it(self) -> None:
        self.point_at(FIXTURE)

        self.assertTrue(self._may_read(FIXTURE / "Config" / "PinballX.ini"))

    def test_pointing_somewhere_else_takes_the_old_one_away(self) -> None:
        """Replaced rather than added to: somebody who moves a share has not agreed to
        keep the machine reading the old one."""
        other = self.root / "other"
        other.mkdir()
        self.point_at(FIXTURE)

        self.point_at(other)

        self.assertFalse(self._may_read(FIXTURE / "Config" / "PinballX.ini"))
        self.assertTrue(self._may_read(other))

    def test_taking_the_extension_out_takes_its_folders_with_it(self) -> None:
        self.point_at(FIXTURE)

        with self.assertLogs("vpinfe.common.extensions", "ERROR"):
            self.registry.disable("library_importer", "asked to")

        self.assertFalse(self._may_read(FIXTURE / "Config" / "PinballX.ini"))

    def test_an_extension_that_never_asked_for_it_cannot_widen_anything(self) -> None:
        """The capability is the consent, so one that did not declare it is refused
        rather than quietly allowed."""
        from common.extensions.context import ExtensionFiles
        from common.extensions.contract import ContractError

        files = ExtensionFiles("nosy", allowed=False)

        with self.assertRaises(ContractError):
            files.set_roots(["/"])


if __name__ == "__main__":
    unittest.main()
