import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.iniconfig import IniConfig


class TestIniConfig(unittest.TestCase):
    def test_adds_libdmdutil_defaults_to_new_config(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = IniConfig(str(ini_path))

            self.assertTrue(config.config.has_section("libdmdutil"))
            self.assertEqual(config.config.get("libdmdutil", "enabled"), "false")
            self.assertEqual(config.config.get("libdmdutil", "pin2dmdenabled"), "false")
            self.assertEqual(config.config.get("libdmdutil", "pixelcadedevice"), "")
            self.assertEqual(config.config.get("libdmdutil", "zedmddevice"), "")
            self.assertEqual(config.config.get("libdmdutil", "zedmdwifiaddr"), "")

    def test_adds_missing_libdmdutil_defaults_to_existing_config(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"
            ini_path.write_text("[Settings]\ntheme = Revolution\n", encoding="utf-8")

            config = IniConfig(str(ini_path))

            self.assertTrue(config.config.has_section("libdmdutil"))
            self.assertEqual(config.config.get("libdmdutil", "enabled"), "false")
            self.assertEqual(config.config.get("libdmdutil", "pin2dmdenabled"), "false")
            self.assertEqual(config.config.get("libdmdutil", "pixelcadedevice"), "")
            self.assertEqual(config.config.get("libdmdutil", "zedmddevice"), "")
            self.assertEqual(config.config.get("libdmdutil", "zedmdwifiaddr"), "")

    def test_adds_joytutorial_default_input_mapping(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = IniConfig(str(ini_path))

            self.assertTrue(config.config.has_section("Input"))
            self.assertEqual(config.config.get("Input", "joytutorial"), "")

    def test_adds_keyboard_defaults_to_input_mapping(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = IniConfig(str(ini_path))

            self.assertTrue(config.config.has_section("Input"))
            self.assertEqual(config.config.get("Input", "keyleft"), "ArrowLeft,ShiftLeft")
            self.assertEqual(config.config.get("Input", "keypageup"), "PageUp")
            self.assertEqual(config.config.get("Input", "keypagedown"), "PageDown")
            self.assertEqual(config.config.get("Input", "keyback"), "b")
            self.assertEqual(config.config.get("Input", "keyexit"), "Escape,q")

    def test_adds_mainmenu_hide_quit_button_setting_default(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = IniConfig(str(ini_path))

            self.assertTrue(config.config.has_section("Settings"))
            self.assertEqual(config.config.get("Settings", "MMhideQuitButton"), "false")

    def test_splashscreen_defaults_off(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"

            config = IniConfig(str(ini_path))

            self.assertTrue(config.config.has_section("Settings"))
            self.assertEqual(config.config.get("Settings", "splashscreen"), "false")

    def test_existing_splashscreen_setting_is_preserved(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "vpinfe.ini"
            ini_path.write_text("[Settings]\nsplashscreen = true\n", encoding="utf-8")

            config = IniConfig(str(ini_path))

            self.assertEqual(config.config.get("Settings", "splashscreen"), "true")


if __name__ == "__main__":
    unittest.main()
