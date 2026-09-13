"""Creating an entry, and putting a game file into one, over the wire.

Both exist because everything else that writes a game needs an id that already exists,
and the only way to get one was to upload a bundle through a browser. An importer
converting a foreign library has the files on a share already.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

import httpapi
from common.games import game_repository, locations
from common.games.info_file import GAME_ID_KEY
from tests.support.library import write_game


class CreateGameCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.library = self.root / "library"
        self.library.mkdir()
        self.elsewhere = self.root / "elsewhere"
        self.elsewhere.mkdir()

        self.store = locations.LocationStore(os.path.join(self.tmp.name, "locations.json"))
        patcher = patch.object(locations, "get_location_store", return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store.mark_migration(locations.SEEDED)

        # A read allowlist of this test's own. Unpatched it is built from this machine's
        # configuration, so `within_roots` would be answering about a real library.
        # Resolved, the way the real one answers: /var is a symlink on macOS, and a root
        # that has not been through realpath matches nothing under it.
        roots = patch("httpapi.filesystem.roots",
                      side_effect=lambda game_dir="": [
                          {"path": str(self.elsewhere.resolve()), "name": "elsewhere",
                           "source": "configured"},
                          {"path": str(self.library.resolve()), "name": "library",
                           "source": "library"}])
        roots.start()
        self.addCleanup(roots.stop)

        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)
        self.addCleanup(game_repository.all_games, True)

    def add_location(self, path: Path, location_id: str = "one") -> None:
        self.client.put(f"/locations/{location_id}", json={"path": str(path)})
        self.client.put(f"/locations/{location_id}/write-to", json={})
        game_repository.all_games(reload=True)

    def create(self, name: str, **body) -> dict:
        return self.client.post("/games", json={"name": name, **body})


class CreateTests(CreateGameCase):
    def test_a_created_game_has_a_folder_a_record_and_an_id(self) -> None:
        self.add_location(self.library)

        made = self.create("Attack from Mars (Bally 1995)")

        self.assertEqual(made.status_code, 201, made.text)
        folder = self.library / "Attack from Mars (Bally 1995)"
        self.assertTrue(folder.is_dir())
        record = folder / "Attack from Mars (Bally 1995).info"
        self.assertTrue(record.is_file())
        held = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(held["vpinfe"][GAME_ID_KEY], made.json()["id"])

    def test_it_is_in_the_library_immediately(self) -> None:
        """A caller that just made one has to be able to address it."""
        self.add_location(self.library)
        made = self.create("Medieval Madness")

        found = self.client.get(f"/games/{made.json()['id']}")

        self.assertEqual(found.status_code, 200, found.text)

    def test_it_lands_in_the_location_new_games_go_to(self) -> None:
        second = self.root / "second"
        second.mkdir()
        self.add_location(self.library, "one")
        self.add_location(second, "two")

        self.create("Taxi")

        self.assertTrue((second / "Taxi").is_dir())
        self.assertFalse((self.library / "Taxi").is_dir())

    def test_a_named_location_overrides_where_it_goes(self) -> None:
        second = self.root / "second"
        second.mkdir()
        self.add_location(self.library, "one")
        self.add_location(second, "two")

        self.create("Taxi", location="one")

        self.assertTrue((self.library / "Taxi").is_dir())

    def test_it_is_found_in_a_location_that_already_holds_games(self) -> None:
        """The folder is looked up canonically rather than by spelling.

        Re-reading one folder resolves the path it is given, so the game that has just
        been created carries the real path while a game found by a scan carries the
        location's own spelling. On macOS every path under /var differs between those
        two, and matching the spelling meant a game could be created and then not found.

        An empty library never sees it: re-reading one folder is skipped where the
        location has loaded nothing, and the whole-library fallback keeps the spelling.
        """
        write_game(self.library, "Already Here")
        self.add_location(self.library)

        made = self.create("Taxi")

        self.assertEqual(made.status_code, 201, made.text)
        self.assertEqual(self.client.get(f"/games/{made.json()['id']}").status_code, 200)

    def test_a_folder_that_is_already_there_is_a_conflict(self) -> None:
        self.add_location(self.library)
        (self.library / "Taxi").mkdir()

        found = self.create("Taxi")

        self.assertEqual(found.status_code, 409)
        self.assertEqual(found.json()["error"]["code"], "conflict")

    def test_a_name_that_is_only_reserved_characters_is_refused(self) -> None:
        self.add_location(self.library)

        found = self.create("///")

        self.assertEqual(found.status_code, 400)

    def test_with_nowhere_to_write_it_says_so_rather_than_failing_late(self) -> None:
        found = self.create("Taxi")

        self.assertEqual(found.status_code, 400)
        self.assertIn("nowhere", found.json()["error"]["message"])

    def test_a_refusal_names_the_locations_that_would_have_worked(self) -> None:
        """The answer somebody needs is not only that it failed."""
        self.add_location(self.library, "one")
        read_only = self.root / "readonly"
        read_only.mkdir()
        self.client.put("/locations/two", json={"path": str(read_only)})
        self.client.put("/locations/two/write-to", json={})
        os.chmod(read_only, 0o500)
        self.addCleanup(os.chmod, read_only, 0o700)

        found = self.create("Taxi")

        self.assertEqual(found.status_code, 400)
        named = [one["location_id"]
                 for one in found.json()["error"]["details"]["alternatives"]]
        self.assertIn("one", named)


class ImportTableTests(CreateGameCase):
    def _game(self, name: str = "Taxi") -> str:
        self.add_location(self.library)
        return self.create(name).json()["id"]

    def _source(self, name: str = "Taxi (Williams 1988).vpx") -> Path:
        path = self.elsewhere / name
        path.write_bytes(b"not really a table")
        return path

    def test_a_file_is_copied_in_and_becomes_a_table(self) -> None:
        game_id = self._game()
        source = self._source()

        made = self.client.post(f"/games/{game_id}/tables/import",
                                json={"path": str(source)})

        self.assertEqual(made.status_code, 201, made.text)
        self.assertTrue((self.library / "Taxi" / source.name).is_file())
        self.assertTrue(source.is_file(), "a copy, not a move")
        self.assertTrue(made.json()["id"])

    def test_the_table_can_be_addressed_by_the_id_it_came_back_with(self) -> None:
        """A minting pass that runs at startup answers too late to be told to."""
        game_id = self._game()
        table_id = self.client.post(f"/games/{game_id}/tables/import",
                                    json={"path": str(self._source())}).json()["id"]

        listed = self.client.get(f"/games/{game_id}/tables").json()["tables"]

        self.assertEqual([one["id"] for one in listed], [table_id])

    def test_a_file_outside_the_allowlist_is_refused(self) -> None:
        game_id = self._game()
        outside = self.root / "outside.vpx"
        outside.write_bytes(b"not really a table")

        found = self.client.post(f"/games/{game_id}/tables/import",
                                 json={"path": str(outside)})

        self.assertEqual(found.status_code, 400)
        self.assertFalse((self.library / "Taxi" / "outside.vpx").exists())

    def test_a_file_nothing_plays_is_refused(self) -> None:
        game_id = self._game()
        source = self._source("notes.txt")

        found = self.client.post(f"/games/{game_id}/tables/import",
                                 json={"path": str(source)})

        self.assertEqual(found.status_code, 400)
        self.assertIn("notes.txt", found.json()["error"]["message"])

    def test_a_second_file_by_the_same_name_is_a_conflict(self) -> None:
        game_id = self._game()
        source = self._source()
        self.client.post(f"/games/{game_id}/tables/import", json={"path": str(source)})

        again = self.client.post(f"/games/{game_id}/tables/import",
                                 json={"path": str(source)})

        self.assertEqual(again.status_code, 409)


class DetailsTests(CreateGameCase):
    def _game(self, name: str = "Taxi") -> str:
        self.add_location(self.library)
        return self.create(name).json()["id"]

    def _put(self, game_id: str, **body):
        return self.client.put(f"/games/{game_id}/details", json=body)

    def test_a_game_no_catalog_matched_can_still_say_what_it_is(self) -> None:
        game_id = self._game()

        found = self._put(game_id, title="Taxi", manufacturer="Williams",
                          year="1988", type="SS", themes=["Cars", "City"])

        self.assertEqual(found.status_code, 200, found.text)
        row = found.json()
        self.assertEqual(row["manufacturer"], "Williams")
        self.assertEqual(row["year"], "1988")
        self.assertEqual(row["themes"], ["Cars", "City"])

    def test_it_lands_in_the_record_on_disk(self) -> None:
        game_id = self._game()
        self._put(game_id, manufacturer="Williams")

        held = json.loads((self.library / "Taxi" / "Taxi.info")
                          .read_text(encoding="utf-8"))

        self.assertEqual(held["Info"]["Manufacturer"], "Williams")

    def test_a_field_left_out_is_left_alone(self) -> None:
        """An importer filling in a year should not have to restate a title it never
        knew, which a whole-value write would make it do."""
        game_id = self._game()
        self._put(game_id, title="Taxi", manufacturer="Williams")

        self._put(game_id, year="1988")

        row = self.client.get(f"/games/{game_id}").json()
        self.assertEqual(row["manufacturer"], "Williams")
        self.assertEqual(row["year"], "1988")

    def test_a_field_sent_empty_is_cleared(self) -> None:
        """Left alone and cleared have to be different, or nothing can undo a typo."""
        game_id = self._game()
        self._put(game_id, manufacturer="Willaims")

        self._put(game_id, manufacturer="")

        self.assertEqual(self.client.get(f"/games/{game_id}").json()["manufacturer"], "")

    def test_a_game_that_is_not_here_is_a_404(self) -> None:
        self.add_location(self.library)

        self.assertEqual(self._put("nosuchgame", title="x").status_code, 404)


if __name__ == "__main__":
    unittest.main()
