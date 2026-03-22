import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.launcher import (
    build_masked_tableini_path,
    build_vpx_launch_command,
    resolve_launch_tableini_override,
)


class TestLauncherTableIniOverride(unittest.TestCase):
    def test_build_masked_tableini_path_enabled_builds_expected_name(self) -> None:
        vpx = "/tables/300 (Gottlieb 1975) team scampa123 mod v1.1.vpx"
        got = build_masked_tableini_path(vpx, True, "windows")
        self.assertEqual(
            got,
            "/tables/300 (Gottlieb 1975) team scampa123 mod v1.1.windows.ini",
        )

    def test_build_masked_tableini_path_disabled_returns_empty(self) -> None:
        vpx = "/tables/example.vpx"
        self.assertEqual(build_masked_tableini_path(vpx, False, "windows"), "")

    def test_build_masked_tableini_path_empty_mask_returns_empty(self) -> None:
        vpx = "/tables/example.vpx"
        self.assertEqual(build_masked_tableini_path(vpx, True, "  "), "")

    def test_resolve_launch_tableini_override_requires_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            vpx = Path(tmp) / "Example Table.vpx"
            vpx.write_text("", encoding="utf-8")
            self.assertEqual(
                resolve_launch_tableini_override(str(vpx), True, "windows"),
                "",
            )

            masked = Path(tmp) / "Example Table.windows.ini"
            masked.write_text("[table]\n", encoding="utf-8")
            self.assertEqual(
                resolve_launch_tableini_override(str(vpx), True, "windows"),
                str(masked),
            )

    def test_build_vpx_launch_command_keeps_play_last_with_all_overrides(self) -> None:
        cmd = build_vpx_launch_command(
            launcher_path="/opt/vpinball/VPinballX",
            vpx_table_path="/tables/example.vpx",
            global_ini_override="/cfg/VPinballX.ini",
            tableini_override="/tables/example.windows.ini",
        )
        self.assertEqual(
            cmd,
            [
                "/opt/vpinball/VPinballX",
                "-ini",
                "/cfg/VPinballX.ini",
                "-tableini",
                "/tables/example.windows.ini",
                "-play",
                "/tables/example.vpx",
            ],
        )
        self.assertEqual(cmd[-2], "-play")

    def test_build_vpx_launch_command_keeps_play_last_without_overrides(self) -> None:
        cmd = build_vpx_launch_command(
            launcher_path="/opt/vpinball/VPinballX",
            vpx_table_path="/tables/example.vpx",
        )
        self.assertEqual(
            cmd,
            ["/opt/vpinball/VPinballX", "-play", "/tables/example.vpx"],
        )
        self.assertEqual(cmd[-2], "-play")


if __name__ == "__main__":
    unittest.main()
