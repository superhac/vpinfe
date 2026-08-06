"""Collections over the wire: two kinds behind one resource.

The rules under test are the ones that keep the two kinds honest - a filter
collection has no member list to edit, membership is the table's own id, and
creating one is refused rather than guessed at when the request says both things.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from common.games.collection_store import CollectionStore
from tests.support.library import TempTree, fake_game

GAME_ID = "aaaa1111"
OTHER_ID = "bbbb2222"


def _game(folder: str, game_id: str) -> SimpleNamespace:
    return fake_game(f"/games/{folder}", folder,
                     meta={"Info": {"Title": folder, "Manufacturer": "Bally"},
                           "vpinfe": {"game_id": game_id}})


class CollectionsApiTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.path = f"{self.root}/collections.ini"
        open(self.path, "w").close()

        self.catalog = {GAME_ID: _game("Cactus Canyon (Bally 1998)", GAME_ID),
                        OTHER_ID: _game("Eight Ball (Bally 1977)", OTHER_ID)}

        # One manager over a throwaway file, shared by the service and the test.
        manager = CollectionStore(self.path)
        self.manager = manager
        for target in ("httpapi.collections.get_collections_manager",
                       "common.games.collections_service.get_collections_manager"):
            patcher = patch(target, lambda: manager)
            patcher.start()
            self.addCleanup(patcher.stop)
        catalog_patch = patch("httpapi.collections._catalog", lambda: self.catalog)
        catalog_patch.start()
        self.addCleanup(catalog_patch.stop)

        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    # --- creating -------------------------------------------------------

    def test_a_manual_collection_is_created_with_its_members(self) -> None:
        response = self.client.post("/collections",
                                    json={"name": "Favourites", "games": [GAME_ID]})

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["type"], "manual")
        self.assertEqual(body["game_count"], 1)
        self.assertIsNone(body["filters"])
        self.assertEqual(response.headers["Location"], "/api/v1/collections/Favourites")
        self.assertEqual(self.manager.get_members("Favourites"), [GAME_ID])

    def test_a_filter_collection_keeps_its_criteria(self) -> None:
        response = self.client.post("/collections", json={
            "name": "Bally 70s", "filters": {"manufacturer": "Bally", "year": "1977"}})

        body = response.json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(body["type"], "filter")
        self.assertEqual(body["filters"]["manufacturer"], "Bally")
        self.assertEqual(body["filters"]["year"], "1977")
        self.assertIsNone(body["game_count"],
                          "a filter collection has no stored member list to count")

    def test_asking_for_both_kinds_at_once_is_refused(self) -> None:
        response = self.client.post("/collections", json={
            "name": "Confused", "games": [GAME_ID], "filters": {"year": "1977"}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_an_unknown_game_id_is_named_rather_than_stored(self) -> None:
        response = self.client.post("/collections",
                                    json={"name": "Bad", "games": [GAME_ID, "nope"]})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["details"]["ids"], ["nope"])
        self.assertNotIn("Bad", self.manager.get_collections_name())

    def test_a_duplicate_name_conflicts(self) -> None:
        self.client.post("/collections", json={"name": "Favourites"})

        response = self.client.post("/collections", json={"name": "Favourites"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "conflict")

    def test_a_blank_name_is_refused(self) -> None:
        self.assertEqual(self.client.post("/collections", json={"name": "  "}).status_code,
                         400)

    # --- membership -----------------------------------------------------

    def test_adding_and_removing_a_member(self) -> None:
        self.client.post("/collections", json={"name": "Favourites"})

        added = self.client.put(f"/collections/Favourites/games/{GAME_ID}")
        self.assertEqual(added.status_code, 204)
        self.assertEqual(self.manager.get_members("Favourites"), [GAME_ID])

        removed = self.client.delete(f"/collections/Favourites/games/{GAME_ID}")
        self.assertEqual(removed.status_code, 204)
        self.assertEqual(self.manager.get_members("Favourites"), [])

    def test_adding_a_member_twice_is_a_success(self) -> None:
        """The caller's intent is that it be in there; it is."""
        self.client.post("/collections", json={"name": "Favourites"})
        self.client.put(f"/collections/Favourites/games/{GAME_ID}")

        again = self.client.put(f"/collections/Favourites/games/{GAME_ID}")

        self.assertEqual(again.status_code, 204)
        self.assertEqual(self.manager.get_members("Favourites"), [GAME_ID])

    def test_a_filter_collections_membership_cannot_be_edited(self) -> None:
        self.client.post("/collections",
                         json={"name": "Smart", "filters": {"manufacturer": "Bally"}})

        response = self.client.put(f"/collections/Smart/games/{GAME_ID}")

        self.assertEqual(response.status_code, 409)
        self.assertIn("criteria", response.json()["error"]["message"])

    def test_membership_of_an_unknown_game_or_collection_is_not_found(self) -> None:
        self.client.post("/collections", json={"name": "Favourites"})

        self.assertEqual(
            self.client.put("/collections/Favourites/games/nope").status_code, 404)
        self.assertEqual(
            self.client.put(f"/collections/Nope/games/{GAME_ID}").status_code, 404)

    def test_removing_a_game_that_is_not_a_member_is_not_found(self) -> None:
        self.client.post("/collections", json={"name": "Favourites"})

        response = self.client.delete(f"/collections/Favourites/games/{GAME_ID}")

        self.assertEqual(response.status_code, 404)

    # --- reading and deleting -------------------------------------------

    def test_listing_and_fetching(self) -> None:
        self.client.post("/collections", json={"name": "Favourites"})

        listed = self.client.get("/collections").json()["collections"]
        one = self.client.get("/collections/Favourites").json()

        self.assertEqual([row["name"] for row in listed], ["Favourites"])
        self.assertEqual(one["links"]["games"], "/api/v1/collections/Favourites/games")

    def test_resolved_membership_answers_for_both_kinds(self) -> None:
        self.client.post("/collections", json={"name": "Manual", "games": [GAME_ID]})
        self.client.post("/collections",
                         json={"name": "Smart", "filters": {"manufacturer": "Bally"}})

        manual = self.client.get("/collections/Manual/games").json()
        smart = self.client.get("/collections/Smart/games").json()

        self.assertEqual([row["id"] for row in manual["games"]], [GAME_ID])
        self.assertEqual(manual["total"], 1)
        self.assertEqual({row["id"] for row in smart["games"]}, {GAME_ID, OTHER_ID},
                         "the filter resolves against the library, not a stored list")

    def test_deleting_a_collection(self) -> None:
        self.client.post("/collections", json={"name": "Favourites"})

        response = self.client.delete("/collections/Favourites")

        self.assertEqual(response.status_code, 204)
        self.assertNotIn("Favourites", self.manager.get_collections_name())

    def test_an_unknown_collection_is_a_not_found_envelope(self) -> None:
        response = self.client.get("/collections/Nope")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_a_name_with_a_space_survives_the_round_trip(self) -> None:
        self.client.post("/collections", json={"name": "Last Played"})

        body = self.client.get("/collections/Last%20Played").json()

        self.assertEqual(body["name"], "Last Played")
        self.assertEqual(body["links"]["self"], "/api/v1/collections/Last%20Played")

    def test_discovery_advertises_collections(self) -> None:
        self.assertEqual(self.client.get("/").json()["links"]["collections"],
                         "/api/v1/collections")


if __name__ == "__main__":
    unittest.main()


class CollectionEntriesTests(CollectionsApiTests):
    """The play lens. Same resolution the theme payload uses, serialized for REST."""

    def setUp(self) -> None:
        super().setUp()
        # The base fixture's games have no tables, which is a real state - a folder
        # nothing has parsed - but it produces no entries by design. Give them one
        # each so there is something for the play lens to answer with.
        for index, game in enumerate(self.catalog.values()):
            game.meta_config["tables"] = {
                f"tbl{index}": {"id": f"tbl{index}", "filename": f"game{index}.vpx",
                                "version": "1.0", "rom": ""}}

    def test_entries_answer_one_per_game_by_default(self) -> None:
        self.client.post("/collections", json={"name": "Manual", "games": [GAME_ID]})

        body = self.client.get("/collections/Manual/entries").json()

        self.assertFalse(body["expanded"])
        self.assertEqual(body["count"], len(body["entries"]))
        for entry in body["entries"]:
            self.assertTrue(entry["table"]["id"], "every entry names a table")
            self.assertIn("launch", entry["links"])

    def test_expanded_is_echoed_back(self) -> None:
        self.client.post("/collections", json={"name": "Manual", "games": [GAME_ID]})

        body = self.client.get("/collections/Manual/entries?expanded=true").json()

        self.assertTrue(body["expanded"])

    def test_a_collection_that_does_not_exist_is_a_404(self) -> None:
        self.assertEqual(self.client.get("/collections/Nope/entries").status_code, 404)

    def test_a_filter_this_build_cannot_read_is_refused_by_name(self) -> None:
        """Answering with what is left would be a different question, silently."""
        self.client.post("/collections",
                         json={"name": "VR", "filters": {"manufacturer": "Bally"}})
        self.manager.set_filter("VR", "app", "VPX VR")
        self.manager.save()

        response = self.client.get("/collections/VR/entries")

        self.assertEqual(response.status_code, 409)
        self.assertIn("app", response.json()["error"]["details"]["unknown_filters"])

    def test_the_two_lenses_agree_on_order(self) -> None:
        """The defect this replaced: REST answered in one order, the frontend another."""
        self.client.post("/collections",
                         json={"name": "Smart", "filters": {"manufacturer": "Bally"}})

        games = [row["id"] for row in
                 self.client.get("/collections/Smart/games").json()["games"]]
        entries = [e["game"]["id"] for e in
                   self.client.get("/collections/Smart/entries").json()["entries"]]

        self.assertEqual(games, entries)

    def test_the_default_table_is_computed_not_read_off_the_entry(self) -> None:
        """`default` is the game's own choice, stored in its vpinfe section. Reading it
        off the table entry - where nothing writes it - answers false for everything."""
        game = next(iter(self.catalog.values()))
        game.meta_config["tables"] = {
            "aa": {"id": "aa", "filename": "z-later.vpx"},
            "bb": {"id": "bb", "filename": "a-earlier.vpx"},
        }
        self.client.post("/collections", json={"name": "Manual",
                                               "games": [list(self.catalog)[0]]})

        entries = self.client.get("/collections/Manual/entries?expanded=true").json()
        defaults = [e["table"]["id"] for e in entries["entries"] if e["table"]["default"]]

        self.assertEqual(defaults, ["bb"], "the resolved default, exactly one of them")
