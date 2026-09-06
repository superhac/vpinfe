import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from apps.vpx.launch import VPXLaunch, masked_tableini_path, resolve_tableini_override
from common.apps.contract import SESSION_CHILD_WITH_READINESS, Entry


def _command(table: str, **settings) -> list[str]:
    return VPXLaunch().command(Entry(table=table), settings)


class TableIniOverrideTests(unittest.TestCase):
    def test_the_mask_names_the_ini_after_the_table(self) -> None:
        stem = "300 (Gottlieb 1975) team scampa123 mod v1.1"
        table = os.path.join(os.sep, "games", f"{stem}.vpx")

        got = masked_tableini_path(table, True, "windows")

        self.assertEqual(got, os.path.join(os.sep, "games", f"{stem}.windows.ini"))

    def test_a_disabled_override_names_nothing(self) -> None:
        self.assertEqual(masked_tableini_path("/games/example.vpx", False, "windows"), "")

    def test_an_empty_mask_names_nothing(self) -> None:
        self.assertEqual(masked_tableini_path("/games/example.vpx", True, "  "), "")

    def test_the_override_has_to_actually_be_there(self) -> None:
        with TemporaryDirectory() as tmp:
            table = Path(tmp) / "Example Table.vpx"
            table.write_text("", encoding="utf-8")
            self.assertEqual(resolve_tableini_override(str(table), True, "windows"), "")

            masked = Path(tmp) / "Example Table.windows.ini"
            masked.write_text("[table]\n", encoding="utf-8")
            self.assertEqual(resolve_tableini_override(str(table), True, "windows"),
                             str(masked))


class CommandTests(unittest.TestCase):
    def test_play_is_last_with_every_override_set(self) -> None:
        with TemporaryDirectory() as tmp:
            table = Path(tmp) / "example.vpx"
            table.write_text("", encoding="utf-8")
            (Path(tmp) / "example.windows.ini").write_text("[t]\n", encoding="utf-8")

            cmd = _command(str(table),
                           bin_path="/opt/vpinball/VPinballX",
                           ini_override="/cfg/VPinballX.ini",
                           table_ini_override_enabled=True,
                           table_ini_override_mask="windows")

        self.assertEqual(cmd, [
            "/opt/vpinball/VPinballX",
            "-ini", "/cfg/VPinballX.ini",
            "-tableini", str(Path(tmp) / "example.windows.ini"),
            "-play", str(Path(tmp) / "example.vpx"),
        ])
        self.assertEqual(cmd[-2], "-play")

    def test_play_is_last_with_no_overrides(self) -> None:
        cmd = _command("/games/example.vpx", bin_path="/opt/vpinball/VPinballX")

        self.assertEqual(cmd, ["/opt/vpinball/VPinballX", "-play", "/games/example.vpx"])
        self.assertEqual(cmd[-2], "-play")

    def test_the_launchers_ini_fills_the_slot(self) -> None:
        """One ini, from the launcher that is running. A plugin profile and the
        install-wide override both drove VPX's single -ini and had to be ranked; a
        launcher carries one, so which launcher is playing already answered it."""
        cmd = _command("/games/example.vpx",
                       bin_path="/opt/vpinball/VPinballX",
                       ini_override="/cfg/plugin_profiles/no-dmd.ini")

        self.assertEqual(cmd, ["/opt/vpinball/VPinballX",
                               "-ini", "/cfg/plugin_profiles/no-dmd.ini",
                               "-play", "/games/example.vpx"])

    def test_only_ever_one_ini(self) -> None:
        """VPX accepts a single -ini and silently drops a second, which would make us
        the one who lost the setting without saying so."""
        cmd = _command("/games/example.vpx",
                       bin_path="/opt/vpinball/VPinballX",
                       ini_override="/cfg/VPinballX.ini",
                       table_ini_override_enabled=True,
                       table_ini_override_mask="windows")

        self.assertEqual(cmd.count("-ini"), 1)


class SessionTests(unittest.TestCase):
    def test_the_session_waits_for_the_startup_marker(self) -> None:
        """The process exists well before the player is looking at anything."""
        session = VPXLaunch().session({})

        self.assertEqual(session.kind, SESSION_CHILD_WITH_READINESS)
        self.assertEqual(session.readiness_marker, "Startup done")


if __name__ == "__main__":
    unittest.main()
