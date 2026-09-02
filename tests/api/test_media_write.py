"""Placing media through the API, at the tier the route addressed.

Nothing could write above the fixed name before this: `replace_media_file` puts a file
where vpinmediadb writes, so a user's own art landed in the slot a media refresh owns
and the two tiers above it could never be populated at all.

The route is the tier. A game gets the folder's name, a build gets its own, and neither
caller names a tier or learns what one is.
"""

from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from common.online import asset_sources
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

    # --- filled from a catalog, rather than from a file the caller sent ---------

    def _fetch(self, md5: str) -> None:
        offer = asset_sources.Offer(source="vpinmediadb", name="wheel.png",
                                    url="https://example.invalid/wheel.png",
                                    kind="wheel", size="", md5=md5)

        def staged(url: str, path) -> None:
            Path(path).write_bytes(b"\x89PNGfetched")

        with patch("common.online.asset_sources.url_for", return_value=offer), \
                patch("common.http_client.download_file", staged):
            response = self.client.post(
                f"/games/{GAME_ID}/media/wheel/fetch",
                json={"source": "vpinmediadb", "vps_id": "abc", "size": ""})
        self.assertEqual(response.status_code, 200, response.text)

    def _recorded(self) -> dict:
        info = json.loads((self.folder / f"{FOLDER}.info").read_text())
        return info["assets"][f"medias/(Wheel) {FOLDER}.png"]["source"]

    def test_the_catalog_s_hash_is_recorded_beside_the_source(self) -> None:
        # Without it nothing can prove this art is still the published art, so a later
        # refresh has to leave it alone - the same fetch through the bulk downloader
        # has always stored one.
        self._fetch("d41d8cd98f00b204e9800998ecf8427e")

        self.assertEqual(self._recorded(),
                         {"host": "vpinmediadb",
                          "hash": "d41d8cd98f00b204e9800998ecf8427e"})

    def test_a_source_that_publishes_no_hash_still_records_itself(self) -> None:
        self._fetch("")

        self.assertEqual(self._recorded(), {"host": "vpinmediadb"})

    def test_a_slot_is_revalidated_rather_than_assumed_fresh(self) -> None:
        """The URL names a slot, so a replacement changes the bytes without changing
        the address. With no directive a browser picks its own freshness from the
        file's age and can show art that has been replaced."""
        self.client.put(f"/games/{GAME_ID}/media/wheel", files=_png())
        response = self.client.get(f"/games/{GAME_ID}/media/wheel")

        self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_revalidating_an_unchanged_file_sends_no_bytes(self) -> None:
        """`no-cache` asks every time, so the answer has to be cheap. Starlette
        answers conditional requests only from StaticFiles, and without this a media
        map of thirteen tiles re-downloads all of them on every draw."""
        self.client.put(f"/games/{GAME_ID}/media/wheel", files=_png())
        etag = self.client.get(f"/games/{GAME_ID}/media/wheel").headers["etag"]

        again = self.client.get(f"/games/{GAME_ID}/media/wheel",
                                headers={"If-None-Match": etag})

        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.content, b"")

    def test_a_replaced_file_is_sent_in_full(self) -> None:
        """The other half: a stale etag must not be answered with 304."""
        self.client.put(f"/games/{GAME_ID}/media/wheel", files=_png())
        stale = self.client.get(f"/games/{GAME_ID}/media/wheel").headers["etag"]
        self.client.put(f"/games/{GAME_ID}/media/wheel", files=_png(b"different"))

        again = self.client.get(f"/games/{GAME_ID}/media/wheel",
                                headers={"If-None-Match": stale})

        self.assertEqual(again.status_code, 200)


if __name__ == "__main__":
    unittest.main()
