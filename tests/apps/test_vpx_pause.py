"""Visual Pinball's Pause: its own key, and the lines it writes on either side."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from apps.vpx import VPX, pause
from common.apps.contract import Pause


class VPXPauseTests(unittest.TestCase):
    def _ini(self, body: str) -> str:
        held = TemporaryDirectory()
        self.addCleanup(held.cleanup)
        path = Path(held.name) / "VPinballX.ini"
        path.write_text(body, encoding="utf-8")
        return str(path)

    def test_the_app_says_how_it_pauses(self) -> None:
        self.assertIsInstance(VPX.pause, Pause)
        self.assertEqual((VPX.pause.paused_marker, VPX.pause.resumed_marker),
                         ("Pausing Game", "Unpausing Game"))

    def test_the_key_is_the_one_its_settings_file_maps_to_pause(self) -> None:
        ini = self._ini("[Input]\nMapping.Pause = Key;72\n")
        self.assertEqual(pause.VPXPause().key({"ini_path": ini}), "Pause")

    def test_p_where_nothing_is_mapped(self) -> None:
        ini = self._ini("[Input]\nMapping.Pause = \nMapping.Start = Key;30\n")
        self.assertEqual(pause.VPXPause().key({"ini_path": ini}), "KeyP")

    def test_its_own_file_where_the_launcher_names_none(self) -> None:
        ini = self._ini("[Input]\nMapping.Pause = Key;72\n")
        with mock.patch.object(pause, "own_file", return_value=Path(ini)) as own:
            self.assertEqual(pause.VPXPause().key({"ini_path": "", "bin_path": "/opt/vpx"}),
                             "Pause")
        own.assert_called_once_with("/opt/vpx")


if __name__ == "__main__":
    unittest.main()
