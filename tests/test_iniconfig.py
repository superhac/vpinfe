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
            self.assertEqual(config.config.get("Input", "keyback"), "b")
            self.assertEqual(config.config.get("Input", "keyexit"), "Escape,q")


if __name__ == "__main__":
    unittest.main()
