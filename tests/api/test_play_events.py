"""The frontend's reaction to a launch, now that it is a subscriber.

The window messages are load-bearing: TableLaunching suppresses frontend input and
TableLaunchComplete restores it, so a launch that announces the first without ever
reaching the second leaves the wheel dead for the life of the process.
"""

from __future__ import annotations

import re
import types
import unittest
from pathlib import Path
from unittest import mock

from common import events
from frontend import play_events


class _Bridge:
    def __init__(self):
        self.messages = []

    def send_event_all_with_iframe(self, message):
        self.messages.append(message["type"])


class PlayEventTests(unittest.TestCase):
    def setUp(self) -> None:
        events.clear()
        play_events.reset_for_tests()
        self.addCleanup(events.clear)
        self.addCleanup(play_events.reset_for_tests)
        self.bridge = _Bridge()

    def _register(self, ini_config=None):
        with mock.patch.object(play_events, "save_last_game"):
            play_events.register(self.bridge, None, ini_config)

    def _settle(self):
        """Wait out the coalescing window that answers a run of game changes."""
        timer = play_events._change_timer
        if timer is not None:
            timer.join(timeout=5)

    def test_registering_twice_leaves_one_of_each(self) -> None:
        """Three windows share one bridge; registering per window would treble
        every message."""
        self._register()
        self._register()

        for name in (events.GAME_LAUNCHING, events.GAME_LAUNCHED, events.GAME_EXITED,
                     events.GAME_PLAY_RECORDED, events.GAME_CHANGED,
                     events.COLLECTIONS_CHANGED):
            with self.subTest(event=name):
                self.assertEqual(events.registered(name), (0, 1))

    def test_the_windows_are_driven_by_the_lifecycle(self) -> None:
        self._register()

        with mock.patch.object(play_events, "save_last_game"):
            events.emit(events.GAME_LAUNCHING, game=None, ini_config=None)
            events.emit(events.GAME_LAUNCHED, game=None, ini_config=None)
            events.emit(events.GAME_EXITED, game=None, ini_config=None)

        # Each goes out twice: the current spelling and the 2.x one a shipped theme
        # still matches on. PAR-24.
        self.assertEqual(self.bridge.messages,
                         ["GameLaunching", "TableLaunching",
                          "GameRunning", "TableRunning",
                          "GameLaunchComplete", "TableLaunchComplete"])

    def test_a_launch_from_anywhere_drives_the_windows(self) -> None:
        """The Remote page used to produce no window messages at all."""
        self._register()

        with mock.patch.object(play_events, "save_last_game"):
            events.emit(events.GAME_LAUNCHING, game=None, ini_config=None)

        self.assertEqual(self.bridge.messages, ["GameLaunching", "TableLaunching"])

    def test_the_last_game_is_recorded_on_launch(self) -> None:
        game = types.SimpleNamespace(gameDirName="Example")
        ini = types.SimpleNamespace(config={})
        self._register(ini)

        with mock.patch.object(play_events, "save_last_game") as save:
            events.emit(events.GAME_LAUNCHING, game=game, ini_config=None)

        save.assert_called_once_with(ini, game)

    def test_a_finished_session_sends_the_windows_back_for_the_payload(self) -> None:
        """Without this the play counts a theme shows are whatever they were at boot."""
        self._register()

        events.emit(events.GAME_PLAY_RECORDED, game=None, ini_config=None)

        self.assertEqual(self.bridge.messages, ["GameDataChange", "TableDataChange"])

    def test_the_exit_is_not_what_refreshes_the_payload(self) -> None:
        """The runtime and the score are written after the exit goes out, so a refresh
        there would show the session that just ended as one short."""
        self._register()

        events.emit(events.GAME_EXITED, game=None, ini_config=None)

        self.assertNotIn("GameDataChange", self.bridge.messages)

    def test_a_game_changed_outside_the_frontend_reaches_the_windows(self) -> None:
        """A Manager UI edit is the case: same process, but nothing told the wheel."""
        self._register()

        events.emit(events.GAME_CHANGED, game=None, path="/games/Example")
        self._settle()

        self.assertEqual(self.bridge.messages, ["GameDataChange", "TableDataChange"])

    def test_a_run_of_changes_is_answered_once(self) -> None:
        """An import re-reads one game at a time, and each refresh costs every window a
        rebuild of the whole list."""
        self._register()

        for index in range(20):
            events.emit(events.GAME_CHANGED, game=None, path=f"/games/{index}")
        self._settle()

        self.assertEqual(self.bridge.messages, ["GameDataChange", "TableDataChange"])

    def test_a_collections_write_reaches_the_windows_too(self) -> None:
        """Membership is not derivable from any game, so a wheel showing a collection
        has nothing else to go on."""
        self._register()

        events.emit(events.COLLECTIONS_CHANGED, path="/config/collections.json")
        self._settle()

        self.assertEqual(self.bridge.messages, ["GameDataChange", "TableDataChange"])

    def test_a_change_is_not_broadcast_before_the_run_goes_quiet(self) -> None:
        self._register()

        events.emit(events.GAME_CHANGED, game=None, path="/games/Example")

        self.assertEqual(self.bridge.messages, [])

    def test_a_broken_window_message_cannot_stop_a_launch(self) -> None:
        """These are subscribers, so the bus contains them. As hooks they could
        abandon a launch mid-ball."""
        self._register()
        self.bridge.send_event_all_with_iframe = mock.Mock(side_effect=RuntimeError("bridge down"))

        with self.assertLogs("vpinfe.common.events", level="ERROR"):
            events.emit(events.GAME_LAUNCHED, game=None, ini_config=None)


class LifecycleMessageSpellingTests(unittest.TestCase):
    """Both spellings of a renamed message have to reach the windows.

    The dual send landed in vpinfe-core.js only, which covers messages a theme
    originates. The launch lifecycle comes from here instead, so it kept sending the 2.x
    names alone: every installed theme carried on working and a theme written against
    3.0's documented names got no launch events at all. PAR-24.
    """

    JS = Path(__file__).resolve().parent.parent.parent / "frontend" / "static" / "common" / "vpinfe-core.js"

    def test_python_and_javascript_agree_on_the_aliases(self) -> None:
        """One contract, written down twice - so assert the two copies match."""
        block = self.JS.read_text(encoding="utf-8").split("MESSAGE_TYPE_ALIASES = {")[1]
        js_map = dict(re.findall(r'(\w+): "(\w+)"', block[:block.index("}")]))

        self.assertEqual(js_map, play_events._LEGACY_MESSAGE_TYPES)

    def test_a_launch_sends_the_current_name_and_the_legacy_one(self) -> None:
        bridge = _Bridge()
        events.clear()
        play_events.reset_for_tests()
        self.addCleanup(events.clear)
        self.addCleanup(play_events.reset_for_tests)
        with mock.patch.object(play_events, "save_last_game"):
            play_events.register(bridge, None, None)

        events.emit(events.GAME_LAUNCHING, game=None)
        events.emit(events.GAME_LAUNCHED)
        events.emit(events.GAME_EXITED)

        for current, legacy in (("GameLaunching", "TableLaunching"),
                                ("GameRunning", "TableRunning"),
                                ("GameLaunchComplete", "TableLaunchComplete")):
            self.assertIn(current, bridge.messages)
            self.assertIn(legacy, bridge.messages)


if __name__ == "__main__":
    unittest.main()
