from __future__ import annotations

import configparser
import json
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common import metadata_service, system_actions, table_play_service, table_report_service
from frontend import config_api, realdmd_service, table_state, theme_api


class FrontendServiceTests(unittest.TestCase):
    def test_system_actions_restart_reexecs_when_flag_exists(self):
        with TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            (config_dir / ".restart").touch()
            logger = types.SimpleNamespace(info=mock.Mock())
            calls = []

            with mock.patch("common.system_actions.os.execvp", side_effect=lambda *args: calls.append(args)):
                system_actions.restart_if_requested(
                    config_dir,
                    logger,
                    main_script=Path("/app/main.py"),
                    sleep_func=lambda _seconds: None,
                )

            self.assertFalse((config_dir / ".restart").exists())
            self.assertEqual(calls, [(system_actions.sys.executable, [system_actions.sys.executable, "/app/main.py"])])

    def test_theme_config_missing_file_is_optional(self):
        parser = configparser.ConfigParser()
        parser["Settings"] = {"theme": "Example"}
        with TemporaryDirectory() as temp_dir, mock.patch("frontend.theme_api.THEMES_DIR", Path(temp_dir)):
            (Path(temp_dir) / "Example").mkdir()
            self.assertIsNone(theme_api.get_theme_config(parser))

    def test_theme_config_flattens_values_from_theme_json(self):
        parser = configparser.ConfigParser()
        parser["Settings"] = {"theme": "Example"}
        with TemporaryDirectory() as temp_dir, mock.patch("frontend.theme_api.THEMES_DIR", Path(temp_dir)):
            theme_dir = Path(temp_dir) / "Example"
            theme_dir.mkdir()
            (theme_dir / "theme.json").write_text(
                json.dumps(
                    {
                        "title": "Example Options",
                        "options": [
                            {"key": "showClock", "type": "boolean", "value": True},
                            {"key": "wheel.scale", "type": "number", "value": 1.25},
                            {"key": "audio.maxVolume", "type": "number", "default": 0.8},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = theme_api.get_theme_config(parser)

        self.assertEqual(
            result,
            {
                "showClock": True,
                "wheel": {"scale": 1.25},
                "audio": {"maxVolume": 0.8},
            },
        )

    def test_config_api_set_audio_mute_saves_and_broadcasts(self):
        parser = configparser.ConfigParser()
        parser["Settings"] = {"muteaudio": "false"}

        class DummyIni:
            def __init__(self):
                self.config = parser
                self.saved = False

            def save(self):
                self.saved = True

        events = []
        api = types.SimpleNamespace(
            _iniConfig=DummyIni(),
            send_event_all_windows_incself=lambda event: events.append(event),
        )

        self.assertTrue(config_api.set_audio_muted(api, "true"))
        self.assertEqual(parser["Settings"]["muteaudio"], "true")
        self.assertTrue(api._iniConfig.saved)
        self.assertEqual(events, [{"type": "AudioMuteChanged", "muted": True}])

    def test_realdmd_helpers_and_updater_process_pending(self):
        table = types.SimpleNamespace(
            tableDirName="Example",
            realDMDImagePath="/tmp/realdmd.png",
            metaConfig={"User": {"FrontendDOFEvent": "E901"}},
        )
        self.assertEqual(realdmd_service.get_frontend_dof_event_for_table(table), "E901")
        self.assertEqual(realdmd_service.get_realdmd_image_for_table(table), Path("/tmp/realdmd.png"))

        calls = []
        updater = realdmd_service.RealDmdUpdater("ini", "table", lambda ini, image: calls.append((ini, image)) or True)
        updater._table_name = "Example"
        updater._image_path = Path("/tmp/realdmd.png")
        updater._process_pending()
        self.assertEqual(calls, [("ini", Path("/tmp/realdmd.png"))])

    def test_claim_media_for_table_adds_user_media_entries(self):
        with TemporaryDirectory() as temp_dir:
            table_dir = Path(temp_dir) / "Example"
            medias_dir = table_dir / "medias"
            medias_dir.mkdir(parents=True)
            (table_dir / "Example.info").write_text("{}", encoding="utf-8")
            (medias_dir / "bg.png").write_text("x", encoding="utf-8")

            table = types.SimpleNamespace(fullPathTable=str(table_dir), tableDirName="Example")
            claimed = metadata_service.claim_media_for_table(table, "table", log=lambda *_args: None)

            self.assertEqual(claimed, 1)
            info = json.loads((table_dir / "Example.info").read_text(encoding="utf-8"))
            self.assertEqual(info["Medias"]["bg"]["Source"], "user")

    def test_table_report_service_logs_unknown_table(self):
        parser_instance = mock.Mock()
        table = types.SimpleNamespace(tableDirName="Unknown")
        parser_instance.getAllTables.return_value = [table]
        vps_instance = mock.Mock()
        vps_instance.__len__ = mock.Mock(return_value=0)
        vps_instance.parseTableNameFromDir.return_value = {"name": "Unknown", "manufacturer": "", "year": ""}
        vps_instance.lookupName.return_value = None
        logs = []
        ini = types.SimpleNamespace(config={"Settings": {"tablerootdir": "/tables"}})

        with mock.patch("common.table_report_service.TableParser", return_value=parser_instance), \
            mock.patch("common.table_report_service.VPSdb", return_value=vps_instance):
            table_report_service.list_unknown_tables(iniconfig=ini, log=lambda msg, *args: logs.append(msg % args if args else msg))

        self.assertTrue(any("Unknown table 1: Unknown" in line for line in logs))

    def test_frontend_rating_write_preserves_newer_on_disk_stats(self):
        with TemporaryDirectory() as temp_dir:
            table_dir = Path(temp_dir) / "Example"
            table_dir.mkdir()
            info_path = table_dir / "Example.info"
            info_path.write_text(
                json.dumps(
                    {
                        "Info": {"Title": "Example", "VPSId": "vps-1"},
                        "User": {"Rating": 0, "StartCount": 0, "RunTime": 0},
                        "VPXFile": {},
                        "VPinFE": {},
                    }
                ),
                encoding="utf-8",
            )
            table = types.SimpleNamespace(
                fullPathTable=str(table_dir),
                tableDirName="Example",
                metaConfig=json.loads(info_path.read_text(encoding="utf-8")),
            )

            info_path.write_text(
                json.dumps(
                    {
                        "Info": {"Title": "Example", "VPSId": "vps-1"},
                        "User": {"Rating": 0, "StartCount": 7, "RunTime": 15},
                        "VPXFile": {},
                        "VPinFE": {},
                    }
                ),
                encoding="utf-8",
            )

            result = table_state.set_table_rating([table], 0, 5)

            self.assertEqual(result, {"success": True, "rating": 5})
            saved = json.loads(info_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["User"]["Rating"], 5)
            self.assertEqual(saved["User"]["StartCount"], 7)
            self.assertEqual(saved["User"]["RunTime"], 15)

    def test_play_tracking_preserves_newer_on_disk_rating(self):
        with TemporaryDirectory() as temp_dir:
            table_dir = Path(temp_dir) / "Example"
            table_dir.mkdir()
            info_path = table_dir / "Example.info"
            info_path.write_text(
                json.dumps(
                    {
                        "Info": {"Title": "Example", "VPSId": "vps-1"},
                        "User": {"Rating": 0, "StartCount": 0, "RunTime": 0},
                        "VPXFile": {},
                        "VPinFE": {},
                    }
                ),
                encoding="utf-8",
            )
            table = types.SimpleNamespace(
                fullPathTable=str(table_dir),
                tableDirName="Example",
                metaConfig=json.loads(info_path.read_text(encoding="utf-8")),
            )

            info_path.write_text(
                json.dumps(
                    {
                        "Info": {"Title": "Example", "VPSId": "vps-1"},
                        "User": {"Rating": 4, "StartCount": 0, "RunTime": 0},
                        "VPXFile": {},
                        "VPinFE": {},
                    }
                ),
                encoding="utf-8",
            )

            table_play_service.increment_start_count(table)

            saved = json.loads(info_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["User"]["Rating"], 4)
            self.assertEqual(saved["User"]["StartCount"], 1)

    def test_parse_score_from_nvram_prefers_vpxfile_rom(self) -> None:
        with TemporaryDirectory() as tmp:
            table_dir = Path(tmp) / "Example"
            table_dir.mkdir()
            info_path = table_dir / "Example.info"
            info_path.write_text(
                json.dumps(
                    {
                        "Info": {"Rom": "info_rom"},
                        "VPXFile": {"rom": "vpx_rom"},
                    }
                ),
                encoding="utf-8",
            )
            table = types.SimpleNamespace(
                fullPathTable=str(table_dir),
                tableDirName="Example",
                metaConfig={},
            )

            with mock.patch("common.score_parser.read_rom_with_source", return_value=(123, "/scores/vpx_rom.nv")) as read_rom, \
                    mock.patch("common.score_parser.result_to_jsonable", return_value={"rom": "vpx_rom"}) as to_json:
                score_data, score_path = table_play_service.parse_score_from_nvram(table)

            read_rom.assert_called_once_with("vpx_rom", str(table_dir))
            to_json.assert_called_once_with("vpx_rom", 123, "/scores/vpx_rom.nv")
            self.assertEqual(score_data, {"rom": "vpx_rom"})
            self.assertEqual(score_path, "/scores/vpx_rom.nv")

    def test_parse_score_from_nvram_falls_back_to_info_rom(self) -> None:
        with TemporaryDirectory() as tmp:
            table_dir = Path(tmp) / "Example"
            table_dir.mkdir()
            info_path = table_dir / "Example.info"
            info_path.write_text(
                json.dumps(
                    {
                        "Info": {"Rom": "info_rom"},
                        "VPXFile": {"rom": ""},
                    }
                ),
                encoding="utf-8",
            )
            table = types.SimpleNamespace(
                fullPathTable=str(table_dir),
                tableDirName="Example",
                metaConfig={},
            )

            with mock.patch("common.score_parser.read_rom_with_source", return_value=(123, "/scores/info_rom.nv")) as read_rom, \
                    mock.patch("common.score_parser.result_to_jsonable", return_value={"rom": "info_rom"}):
                table_play_service.parse_score_from_nvram(table)

            read_rom.assert_called_once_with("info_rom", str(table_dir))

    def test_delete_nvram_if_configured_prefers_vpxfile_rom(self) -> None:
        with TemporaryDirectory() as tmp:
            table_dir = Path(tmp) / "Example"
            nvram_dir = table_dir / "pinmame" / "nvram"
            nvram_dir.mkdir(parents=True)
            vpx_nvram = nvram_dir / "vpx_rom.nv"
            info_nvram = nvram_dir / "info_rom.nv"
            vpx_nvram.write_bytes(b"vpx")
            info_nvram.write_bytes(b"info")
            table = types.SimpleNamespace(
                fullPathTable=str(table_dir),
                tableDirName="Example",
                metaConfig={
                    "Info": {"Rom": "info_rom"},
                    "VPXFile": {"rom": "vpx_rom"},
                    "VPinFE": {"deletedNVRamOnClose": True},
                },
            )

            table_play_service.delete_nvram_if_configured(table)

            self.assertFalse(vpx_nvram.exists())
            self.assertTrue(info_nvram.exists())


if __name__ == "__main__":
    unittest.main()
