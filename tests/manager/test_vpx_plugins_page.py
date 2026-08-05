from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


try:
    # Prefer the real framework when it's installed. Installing an incomplete
    # stub via setdefault would leak into sys.modules and break later tests that
    # import the full managerui UI (which needs nicegui.app / nicegui.context).
    import nicegui  # noqa: F401
except ImportError:
    sys.modules.setdefault(
        "nicegui",
        types.SimpleNamespace(ui=types.SimpleNamespace(input=object)),
    )
sys.modules.setdefault(
    "platformdirs",
    types.SimpleNamespace(user_config_dir=lambda *args, **kwargs: "/tmp/vpinfe-test"),
)

plugin_profile_service = importlib.import_module("managerui.services.plugin_profile_service")
vpx_config_service = importlib.import_module("managerui.services.vpx_config_service")


SAMPLE_INI = (
    "[Editor]\n"
    "EnableLog = 1\n"
    "\n"
    "[Plugin.AltSound]\n"
    "; Enable: Enable legacy AltSound plugin [Default: 1]\n"
    "Enable = \n"
    "Folder = /old/path\n"
    "\n"
    "[Standalone]\n"
    "Haptics = 1\n"
    "\n"
    "[Plugin.DOF]\n"
    "Enable = 1\n"
)


class PluginSectionTests(unittest.TestCase):
    def test_only_plugin_sections_are_returned_in_file_order(self):
        with TemporaryDirectory() as temp_dir:
            ini_path = Path(temp_dir) / "VPinballX.ini"
            ini_path.write_text(SAMPLE_INI, encoding="utf-8")
            sections = plugin_profile_service.load_plugin_sections(ini_path)

        self.assertEqual([s["name"] for s in sections], ["Plugin.AltSound", "Plugin.DOF"])
        self.assertEqual([s["label"] for s in sections], ["AltSound", "DOF"])
        self.assertEqual(
            [f.key for f in sections[0]["fields"]],
            ["Enable", "Folder"],
        )

    def test_comment_metadata_is_parsed_for_plugin_keys(self):
        with TemporaryDirectory() as temp_dir:
            ini_path = Path(temp_dir) / "VPinballX.ini"
            ini_path.write_text(SAMPLE_INI, encoding="utf-8")
            sections = plugin_profile_service.load_plugin_sections(ini_path)

        enable = sections[0]["fields"][0]
        self.assertEqual(enable.label, "Enable")
        self.assertEqual(enable.description, "Enable legacy AltSound plugin")
        self.assertEqual(enable.default_text, "[Default: 1]")


class SaveTests(unittest.TestCase):
    def test_save_updates_plugin_keys_and_preserves_other_sections(self):
        with TemporaryDirectory() as temp_dir:
            ini_path = Path(temp_dir) / "VPinballX.ini"
            ini_path.write_text(SAMPLE_INI, encoding="utf-8")

            sections = plugin_profile_service.load_plugin_sections(ini_path)
            vpx_config_service.write_updated_ini(
                ini_path,
                sections,
                {
                    "Plugin.AltSound": {"Enable": "1", "Folder": "/new/path"},
                    "Plugin.DOF": {"Enable": "0"},
                },
            )
            written = ini_path.read_text(encoding="utf-8")

        self.assertIn("Enable = 1\nFolder = /new/path\n", written)
        self.assertIn("[Plugin.DOF]\nEnable = 0\n", written)
        # Untouched sections and the plugin's comment must survive the rewrite.
        self.assertIn("[Editor]\nEnableLog = 1\n", written)
        self.assertIn("[Standalone]\nHaptics = 1\n", written)
        self.assertIn("; Enable: Enable legacy AltSound plugin [Default: 1]\n", written)


class ProfileTests(unittest.TestCase):
    def test_sanitize_profile_name_strips_path_separators(self):
        self.assertEqual(plugin_profile_service.sanitize_profile_name("no dmd"), "no dmd")
        self.assertEqual(plugin_profile_service.sanitize_profile_name("../../etc/passwd"), "etc-passwd")
        self.assertEqual(plugin_profile_service.sanitize_profile_name("  "), "")

    def test_default_profile_resolves_to_live_vpx_ini(self):
        with TemporaryDirectory() as temp_dir:
            ini_path = Path(temp_dir) / "VPinballX.ini"
            ini_path.write_text(SAMPLE_INI, encoding="utf-8")
            with mock.patch.object(
                plugin_profile_service.vpx_config_service, "load_vpx_ini_path", return_value=ini_path
            ):
                resolved = plugin_profile_service.profile_path("Default")

        self.assertEqual(resolved, ini_path)

    def test_create_profile_copies_full_ini_and_lists_it(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            ini_path = temp_path / "VPinballX.ini"
            ini_path.write_text(SAMPLE_INI, encoding="utf-8")
            profiles_dir = temp_path / "plugin_profiles"

            with mock.patch.object(
                plugin_profile_service.vpx_config_service, "load_vpx_ini_path", return_value=ini_path
            ), mock.patch.object(plugin_profile_service, "PLUGIN_PROFILES_DIR", profiles_dir):
                created = plugin_profile_service.create_profile("No DMD")

                self.assertEqual(created, profiles_dir / "No DMD.ini")
                # A new profile starts as a byte-for-byte copy of VPinballX.ini.
                self.assertEqual(created.read_text(encoding="utf-8"), SAMPLE_INI)
                self.assertEqual(
                    plugin_profile_service.list_profiles(), ["Default", "No DMD"]
                )
                self.assertEqual(
                    plugin_profile_service.profile_path("No DMD"), profiles_dir / "No DMD.ini"
                )

                with self.assertRaises(ValueError):
                    plugin_profile_service.create_profile("No DMD")
                with self.assertRaises(ValueError):
                    plugin_profile_service.create_profile("Default")

    def test_saving_custom_profile_leaves_live_ini_untouched(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            ini_path = temp_path / "VPinballX.ini"
            ini_path.write_text(SAMPLE_INI, encoding="utf-8")
            profiles_dir = temp_path / "plugin_profiles"

            with mock.patch.object(
                plugin_profile_service.vpx_config_service, "load_vpx_ini_path", return_value=ini_path
            ), mock.patch.object(plugin_profile_service, "PLUGIN_PROFILES_DIR", profiles_dir):
                created = plugin_profile_service.create_profile("no-dmd")

            sections = plugin_profile_service.load_plugin_sections(created)
            vpx_config_service.write_updated_ini(
                created, sections, {"Plugin.DOF": {"Enable": "0"}}
            )

            self.assertIn("[Plugin.DOF]\nEnable = 0\n", created.read_text(encoding="utf-8"))
            self.assertEqual(ini_path.read_text(encoding="utf-8"), SAMPLE_INI)


if __name__ == "__main__":
    unittest.main()
