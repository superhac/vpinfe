"""A game's high scores over the API, read again when the score file says they changed.

The launch reads the table after every game. What is pinned here is the read on looking:
it happens only where the file is newer than the read kept, it counts New against that
read, and every state a surface draws is told apart.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

import httpapi
from common.games.score_parser import ParsedEntry
from tests.support.library import TempTree, fake_game, write_game

GAME_ID = "Scores000001"
FOLDER = "Example (Maker 1990)"
MAP = {"abc_l1": {"scoretype": "Leaderboard", "decoder": "unused"},
       "abc_mod": {"scoretype": "HIGHEST SCORE", "decoder": "unused"}}
BEFORE = [ParsedEntry(section="HIGH SCORES", rank=1, initials="OWN", score=300),
          ParsedEntry(section="HIGH SCORES", rank=2, initials="ABC", score=200)]
AFTER = [ParsedEntry(section="HIGH SCORES", rank=1, initials="OWN", score=300),
         ParsedEntry(section="HIGH SCORES", rank=2, initials="", score=250),
         ParsedEntry(section="HIGH SCORES", rank=3, initials="ABC", score=200)]


def _kept(entries: list[ParsedEntry], read_at: str | None) -> dict:
    return {"read_at": read_at, "score_kind": "Leaderboard", "new": [],
            "entries": [asdict(entry) for entry in entries]}


class HighScoreReadTests(TempTree):
    def _library(self, *, roms: dict[str, str], held: dict | None = None,
                 score_files: tuple[str, ...] = ()) -> None:
        """One game whose tables declare `roms` (table id -> ROM), the first its default."""
        info = {"Info": {"Title": "Example"},
                "User": {"Rating": 3, **({"HighScores": held} if held else {})},
                "vpinfe": {"schema": 2, "id": GAME_ID, "default_table": next(iter(roms))},
                "tables": {table_id: {"id": table_id, "filename": f"{table_id}.vpx", "rom": rom}
                           for table_id, rom in roms.items()}}
        files = {f"{table_id}.vpx": b"vpx" for table_id in roms}
        files.update({f"pinmame/nvram/{rom}.nv": b"nv" for rom in score_files})
        self.folder = write_game(self.root, FOLDER, info=info, vpx=False, files=files)
        game = fake_game(self.folder, FOLDER, meta=info)
        for patcher in (patch("common.games.game_repository.catalog",
                              return_value={GAME_ID: game}),
                        patch("common.games.score_parser.roms", MAP)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def _age(self, rom: str, seconds_ago: float) -> None:
        stamp = time.time() - seconds_ago
        os.utime(self.folder / "pinmame" / "nvram" / f"{rom}.nv", (stamp, stamp))

    def _get(self, path: str = f"/games/{GAME_ID}/high_scores"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _stored(self) -> dict:
        info = json.loads((self.folder / f"{FOLDER}.info").read_text(encoding="utf-8"))
        return info["User"].get("HighScores") or {}

    def _reading(self, entries: list[ParsedEntry]):
        return patch("common.games.score_parser.read_rom_with_source",
                     return_value=(entries, str(Path("/nv/abc_l1.nv"))))

    def test_a_newer_score_file_is_read_again_and_kept(self) -> None:
        self._library(roms={"t1": "abc_l1"}, score_files=("abc_l1",),
                      held={"abc_l1": _kept(BEFORE, "2026-01-01T00:00:00Z")})

        with self._reading(AFTER):
            shown = self._get()

        (section,) = shown["sections"]
        self.assertEqual([(one["initials"], one["score"], one["new"])
                          for one in section["entries"]],
                         [("OWN", 300, False), ("", 250, True), ("ABC", 200, False)])
        self.assertEqual((shown["state"], shown["rom"], shown["table_id"]),
                         ("read", "abc_l1", "t1"))
        kept = self._stored()["abc_l1"]
        self.assertEqual(kept["new"], [1])
        self.assertEqual(kept["entries"][1]["initials"], "", "nothing is filled in")
        self.assertNotEqual(kept["read_at"], "2026-01-01T00:00:00Z")

    def test_an_older_score_file_is_not_read(self) -> None:
        self._library(roms={"t1": "abc_l1"}, score_files=("abc_l1",),
                      held={"abc_l1": _kept(BEFORE, "2099-01-01T00:00:00Z")})

        with self._reading(AFTER) as read:
            shown = self._get()

        read.assert_not_called()
        self.assertEqual(len(shown["sections"][0]["entries"]), 2)
        self.assertEqual(shown["read_at"], "2099-01-01T00:00:00Z")

    def test_a_read_nobody_timed_is_read_again_and_counts_nothing_new(self) -> None:
        self._library(roms={"t1": "abc_l1"}, score_files=("abc_l1",),
                      held={"abc_l1": _kept(BEFORE, None)})
        self._age("abc_l1", 3600 * 24 * 365)

        with self._reading(AFTER):
            shown = self._get()

        self.assertEqual([one["new"] for one in shown["sections"][0]["entries"]],
                         [False, False, False])
        self.assertIsNotNone(shown["read_at"])

    def test_a_rom_the_map_knows_with_nothing_saved_yet(self) -> None:
        self._library(roms={"t1": "abc_l1"})

        shown = self._get()

        self.assertEqual((shown["state"], shown["sections"]), ("none", []))

    def test_a_rom_outside_the_map_with_no_score_file_has_nothing_to_show(self) -> None:
        self._library(roms={"t1": "orig_table"})

        self.assertIsNone(self._get())

    def test_a_table_with_no_rom_has_nothing_to_show(self) -> None:
        self._library(roms={"t1": ""})

        self.assertIsNone(self._get())

    def test_a_score_file_the_map_cannot_read(self) -> None:
        self._library(roms={"t1": "orig_table"}, score_files=("orig_table",))

        shown = self._get()

        self.assertEqual((shown["state"], shown["rom"]), ("unsupported", "orig_table"))

    def test_a_read_that_fails_says_why(self) -> None:
        self._library(roms={"t1": "abc_l1"}, score_files=("abc_l1",))

        with patch("common.games.score_parser.read_rom_with_source",
                   side_effect=ValueError("offset past the end of the file")), \
                self.assertLogs("vpinfe.common.games.high_score_reads", "WARNING"):
            shown = self._get()

        self.assertEqual(shown["state"], "unreadable")
        self.assertIn("offset past the end of the file", shown["reason"])
        self.assertEqual(self._stored(), {})

    def test_a_table_answers_for_its_own_rom(self) -> None:
        self._library(roms={"t1": "abc_l1", "t2": "abc_mod"},
                      held={"abc_l1": _kept(BEFORE, "2099-01-01T00:00:00Z"),
                            "abc_mod": {"read_at": "2099-01-01T00:00:00Z",
                                        "score_kind": "HIGHEST SCORE", "value": 9000,
                                        "new": []}})

        game = self._get()
        mod = self._get(f"/games/{GAME_ID}/tables/t2/high_scores")

        self.assertEqual(game["rom"], "abc_l1")
        self.assertEqual((mod["rom"], mod["table_id"]), ("abc_mod", "t2"))
        (section,) = mod["sections"]
        self.assertEqual((section["name"], section["entries"][0]["score"]),
                         ("HIGHEST SCORE", 9000))

    def test_a_table_the_game_does_not_have_is_refused(self) -> None:
        self._library(roms={"t1": "abc_l1"})

        response = self.client.get(f"/games/{GAME_ID}/tables/nope/high_scores")

        self.assertEqual(response.status_code, 404, response.text)

    def test_the_game_carries_what_is_kept_without_reading(self) -> None:
        self._library(roms={"t1": "abc_l1"}, score_files=("abc_l1",),
                      held={"abc_l1": _kept(BEFORE, "2026-01-01T00:00:00Z")})

        with self._reading(AFTER) as read:
            response = self.client.get(f"/games/{GAME_ID}")

        read.assert_not_called()
        self.assertEqual(response.status_code, 200, response.text)
        shown = response.json()["user"]["high_scores"]
        self.assertEqual(len(shown["sections"][0]["entries"]), 2)
