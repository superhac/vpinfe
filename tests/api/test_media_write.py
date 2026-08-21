"""Placing media through the API, at the tier the route addressed.

Nothing could write above the fixed name before this: `replace_media_file` puts a file
where vpinmediadb writes, so a user's own art landed in the slot a media refresh owns
and the two tiers above it could never be populated at all.

The route is the tier. A game gets the folder's name, a build gets its own, and neither
caller names a tier or learns what one is.
"""

from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from tests.support.library import TempTree, fake_game, write_game

GAME_ID = "Placed00001"
FOLDER = "Cactus Canyon (Bally 1998)"
DESKTOP = f"{FOLDER}.vpx"
VR = f"{FOLDER} - VR.vpx"

INFO = {
    "Info": {"Name": "Cactus Canyon"},
    "VPinFE": {"game_id": GAME_ID},
    "tables": {"tbl0000001": {"id": "tbl0000001", "filename": DESKTOP},
               "tbl0000002": {"id": "tbl0000002", "filename": VR}},
}


def _png(marker: bytes = b"x") -> dict:
    return {"file": ("art.png", io.BytesIO(b"\x89PNG" + marker), "image/png")}


class MediaWriteTests(TempTree):
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

    def _medias(self) -> set[str]:
        return {p.name for p in (self.folder / "medias").iterdir()}

    def test_a_game_write_is_named_for_the_folder(self) -> None:
        response = self.client.put(f"/games/{GAME_ID}/media/playfield", files=_png())

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["written"], f"(Playfield) {FOLDER}.png")
        self.assertIn(f"(Playfield) {FOLDER}.png", self._medias())

    def test_a_table_write_is_named_for_that_build(self) -> None:
        response = self.client.put(
            f"/games/{GAME_ID}/tables/tbl0000002/media/playfield", files=_png())

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["written"],
                         f"(Playfield) {FOLDER} - VR.png")

    def test_a_game_write_beats_the_default_it_did_not_touch(self) -> None:
        entry = self.client.put(f"/games/{GAME_ID}/media/playfield",
                                files=_png()).json()["media"]["playfield"]

        self.assertEqual(entry["via"], "game")
        self.assertIn("table.png", self._medias(), "the default file is left alone")

    def test_a_write_says_what_now_resolves_not_just_what_it_wrote(self) -> None:
        """A shared file is outranked by a build's own, so writing it can change
        nothing - and finding that out from the art not moving is the worst way."""
        self.client.put(f"/games/{GAME_ID}/tables/tbl0000002/media/playfield",
                        files=_png(b"vr"))
        body = self.client.put(f"/games/{GAME_ID}/media/playfield",
                               files=_png(b"shared")).json()

        self.assertEqual(body["written"], f"(Playfield) {FOLDER}.png")
        # Asked as the VR build, the file just written is not what it sees.
        vr = self.client.get(
            f"/games/{GAME_ID}/tables/tbl0000002/media").json()["media"]["playfield"]
        self.assertEqual(vr["via"], "table")

    def test_a_write_records_who_placed_it(self) -> None:
        entry = self.client.put(f"/games/{GAME_ID}/media/wheel",
                                files=_png()).json()["media"]["wheel"]

        self.assertEqual(entry["origin"], "user")

    def test_replacing_does_not_leave_the_old_extension_behind(self) -> None:
        self.client.put(f"/games/{GAME_ID}/media/wheel", files=_png())
        self.client.put(f"/games/{GAME_ID}/media/wheel",
                        files={"file": ("art.jpg", io.BytesIO(b"\xff\xd8jpg"),
                                        "image/jpeg")})

        names = self._medias()
        self.assertIn(f"(Wheel) {FOLDER}.jpg", names)
        self.assertNotIn(f"(Wheel) {FOLDER}.png", names,
                         "the png would sit ahead of the jpg in the family order")

    def test_an_extension_the_kind_does_not_take_is_refused(self) -> None:
        response = self.client.put(
            f"/games/{GAME_ID}/media/wheel",
            files={"file": ("art.mp4", io.BytesIO(b"mp4"), "video/mp4")})

        self.assertEqual(response.status_code, 400)

    def test_an_unknown_kind_is_refused(self) -> None:
        response = self.client.put(f"/games/{GAME_ID}/media/poster", files=_png())

        self.assertEqual(response.status_code, 400)

    def test_deleting_takes_only_that_tier(self) -> None:
        self.client.put(f"/games/{GAME_ID}/media/playfield", files=_png())

        response = self.client.delete(f"/games/{GAME_ID}/media/playfield")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["removed"],
                         [f"medias/(Playfield) {FOLDER}.png"])
        self.assertIn("table.png", self._medias(), "the default is not ours to delete")

    def test_deleting_nothing_is_not_an_error(self) -> None:
        response = self.client.delete(f"/games/{GAME_ID}/media/flyer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["removed"], [])

    def test_a_table_that_is_not_this_game_s_is_a_404(self) -> None:
        response = self.client.put(
            f"/games/{GAME_ID}/tables/tbl0000009/media/wheel", files=_png())

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
