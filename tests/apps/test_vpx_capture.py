"""Visual Pinball launched to be recorded: through copies of its settings, never its own."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from apps.vpx import ini as vini
from apps.vpx.capture import VPXCapture
from common.apps.contract import Entry

SETTINGS = """[Player]
; Synchronization:  [Default: 3, 0='No Sync', 1='Vertical Sync', 3='Frame Pacing']:
SyncMode = 3
MaxFramerate =
PlaySound = 1
BGSet = 1

[Backglass]
BackglassOutput = 1
"""


class CaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.folder = root / "capture"
        self.folder.mkdir()
        self.settings_file = root / "VPinballX.ini"
        self.settings_file.write_text(SETTINGS, encoding="utf-8")
        self.game = root / "Example"
        self.game.mkdir()
        self.table = self.game / "Example.vpx"

    def _command(self, sound: bool = False, table: str | None = None,
                 **settings: str) -> list[str]:
        settings = {"bin_path": "/opt/vpinball/VPinballX",
                    "ini_path": str(self.settings_file), **settings}
        return VPXCapture().command(Entry(table=str(self.table) if table is None else table),
                                    settings, sound=sound, folder=str(self.folder))

    def _passed(self, cmd: list[str], flag: str) -> vini.Ini:
        return vini.parse(Path(cmd[cmd.index(flag) + 1]).read_text(encoding="utf-8"))

    def test_the_settings_file_is_passed_as_a_copy_in_the_folder(self) -> None:
        cmd = self._command()

        self.assertEqual(cmd[:3], ["/opt/vpinball/VPinballX", "-ini",
                                   str(self.folder / "VPinballX.ini")])
        self.assertEqual(cmd[-2:], ["-play", str(self.table)])

    def test_the_copy_is_unsynced_with_the_frame_cap_at_the_display_s_refresh(self) -> None:
        copy = self._passed(self._command(), "-ini")

        self.assertEqual((copy.value("Player.SyncMode"), copy.value("Player.MaxFramerate")),
                         ("0", "-1"))

    def test_the_copy_keeps_everything_else_the_settings_file_says(self) -> None:
        copy = self._passed(self._command(sound=True), "-ini")

        self.assertEqual(copy.value("Backglass.BackglassOutput"), "1")
        self.assertEqual(copy.value("Player.BGSet"), "1")
        self.assertEqual(copy.value("Player.PlaySound"), "1")
        self.assertEqual(copy.settings["Player.SyncMode"].label, "Synchronization")

    def test_the_copy_is_muted_unless_the_sound_is_recorded(self) -> None:
        muted = self._passed(self._command(sound=False), "-ini")
        heard = self._passed(self._command(sound=True), "-ini")

        for key in ("Player.PlaySound", "Player.PlayMusic", "Player.SoundVolume",
                    "Player.MusicVolume"):
            self.assertEqual(muted.value(key), "0", key)
        self.assertIsNone(heard.value("Player.PlayMusic"))

    def test_the_launcher_s_own_file_is_never_written(self) -> None:
        self._command()

        self.assertEqual(self.settings_file.read_text(encoding="utf-8"), SETTINGS)

    def test_with_no_settings_file_anywhere_the_copy_holds_the_recording_s_values(self) -> None:
        self.settings_file.unlink()

        copy = self._passed(self._command(), "-ini")

        self.assertEqual(copy.value("Player.SyncMode"), "0")

    def test_a_table_setting_none_of_them_is_given_no_table_copy(self) -> None:
        (self.game / "Example.ini").write_text("[Player]\nBGSet = 2\n", encoding="utf-8")

        cmd = self._command()

        self.assertNotIn("-tableini", cmd)

    def test_a_table_setting_one_of_them_is_given_a_copy_with_the_recording_s(self) -> None:
        """The table's own file wins over the Settings File, so its SyncMode 3 would
        undo the copy's 0."""
        own = "[Player]\nSyncMode = 3\nBGSet = 2\n"
        (self.game / "Example.ini").write_text(own, encoding="utf-8")

        cmd = self._command()

        table = self._passed(cmd, "-tableini")
        self.assertEqual((table.value("Player.SyncMode"), table.value("Player.BGSet")),
                         ("0", "2"))
        self.assertEqual(cmd[-2:], ["-play", str(self.table)])
        self.assertEqual(cmd.count("-ini"), 1)
        self.assertEqual((self.game / "Example.ini").read_text(encoding="utf-8"), own)

    def test_the_table_s_file_is_the_one_visual_pinball_would_read(self) -> None:
        """No `<table>.ini`, so the folder's."""
        (self.game / "example.INI").write_text("[Player]\nPlayMusic = 1\n", encoding="utf-8")

        table = self._passed(self._command(), "-tableini")

        self.assertEqual(table.value("Player.PlayMusic"), "0")

    def test_a_table_setting_sound_is_left_alone_when_the_sound_is_recorded(self) -> None:
        (self.game / "Example.ini").write_text("[Player]\nPlaySound = 1\n", encoding="utf-8")

        self.assertNotIn("-tableini", self._command(sound=True))

    def test_an_entry_with_no_file_has_no_table_copy(self) -> None:
        cmd = VPXCapture().command(Entry(key="mm"), {"bin_path": "/opt/vpinball/VPinballX"},
                                   sound=False, folder=str(self.folder))

        self.assertNotIn("-tableini", cmd)
        self.assertIn("-ini", cmd)


if __name__ == "__main__":
    unittest.main()
