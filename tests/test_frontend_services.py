from __future__ import annotations

import configparser
import json
import types
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common.host import realdmd, system_actions
from common.tables import table_play_service, table_report_service
from common.tables.table_metadata import game_frontend_dof_event
from frontend import config_api, table_state, theme_api


class FrontendServiceTests(unittest.TestCase):
    def test_system_actions_restart_reexecs_when_flag_exists(self):
        with TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            (config_dir / ".restart").touch()
            logger = types.SimpleNamespace(info=mock.Mock())
            calls = []

            with mock.patch("common.host.system_actions.os.execvp", side_effect=lambda *args: calls.append(args)):
                system_actions.restart_if_requested(
                    config_dir,
                    logger,
                    main_script=Path("/app/main.py"),
                    sleep_func=lambda _seconds: None,
                )

            self.assertFalse((config_dir / ".restart").exists())
            # The code passes main_script through os.path.abspath, which on Windows
            # prefixes the current drive. Expect what it actually builds.
            main_script = os.path.abspath(Path("/app/main.py"))
            self.assertEqual(
                calls,
                [(system_actions.sys.executable,
                  [system_actions.sys.executable, main_script])],
            )

    def test_theme_config_missing_file_is_optional(self):
        parser = configparser.ConfigParser()
        parser["Settings"] = {"theme": "Example"}
        with TemporaryDirectory() as temp_dir, mock.patch("frontend.theme_api.THEMES_DIR", Path(temp_dir)):
            (Path(temp_dir) / "Example").mkdir()
            self.assertIsNone(theme_api.get_theme_config(parser))

    def _theme_config(self, **files):
        """get_theme_config for a theme dir holding the given <name>.json files."""
        parser = configparser.ConfigParser()
        parser["Settings"] = {"theme": "Example"}
        with (
            TemporaryDirectory() as temp_dir,
            mock.patch("frontend.theme_api.THEMES_DIR", Path(temp_dir)),
        ):
            theme_dir = Path(temp_dir) / "Example"
            theme_dir.mkdir()
            for name, body in files.items():
                (theme_dir / f"{name}.json").write_text(json.dumps(body), encoding="utf-8")
            return theme_api.get_theme_config(parser)

    def test_theme_config_merges_author_config_under_user_options(self):
        """Revolution's shape: one user option must not drop the author's config.json."""
        result = self._theme_config(
            config={"use_core_audio": True, "audio": {"enabled": True}},
            theme={"options": [{"key": "startCollectionSelection", "value": False}]},
        )

        self.assertEqual(
            result,
            {
                "use_core_audio": True,
                "audio": {"enabled": True},
                "startCollectionSelection": False,
            },
        )

    def test_theme_config_user_option_wins_but_keeps_the_rest_of_the_section(self):
        result = self._theme_config(
            config={"audio": {"enabled": True, "maxVolume": 0.4}},
            theme={"options": [{"key": "audio.maxVolume", "value": 0.9}]},
        )

        self.assertEqual(result, {"audio": {"enabled": True, "maxVolume": 0.9}})

    def test_theme_config_reads_author_config_when_there_are_no_options(self):
        result = self._theme_config(config={"use_core_audio": True})

        self.assertEqual(result, {"use_core_audio": True})

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
        game = types.SimpleNamespace(
            tableDirName="Example",
            realDMDImagePath="/tmp/realdmd.png",
            realDMDColorImagePath="/tmp/realdmd-color.png",
            metaConfig={"vpinfe": {"frontend_dof_event": "E901"}},
        )
        color_config = configparser.ConfigParser()
        color_config.read_dict({"Media": {"realdmdmediapriority": "color"}})
        standard_config = configparser.ConfigParser()
        standard_config.read_dict({"Media": {"realdmdmediapriority": "standard"}})

        # get_realdmd_image_for_table returns path.resolve(); on macOS /tmp is a
        # symlink to /private/tmp, so compare against the resolved expectation.
        color_expected = Path("/tmp/realdmd-color.png").resolve()
        standard_expected = Path("/tmp/realdmd.png").resolve()
        self.assertEqual(game_frontend_dof_event(game), "E901")
        self.assertEqual(realdmd.get_realdmd_image_for_game(game), color_expected)
        self.assertEqual(realdmd.get_realdmd_image_for_game(game, color_config), color_expected)
        self.assertEqual(realdmd.get_realdmd_image_for_game(game, standard_config), standard_expected)

        game.realDMDColorImagePath = ""
        self.assertEqual(realdmd.get_realdmd_image_for_game(game, color_config), standard_expected)

        calls = []
        updater = realdmd.RealDmdUpdater("ini", "table", lambda ini, image: calls.append((ini, image)) or True)
        updater._game_name = "Example"
        updater._image_path = Path("/tmp/realdmd.png")
        updater._process_pending()
        self.assertEqual(calls, [("ini", Path("/tmp/realdmd.png"))])

    def test_game_report_service_logs_unknown_game(self):
        parser_instance = mock.Mock()
        game = types.SimpleNamespace(tableDirName="Unknown")
        parser_instance.getAllGames.return_value = [game]
        vps_instance = mock.Mock()
        vps_instance.__len__ = mock.Mock(return_value=0)
        vps_instance.parseGameNameFromDir.return_value = {"name": "Unknown", "manufacturer": "", "year": ""}
        vps_instance.lookupName.return_value = None
        logs = []
        ini = types.SimpleNamespace(config={"Settings": {"tablerootdir": "/tables"}})

        with mock.patch("common.tables.table_report_service.GameParser", return_value=parser_instance), \
            mock.patch("common.tables.table_report_service.VPSdb", return_value=vps_instance):
            table_report_service.list_unknown_games(iniconfig=ini, log=lambda msg, *args: logs.append(msg % args if args else msg))

        self.assertTrue(any("Unknown table 1: Unknown" in line for line in logs))

    def test_frontend_rating_write_preserves_newer_on_disk_stats(self):
        with TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir) / "Example"
            game_dir.mkdir()
            info_path = game_dir / "Example.info"
            info_path.write_text(
                json.dumps(
                    {
                        "Info": {"Title": "Example", "VPSId": "vps-1"},
                        "User": {"Rating": 0, "StartCount": 0, "RunTime": 0},
                        "VPXFile": {},
                        "vpinfe": {},
                    }
                ),
                encoding="utf-8",
            )
            game = types.SimpleNamespace(
                fullPathTable=str(game_dir),
                tableDirName="Example",
                metaConfig=json.loads(info_path.read_text(encoding="utf-8")),
            )

            info_path.write_text(
                json.dumps(
                    {
                        "Info": {"Title": "Example", "VPSId": "vps-1"},
                        "User": {"Rating": 0, "StartCount": 7, "RunTime": 15},
                        "VPXFile": {},
                        "vpinfe": {},
                    }
                ),
                encoding="utf-8",
            )

            result = table_state.set_table_rating([game], 0, 5)

            self.assertEqual(result, {"success": True, "rating": 5})
            saved = json.loads(info_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["User"]["Rating"], 5)
            self.assertEqual(saved["User"]["StartCount"], 7)
            self.assertEqual(saved["User"]["RunTime"], 15)

    def test_play_tracking_preserves_newer_on_disk_rating(self):
        with TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir) / "Example"
            game_dir.mkdir()
            info_path = game_dir / "Example.info"
            info_path.write_text(
                json.dumps(
                    {
                        "Info": {"Title": "Example", "VPSId": "vps-1"},
                        "User": {"Rating": 0, "StartCount": 0, "RunTime": 0},
                        "VPXFile": {},
                        "vpinfe": {},
                    }
                ),
                encoding="utf-8",
            )
            game = types.SimpleNamespace(
                fullPathTable=str(game_dir),
                tableDirName="Example",
                metaConfig=json.loads(info_path.read_text(encoding="utf-8")),
            )

            info_path.write_text(
                json.dumps(
                    {
                        "Info": {"Title": "Example", "VPSId": "vps-1"},
                        "User": {"Rating": 4, "StartCount": 0, "RunTime": 0},
                        "VPXFile": {},
                        "vpinfe": {},
                    }
                ),
                encoding="utf-8",
            )

            table_play_service.increment_start_count(game)

            saved = json.loads(info_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["User"]["Rating"], 4)
            self.assertEqual(saved["User"]["StartCount"], 1)

    def test_parse_score_from_nvram_reads_the_game_files_rom(self) -> None:
        with TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Example"
            game_dir.mkdir()
            info_path = game_dir / "Example.info"
            info_path.write_text(
                json.dumps(
                    {
                        "game_files": {"Example.vpx": {"rom": "vpx_rom"}},
                    }
                ),
                encoding="utf-8",
            )
            game = types.SimpleNamespace(
                fullPathTable=str(game_dir),
                tableDirName="Example",
                metaConfig={},
            )

            with mock.patch("common.tables.score_parser.read_rom_with_source", return_value=(123, "/scores/vpx_rom.nv")) as read_rom, \
                    mock.patch("common.tables.score_parser.result_to_jsonable", return_value={"rom": "vpx_rom"}) as to_json:
                score_data, score_path = table_play_service.parse_score_from_nvram(game)

            read_rom.assert_called_once_with("vpx_rom", str(game_dir))
            to_json.assert_called_once_with("vpx_rom", 123, "/scores/vpx_rom.nv")
            self.assertEqual(score_data, {"rom": "vpx_rom"})
            self.assertEqual(score_path, "/scores/vpx_rom.nv")

    def test_a_migrated_game_reads_its_rom_from_the_game_file(self) -> None:
        """2.x kept a table-level Info.Rom and the migration drops it. A value carried
        from there could disagree with the file it claims to describe."""
        with TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Example"
            game_dir.mkdir()
            info_path = game_dir / "Example.info"
            info_path.write_text(
                json.dumps(
                    {
                        "Info": {"Rom": "info_rom"},
                        "VPXFile": {"filename": "Example.vpx", "rom": "vpx_rom"},
                    }
                ),
                encoding="utf-8",
            )
            game = types.SimpleNamespace(
                fullPathTable=str(game_dir),
                tableDirName="Example",
                metaConfig={},
            )

            with mock.patch("common.tables.score_parser.read_rom_with_source", return_value=(123, "/scores/vpx_rom.nv")) as read_rom, \
                    mock.patch("common.tables.score_parser.result_to_jsonable", return_value={"rom": "vpx_rom"}):
                table_play_service.parse_score_from_nvram(game)

            read_rom.assert_called_once_with("vpx_rom", str(game_dir))

    def test_delete_nvram_if_configured_reads_the_game_files_rom(self) -> None:
        with TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Example"
            nvram_dir = game_dir / "pinmame" / "nvram"
            nvram_dir.mkdir(parents=True)
            vpx_nvram = nvram_dir / "vpx_rom.nv"
            info_nvram = nvram_dir / "info_rom.nv"
            vpx_nvram.write_bytes(b"vpx")
            info_nvram.write_bytes(b"info")
            game = types.SimpleNamespace(
                fullPathTable=str(game_dir),
                tableDirName="Example",
                metaConfig={
                    "game_files": {"Example.vpx": {"rom": "vpx_rom"}},
                    "vpinfe": {"delete_nvram_on_close": True},
                },
            )

            table_play_service.delete_nvram_if_configured(game)

            self.assertFalse(vpx_nvram.exists())
            self.assertTrue(info_nvram.exists())


class PerGameFilePlayStatsTests(unittest.TestCase):
    """A folder holds several game files and the API can launch any of them, so a play
    is credited to the one that ran as well as to the table."""

    def _launch(self, config, game_file, seconds=90, played_at=1000):
        table_play_service.apply_start_count_update(config, played_at, game_file)
        table_play_service.apply_runtime_update(config, seconds, game_file)
        return config

    def test_a_launch_counts_against_the_game_and_the_game_file(self):
        config = self._launch({}, "Example (VR).vpx")

        self.assertEqual(config["User"]["StartCount"], 1)
        self.assertEqual(config["User"]["LastRun"], 1000)
        played = config["game_files"]["Example (VR).vpx"]["user"]
        self.assertEqual(played, {"last_run": "1970-01-01T00:16:40Z",
                                  "start_count": 1, "run_time_seconds": 90})

    def test_each_game_file_keeps_its_own_count(self):
        config = self._launch({}, "Example.vpx")
        self._launch(config, "Example.vpx")
        self._launch(config, "Example (VR).vpx")

        entries = config["game_files"]
        self.assertEqual(entries["Example.vpx"]["user"]["start_count"], 2)
        self.assertEqual(entries["Example (VR).vpx"]["user"]["start_count"], 1)
        self.assertEqual(config["User"]["StartCount"], 3, "the table saw all three")

    def test_the_game_total_is_not_a_rollup(self):
        """Deleting a game file must not un-play hours that were played, which is what
        a total summed from the entries would do."""
        config = self._launch({}, "Example.vpx")
        self._launch(config, "Gone.vpx")
        del config["game_files"]["Gone.vpx"]

        self.assertEqual(config["User"]["StartCount"], 2)
        self.assertEqual(config["User"]["RunTime"], 4, "minutes, as the spec key always was")

    def test_a_hidden_game_file_still_accrues_and_stays_hidden(self):
        """Hiding is presentation: the API can still launch it, and it is still played."""
        config = {"game_files": {"Base.vpx": {"hidden": True, "rom": "afm_113b"}}}
        self._launch(config, "Base.vpx")

        entry = config["game_files"]["Base.vpx"]
        self.assertEqual(entry["user"]["start_count"], 1)
        self.assertTrue(entry["hidden"])
        self.assertEqual(entry["rom"], "afm_113b", "the parse must survive a play")

    def test_a_launch_with_no_game_file_named_still_counts_for_the_game(self):
        """Nothing outside the launch path knows which file ran."""
        config = self._launch({}, "")

        self.assertEqual(config["User"]["StartCount"], 1)
        self.assertNotIn("game_files", config)


if __name__ == "__main__":
    unittest.main()
