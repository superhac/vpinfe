"""What the frontend's own page asks core about a recording run."""

from __future__ import annotations

from common.capture import run
from frontend.api import API
from tests.capture.test_runs import THREE, _Held


class StopRecordingTests(_Held):
    def test_exit_s_stop_ends_the_run_throwing_the_game_in_hand_away(self) -> None:
        job = run.start(THREE)
        self.inside.wait(10)

        API.__new__(API).stop_recording()
        result = self.ran(job)

        self.assertEqual((result["run"]["state"], result["tables"]), ("stopped", []))
        self.assertIsNone(run.current())

    def test_a_run_already_gone_is_not_a_failure(self) -> None:
        self.assertEqual(API.__new__(API).stop_recording(), {"run": None})
