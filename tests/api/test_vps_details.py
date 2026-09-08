"""A game's details against the entry it is matched to.

They agree by construction: `Info` is written from the entry when a folder is
associated, so on a real library nothing disagrees - measured across 71 matched games,
not one field did. Correcting a match is what parts them, and it parts all of them at
once: the details go on describing the machine the game used to be.

So this is not drift detection. It is the second half of re-matching.
"""

from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from tests.support.library import TempTree, fake_game, write_game

GAME_ID = "Details001"
FOLDER = "The Addams Family (Bally 1992)"
FOUND = "aT_GONvw"
OTHER = "P12wTlyY"

INFO = {
    "Info": {"Title": "The Addams Family", "Manufacturer": "Bally", "Year": 1992,
             "Type": "SS", "Themes": ["Movie"], "VPSId": FOUND, "IPDBId": "20"},
    "vpinfe": {"game_id": GAME_ID},
    "tables": {"tbl0000001": {"id": "tbl0000001", "filename": f"{FOLDER}.vpx"}},
}

CATALOG = [
    {"id": FOUND, "name": "The Addams Family", "manufacturer": "Bally", "year": 1992,
     "type": "SS", "theme": ["Movie"], "ipdbUrl": "https://www.ipdb.org/machine.cgi?id=20"},
    {"id": OTHER, "name": "Star Trek", "manufacturer": "Data East", "year": 1991,
     "type": "SS", "theme": ["Movie", "Outer Space"],
     "ipdbUrl": "https://www.ipdb.org/machine.cgi?id=2356"},
]


class VpsDetailTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.meta = copy.deepcopy(INFO)
        self.folder = write_game(self.root, FOLDER, info=self.meta, vpx=False,
                                 files={f"{FOLDER}.vpx": b"vpx"})
        self.game = fake_game(self.folder, FOLDER, meta=copy.deepcopy(self.meta))
        patcher = patch("common.games.game_service.load_vpsdb",
                        return_value=copy.deepcopy(CATALOG))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("httpapi.games._catalog", return_value={GAME_ID: self.game})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(httpapi.create_api_app(),
                                 raise_server_exceptions=False)

    def _rematch(self, vps_id: str) -> None:
        path = self.folder / f"{FOLDER}.info"
        written = json.loads(path.read_text())
        written["vpinfe"]["alt_vpsid"] = vps_id
        path.write_text(json.dumps(written))
        self.game.meta_config = written

    def _differs(self) -> dict[str, tuple[str, str]]:
        response = self.client.get(f"/games/{GAME_ID}/vps_details")
        self.assertEqual(response.status_code, 200, response.text)
        return {item["field"]: (item["ours"], item["theirs"])
                for item in response.json()["differs"]}

    def _stored(self) -> dict:
        return json.loads((self.folder / f"{FOLDER}.info").read_text())["Info"]

    def test_a_game_matched_where_it_was_found_disagrees_about_nothing(self) -> None:
        self.assertEqual(self._differs(), {})

    def test_correcting_a_match_parts_every_described_field(self) -> None:
        self._rematch(OTHER)

        self.assertEqual(self._differs(), {
            "Title": ("The Addams Family", "Star Trek"),
            "Manufacturer": ("Bally", "Data East"),
            "Year": ("1992", "1991"),
            "Themes": ("Movie", "Movie, Outer Space"),
            "IPDBId": ("20", "2356"),
        })

    def test_which_entry_it_is_is_not_one_of_them(self) -> None:
        """`Info.VPSId` is what VPS supplied and is what a corrected match reverts to.
        Comparing it would report the correction itself as a disagreement, and adopting
        would then destroy the baseline the undo needs."""
        self._rematch(OTHER)

        self.assertNotIn("VPSId", self._differs())

    def test_adopting_leaves_nothing_disagreeing(self) -> None:
        self._rematch(OTHER)
        response = self.client.put(f"/games/{GAME_ID}/vps_details")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["differs"], [])
        self.assertEqual(self._differs(), {})

    def test_adopting_writes_the_entry_details(self) -> None:
        self._rematch(OTHER)
        self.client.put(f"/games/{GAME_ID}/vps_details")
        stored = self._stored()

        self.assertEqual(stored["Manufacturer"], "Data East")
        self.assertEqual(stored["Year"], 1991)
        self.assertEqual(stored["Themes"], ["Movie", "Outer Space"])

    def test_adopting_leaves_the_discovered_id_alone(self) -> None:
        """Or the correction becomes unundoable: with `Info.VPSId` overwritten, the
        override and the discovered value agree and nothing records that a person
        chose one over the other."""
        self._rematch(OTHER)
        self.client.put(f"/games/{GAME_ID}/vps_details")

        self.assertEqual(self._stored()["VPSId"], FOUND)

    def test_a_game_matched_to_nothing_has_nothing_to_compare(self) -> None:
        self._rematch("")
        path = self.folder / f"{FOLDER}.info"
        written = json.loads(path.read_text())
        written["Info"]["VPSId"] = ""
        path.write_text(json.dumps(written))
        self.game.meta_config = written

        self.assertEqual(self._differs(), {})
        self.assertEqual(
            self.client.put(f"/games/{GAME_ID}/vps_details").status_code, 404)


if __name__ == "__main__":
    unittest.main()
