import configparser
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from common import events
from frontend import play_events
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

    @patch("common.host.launch.subprocess.Popen")
    @patch("common.host.launch.build_vpx_launch_command",
           return_value=["/tmp/fake-launcher", "-play", "/tmp/table.vpx"])
    @patch("common.host.launch.get_effective_launcher")
    @patch("frontend.api.ensure_tables_loaded")
    def test_launch_table_emits_launching_and_complete_events(
        self,
        mock_tables,
        mock_get_launcher,
        _mock_build_cmd,
        mock_popen,
    ) -> None:
        """The wheel launches through the shared service; the windows hear about it
        as subscribers rather than from the launch itself."""
        with TemporaryDirectory() as tmp:
            launcher = Path(tmp) / "VPinballX"
            launcher.write_text("", encoding="utf-8")
            table_path = Path(tmp) / "Example.vpx"
            table_path.write_text("", encoding="utf-8")

            game = types.SimpleNamespace(
                fullPathVPXfile=str(table_path),
                metaConfig={},
                tableDirName="Example",
                fullPathTable=str(Path(tmp)),
            )
            mock_tables.return_value = [game]
            mock_get_launcher.return_value = (launcher, "Settings", None)

            process = types.SimpleNamespace(stdout=[], wait=lambda: 0)
            mock_popen.return_value = process

            window_messages = []
            call_order = []
            ws_bridge = types.SimpleNamespace(
                send_event_all_with_iframe=lambda message: window_messages.append(message)
            )

            ini = self._build_ini()
            api = API(ini, ws_bridge=ws_bridge)

            def popen_side_effect(*args, **kwargs):
                call_order.append("popen")
                return process

            mock_popen.side_effect = popen_side_effect

            play_events.reset_for_tests()
            self.addCleanup(play_events.reset_for_tests)
            self.addCleanup(events.clear)
            with patch("common.host.launch.delete_vpinball_log_on_start_if_configured", side_effect=lambda _settings: call_order.append("delete_log")), \
                patch("common.host.launch.table_play_service"), \
                patch("frontend.play_events.save_last_table"):
                play_events.register(ws_bridge)
                api.launch_table(0)

            self.assertEqual(call_order[:2], ["delete_log", "popen"])
            self.assertEqual(window_messages[0]["type"], "TableLaunching")
            self.assertEqual(window_messages[-1]["type"], "TableLaunchComplete")
