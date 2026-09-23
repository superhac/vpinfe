"""A file VPX finds by name, placed in a game's folder and taken out again, over HTTP."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from common.games import asset_origin
from tests.support.library import TempTree, fake_game, write_game

GAME_ID = "Assets0002"
FOLDER = "Attack from Mars (Bally 1995)"


class AssetWrites(TempTree):
    def setUp(self) -> None:
        super().setUp()
        info = {"Info": {"Name": "Attack from Mars"}, "VPinFE": {"game_id": GAME_ID},
                "tables": {"a1": {"id": "a1", "filename": f"{FOLDER}.vpx"},
                           "vr": {"id": "vr", "filename": "AFM VR.vpx"}}}
        self.folder = write_game(self.root, FOLDER, info=info,
                                 files={"AFM VR.vpx": b"vpx",
                                        "AFM VR.directb2s": b"old backglass"})
        game = fake_game(self.folder, FOLDER, meta=info)
        patcher = patch("common.games.game_repository.catalog",
                        return_value={GAME_ID: game})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def _put(self, kind: str, name: str, data: bytes, table: str = ""):
        where = f"/tables/{table}" if table else ""
        return self.client.put(f"/games/{GAME_ID}{where}/assets/{kind}",
                               files={"file": (name, data)})

    def test_a_kind_with_a_shared_name_offers_it_and_each_table(self) -> None:
        body = self.client.get(f"/games/{GAME_ID}/assets/backglass/placements").json()

        self.assertEqual([("", FOLDER, []), ("vr", "AFM VR", ["AFM VR.directb2s"])],
                         [(one["table"], one["base"], one["displaces"])
                          for one in body["placements"]])
        self.assertEqual([".directb2s"], body["extensions"])

    def test_a_point_of_view_is_offered_only_for_a_table(self) -> None:
        body = self.client.get(f"/games/{GAME_ID}/assets/pov/placements").json()

        self.assertEqual({"a1", "vr"}, {one["table"] for one in body["placements"]})

    def test_a_table_s_file_takes_the_table_s_name_and_says_what_it_replaced(self) -> None:
        said = self._put("backglass", "anything.directb2s", b"new backglass", "vr").json()

        self.assertEqual(("AFM VR.directb2s", ["AFM VR.directb2s"]),
                         (said["written"], said["displaced"]))
        self.assertEqual(b"new backglass", (self.folder / "AFM VR.directb2s").read_bytes())

    def test_a_shared_file_takes_the_folder_s_name(self) -> None:
        said = self._put("ini", "settings.ini", b"[Player]").json()

        self.assertEqual((f"{FOLDER}.ini", []), (said["written"], said["displaced"]))

    def test_a_placed_file_is_recorded_as_the_user_s(self) -> None:
        self._put("ini", "settings.ini", b"[Player]", "vr")

        self.assertEqual("user", asset_origin.origin_of(
            asset_origin.ledger(self.folder), self.folder, self.folder / "AFM VR.ini"))

    def test_a_shared_point_of_view_is_refused(self) -> None:
        self.assertEqual(400, self._put("pov", "view.pov", b"pov").status_code)

    def test_a_file_of_another_kind_is_refused(self) -> None:
        self.assertEqual(400, self._put("backglass", "art.png", b"png", "vr").status_code)
        self.assertFalse((self.folder / "AFM VR.png").exists())

    def test_what_a_write_would_replace_is_asked_first(self) -> None:
        body = self.client.get(f"/games/{GAME_ID}/assets/backglass/displaced",
                               params={"filename": "b.directb2s", "table": "vr"}).json()

        self.assertEqual(["AFM VR.directb2s"], body["displaced"])

    def test_a_file_on_this_machine_is_copied_in(self) -> None:
        elsewhere = self.root / "downloads" / "AFM.pov"
        elsewhere.parent.mkdir()
        elsewhere.write_bytes(b"pov")
        with patch("common.media_browse.within_roots", return_value=elsewhere):
            said = self.client.post(f"/games/{GAME_ID}/assets/pov/import",
                                    json={"path": str(elsewhere), "table": "vr"}).json()

        self.assertEqual("AFM VR.pov", said["written"])
        self.assertTrue(elsewhere.exists(), "copied, not moved")

    def test_removing_takes_the_one_file(self) -> None:
        response = self.client.delete(f"/games/{GAME_ID}/assets",
                                      params={"path": "AFM VR.directb2s"})

        self.assertEqual(["AFM VR.directb2s"], response.json()["removed"])
        self.assertFalse((self.folder / "AFM VR.directb2s").exists())
        self.assertTrue((self.folder / "AFM VR.vpx").exists())

    def test_removing_a_table_or_a_path_out_of_the_folder_is_refused(self) -> None:
        for path in ("AFM VR.vpx", "../outside.ini"):
            with self.subTest(path=path):
                self.assertEqual(400, self.client.delete(
                    f"/games/{GAME_ID}/assets", params={"path": path}).status_code)
        self.assertTrue(Path(self.folder / "AFM VR.vpx").exists())
