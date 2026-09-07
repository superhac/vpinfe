"""Launchers over the wire.

The id is the caller's to send, which is the part worth pinning: it is also how a launcher
copied to a cabinet lands without being renumbered, and renumbering would break every
mapping that travelled with it.
"""

import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

import httpapi
from common.games import launcher_migration, launchers


def _client() -> TestClient:
    return TestClient(httpapi.create_api_app(), raise_server_exceptions=False)


class LauncherApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = launchers.LauncherStore(
            os.path.join(self.tmp.name, "launchers.json"))
        patcher = patch.object(launchers, "get_launcher_store",
                               return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Marked as already seeded: building the app runs the startup pass, and a
        # shipped launcher appearing under these would make every count here wrong.
        # A real install is in this state from its second start onwards.
        self.store.mark_migration(launcher_migration.SEEDED)
        self.client = _client()

    def _put(self, launcher_id: str, **body):
        return self.client.put(f"/launchers/{launcher_id}",
                               json={"app": "vpx", **body})

    def test_an_install_with_none_answers_an_empty_list(self) -> None:
        body = self.client.get("/launchers").json()

        self.assertEqual(body["launchers"], [])
        self.assertEqual(body["mappings"], {})
        self.assertIsNone(body["defaults"]["vpx"])

    def test_a_launcher_carries_the_shape_of_its_own_settings(self) -> None:
        """So a client can draw an editor without knowing what a Visual Pinball launcher
        happens to hold - which is the point of the app declaring its fields."""
        self._put("one", display_name="VPX")

        found = self.client.get("/launchers").json()["launchers"][0]

        self.assertEqual(found["app_name"], "Visual Pinball X")
        keys = [field["key"] for field in found["fields"]]
        self.assertIn("bin_path", keys)
        self.assertEqual(sorted(found["settings"]), sorted(keys))

    def test_the_caller_names_the_id(self) -> None:
        """A launcher copied from another machine is that launcher. Minting a new id here
        would break the mappings that came with it."""
        self._put("kept-id", display_name="VPX")

        self.assertEqual(self.client.get("/launchers").json()["launchers"][0]
                         ["launcher_id"], "kept-id")

    def test_putting_it_again_replaces_it(self) -> None:
        self._put("one", display_name="First")
        self._put("one", display_name="Second")

        held = self.client.get("/launchers").json()["launchers"]

        self.assertEqual([one["display_name"] for one in held], ["Second"])

    def test_the_default_is_named_rather_than_left_to_be_worked_out(self) -> None:
        """A client re-deriving "first enabled for this app" is a second place for the
        rule to be wrong."""
        self._put("off", display_name="Off", enabled=False)
        self._put("on", display_name="On")

        self.assertEqual(self.client.get("/launchers").json()["defaults"]["vpx"], "on")

    def test_an_app_this_build_does_not_know_is_refused(self) -> None:
        """A typo would make a launcher nothing can ever run, listed as though it could."""
        response = self.client.put("/launchers/one", json={"app": "atari-pinball"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("atari-pinball", response.json()["error"]["message"])

    def test_a_launcher_says_what_the_disk_makes_of_its_paths(self) -> None:
        """Without it, one pointing at a program that has been uninstalled looks exactly
        like one that works, and the list cannot say which of two can run a table."""
        self._put("one", settings={"bin_path": "/nope/VPinballX"})

        checks = self.client.get("/launchers").json()["launchers"][0]["checks"]

        self.assertEqual(checks["bin_path"]["state"], "missing")
        self.assertTrue(checks["bin_path"]["reason"])

    def test_a_path_that_is_there_is_reported_ok(self) -> None:
        import os
        program = os.path.join(self.tmp.name, "VPinballX")
        with open(program, "w", encoding="utf-8"):
            pass
        os.chmod(program, 0o755)
        self._put("one", settings={"bin_path": program})

        checks = self.client.get("/launchers").json()["launchers"][0]["checks"]

        self.assertEqual(checks["bin_path"]["state"], "ok")
        self.assertEqual(checks["bin_path"]["reason"], "")

    def test_only_the_fields_that_name_a_path_are_checked(self) -> None:
        """A state on every field would be a mark on every row, which says nothing."""
        self._put("one", settings={"bin_path": "/nope/VPinballX"})

        checks = self.client.get("/launchers").json()["launchers"][0]["checks"]

        self.assertNotIn("launch_env", checks)
        self.assertNotIn("log_delete_on_start", checks)

    def test_removing_one_takes_its_mappings(self) -> None:
        self._put("one", display_name="VPX")
        self.client.put("/launchers/mappings/t1", json={"launcher_id": "one"})

        self.client.delete("/launchers/one")

        body = self.client.get("/launchers").json()
        self.assertEqual(body["launchers"], [])
        self.assertEqual(body["mappings"], {})

    def test_removing_one_that_is_not_there_is_a_404(self) -> None:
        self.assertEqual(self.client.delete("/launchers/ghost").status_code, 404)

    def test_a_table_can_be_pointed_at_one_and_cleared(self) -> None:
        self._put("one", display_name="VPX")

        self.client.put("/launchers/mappings/t1", json={"launcher_id": "one"})
        self.assertEqual(self.client.get("/launchers").json()["mappings"],
                         {"t1": "one"})

        self.client.put("/launchers/mappings/t1", json={"launcher_id": ""})
        self.assertEqual(self.client.get("/launchers").json()["mappings"], {},
                         "cleared drops the row, because absent already means default")

    def test_pointing_a_table_at_a_launcher_that_is_not_there_is_refused(self) -> None:
        """Storing it would be a table reporting an override it does not have."""
        response = self.client.put("/launchers/mappings/t1",
                                   json={"launcher_id": "ghost"})

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
