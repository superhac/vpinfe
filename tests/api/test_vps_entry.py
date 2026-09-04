"""A VPSdb entry reads the same whether you searched for it or asked for it by id.

Two routes answer with one response model, and they built their field lists separately.
That pair drifts a field at a time and the shared model does not catch it, because a
field the builder never sets just takes its default.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi

# Two entries: one VPS photographed and one it did not. Art is on 39% of a real
# snapshot, so the absent case is the common one and has to be in the fixture.
ENTRIES = [
    {"id": "aaaaaaaaaa", "name": "Attack from Mars", "manufacturer": "Bally",
     "year": 1995, "type": "SS", "imgUrl": "https://example.invalid/afm.png",
     "tableFiles": [{"id": "f1"}, {"id": "f2"}]},
    {"id": "bbbbbbbbbb", "name": "Space Invaders", "manufacturer": "Bally",
     "year": 1980, "type": "EM", "tableFiles": []},
]


class VpsEntryTests(unittest.TestCase):
    def setUp(self) -> None:
        for name in ("load_vpsdb", "search_vpsdb"):
            patcher = patch(f"common.games.game_service.{name}",
                            side_effect=lambda *a, **k: list(ENTRIES))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(httpapi.create_api_app(),
                                 raise_server_exceptions=False)

    def _searched(self, vps_id: str) -> dict:
        response = self.client.get("/vps/search", params={"q": "a"})
        self.assertEqual(response.status_code, 200, response.text)
        return next(r for r in response.json()["results"] if r["vps_id"] == vps_id)

    def _looked_up(self, vps_id: str) -> dict:
        response = self.client.get(f"/vps/entry/{vps_id}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_both_routes_report_the_same_entry(self) -> None:
        self.assertEqual(self._looked_up("aaaaaaaaaa"), self._searched("aaaaaaaaaa"))

    def test_the_photograph_is_carried(self) -> None:
        self.assertEqual(self._looked_up("aaaaaaaaaa")["img_url"],
                         "https://example.invalid/afm.png")

    def test_an_entry_with_no_photograph_says_so_with_a_blank(self) -> None:
        """Not null: a surface that lays out around art needs one falsy thing to test,
        and the model would have to widen to carry two of them."""
        self.assertEqual(self._looked_up("bbbbbbbbbb")["img_url"], "")

    def test_releases_counts_the_builds(self) -> None:
        self.assertEqual(self._looked_up("aaaaaaaaaa")["releases"], 2)
        self.assertEqual(self._looked_up("bbbbbbbbbb")["releases"], 0)


if __name__ == "__main__":
    unittest.main()
