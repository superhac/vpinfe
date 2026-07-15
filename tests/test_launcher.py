import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common import launcher
from common.launcher import (
    build_masked_tableini_path,
    build_vpx_launch_command,
    get_plugin_profile_from_meta,
    resolve_launch_plugin_profile,
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


class TestLauncherPluginProfile(unittest.TestCase):
    def test_get_plugin_profile_from_meta_handles_missing_and_malformed_meta(self) -> None:
        self.assertEqual(get_plugin_profile_from_meta({"VPinFE": {"pluginprofile": " no-dmd "}}), "no-dmd")
        self.assertEqual(get_plugin_profile_from_meta({"VPinFE": {}}), "")
        self.assertEqual(get_plugin_profile_from_meta({"VPinFE": None}), "")
        self.assertEqual(get_plugin_profile_from_meta({}), "")
        self.assertEqual(get_plugin_profile_from_meta(None), "")

    def test_resolve_plugin_profile_returns_path_for_existing_profile(self) -> None:
        with TemporaryDirectory() as tmp:
            profiles = Path(tmp)
            profile = profiles / "no-dmd.ini"
            profile.write_text("[Plugin.DOF]\nEnable = 0\n", encoding="utf-8")

            with mock.patch.object(launcher, "PLUGIN_PROFILES_DIR", profiles):
                self.assertEqual(resolve_launch_plugin_profile("no-dmd"), str(profile))

    def test_resolve_plugin_profile_empty_for_default_blank_and_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            with mock.patch.object(launcher, "PLUGIN_PROFILES_DIR", Path(tmp)):
                # Default means "use the live VPinballX.ini" -> no -ini of its own.
                self.assertEqual(resolve_launch_plugin_profile("Default"), "")
                self.assertEqual(resolve_launch_plugin_profile("default"), "")
                self.assertEqual(resolve_launch_plugin_profile(""), "")
                self.assertEqual(resolve_launch_plugin_profile("   "), "")
                # A profile whose file was deleted must not break the launch.
                self.assertEqual(resolve_launch_plugin_profile("deleted-profile"), "")

    def test_plugin_profile_fills_ini_slot_and_keeps_play_last(self) -> None:
        cmd = build_vpx_launch_command(
            launcher_path="/opt/vpinball/VPinballX",
            vpx_table_path="/tables/example.vpx",
            plugin_profile_override="/cfg/plugin_profiles/no-dmd.ini",
        )
        self.assertEqual(
            cmd,
            [
                "/opt/vpinball/VPinballX",
                "-ini",
                "/cfg/plugin_profiles/no-dmd.ini",
                "-play",
                "/tables/example.vpx",
            ],
        )
        self.assertEqual(cmd[-2], "-play")

    def test_plugin_profile_wins_over_global_ini_override_without_duplicate_flag(self) -> None:
        cmd = build_vpx_launch_command(
            launcher_path="/opt/vpinball/VPinballX",
            vpx_table_path="/tables/example.vpx",
            global_ini_override="/cfg/VPinballX.ini",
            plugin_profile_override="/cfg/plugin_profiles/no-dmd.ini",
        )
        # VPX accepts a single -ini, so the per-table profile replaces the
        # global override rather than being appended alongside it.
        self.assertEqual(cmd.count("-ini"), 1)
        self.assertEqual(cmd[cmd.index("-ini") + 1], "/cfg/plugin_profiles/no-dmd.ini")
        self.assertNotIn("/cfg/VPinballX.ini", cmd)

    def test_global_ini_override_still_applies_when_no_plugin_profile(self) -> None:
        cmd = build_vpx_launch_command(
            launcher_path="/opt/vpinball/VPinballX",
            vpx_table_path="/tables/example.vpx",
            global_ini_override="/cfg/VPinballX.ini",
            plugin_profile_override="",
        )
        self.assertEqual(
            cmd,
            [
                "/opt/vpinball/VPinballX",
                "-ini",
                "/cfg/VPinballX.ini",
                "-play",
                "/tables/example.vpx",
            ],
        )


if __name__ == "__main__":
    unittest.main()
