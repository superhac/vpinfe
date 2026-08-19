import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.config_store import ConfigStore


class TestConfigStore(unittest.TestCase):
    def test_adds_libdmdutil_defaults_to_new_config(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = ConfigStore(str(ini_path))

            self.assertTrue(config.config.has_section("libdmdutil"))
            self.assertEqual(config.config.get("libdmdutil", "enabled"), "false")
            self.assertEqual(config.config.get("libdmdutil", "pin2dmd_enabled"), "false")
            self.assertEqual(config.config.get("libdmdutil", "pixelcade_serial_port"), "")
            self.assertEqual(config.config.get("libdmdutil", "zedmd_serial_port"), "")
            self.assertEqual(config.config.get("libdmdutil", "zedmd_wifi_address"), "")

    def test_adds_missing_libdmdutil_defaults_to_existing_config(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"
            ini_path.write_text("[Settings]\ntheme = Revolution\n", encoding="utf-8")

            config = ConfigStore(str(ini_path))

            self.assertTrue(config.config.has_section("libdmdutil"))
            self.assertEqual(config.config.get("libdmdutil", "enabled"), "false")
            self.assertEqual(config.config.get("libdmdutil", "pin2dmd_enabled"), "false")
            self.assertEqual(config.config.get("libdmdutil", "pixelcade_serial_port"), "")
            self.assertEqual(config.config.get("libdmdutil", "zedmd_serial_port"), "")
            self.assertEqual(config.config.get("libdmdutil", "zedmd_wifi_address"), "")

    def test_adds_the_shipped_input_bindings(self) -> None:
        """One list per action, each binding naming its own input."""
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = ConfigStore(str(ini_path))

            self.assertTrue(config.config.has_section("input"))
            self.assertEqual(config.config.get("input", "previous"),
                             "key:ArrowLeft,key:ShiftLeft")
            self.assertEqual(config.config.get("input", "page_previous"),
                             "key:PageUp,key:ArrowUp")
            self.assertEqual(config.config.get("input", "back"), "key:b")
            self.assertEqual(config.config.get("input", "exit"), "key:Escape,key:q")
            self.assertEqual(config.config.get("input", "tutorial"), "key:t")

    def test_adds_mainmenu_hide_quit_button_setting_default(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = ConfigStore(str(ini_path))

            self.assertTrue(config.config.has_section("general"))
            self.assertEqual(config.config.get("frontend", "hide_quit_button"), "false")

    def test_splashscreen_defaults_off(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = ConfigStore(str(ini_path))

            self.assertTrue(config.config.has_section("general"))
            self.assertEqual(config.config.get("general", "splashscreen"), "false")

    def test_chrome_options_default_empty(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = ConfigStore(str(ini_path))

            self.assertTrue(config.config.has_section("general"))
            self.assertEqual(config.config.get("general", "chrome_options"), "")

    def test_disable_default_chrome_options_defaults_off(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = ConfigStore(str(ini_path))

            self.assertTrue(config.config.has_section("general"))
            self.assertEqual(
                config.config.get("general", "disable_default_chrome_options"), "false")

    def test_vpx_log_delete_on_start_defaults_off(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = ConfigStore(str(ini_path))

            self.assertTrue(config.config.has_section("general"))
            self.assertEqual(config.config.get("general", "vpx_log_delete_on_start"), "false")

    def test_restore_last_game_defaults_on(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = ConfigStore(str(ini_path))

            self.assertTrue(config.config.has_section("general"))
            self.assertEqual(config.config.get("frontend", "restore_last_table"), "true")

    def test_state_section_lasttable_defaults_empty(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = ConfigStore(str(ini_path))

            self.assertTrue(config.config.has_section("state"))
            self.assertEqual(config.config.get("state", "last_table"), "")

    def test_existing_splashscreen_setting_is_preserved(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"
            ini_path.write_text("[Settings]\nsplashscreen = true\n", encoding="utf-8")

            config = ConfigStore(str(ini_path))

            self.assertEqual(config.config.get("general", "splashscreen"), "true")

    def test_a_renamed_key_keeps_the_users_value(self) -> None:
        """The rename must run before defaults are filled in.

        With the default already present, "copy only if the new key is absent" copies
        nothing, and removing the old key then throws the user's setting away. Every
        value below was silently reset to its default before this was fixed.
        """
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"
            ini_path.write_text(
                "[Settings]\ntablerootdir = /old/path\nrestorelasttable = false\n"
                "[Media]\ntabletype = fss\n"
                "[Displays]\ntablerotation = 270\n"
                "[State]\nlasttable = Foo\n", encoding="utf-8")

            config = ConfigStore(str(ini_path))

            self.assertEqual(config.config.get("general", "game_root_dir"), "/old/path")
            self.assertEqual(config.config.get("frontend", "restore_last_table"), "false")
            # Both of these also moved into their window's own section at schema 3.
            self.assertEqual(config.config.get("windows.playfield", "variant"), "fss")
            self.assertEqual(config.config.get("windows.playfield", "rotation"), "270")
            self.assertEqual(config.config.get("state", "last_table"), "Foo")
            self.assertFalse(config.config.has_option("general", "tablerootdir"),
                             "the old key should be gone once it has been read")


    def test_a_moved_option_keeps_the_users_value(self) -> None:
        """The move has to happen before the defaults are written.

        Every moved key has a default. Once one is in place, "copy only if absent"
        copies nothing and remove_option drops the real value - so an upgrade turned
        cab mode and DOF off and left nothing to explain why.
        """
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"
            ini_path.write_text(
                "[Settings]\ncabmode = true\nenabledof = true\n"
                "[Displays]\nsplashscreen = true\n",
                encoding="utf-8",
            )

            config = ConfigStore(str(ini_path))

            self.assertEqual(config.config.get("displays", "cab_mode"), "true")
            self.assertEqual(config.config.get("dof", "enable_dof"), "true")
            self.assertEqual(config.config.get("general", "splashscreen"), "true")
            # and the old spellings are gone, so the move is not repeated
            self.assertFalse(config.config.has_option("general", "cab_mode"))
            self.assertFalse(config.config.has_option("general", "enable_dof"))
            self.assertFalse(config.config.has_option("displays", "splashscreen"))

    def test_a_moved_option_does_not_overwrite_a_value_already_there(self) -> None:
        """If both spellings exist, the one in the current section wins."""
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"
            ini_path.write_text(
                "[Settings]\ncabmode = true\n[Displays]\ncabmode = false\n",
                encoding="utf-8",
            )

            config = ConfigStore(str(ini_path))

            self.assertEqual(config.config.get("displays", "cab_mode"), "false")
            self.assertFalse(config.config.has_option("general", "cab_mode"))


if __name__ == "__main__":
    unittest.main()
