"""Since when a catalog change counts as new, and what that turns into.

State is derived and needs no baseline; a transition is not reconstructable without
one. What this covers is the three ways the baseline can be wrong in a way nobody
would notice: never answered reported as nothing changed, a new game inheriting a
backlog, and a dismissal that quietly stops applying.
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from common.games import watching
from tests.support.library import TempTree, fake_game, write_game

GAME_ID = "Watch00001"
FOLDER = "Twilight Zone (Bally 1993)"
ENTRY = "tz_1993x"
HELD = "b2s_held"
OTHER = "b2s_other"

# Epoch milliseconds, which is how VPSdb keeps them.
JAN_2026 = 1767225600000
JUN_2026 = 1780272000000

INFO = {
    "Info": {"Title": "Twilight Zone", "VPSId": ENTRY},
    "vpinfe": {"game_id": GAME_ID},
    "tables": {"tbl0000001": {"id": "tbl0000001", "filename": f"{FOLDER}.vpx"}},
    "assets": {f"{FOLDER}.directb2s": {"source": {"host": "user",
                                                  "vps_file_id": HELD,
                                                  "confirmed_by": "user"}}},
}

CATALOG = [{
    "id": ENTRY, "name": "Twilight Zone",
    "b2sFiles": [{"id": HELD, "updatedAt": JAN_2026},
                 {"id": OTHER, "updatedAt": JUN_2026}],
}]


class WatchingStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patcher = patch.object(watching, "WATCHING_PATH",
                               Path(self.dir.name) / "watching.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_nobody_has_answered_until_somebody_does(self) -> None:
        self.assertEqual(watching.since(), "")

    def test_a_game_falls_back_to_the_install(self) -> None:
        watching.set_since("2026-01-01T00:00:00Z")

        self.assertEqual(watching.since_for("anything"), "2026-01-01T00:00:00Z")

    def test_a_new_game_gets_its_own_baseline(self) -> None:
        """Or it arrives holding every change published since the install started
        watching - a year of somebody else's backlog on its first day."""
        watching.set_since("2020-01-01T00:00:00Z")
        watching.note_games(["g1"])

        self.assertNotEqual(watching.since_for("g1"), "2020-01-01T00:00:00Z")

    def test_a_game_seen_before_keeps_the_baseline_it_had(self) -> None:
        watching.set_since("2020-01-01T00:00:00Z")
        watching.note_games(["g1"])
        first = watching.since_for("g1")
        watching.note_games(["g1", "g2"])

        self.assertEqual(watching.since_for("g1"), first)

    def test_nothing_is_stamped_before_watching_starts(self) -> None:
        """There is no backlog to protect a game from yet, and stamping would freeze a
        baseline the user has not chosen."""
        self.assertEqual(watching.note_games(["g1"]), 0)
        self.assertEqual(watching.since_for("g1"), "")

    def test_a_dismissal_is_kept_per_game_and_kind(self) -> None:
        watching.acknowledge("g1", "b2sFiles", "rec1")

        self.assertEqual(watching.acknowledged("g1"), {"b2sFiles": {"rec1"}})
        self.assertEqual(watching.acknowledged("g2"), {})

    def test_forgetting_a_game_takes_its_dismissals_with_it(self) -> None:
        """Kept, they would silently apply to whatever takes that id next."""
        watching.set_since("2020-01-01T00:00:00Z")
        watching.note_games(["g1"])
        watching.acknowledge("g1", "b2sFiles", "rec1")
        watching.forget("g1")

        self.assertEqual(watching.acknowledged("g1"), {})
        self.assertEqual(watching.since_for("g1"), "2020-01-01T00:00:00Z")

    def test_a_store_from_another_schema_is_ignored(self) -> None:
        watching.WATCHING_PATH.write_text(json.dumps({"schema": 99, "watching_since": "x"}))

        self.assertEqual(watching.since(), "")


class TransitionTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        folder = write_game(self.root, FOLDER, info=copy.deepcopy(INFO), vpx=False,
                            files={f"{FOLDER}.vpx": b"vpx",
                                   f"{FOLDER}.directb2s": b"b2s"})
        game = fake_game(folder, FOLDER, meta=copy.deepcopy(INFO))
        for target, value in (("common.games.game_service.load_vpsdb", CATALOG),):
            patcher = patch(target, return_value=copy.deepcopy(value))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("httpapi.games._catalog", return_value={GAME_ID: game})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patcher = patch.object(watching, "WATCHING_PATH",
                               Path(self.dir.name) / "watching.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        from httpapi.games import _crowded_links_for
        _crowded_links_for.cache_clear()
        self.client = TestClient(httpapi.create_api_app(),
                                 raise_server_exceptions=False)

    def _b2s(self) -> dict:
        body = self.client.get(f"/games/{GAME_ID}/vps_state").json()
        return {item["kind"]: item for item in body["kinds"]}["b2sFiles"]

    def test_nothing_is_new_until_somebody_says_when_to_start(self) -> None:
        """The alternative is answering the first look with everything the catalog has
        ever published, which is the same as answering with nothing useful."""
        state = self._b2s()

        self.assertFalse(state["updated"])
        self.assertEqual(state["new_upstream"], 0)

    def test_the_record_you_hold_moving_is_an_update(self) -> None:
        watching.set_since("2025-01-01T00:00:00Z")

        self.assertTrue(self._b2s()["updated"])

    def test_a_record_you_do_not_hold_moving_is_not(self) -> None:
        """"Yours was updated" and "somebody published something" are different
        claims, and only the first is about the user's file."""
        watching.set_since("2026-03-01T00:00:00Z")
        state = self._b2s()

        self.assertFalse(state["updated"], "the held record predates this baseline")
        self.assertEqual(state["new_upstream"], 1)

    def test_watching_from_now_reports_nothing(self) -> None:
        watching.set_since("2030-01-01T00:00:00Z")
        state = self._b2s()

        self.assertFalse(state["updated"])
        self.assertEqual(state["new_upstream"], 0)

    def test_a_dismissal_stops_it_being_reported(self) -> None:
        watching.set_since("2026-03-01T00:00:00Z")
        self.client.post("/library/watching/acknowledge",
                         json={"game_id": GAME_ID, "kind": "b2sFiles",
                               "vps_file_id": OTHER})

        self.assertEqual(self._b2s()["new_upstream"], 0)

    def test_reviewing_everything_is_the_beginning_of_time(self) -> None:
        """One mechanism for both first-run answers, rather than a mode."""
        response = self.client.put("/library/watching", json={"since": ""})

        self.assertEqual(response.json()["since"], watching.FROM_THE_BEGINNING)
        self.assertTrue(self._b2s()["updated"])


if __name__ == "__main__":
    unittest.main()
