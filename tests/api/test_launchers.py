"""Launchers over the wire.

The id is the caller's to send, which is the part worth pinning: it is also how a launcher
copied to a cabinet lands without being renumbered, and renumbering would break every
mapping that travelled with it.
"""

import os
import pathlib
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


class TableFileSeedingTests(unittest.TestCase):
    """The two settings layers do not stack, so the write that gives a table its own
    file takes the folder's other keys off it. Carrying them across on that first write
    is what keeps the table doing what it did a moment ago."""

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = launchers.LauncherStore(
            os.path.join(self.tmp.name, "launchers.json"))
        store_patch = patch.object(launchers, "get_launcher_store",
                                   return_value=self.store)
        store_patch.start()
        self.addCleanup(store_patch.stop)
        self.store.mark_migration(launcher_migration.SEEDED)
        self.client = _client()
        self.client.put("/launchers/l1",
                        json={"app": "vpx", "settings": {"bin_path": "/opt/vpx"}})
        folder = os.path.join(self.tmp.name, "Attack from Mars")
        os.makedirs(folder)
        self.table = os.path.join(folder, "afm.vpx")
        pathlib.Path(self.table).touch()
        pathlib.Path(folder, "Attack from Mars.ini").write_text(
            "[Player]\nBallTrail = 1\nFXAA = 3\n")
        self.beside = os.path.join(folder, "afm.ini")
        patcher = patch("httpapi.launchers._game_file", return_value=self.table)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write(self, **body):
        return self.client.put("/launchers/l1/config",
                               json={"scope": "entry", "table": "t1", **body})

    def test_a_folder_says_what_it_is_giving_a_table_with_no_file_of_its_own(self) -> None:
        got = self.client.get("/launchers/l1/config/reaching?table=t1")

        self.assertEqual(got.json()["reaching"],
                         {"Player.BallTrail": "1", "Player.FXAA": "3"})

    def test_the_first_write_carries_them_across_when_it_is_asked_to(self) -> None:
        self._write(values={"Backglass.BackglassWndX": "137"}, seed=True)

        written = pathlib.Path(self.beside).read_text()
        self.assertIn("BallTrail = 1", written)
        self.assertIn("FXAA = 3", written)
        self.assertIn("BackglassWndX = 137", written)

    def test_and_the_value_being_set_wins_over_what_it_carried(self) -> None:
        """The write is the reason any of this is happening."""
        self._write(values={"Player.FXAA": "0"}, seed=True)

        self.assertIn("FXAA = 0", pathlib.Path(self.beside).read_text())

    def test_without_asking_it_writes_only_what_it_was_given(self) -> None:
        """Which is what takes the other two off the table - so nothing does this
        silently."""
        self._write(values={"Backglass.BackglassWndX": "137"})

        written = pathlib.Path(self.beside).read_text()
        self.assertNotIn("BallTrail", written)
        self.assertIn("BackglassWndX = 137", written)

    def test_a_table_that_already_has_a_file_has_nothing_left_reaching_it(self) -> None:
        """So the second write cannot re-seed from a folder it no longer reads."""
        self._write(values={"Backglass.BackglassWndX": "137"}, seed=True)

        got = self.client.get("/launchers/l1/config/reaching?table=t1")

        self.assertEqual(got.json()["reaching"], {})
