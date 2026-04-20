import configparser
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("screeninfo", types.SimpleNamespace(get_monitors=lambda: []))
sys.modules.setdefault("platformdirs", types.SimpleNamespace(user_config_dir=lambda *args, **kwargs: "/tmp"))

table_repository_stub = types.ModuleType("common.table_repository")
table_repository_stub.ensure_tables_loaded = lambda: []
sys.modules.setdefault("common.table_repository", table_repository_stub)

vpxcollections_stub = types.ModuleType("common.vpxcollections")
vpxcollections_stub.VPXCollections = object
sys.modules.setdefault("common.vpxcollections", vpxcollections_stub)

tablelistfilters_stub = types.ModuleType("common.tablelistfilters")
tablelistfilters_stub.TableListFilters = object
sys.modules.setdefault("common.tablelistfilters", tablelistfilters_stub)

dof_service_stub = types.ModuleType("common.dof_service")
dof_service_stub.send_frontend_dof_event = lambda *args, **kwargs: None
dof_service_stub.start_dof_service_if_enabled = lambda *args, **kwargs: None
dof_service_stub.stop_dof_service = lambda *args, **kwargs: None
dof_service_stub.find_dof_file = lambda *args, **kwargs: None
sys.modules.setdefault("common.dof_service", dof_service_stub)

libdmdutil_stub = types.ModuleType("common.libdmdutil_service")
libdmdutil_stub.show_image = lambda *args, **kwargs: False
libdmdutil_stub.stop_libdmdutil_service = lambda *args, **kwargs: None
sys.modules.setdefault("common.libdmdutil_service", libdmdutil_stub)

launcher_stub = types.ModuleType("common.launcher")
launcher_stub.build_vpx_launch_command = lambda *args, **kwargs: []
launcher_stub.get_effective_launcher = lambda *args, **kwargs: ("", "Settings", None)
launcher_stub.parse_launch_env_overrides = lambda *args, **kwargs: {}
launcher_stub.resolve_launch_tableini_override = lambda *args, **kwargs: None
sys.modules.setdefault("common.launcher", launcher_stub)

score_parser_stub = types.ModuleType("common.score_parser")
score_parser_stub.read_rom_with_source = lambda *args, **kwargs: None
score_parser_stub.result_to_jsonable = lambda result: result
sys.modules.setdefault("common.score_parser", score_parser_stub)

from frontend.api import API


class TestApiInputMapping(unittest.TestCase):
    def _build_ini(self):
        parser = configparser.ConfigParser()
        parser.add_section("Input")
        parser.set("Input", "joyleft", "1")
        parser.set("Input", "joyright", "2")
        parser.set("Input", "joyup", "3")
        parser.set("Input", "joydown", "4")
        parser.set("Input", "joyselect", "5")
        parser.set("Input", "joymenu", "6")
        parser.set("Input", "joyback", "7")
        parser.set("Input", "joytutorial", "8")
        parser.set("Input", "joyexit", "9")
        parser.set("Input", "joycollectionmenu", "10")
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
