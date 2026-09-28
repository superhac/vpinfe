"""Take Picture during play: freeze, look, then take it - with the table, its pause key,
its screens and the clock all stood in for. Nothing here presses a key or takes a
picture of this machine."""

from __future__ import annotations

import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from PIL import Image

from common import events
from common.capture import adapters, freeze, geometry
from common.capture.geometry import Turn
from common.games import pictures
from common.host import launch_state


class _Table:
    """A running table: pressing its pause key flips it, as VPX's own does, unless it
    has been told to ignore the key."""

    def __init__(self) -> None:
        self.state = launch_state.LaunchState(launching=True, game_name="Example",
                                              source=launch_state.SOURCE_FRONTEND)
        self.presses = 0
        self.deaf = False

    def toggle(self) -> bool:
        self.presses += 1
        if not self.deaf:
            self.state = launch_state.LaunchState(**{**self.state.as_dict(),
                                                     "paused": not self.state.paused})
        return True

    def wait(self, paused: bool, _timeout: float) -> bool:
        return self.state.paused == paused


class _Flow(unittest.TestCase):
    def setUp(self) -> None:
        self.table = _Table()
        self.now = 100.0
        self.grabbed: list[str] = []
        self.kept: list[freeze.Shot] = []
        self.shot = freeze.Shot(stills={"playfield": Path("/work/playfield.png")})
        kit = freeze.Kit(
            toggle=self.table.toggle, wait=self.table.wait, state=lambda: self.table.state,
            clock=lambda: self.now, aim=lambda playing: "aimed",
            grab=lambda aimed: self.grabbed.append(aimed) or self.shot,
            keep=lambda shot, playing: self.kept.append(shot) or Path("/kept.png"),
            later=lambda work: work())
        self.flow = freeze.reset_for_tests(kit)
        self.addCleanup(freeze.reset_for_tests)
        self.game = types.SimpleNamespace(full_path_game="/games/Example")
        self.flow.launched(game=self.game, table_id="t1",
                           source=launch_state.SOURCE_FRONTEND)

    def _press(self, after: float = 1.0) -> str:
        self.now += after
        return self.flow.take_picture()["state"]

    def _back(self) -> str:
        return self.flow.resume()["state"]


class FreezeLookTakeTests(_Flow):
    def test_the_first_press_freezes_and_the_second_takes_and_resumes(self) -> None:
        self.assertEqual(self._press(), freeze.FROZEN)
        self.assertTrue(self.table.state.paused)
        self.assertEqual(self.grabbed, [])

        self.assertEqual(self._press(), freeze.TAKEN)

        self.assertEqual(self.grabbed, ["aimed"])
        self.assertEqual(self.kept, [self.shot])
        self.assertFalse(self.table.state.paused)
        self.assertEqual(self.table.presses, 2)

    def test_back_resumes_without_a_picture(self) -> None:
        self._press()

        self.assertEqual(self._back(), freeze.RESUMED)

        self.assertFalse(self.table.state.paused)
        self.assertEqual(self.grabbed, [])
        self.assertEqual(self._press(), freeze.FROZEN, "the next press starts over")

    def test_back_while_playing_does_nothing(self) -> None:
        self.assertEqual(self._back(), freeze.IGNORED)
        self.assertEqual(self.table.presses, 0)

    def test_a_table_paused_with_its_own_key_takes_at_once(self) -> None:
        self.table.toggle()

        self.assertEqual(self._press(), freeze.TAKEN)

        self.assertEqual(self.grabbed, ["aimed"])
        self.assertFalse(self.table.state.paused)

    def test_a_second_press_within_half_a_second_is_a_bounce(self) -> None:
        self._press()

        self.assertEqual(self._press(after=0.3), freeze.IGNORED)

        self.assertEqual(self.grabbed, [])
        self.assertEqual(self._press(after=0.3), freeze.TAKEN,
                         "half a second from the last press that counted")

    def test_a_table_that_never_says_it_paused_is_not_frozen(self) -> None:
        self.table.deaf = True

        with self.assertLogs("vpinfe.common.capture.freeze", "WARNING"):
            self.assertEqual(self._press(), freeze.NOT_PAUSED)

    def test_a_key_that_cannot_be_pressed_is_said(self) -> None:
        self.flow.kit.toggle = lambda: False

        with self.assertLogs("vpinfe.common.capture.freeze", "WARNING"):
            self.assertEqual(self._press(), freeze.NOT_PAUSED)

    def test_nothing_to_picture_still_resumes(self) -> None:
        self.shot = freeze.Shot()
        self._press()

        self.assertEqual(self._press(), freeze.FAILED)

        self.assertFalse(self.table.state.paused)
        self.assertEqual(self.kept, [])


class WhatIsPlayingTests(_Flow):
    def test_no_table_is_not_playing(self) -> None:
        self.table.state = launch_state.LaunchState()
        self.assertEqual(self._press(), freeze.NOT_PLAYING)

    def test_a_recording_is_never_paused(self) -> None:
        self.table.state = launch_state.LaunchState(launching=True,
                                                    source=launch_state.SOURCE_CAPTURE)
        self.flow.exited()
        self.flow.launched(game=self.game, source=launch_state.SOURCE_CAPTURE)

        self.assertEqual(self._press(), freeze.NOT_PLAYING)
        self.assertEqual(self.table.presses, 0)

    def test_the_table_is_followed_on_the_bus(self) -> None:
        freeze.register()
        events.emit(events.TABLE_EXITED, source=launch_state.SOURCE_FRONTEND)
        self.assertEqual(self._press(), freeze.NOT_PLAYING)

        events.emit(events.TABLE_LAUNCHED, game=self.game, table_id="t2",
                    source=launch_state.SOURCE_API)

        self.assertEqual(freeze._flow.playing, freeze.Playing(self.game, "t2"))


class _Adapter:
    id = "fake"

    def __init__(self, outputs: list[adapters.Output],
                 windows: list[adapters.Window] | None = None) -> None:
        self._outputs = outputs
        self._windows = windows or []

    def windows(self):
        return self._windows

    def requirements(self):
        return ()

    def outputs(self):
        return self._outputs

    def at_once(self, _ffmpeg):
        return False

    def still(self, found, output, dest):
        return ["still", output.name, str(dest)]

    def still_turn(self, output):
        return output.transform


def _output(name: str, x: int, width: int, height: int, transform: Turn = geometry.NONE):
    return adapters.Output(name, x, 0, width, height, (width, height), 60.0, transform)


class AimAndGrabTests(unittest.TestCase):
    OUTPUTS = [_output("DP-1", 0, 1920, 1080, Turn(ccw=270)),
               _output("HDMI-A-1", 1920, 1920, 1080), _output("HDMI-A-2", 3840, 1280, 390)]

    def _config(self, rotation: str = "0"):
        values = {("windows.playfield", "screen_id"): "0",
                  ("windows.playfield", "rotation"): rotation,
                  ("windows.backglass", "screen_id"): "1",
                  ("windows.score_view", "screen_id"): "2"}
        return values

    def _aim(self, rotation: str = "0", shown=None, windows=None):
        adapter = _Adapter(self.OUTPUTS, windows)
        values = self._config(rotation)
        monitors = [types.SimpleNamespace(name=one.name, x=one.x, y=0, width=one.width,
                                          height=one.height) for one in self.OUTPUTS]
        report = {"screens": [
            {"window": window, "output": "x", "picture": {"available": True, "reason": None}}
            for window in ("playfield", "backglass", "scoreview")]}
        with mock.patch.object(adapters, "resolve", return_value=adapter), \
                mock.patch.object(freeze.preflight, "report", return_value=report), \
                mock.patch("common.host.display_service.get_display_monitors",
                           return_value=monitors), \
                mock.patch.object(adapters, "cfg_get",
                                  lambda _c, section, key: values.get((section, key), "")), \
                mock.patch.object(freeze, "cfg_get",
                                  lambda _c, section, key: values.get((section, key), "")), \
                mock.patch.object(freeze.placing, "shown", return_value=shown):
            return freeze.aim(config=object()), adapter

    def test_every_screen_is_aimed_at_its_own_output(self) -> None:
        aimed, _ = self._aim()

        self.assertEqual({window: output.name for window, output in aimed.outputs.items()},
                         {"playfield": "DP-1", "backglass": "HDMI-A-1",
                          "scoreview": "HDMI-A-2"})

    def test_the_desktop_says_where_the_running_tables_windows_are(self) -> None:
        """VPinFE's own screen ids place nothing on Wayland; the table's windows do."""
        shown = freeze.placing.Shown(
            "Visual Pinball X", {"playfield": "HDMI-A-1", "backglass": "DP-1"},
            lambda app_id, title: {"Visual Pinball Player": "playfield",
                                   "Visual Pinball Backglass": "backglass"}.get(title, ""))
        windows = [adapters.Window("vpx", "Visual Pinball Player", "HDMI-A-1"),
                   adapters.Window("vpx", "Visual Pinball Backglass", "DP-1")]

        aimed, _ = self._aim(shown=shown, windows=windows)

        self.assertEqual({window: output.name for window, output in aimed.outputs.items()},
                         {"playfield": "HDMI-A-1", "backglass": "DP-1"})

    def test_a_missing_tool_aims_at_nothing(self) -> None:
        adapter = _Adapter(self.OUTPUTS)
        report = {"screens": [{"window": "playfield", "output": "DP-1", "picture": {
            "available": False, "reason": {"key": freeze.preflight.NEEDS_TOOL,
                                           "params": {"tool": "grim"}, "remedy": None}}}]}
        with mock.patch.object(adapters, "resolve", return_value=adapter), \
                mock.patch.object(freeze.preflight, "report", return_value=report), \
                mock.patch("common.host.display_service.get_display_monitors",
                           return_value=[]), \
                mock.patch.object(freeze.placing, "shown", return_value=None), \
                self.assertLogs("vpinfe.common.capture.freeze", "WARNING") as logs:
            self.assertIsNone(freeze.aim(config=object()))
        self.assertIn("grim", logs.output[0])

    def test_the_playfield_is_turned_upright_and_the_rest_left_as_shown(self) -> None:
        aimed, _ = self._aim()

        self.assertEqual(aimed.turns["playfield"], Turn(ccw=270))
        self.assertEqual(aimed.turns["backglass"], Turn())

    def test_the_ui_rotation_is_undone_too(self) -> None:
        aimed, _ = self._aim(rotation="90")
        self.assertEqual(aimed.turns["playfield"], Turn(ccw=0))

    def test_an_unsupported_session_aims_at_nothing_and_says_why(self) -> None:
        unsupported = adapters.Unsupported("avfoundation", adapters.NOT_YET,
                                           {"desktop": "macOS"})
        with mock.patch.object(adapters, "resolve", return_value=unsupported), \
                self.assertLogs("vpinfe.common.capture.freeze", "WARNING") as logs:
            self.assertIsNone(freeze.aim(config=object()))
        self.assertIn("macOS", logs.output[0])

    def test_every_screen_is_taken_at_once_and_a_failure_left_out(self) -> None:
        aimed, _ = self._aim()
        ran: list[list[str]] = []

        def runner(argv, **_kwargs):
            ran.append(argv)
            if argv[1] == "HDMI-A-2":
                raise OSError("no such output")
            Path(argv[2]).write_bytes(b"png")

        with tempfile.TemporaryDirectory() as held, \
                mock.patch.object(freeze, "_work", return_value=Path(held)), \
                self.assertLogs("vpinfe.common.capture.freeze", "WARNING"):
            shot = freeze.grab(aimed, runner)

        self.assertEqual(sorted(shot.stills), ["backglass", "playfield"])
        self.assertEqual(len(ran), 3)


class KeepTests(unittest.TestCase):
    def test_the_picture_goes_to_the_games_pictures_with_its_table_and_time(self) -> None:
        with tempfile.TemporaryDirectory() as held:
            root = Path(held)
            work = root / "work"
            work.mkdir()
            Image.new("RGB", (40, 80), (0, 0, 255)).save(work / "playfield.png")
            Image.new("RGB", (40, 30), (255, 0, 0)).save(work / "backglass.png")
            shot = freeze.Shot(stills={"playfield": work / "playfield.png",
                                       "backglass": work / "backglass.png"},
                               taken=datetime(2026, 9, 28, 21, 4, 5), work=work)
            game = types.SimpleNamespace(full_path_game=str(root / "Example"))
            (root / "Example").mkdir()

            kept = freeze.keep(shot, freeze.Playing(game, "t1"))
            again = pictures.keep(Image.new("RGB", (4, 4)), game.full_path_game,
                                  table_id="", taken=shot.taken)

            self.assertEqual(kept, root / "Example" / "pictures" / "2026-09-28 21-04-05.png")
            self.assertEqual(again.name, "2026-09-28 21-04-05 2.png")
            self.assertFalse(work.exists(), "the stills go once they are kept")
            with Image.open(kept) as opened:
                self.assertEqual(opened.size, (40, 110))
                self.assertEqual(opened.text[pictures.TABLE], "t1")
                self.assertEqual(opened.text[pictures.TAKEN], "2026-09-28T21:04:05")

    def test_a_folder_that_cannot_be_written_is_said(self) -> None:
        shot = freeze.Shot(stills={"playfield": Path("/nowhere/playfield.png")})
        with self.assertLogs("vpinfe.common.capture.freeze", "WARNING"):
            self.assertIsNone(freeze.keep(shot, freeze.Playing(
                types.SimpleNamespace(full_path_game=""), "t1")))


if __name__ == "__main__":
    unittest.main()
