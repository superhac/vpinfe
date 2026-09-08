"""Locations over the wire.

The reachable and writable flags come back on every read rather than being stored, which
is the part worth pinning: a stored answer is wrong the moment a mount drops, and a late
mount is the case this whole resource exists to report well.
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

import httpapi
from common.games import locations


def _client() -> TestClient:
    return TestClient(httpapi.create_api_app(), raise_server_exceptions=False)


class LocationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = locations.LocationStore(os.path.join(self.tmp.name, "locations.json"))
        patcher = patch.object(locations, "get_location_store", return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Marked as already seeded: building the app runs the startup pass, and a row
        # appearing from this machine's own config would make every count here wrong.
        self.store.mark_migration(locations.SEEDED)
        self.client = _client()

    def _folder(self, name: str) -> str:
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        return str(folder)

    def _put(self, location_id: str, path: str, **body):
        return self.client.put(f"/locations/{location_id}",
                               json={"path": path, **body})

    def test_an_install_with_none_answers_an_empty_list(self) -> None:
        body = self.client.get("/locations").json()

        self.assertEqual(body["locations"], [])
        self.assertEqual(body["write_to"], "")

    def test_a_location_comes_back_with_what_the_disk_says(self) -> None:
        self._put("one", self._folder("share"))

        row = self.client.get("/locations").json()["locations"][0]

        self.assertTrue(row["reachable"])
        self.assertTrue(row["writable"])
        self.assertEqual(row["reason"], "")

    def test_an_unreachable_location_says_why(self) -> None:
        """"Unavailable" on its own leaves a person nothing to act on."""
        self._put("gone", str(self.root / "never-mounted"))

        row = self.client.get("/locations").json()["locations"][0]

        self.assertFalse(row["reachable"])
        self.assertTrue(row["reason"])

    def test_a_read_only_location_is_reachable_and_not_writable(self) -> None:
        path = self._folder("readonly")
        self._put("ro", path)
        os.chmod(path, 0o500)
        self.addCleanup(os.chmod, path, 0o700)

        row = self.client.get("/locations").json()["locations"][0]

        self.assertTrue(row["reachable"])
        self.assertFalse(row["writable"])

    def test_the_same_folder_under_a_new_id_replaces_the_row(self) -> None:
        """Two rows for one place would each report their own state."""
        path = self._folder("share")
        self._put("first", path)
        self._put("second", path)

        self.assertEqual(len(self.client.get("/locations").json()["locations"]), 1)

    def test_a_location_needs_a_path(self) -> None:
        self.assertEqual(self._put("one", "  ").status_code, 400)

    def test_a_kind_this_build_does_not_know_is_refused(self) -> None:
        response = self._put("one", self._folder("share"), kind="mounted-elsewhere")

        self.assertEqual(response.status_code, 400)
        self.assertIn("mounted-elsewhere", response.json()["error"]["message"])

    def test_the_write_target_is_named_rather_than_left_to_be_derived(self) -> None:
        self._put("one", self._folder("share"))
        self._put("two", self._folder("other"))
        self.client.put("/locations/two/write-to")

        body = self.client.get("/locations").json()

        self.assertEqual(body["write_to"], "two")
        self.assertEqual([r["location_id"] for r in body["locations"] if r["write_to"]],
                         ["two"])

    def test_pointing_at_a_location_that_is_not_there_is_refused(self) -> None:
        self.assertEqual(self.client.put("/locations/nothing/write-to").status_code, 404)

    def test_forgetting_one_that_is_not_there_is_refused(self) -> None:
        self.assertEqual(self.client.delete("/locations/nothing").status_code, 404)

    def test_forgetting_one_removes_it(self) -> None:
        self._put("one", self._folder("share"))

        self.assertEqual(self.client.delete("/locations/one").status_code, 200)
        self.assertEqual(self.client.get("/locations").json()["locations"], [])


if __name__ == "__main__":
    unittest.main()
