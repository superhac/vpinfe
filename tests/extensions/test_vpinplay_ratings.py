"""The wheel's VPinPlay rating, answered from the list core reads.

Nothing here reaches VPinPlay: every network call fails the test, so a rating that comes
back came from the list.
"""

from __future__ import annotations

import importlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from starlette.testclient import TestClient

from common import paths, tokens
from common.extensions import catalogs, contributions, host, store
from common.games import community_lists

GAME = {"game_id": "abc", "vps_id": "vps-1"}


def _row(vps_id: str = "vps-1", average: float | None = 13 / 3, ratings: int = 3,
         **more: object) -> dict:
    """A row as the list route answers it."""
    return {"name": "Example", "manufacturer": "Maker", "year": 1995,
            "rating": round(average or 0, 1) or None, "average": average,
            "authors": ["Designer One"], "ratings": ratings, "plays": 0, "hours": 0,
            "players": 0, "last_played": "", "vps_id": vps_id, **more}


class ListRatingTests(unittest.TestCase):
    def setUp(self) -> None:
        contributions.clear()
        self.addCleanup(contributions.clear)
        catalogs.clear()
        self.addCleanup(catalogs.clear)
        self.addCleanup(tokens.forget, "vpinplay")
        kept = paths.COMMUNITY_KEPT_DIR / "vpinplay"
        shutil.rmtree(kept, ignore_errors=True)
        self.addCleanup(shutil.rmtree, kept, True)
        for name in ("urllib.request.urlopen", "requests.get", "requests.post"):
            blocked = patch(name, side_effect=AssertionError(f"{name} reached out"))
            blocked.start()
            self.addCleanup(blocked.stop)

    def _load(self) -> TestClient:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        registry = host.Registry(store.ExtensionStore(Path(folder.name) / "extensions.json"))
        self.addCleanup(registry.clear)
        record = registry.load(host.BUNDLED_DIR / "vpinplay")
        self.assertEqual(record.state, host.LOADED, record.reason)
        app = FastAPI()
        for router, _scope in record.routers:
            app.include_router(router)
        return TestClient(app)

    def _read(self, api: TestClient, rows: list[dict]) -> None:
        community = importlib.import_module("vpinfe_ext_vpinplay.community")
        with patch.object(community, "tables", return_value=rows):
            self.assertEqual(api.get("/community/tables").status_code, 200)

    def _rating(self) -> dict | None:
        return contributions.refresh(dict(GAME)).get("vpinplay")

    def test_a_rating_comes_from_the_list(self) -> None:
        api = self._load()
        self._read(api, [_row()])

        found = self._rating()

        self.assertAlmostEqual(found["cumulativeRating"], 13 / 3)
        self.assertEqual(found["ratingCount"], 3)

    def test_the_shape_themes_read_is_unchanged(self) -> None:
        api = self._load()
        self._read(api, [_row()])

        found = self._rating()

        self.assertEqual(sorted(found), ["cumulativeRating", "fetchedAt", "ratingCount",
                                         "vpsId", "vpsdb"])
        self.assertEqual(found["vpsdb"], {"name": "Example", "authors": ["Designer One"],
                                          "manufacturer": "Maker", "year": 1995})

    def test_a_table_nobody_rated_has_no_rating(self) -> None:
        """The list says 0; the per-game answer said nothing, and themes read that."""
        api = self._load()
        self._read(api, [_row(average=0.0, ratings=0)])

        found = self._rating()

        self.assertIsNone(found["cumulativeRating"])
        self.assertEqual(found["ratingCount"], 0)

    def test_a_table_the_list_does_not_hold_has_no_answer(self) -> None:
        api = self._load()
        self._read(api, [_row(vps_id="someone-else")])

        self.assertIsNone(self._rating())

    def test_a_new_list_replaces_what_was_held(self) -> None:
        api = self._load()
        self._read(api, [_row(average=2.0, ratings=1)])
        self.assertEqual(self._rating()["cumulativeRating"], 2.0)

        self._read(api, [_row(average=5.0, ratings=2)])

        self.assertEqual(self._rating()["cumulativeRating"], 5.0)

    def test_a_failed_read_keeps_the_last_good_list(self) -> None:
        api = self._load()
        self._read(api, [_row(average=3.0, ratings=1)])
        community = importlib.import_module("vpinfe_ext_vpinplay.community")

        with patch.object(community, "tables", side_effect=OSError("down")):
            self.assertEqual(api.get("/community/tables").status_code, 502)

        self.assertEqual(self._rating()["cumulativeRating"], 3.0)

    def test_the_kept_copy_answers_before_any_read(self) -> None:
        """A frontend started offline, or before core's first read, still has ratings."""
        community_lists.keep("vpinplay", "tables", [_row(average=4.0, ratings=5)])

        self._load()

        found = self._rating()
        self.assertEqual(found["cumulativeRating"], 4.0)
        self.assertEqual(found["ratingCount"], 5)


if __name__ == "__main__":
    unittest.main()
