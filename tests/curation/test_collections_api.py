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
from tests.support.library import TempTree, fake_game, write_game

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
        # Reported as lists: the many-valued axes have always been stored comma-joined
        # and split again by the matcher, and a bare string typed the schema as
        # single-valued so no generated client could produce a second value.
        self.assertEqual(body["filters"]["manufacturer"], ["Bally"])
        self.assertEqual(body["filters"]["year"], ["1977"])
        self.assertEqual(body["game_count"], 0,
                         "the stored member list, which criteria do not replace")

    def test_the_reported_sort_is_the_one_the_collection_resolves_by(self) -> None:
        """Read off the `order` block, not the criteria: those carry a default for every
        key a collection never set, so a Last Played reported `Alpha`."""
        self.manager.add_collection("Recent")
        self.manager.make_filter_collection(
            "Recent", {"played": True},
            order={"by": "last_played", "direction": "desc"})
        self.manager.save()

        body = self.client.get("/collections/Recent").json()

        self.assertEqual(body["filters"]["order_by"], "last_played")
        self.assertEqual(body["filters"]["direction"], "desc")

    def test_a_2x_sort_name_is_accepted_and_reported_in_the_stored_vocabulary(self) -> None:
        """The 2.x sort *values* are what carries over. There was never a 2.x client for
        this API - the names it accepts are 3.0's - but a collection on disk holds those
        spellings, so a caller reading one back may well send them."""
        response = self.client.post("/collections", json={
            "name": "Most Played", "filters": {"order_by": "Highest StartCount"}})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["filters"]["order_by"], "play_count")

    def test_criteria_and_named_games_are_stored_together(self) -> None:
        """Not two kinds. COLLECTIONS 2.11 makes them combinable and the resolver
        applies members over what the criteria matched, so a collection may follow a
        rule and still hold something somebody put there by hand."""
        response = self.client.post("/collections", json={
            "name": "Both", "games": [GAME_ID], "filters": {"year": "1977"}})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["type"], "filter")
        self.assertEqual(self.manager.get_members("Both"), [GAME_ID])
        self.assertEqual(self.manager.get_filters("Both")["year"], "1977")

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

    def test_a_collection_that_filters_can_still_be_added_to(self) -> None:
        """A named member states what the collection holds for that game whether or not
        the criteria matched it - which is what makes "add this one too" expressible."""
        self.client.post("/collections",
                         json={"name": "Smart", "filters": {"manufacturer": "Bally"}})

        response = self.client.put(f"/collections/Smart/games/{GAME_ID}")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.manager.get_members("Smart"), [GAME_ID])

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

        self.assertEqual(body["count"], len(body["entries"]))
        for entry in body["entries"]:
            self.assertTrue(entry["table"]["id"], "every entry names a table")
            self.assertIn("launch", entry["links"])

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

        # The entry the collection resolves to is the default, and `default` on it is
        # the game's own choice rather than a flag read off the table row.
        entries = self.client.get("/collections/Manual/entries").json()["entries"]

        self.assertEqual([e["table"]["id"] for e in entries], ["bb"])
        self.assertTrue(entries[0]["table"]["default"], "the resolved default")


TABLED_ID = "Tabled000001"
FOLDER = "Cactus Canyon (Bally 1998)"
DESKTOP = f"{FOLDER}.vpx"
VR = f"{FOLDER} - VR.vpx"
TABLED_INFO = {
    "Info": {"Name": "Cactus Canyon", "Manufacturer": "Bally"},
    "VPinFE": {"game_id": TABLED_ID},
    "tables": {
        "tbl0000001": {"id": "tbl0000001", "filename": DESKTOP, "version": "1.0"},
        "tbl0000002": {"id": "tbl0000002", "filename": VR, "version": "2.1"},
    },
}


class MemberTableTests(TempTree):
    """Which table a member names, changed in place.

    Its own fixture because the table routes enumerate the folder: a game with no
    directory behind it has no tables, so every id is refused before the collection
    is reached.
    """

    def setUp(self) -> None:
        super().setUp()
        self.folder = write_game(self.root, FOLDER, info=TABLED_INFO, vpx=False,
                                 files={DESKTOP: b"vpx", VR: b"vpx"})
        game = fake_game(self.folder, FOLDER, meta=TABLED_INFO)
        self.catalog = {TABLED_ID: game}

        self.path = f"{self.root}/collections.ini"
        open(self.path, "w").close()
        manager = CollectionStore(self.path)
        self.manager = manager
        for target in ("httpapi.collections.get_collections_manager",
                       "common.games.collections_service.get_collections_manager"):
            patcher = patch(target, lambda: manager)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target in ("httpapi.collections._catalog", "httpapi.games._catalog"):
            patcher = patch(target, lambda: self.catalog)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.client = TestClient(httpapi.create_api_app(),
                                 raise_server_exceptions=False)
        self.client.post("/collections", json={"name": "Favourites"})

    def _refs(self) -> list[dict]:
        return self.manager.get_member_refs("Favourites")

    def test_a_member_keeps_its_place_when_its_table_changes(self) -> None:
        """The reason this is a route and not remove-then-add: curated order is what a
        manual collection is for, and rebuilding the ref sends that row to the end."""
        self.client.put(f"/collections/Favourites/games/{TABLED_ID}")

        response = self.client.put(f"/collections/Favourites/games/{TABLED_ID}/table",
                                   json={"table": "tbl0000002"})

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self._refs(),
                         [{"game": TABLED_ID, "table": "tbl0000002"}])

    def test_a_member_can_be_handed_back_its_game_default(self) -> None:
        """The return trip, which is what makes the control reversible."""
        self.client.put(f"/collections/Favourites/games/{TABLED_ID}",
                        json={"table": "tbl0000001"})

        response = self.client.put(f"/collections/Favourites/games/{TABLED_ID}/table",
                                   json={"table": "", "was": "tbl0000001"})

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self._refs(), [{"game": TABLED_ID}],
                         "the key is dropped rather than written empty")

    def test_naming_a_table_of_some_other_game_is_refused(self) -> None:
        """A ref pointing at a table this game has not got resolves to nothing and
        reads as missing for good, so it is refused rather than stored."""
        self.client.put(f"/collections/Favourites/games/{TABLED_ID}")

        response = self.client.put(f"/collections/Favourites/games/{TABLED_ID}/table",
                                   json={"table": "somebody-elses"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._refs(), [{"game": TABLED_ID}])

    def test_a_game_named_twice_can_be_reordered(self) -> None:
        """An order is over the rows, and section 2.10 lets one game hold several.

        `get_members` de-duplicates by design, so an order compared against it counted
        one row where the collection has two and refused every move in a collection
        holding two tables of a game.
        """
        for table in ("tbl0000001", "tbl0000002"):
            self.client.put(f"/collections/Favourites/games/{TABLED_ID}",
                            json={"table": table})

        response = self.client.put("/collections/Favourites/order",
                                   json={"games": [TABLED_ID, TABLED_ID]})

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self._refs(),
                         [{"game": TABLED_ID, "table": "tbl0000001"},
                          {"game": TABLED_ID, "table": "tbl0000002"}],
                         "both refs survive, in their own order")

    def test_an_order_missing_one_of_a_repeated_game_is_refused(self) -> None:
        """Naming it once would drop the other ref, which is the silent removal the
        route exists to refuse."""
        for table in ("tbl0000001", "tbl0000002"):
            self.client.put(f"/collections/Favourites/games/{TABLED_ID}",
                            json={"table": table})

        response = self.client.put("/collections/Favourites/order",
                                   json={"games": [TABLED_ID]})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self._refs()), 2, "and nothing was written")

    def test_naming_a_table_another_row_already_uses_is_refused(self) -> None:
        """A conflict, not a merge. The collection holds the pairing once (2.10), and
        merging would drop a row without anything on the wire saying which."""
        for table in ("tbl0000001", "tbl0000002"):
            self.client.put(f"/collections/Favourites/games/{TABLED_ID}",
                            json={"table": table})

        response = self.client.put(
            f"/collections/Favourites/games/{TABLED_ID}/table",
            json={"table": "tbl0000002", "was": "tbl0000001"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self._refs()), 2, "and both rows are still there")

    def test_changing_a_member_that_is_not_there_is_not_found(self) -> None:
        response = self.client.put(f"/collections/Favourites/games/{TABLED_ID}/table",
                                   json={"table": "tbl0000001"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._refs(), [])
