"""A game folder VPinFE may not write to still shows, and the rest of the library loads.

Read from real 2.x folders with no id, one of them made read-only, through the API.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from starlette.testclient import TestClient

import httpapi
from common.games import game_identity, game_repository
from common.games.locations import KIND_ROOT, Location
from tests.support.library import TempTree, write_game
from tests.support.skips import needs_posix_permissions

LEGACY = {"Info": {"Title": "Sample Game", "Rom": "sample"},
          "VPXFile": {"filename": "Sample Game.vpx", "filehash": "abc", "rom": "sample"}}
LOCKED = "Locked Game (Original 2024)"
KEPT = "Sample Game (Original 2024)"


@needs_posix_permissions
class LockedFolderTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        for name in (LOCKED, KEPT):
            write_game(self.root, name, info=LEGACY)
        self.locked = self.root / LOCKED
        self.locked.chmod(0o555)
        self.addCleanup(self.locked.chmod, 0o755)

        held = mock.patch.object(
            game_repository.locations, "configured",
            return_value=[Location(location_id="test", path=str(self.root),
                                   kind=KIND_ROOT)])
        held.start()
        self.addCleanup(held.stop)
        previous = dict(game_repository._PARSERS)
        game_repository._PARSERS.clear()
        self.addCleanup(game_repository._PARSERS.update, previous)
        self.addCleanup(game_repository._PARSERS.clear)
        logged = mock.patch.object(game_identity.logger, "exception")
        self.logged = logged.start()
        self.addCleanup(logged.stop)

        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def _listed(self) -> dict[str, str]:
        answer = self.client.get("/games")
        self.assertEqual(answer.status_code, 200, answer.text)
        return {Path(one["folder"]).name: one["id"] for one in answer.json()["games"]}

    def _on_disk(self, name: str) -> str:
        info = json.loads((self.root / name / f"{name}.info").read_text(encoding="utf-8"))
        return str((info.get("vpinfe") or {}).get("game_id") or "")

    def test_the_library_lists_with_the_locked_game_in_it(self) -> None:
        listed = self._listed()

        self.assertEqual(sorted(listed), [LOCKED, KEPT])
        self.assertTrue(all(listed.values()), listed)

    def test_the_games_after_it_get_their_ids(self) -> None:
        listed = self._listed()

        self.assertEqual(listed[KEPT], self._on_disk(KEPT))
        self.assertEqual(self._on_disk(LOCKED), "")

    def test_the_write_that_failed_is_logged_with_its_game(self) -> None:
        self._listed()

        self.assertEqual([one.args[1] for one in self.logged.call_args_list], [LOCKED])

    def test_the_locked_game_answers_to_one_id_while_it_is_held(self) -> None:
        first = self._listed()[LOCKED]

        self.assertEqual(self.client.get(f"/games/{first}").status_code, 200)
        self.assertEqual(self._listed()[LOCKED], first)

    def test_it_counts_among_those_written_by_an_older_build(self) -> None:
        self._listed()

        info = self.client.get("/library/info").json()

        self.assertEqual(info["pending_upgrade"], 1)
        self.assertEqual(info["pending_games"], [LOCKED])
