"""Where a file can go for a kind, and what putting it there would replace.

The tier is a filename, so choosing where art lands is choosing what it is called.
That used to be inferred from whichever lens happened to be open; this is the list a
client offers instead, with the cost of each choice attached.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from tests.support.library import TempTree, fake_game, write_game

GAME_ID = "Placed00002"
FOLDER = "Cactus Canyon (Bally 1998)"
DESKTOP = f"{FOLDER}.vpx"
VR = f"{FOLDER} - VR.vpx"

INFO = {
    "Info": {"Name": "Cactus Canyon"},
    "VPinFE": {"game_id": GAME_ID},
    "tables": {"tbl0000001": {"id": "tbl0000001", "filename": DESKTOP},
               "tbl0000002": {"id": "tbl0000002", "filename": VR}},
}


class PlacementTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.folder = write_game(self.root, FOLDER, info=INFO, vpx=False,
                                 files={DESKTOP: b"vpx", VR: b"vpx"},
                                 medias={"table.png": b"\x89PNGdefault"})
        game = fake_game(self.folder, FOLDER, meta=INFO)
        patcher = patch("httpapi.games._catalog", return_value={GAME_ID: game})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def _placements(self, kind: str = "playfield"):
        response = self.client.get(f"/games/{GAME_ID}/media/{kind}/placements")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_the_shared_name_comes_first_then_the_builds(self) -> None:
        """Shared leads because it is the common answer. The builds follow in filename
        order, which is the order the tables list uses - here that puts " - VR.vpx"
        ahead of ".vpx", since a hyphen sorts before a dot."""
        found = self._placements()["placements"]
        self.assertEqual(found[0]["table"], "")
        self.assertEqual([item["label"] for item in found[1:]], [VR])

    def test_each_choice_shows_the_name_the_file_would_take(self) -> None:
        by_table = {item["table"]: item["base"] for item in self._placements()["placements"]}
        self.assertEqual(by_table[""], f"(Playfield) {FOLDER}")
        self.assertEqual(by_table["tbl0000002"], f"(Playfield) {FOLDER} - VR")

    def test_a_build_named_after_its_folder_is_not_offered_twice(self) -> None:
        """Cactus Canyon (Bally 1998).vpx sits in Cactus Canyon (Bally 1998), so its
        own name and the shared name are the same string - and then the same file.
        Most single-table folders look like this."""
        found = self._placements()["placements"]

        self.assertNotIn("tbl0000001", [item["table"] for item in found])
        self.assertEqual(len({item["base"] for item in found}), len(found),
                         "no two choices should write the same filename")

    def test_the_extension_is_left_off_because_the_file_decides_it(self) -> None:
        body = self._placements()
        self.assertNotIn(".", body["placements"][0]["base"].rsplit(")", 1)[-1])
        self.assertEqual(body["extensions"][0], ".png")

    def test_nothing_there_means_nothing_replaced(self) -> None:
        """The default-tier table.png is not at either of these tiers, so it is not
        in anybody's way - and reporting it would be inventing a conflict."""
        for item in self._placements()["placements"]:
            self.assertEqual(item["displaces"], [], item["label"])

    def test_a_file_already_at_that_tier_is_reported_against_it(self) -> None:
        (self.folder / "medias" / f"(Playfield) {FOLDER}.png").write_bytes(b"\x89PNG")
        found = self._placements()["placements"]

        by_table = {item["table"]: item["displaces"] for item in found}
        self.assertEqual(by_table[""], [f"medias/(Playfield) {FOLDER}.png"])
        self.assertEqual(by_table["tbl0000002"], [],
                         "a shared file is not in a build's way")

    def test_the_whole_family_goes_whatever_extension_arrives(self) -> None:
        """A .jpg landing over a .png takes the .png, so the count cannot depend on
        an extension the caller has not chosen yet."""
        (self.folder / "medias" / f"(Playfield) {FOLDER}.jpg").write_bytes(b"\xff\xd8")
        self.assertEqual(self._placements()["placements"][0]["displaces"],
                         [f"medias/(Playfield) {FOLDER}.jpg"])

    def test_an_unknown_kind_is_refused(self) -> None:
        self.assertEqual(
            self.client.get(f"/games/{GAME_ID}/media/nonesuch/placements").status_code,
            400)


if __name__ == "__main__":
    unittest.main()
