from __future__ import annotations

from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from tests.support.library import TempTree, fake_game, game_info


def _game(game_id: str, vps_id: str, release: str = ""):
    tables = {"t1": {"id": "t1", "filename": f"{game_id}.vpx",
                     **({"source": {"vps_file_id": release}} if release else {})}}
    info = game_info(game_id, vps_id=vps_id, game_id=game_id, tables=tables)
    return fake_game(f"/nowhere/{game_id}", game_id, meta=info)


class Owned(TempTree):
    def setUp(self) -> None:
        super().setUp()
        games = [_game("afm", "vps-afm", release="rel-afm-vpw"), _game("mm", "vps-mm")]
        patcher = patch("common.games.game_repository.all_games", lambda: games)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def _owned(self, ids: list[str]) -> dict:
        response = self.client.post("/library/owned", json={"ids": ids})
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["owned"]

    def test_an_entry_answers_with_its_game(self) -> None:
        self.assertEqual({"game_id": "mm", "table_id": "", "name": "mm"},
                         self._owned(["vps-mm"])["vps-mm"])

    def test_a_release_answers_with_its_table(self) -> None:
        self.assertEqual(("afm", "t1"), tuple(self._owned(["rel-afm-vpw"])["rel-afm-vpw"]
                                              [key] for key in ("game_id", "table_id")))

    def test_what_is_not_here_is_left_out(self) -> None:
        self.assertEqual({"vps-afm"}, set(self._owned(["vps-afm", "vps-taf", ""])))
