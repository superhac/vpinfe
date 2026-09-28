"""A guest's own counters, kept apart from the library's.

Moved here with the code. A visitor's half hour is theirs and must not land in the play
count of a library that is not theirs, so it is held per profile and goes when they do.

It had the same bug the game's own counters had: every session rounded up to a whole
minute before being added, so twenty short ones came to twenty minutes.
"""

from __future__ import annotations

import types
import unittest
from unittest.mock import MagicMock, patch

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

        game = types.SimpleNamespace(game_dir_name="Example", full_path_game="/games/Example",
                                     meta_config={})
        with patch.object(game_play_service, "load_game_meta",
                          return_value={"Info": {"Title": "Example"}}):
            submitted = game_play_service.build_runtime_submission_meta(game, state)

        self.assertEqual(submitted["User"]["RunTime"], 3)
        self.assertNotIn("run_time_seconds", submitted["User"])


class _Inline:
    """A thread that runs its target when started, so a test sees what it did."""

    def __init__(self, target, args=(), **_kwargs) -> None:
        self.target, self.args = target, args

    def start(self) -> None:
        self.target(*self.args)


VISITOR = {"type": "vpinplay_identity", "version": 1, "userId": "visitor",
           "initials": "VIS", "machineId": "v" * 64}
FOLDER = "/games/Example"


class GuestGameSendTests(unittest.TestCase):
    """A game a guest plays reaches VPinPlay under their identity once it ends."""

    def setUp(self) -> None:
        import vpinfe_ext_vpinplay as vpinplay

        self.addCleanup(guest.clear_alternate_profile)
        ctx = MagicMock(host_version="3.0.0")
        ctx.config.get.side_effect = lambda key, default="": {
            "endpoint": "https://vpinplay.test"}.get(key, default)
        ctx.games.list_games.return_value = {"games": [
            {"id": "g1", "folder": FOLDER, "name": "Example", "vps_id": "abcd1234",
             "rom": "ex", "user": {"play_count": 33}, "overrides": {}}]}
        ctx.games.game_tables.return_value = {"tables": [
            {"default": True, "filename": "Example.vpx", "file_hash": "h"}]}
        vpinplay.register(ctx)
        self.answers = {call.args[0]: call.args[1] for call in ctx.serves.answer.call_args_list}
        threads = patch.object(vpinplay, "threading", types.SimpleNamespace(Thread=_Inline))
        threads.start()
        self.addCleanup(threads.stop)
        self.sent = MagicMock(return_value={"ok": True, "status_code": 200,
                                            "response_body": ""})
        self.held = MagicMock(return_value={})
        for name, value in (("send", self.sent), ("their_record", self.held)):
            patched = patch.object(vpinplay.sync, name, value)
            patched.start()
            self.addCleanup(patched.stop)

    def play(self) -> bool:
        self.answers["guest.record_start"](FOLDER)
        return self.answers["guest.record_play"](FOLDER, 1800.0, None)

    def test_it_goes_under_their_identity(self) -> None:
        guest.activate_alternate_profile(VISITOR)

        self.assertTrue(self.play())

        payload = self.sent.call_args.args[1]
        self.assertEqual(payload["client"], {"userId": "visitor", "initials": "VIS",
                                             "machineId": "v" * 64})
        self.assertEqual(self.sent.call_args.args[0], "https://vpinplay.test/api/v1/sync")
        self.assertEqual([(one["info"]["vpsId"], one["user"]["startCount"],
                           one["user"]["runTime"]) for one in payload["tables"]],
                         [("abcd1234", 1, 30)])

    def test_signing_out_while_it_is_on_its_way_changes_nothing_sent(self) -> None:
        guest.activate_alternate_profile(VISITOR)
        self.held.side_effect = lambda *_args: (guest.clear_alternate_profile(), {})[1]

        self.play()

        payload = self.sent.call_args.args[1]
        self.assertEqual(payload["tables"][0]["user"]["startCount"], 1)
        self.assertEqual(guest._GAME_USER_STATE_BY_PROFILE, {})

    def test_nothing_goes_when_nobody_is_signed_in(self) -> None:
        self.assertFalse(self.play())

        self.sent.assert_not_called()

    def test_nothing_goes_when_their_record_cannot_be_read(self) -> None:
        guest.activate_alternate_profile(VISITOR)
        self.held.return_value = None

        self.play()

        self.sent.assert_not_called()


if __name__ == "__main__":
    unittest.main()
