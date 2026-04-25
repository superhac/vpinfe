import configparser
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from frontend.api import API


class TestApiInputMapping(unittest.TestCase):
    def _build_ini(self):
        parser = configparser.ConfigParser()
        parser.add_section("Input")
        parser.set("Input", "joyleft", "1")
        parser.set("Input", "keyleft", "ArrowLeft,ShiftLeft")
        parser.set("Input", "joyright", "2")
        parser.set("Input", "keyright", "ArrowRight,ShiftRight")
        parser.set("Input", "joyup", "3")
        parser.set("Input", "keyup", "ArrowUp")
        parser.set("Input", "joydown", "4")
        parser.set("Input", "keydown", "ArrowDown")
        parser.set("Input", "joyselect", "5")
        parser.set("Input", "keyselect", "Enter")
        parser.set("Input", "joymenu", "6")
        parser.set("Input", "keymenu", "m")
        parser.set("Input", "joyback", "7")
        parser.set("Input", "keyback", "b")
        parser.set("Input", "joytutorial", "8")
        parser.set("Input", "keytutorial", "t")
        parser.set("Input", "joyexit", "9")
        parser.set("Input", "keyexit", "Escape,q")
        parser.set("Input", "joycollectionmenu", "10")
        parser.set("Input", "keycollectionmenu", "c")
        parser.add_section("Settings")
        parser.set("Settings", "startup_collection", "")

        class DummyIni:
            def __init__(self, config):
                self.config = config
                self.saved = False

            def save(self):
                self.saved = True

        return DummyIni(parser)

    @patch("frontend.api.ensure_tables_loaded", return_value=[])
    def test_get_joymaping_includes_joytutorial(self, _mock_tables) -> None:
        ini = self._build_ini()
        api = API(ini)

        mapping = api.get_joymaping()

        self.assertEqual(mapping["joytutorial"], "8")

    @patch("frontend.api.ensure_tables_loaded", return_value=[])
    def test_set_button_mapping_accepts_joytutorial(self, _mock_tables) -> None:
        ini = self._build_ini()
        api = API(ini)

        result = api.set_button_mapping("joytutorial", 15)

        self.assertTrue(result["success"])
        self.assertEqual(ini.config.get("Input", "joytutorial"), "15")
        self.assertTrue(ini.saved)

    @patch("frontend.api.ensure_tables_loaded", return_value=[])
    def test_get_keymapping_includes_keytutorial(self, _mock_tables) -> None:
        ini = self._build_ini()
        api = API(ini)

        mapping = api.get_keymapping()

        self.assertEqual(mapping["keytutorial"], "t")

    @patch("frontend.api.start_dof_service_if_enabled")
    @patch("frontend.api.stop_libdmdutil_service")
    @patch("frontend.api.stop_dof_service")
    @patch("frontend.api.subprocess.Popen")
    @patch("frontend.api.build_vpx_launch_command", return_value=["/tmp/fake-launcher", "-play", "/tmp/table.vpx"])
    @patch("frontend.api.get_effective_launcher")
    @patch("frontend.api.ensure_tables_loaded")
    def test_launch_table_emits_launching_and_complete_events(
        self,
        mock_tables,
        mock_get_launcher,
        _mock_build_cmd,
        mock_popen,
        _mock_stop_dof,
        _mock_stop_dmd,
        _mock_start_dof,
    ) -> None:
        with TemporaryDirectory() as tmp:
            launcher = Path(tmp) / "VPinballX"
            launcher.write_text("", encoding="utf-8")
            table_path = Path(tmp) / "Example.vpx"
            table_path.write_text("", encoding="utf-8")

            table = types.SimpleNamespace(
                fullPathVPXfile=str(table_path),
                metaConfig={},
                tableDirName="Example",
                fullPathTable=str(Path(tmp)),
            )
            mock_tables.return_value = [table]
            mock_get_launcher.return_value = (launcher, "Settings", None)

            process = types.SimpleNamespace(stdout=[], wait=lambda: 0)
            mock_popen.return_value = process

            events = []
            ws_bridge = types.SimpleNamespace(
                send_event_all_with_iframe=lambda message: events.append(message)
            )

            ini = self._build_ini()
            api = API(ini, ws_bridge=ws_bridge)

            with patch("frontend.launch_service.table_play_service.track_table_play"), \
                patch("frontend.launch_service.table_play_service.increment_start_count"), \
                patch("frontend.launch_service.table_play_service.add_runtime_minutes"), \
                patch("frontend.launch_service.table_play_service.update_score_from_nvram"), \
                patch("frontend.launch_service.table_play_service.delete_nvram_if_configured"):
                api.launch_table(0)

            self.assertEqual(events[0]["type"], "TableLaunching")
            self.assertEqual(events[-1]["type"], "TableLaunchComplete")
