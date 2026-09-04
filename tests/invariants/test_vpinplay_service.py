import types
import unittest
from unittest.mock import MagicMock, patch

from common.games import game_play_service
from common.online import vpinplay_runtime
from common.online.vpinplay_service import _build_game_payload, sync_installed_games


class TestVPinPlayService(unittest.TestCase):
    def test_the_payload_uses_the_service_names_not_ours(self) -> None:
        """Names checked against the service's own pydantic models (superhac/vpinplay,
        app/models.py). It rejects nothing it does not recognize, so a key we spell our
        way is dropped in silence and stored as the field's default.
        """
        payload = _build_game_payload({
            "Info": {"VPSId": "vps-123"},
            "User": {"Rating": 4},
            "tables": {"t.vpx": {
                "detect_nfozzy": True, "detect_fleep": True, "detect_ssf": True,
                "detect_lut": True, "detect_scorbit": True, "detect_fastflips": True,
                "detect_flex": True, "save_rev": "7",
            }},
            "vpinfe": {"alt_title": "My Title", "alt_vpsid": "vps-999"},
        })

        assert payload is not None
        self.assertEqual(payload["vpinfe"], {"alttitle": "My Title", "altvpsid": "vps-999"})
        for wire_name in ("detectNfozzy", "detectFleep", "detectSSF", "detectLUT",
                          "detectScorebit", "detectFastflips", "detectFlex"):
            self.assertIs(payload["vpxFile"][wire_name], True, wire_name)
        self.assertIn("saveRev", payload["vpxFile"])

    def test_a_rating_outside_the_services_bounds_cannot_fail_the_whole_sync(self) -> None:
        """Their rating is validated 0-5 across the whole request, so one game over the
        bound rejects every other table with it.
        """
        payload = _build_game_payload(
            {"Info": {"VPSId": "vps-123"}, "User": {"Rating": 7}, "tables": {}, "vpinfe": {}})

        assert payload is not None
        self.assertEqual(payload["user"]["rating"], 5)

    def test_build_game_payload_includes_user_score(self) -> None:
        payload = _build_game_payload(
            {
                "Info": {
                    "VPSId": "vps-123",
                    "Rom": "agent777",
                },
                "User": {
                    "Rating": 4,
                    "LastRun": 1234567890,
                    "StartCount": 12,
                    "RunTime": 34,
                    "Score": {
                        "rom": "agent777",
                        "resolved_rom": "agent777",
                        "score_type": "HIGH SCORE",
                        "value": 999999,
                    },
                },
                "VPXFile": {},
                "vpinfe": {},
            }
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["user"]["score"]["value"], 999999)
        self.assertEqual(payload["user"]["rating"], 4)
        self.assertEqual(payload["user"]["startCount"], 12)
        self.assertEqual(payload["user"]["runTime"], 34)

    def test_build_game_payload_ignores_non_dict_user_score(self) -> None:
        payload = _build_game_payload(
            {
                "Info": {
                    "VPSId": "vps-123",
                    "Rom": "agent777",
                },
                "User": {
                    "Score": "not-a-dict",
                },
                "VPXFile": {},
                "vpinfe": {},
            }
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIsNone(payload["user"]["score"])

    @patch("common.online.vpinplay_service.requests.post")
    @patch("common.online.vpinplay_service.get_version", return_value="test-version")
    @patch("common.online.vpinplay_service.games_under")
    def test_sync_installed_games_includes_initials_in_client_payload(
        self,
        mock_games_under,
        _mock_get_version,
        mock_post,
    ) -> None:
        game = MagicMock()
        game.meta_config = {
            "Info": {"VPSId": "vps-123", "Rom": "agent777"},
            "User": {},
            "VPXFile": {},
            "vpinfe": {},
        }
        # games_under hands back the library directly - the cache when the root is the
        # configured one, a fresh parse when it is not.
        mock_games_under.return_value = [game]

        response = MagicMock()
        response.status_code = 200
        response.ok = True
        response.text = "ok"
        response.json.return_value = {"ok": True}
        mock_post.return_value = response

        with patch("common.online.vpinplay_service.Path.exists", return_value=True), patch(
            "common.online.vpinplay_service.Path.is_dir", return_value=True
        ):
            sync_installed_games(
                service_ip="https://api.vpinplay.com:8888",
                user_id="user-123",
                initials="ABC",
                machine_id="machine-123",
                game_root_dir="/games",
            )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["client"]["userId"], "user-123")
        self.assertEqual(payload["client"]["initials"], "ABC")
        self.assertEqual(payload["client"]["machineId"], "machine-123")


class ProfilePlayTimeTests(unittest.TestCase):
    """The alternate-profile path keeps its own counters, and had the same bug as the
    .info one: every session was rounded up to a whole minute before being added."""

    def setUp(self) -> None:
        vpinplay_runtime._GAME_USER_STATE_BY_PROFILE.clear()
        self.addCleanup(vpinplay_runtime._GAME_USER_STATE_BY_PROFILE.clear)

    def test_a_short_session_is_not_charged_a_whole_minute(self) -> None:
        state = vpinplay_runtime.add_game_runtime("/games/Example", 3, profile_key="p1")

        self.assertEqual(state["run_time_seconds"], 3)
        self.assertEqual(state["RunTime"], 0)

    def test_short_sessions_add_up(self) -> None:
        for _ in range(20):
            state = vpinplay_runtime.add_game_runtime("/games/Example", 30, profile_key="p1")

        self.assertEqual(state["run_time_seconds"], 600)
        self.assertEqual(state["RunTime"], 10)

    def test_what_is_submitted_is_still_the_minutes(self) -> None:
        """RunTime is the service's field and its unit. Ours rides alongside, not into
        the payload."""
        vpinplay_runtime.add_game_runtime("/games/Example", 200, profile_key="p1")
        state = vpinplay_runtime.get_game_user_state("/games/Example", "p1")

        game = types.SimpleNamespace(gameDirName="Example", fullPathGame="/games/Example",
                                     meta_config={})
        with patch.object(game_play_service, "load_game_meta",
                          return_value={"Info": {"Title": "Example"}}):
            submitted = game_play_service.build_runtime_submission_meta(game, state)

        self.assertEqual(submitted["User"]["RunTime"], 3)
        self.assertNotIn("run_time_seconds", submitted["User"])


if __name__ == "__main__":
    unittest.main()
