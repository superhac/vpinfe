"""A guest's own counters, kept apart from the library's.

Moved here with the code. A visitor's half hour is theirs and must not land in the play
count of a library that is not theirs, so it is held per profile and goes when they do.

It had the same bug the game's own counters had: every session rounded up to a whole
minute before being added, so twenty short ones came to twenty minutes.
"""

from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from common.extensions import host
from common.games import game_play_service

host.Registry().load(host.BUNDLED_DIR / "vpinplay")

from vpinfe_ext_vpinplay import guest  # noqa: E402


class ProfilePlayTimeTests(unittest.TestCase):
    """The alternate-profile path keeps its own counters, and had the same bug as the
    .info one: every session was rounded up to a whole minute before being added."""

    def setUp(self) -> None:
        guest._GAME_USER_STATE_BY_PROFILE.clear()
        self.addCleanup(guest._GAME_USER_STATE_BY_PROFILE.clear)

    def test_a_short_session_is_not_charged_a_whole_minute(self) -> None:
        state = guest.add_game_runtime("/games/Example", 3, profile_key="p1")

        self.assertEqual(state["run_time_seconds"], 3)
        self.assertEqual(state["RunTime"], 0)

    def test_short_sessions_add_up(self) -> None:
        for _ in range(20):
            state = guest.add_game_runtime("/games/Example", 30, profile_key="p1")

        self.assertEqual(state["run_time_seconds"], 600)
        self.assertEqual(state["RunTime"], 10)

    def test_what_is_submitted_is_still_the_minutes(self) -> None:
        """RunTime is the service's field and its unit. Ours rides alongside, not into
        the payload."""
        guest.add_game_runtime("/games/Example", 200, profile_key="p1")
        state = guest.get_game_user_state("/games/Example", "p1")

        game = types.SimpleNamespace(gameDirName="Example", fullPathGame="/games/Example",
                                     meta_config={})
        with patch.object(game_play_service, "load_game_meta",
                          return_value={"Info": {"Title": "Example"}}):
            submitted = game_play_service.build_runtime_submission_meta(game, state)

        self.assertEqual(submitted["User"]["RunTime"], 3)
        self.assertNotIn("run_time_seconds", submitted["User"])


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
