import ast
import configparser
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from common.config_access import (
    DisplayConfig,
    MediaConfig,
    NetworkConfig,
    SettingsConfig,
    VPinPlayConfig,
)
from common.games.game_metadata import game_themes, game_title, game_type
from common.games.game_repository import game_to_row
from common.games.game_parser import GameParser
from common.games.standalone_scripts import StandaloneScripts
from common.jobs import JobReporter
from common.media_specs import apply_media_specs, game_media_payload, media_filename_map
from common.online.theme_installer import ThemeInstallStore
from common.online.vpsdb_cache import VPSDatabaseCache
from common.third_party import find_named_path, import_module_from_path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _tableparser_target(node) -> str | None:
    """The variable name, if this statement is `x = GameParser(...)`."""
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    if not isinstance(node.value, ast.Call):
        return None
    func = node.value.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name != "GameParser":
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _is_reload_of(node, name: str) -> bool:
    """Whether this statement is `name.loadGames(...)`."""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "loadGames"
        and isinstance(func.value, ast.Name)
        and func.value.id == name
    )


class _FakeIni:
    def __init__(self) -> None:
        self.config = configparser.ConfigParser()
        self.saved = False

    def save(self) -> None:
        self.saved = True


class TestCommonArchitecture(unittest.TestCase):
    def test_third_party_helpers_find_and_import_module(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "nested"
            nested.mkdir()
            module_path = nested / "service_wrapper.py"
            module_path.write_text(
                "class DemoController:\n"
                "    value = 42\n",
                encoding="utf-8",
            )

            self.assertEqual(find_named_path(root, ("service_wrapper.py",)), module_path)
            module = import_module_from_path(module_path, module_prefix="_test")

            self.assertEqual(module.DemoController.value, 42)

    def test_vps_cache_loads_local_list_without_network_version(self) -> None:
        with TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            (config_dir / "vpsdb.json").write_text(
                json.dumps([{"id": "vps-1", "name": "Example"}]),
                encoding="utf-8",
            )
            cache = VPSDatabaseCache(
                config_dir,
                _FakeIni(),
                db_url="https://example.invalid/db.json",
                last_update_url="https://example.invalid/last.json",
            )

            with mock.patch.object(cache, "fetch_last_update", return_value=None):
                self.assertEqual(cache.ensure_current(), [{"id": "vps-1", "name": "Example"}])

    def test_theme_install_store_detects_folders_and_versions(self) -> None:
        with TemporaryDirectory() as tmp:
            themes_dir = Path(tmp)
            installed = themes_dir / "ExampleTheme"
            installed.mkdir()
            (installed / "manifest.json").write_text(
                json.dumps({"version": "1.2.3"}),
                encoding="utf-8",
            )

            store = ThemeInstallStore(str(themes_dir))

            self.assertEqual(store.installed_folder("ExampleTheme"), "ExampleTheme")
            self.assertEqual(store.installed_version("ExampleTheme"), "1.2.3")
            self.assertTrue(store.is_version_newer("1.2.4", "1.2.3"))

    def test_game_parser_accessors_return_copies(self) -> None:
        parser = GameParser.__new__(GameParser)
        parser.games = [SimpleNamespace(name="one")]
        parser.missing_games = [{"folder": "missing"}]

        games = parser.getAllGames()
        missing = parser.getMissingGames()
        games.clear()
        missing[0]["folder"] = "changed"

        self.assertEqual(len(parser.games), 1)
        self.assertEqual(parser.missing_games[0]["folder"], "missing")

    def test_metadata_display_helpers_handle_legacy_fields(self) -> None:
        game = SimpleNamespace(
            gameDirName="Fallback",
            metaConfig={
                "VPSdb": {
                    "name": "Legacy Name",
                    "theme": "['Music', 'Movies']",
                    "type": "SS",
                }
            },
        )

        self.assertEqual(game_title(game), "Legacy Name")
        self.assertEqual(game_themes(game), ["Music", "Movies"])
        self.assertEqual(game_type(game), "SS")

    def test_standalone_scripts_can_be_constructed_without_running_network_work(self) -> None:
        with mock.patch("common.games.standalone_scripts.StandaloneScripts.apply_patches") as apply_patches:
            scripts = StandaloneScripts([], auto_run=False)

        self.assertIsNone(scripts.hashes)
        apply_patches.assert_not_called()

    def test_typed_config_accessors_normalize_common_sections(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_dict({
            "Settings": {
                "gamerootdir": "/games",
                "vpxinipath": "/home/player/.vpinball/VPinballX.ini",
                "vpxlogdeleteonstart": "yes",
                "theme": "",
                "autoupdatemediaonstartup": "yes",
                "cabmode": "true",
            },
            "Media": {
                "playfieldvariant": "FSS",
                "playfieldresolution": "4K",
                "playfieldvideoresolution": "1080p",
                "playfieldmediapriority": "image",
                "bgmediapriority": "mp4",
                "dmdmediapriority": "invalid",
                "realdmdmediapriority": "realdmd.png",
            },
            "Network": {
                "wsport": "9002",
                "themeassetsport": "bad",
            },
            "Displays": {
                "playfieldscreenid": "2",
                "playfieldrotation": "270",
            },
            "vpinplay": {
                "apiendpoint": " http://example.test ",
                "synconexit": "1",
            },
        })

        self.assertEqual(SettingsConfig.from_config(parser).game_root_dir, "/games")
        self.assertEqual(SettingsConfig.from_config(parser).vpx_ini_path, "/home/player/.vpinball/VPinballX.ini")
        self.assertEqual(SettingsConfig.from_config(parser).theme, "Revolution")
        self.assertTrue(SettingsConfig.from_config(parser).auto_update_media_on_startup)
        self.assertTrue(SettingsConfig.from_config(parser).vpx_log_delete_on_start)
        self.assertFalse(SettingsConfig.from_config(parser).disable_default_chrome_options)
        media_config = MediaConfig.from_config(parser)
        self.assertEqual(media_config.playfield_variant, "fss")
        self.assertEqual(media_config.playfield_media_priority, "image")
        self.assertEqual(media_config.bg_media_priority, "video")
        self.assertEqual(media_config.dmd_media_priority, "video")
        self.assertEqual(media_config.realdmd_media_priority, "standard")
        self.assertEqual(
            media_config.priority_payload(),
            {"playfield": "image", "bg": "video", "dmd": "video", "real_dmd": "standard"},
        )
        self.assertEqual(NetworkConfig.from_config(parser).ws_port, 9002)
        self.assertEqual(NetworkConfig.from_config(parser).theme_assets_port, 8000)
        self.assertEqual(DisplayConfig.from_config(parser).playfield_screen_id, 2)
        self.assertEqual(
            DisplayConfig.from_config(parser).window_screen_id("playfieldscreenid"), "2")
        self.assertTrue(DisplayConfig.from_config(parser).cab_mode)
        self.assertEqual(VPinPlayConfig.from_config(parser).api_endpoint, "http://example.test")
        self.assertTrue(VPinPlayConfig.from_config(parser).sync_on_exit)

    def test_display_config_preserves_empty_game_screen_for_window_discovery(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_dict({"Displays": {"playfieldscreenid": ""}})

        display = DisplayConfig.from_config(parser)

        self.assertEqual(display.playfield_screen_id, 0)
        self.assertEqual(display.window_screen_id("playfieldscreenid"), "")

    def test_settings_config_defaults_splashscreen_off(self) -> None:
        parser = configparser.ConfigParser()

        self.assertFalse(SettingsConfig.from_config(parser).splashscreen)

    def test_settings_config_reads_disable_default_chrome_options(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_dict({"Settings": {"disabledefaultchromeoptions": "yes"}})

        self.assertTrue(SettingsConfig.from_config(parser).disable_default_chrome_options)

    def test_media_specs_apply_and_payload_use_shared_specs(self) -> None:
        root = os.path.join(os.sep, "tmp", "Table")
        game = SimpleNamespace(fullPathGame=root, PlayfieldImagePath=None, BGImagePath=None)

        apply_media_specs(
            game,
            game_contents={"bg.png"},
            medias_contents={"fss.png"},
            playfield_variant="fss",
        )

        self.assertEqual(game.BGImagePath, os.path.join(root, "bg.png"))
        self.assertEqual(game.PlayfieldImagePath, os.path.join(root, "medias", "fss.png"))
        self.assertEqual(media_filename_map("fss")["playfield"], "fss.png")
        self.assertEqual(game_media_payload(game)["PlayfieldImagePath"],
                         os.path.join(root, "medias", "fss.png"))

    def test_job_reporter_wraps_log_and_progress_callbacks(self) -> None:
        messages: list[str] = []
        progress: list[tuple[int, int, str]] = []
        reporter = JobReporter(
            logger=mock.Mock(),
            log_cb=messages.append,
            progress_cb=lambda current, total, message: progress.append((current, total, message)),
        )

        reporter.log("hello")
        reporter.progress(1, 2, "half")

        self.assertEqual(messages, ["hello"])
        self.assertEqual(progress, [(1, 2, "half")])

    def test_tableparser_detects_directb2s_case_insensitively(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with_b2s = root / "With B2S (Bally 1990)"
            with_b2s.mkdir()
            (with_b2s / "With B2S (Bally 1990).vpx").write_text("")
            (with_b2s / "With B2S (Bally 1990).DirectB2S").write_text("")

            without_b2s = root / "No B2S (Bally 1991)"
            without_b2s.mkdir()
            (without_b2s / "No B2S (Bally 1991).vpx").write_text("")

            parser = GameParser(root)
            by_name = {t.gameDirName: t for t in parser.getAllGames()}

            self.assertTrue(by_name["With B2S (Bally 1990)"].b2sExists)
            self.assertFalse(by_name["No B2S (Bally 1991)"].b2sExists)

            # game_to_row mirrors the flag for the UI
            self.assertTrue(game_to_row(by_name["With B2S (Bally 1990)"])["b2s_exists"])
            self.assertFalse(game_to_row(by_name["No B2S (Bally 1991)"])["b2s_exists"])

    def test_constructing_a_gameparser_reads_each_game_once(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("A Table (Bally 1990)", "B Table (Bally 1991)"):
                folder = root / name
                folder.mkdir()
                (folder / f"{name}.vpx").write_text("")

            real_build = GameParser._build_game
            calls = []

            def counting_build(self, game_dir):
                calls.append(game_dir)
                return real_build(self, game_dir)

            with mock.patch.object(GameParser, "_build_game", counting_build):
                parser = GameParser(root)
                games = parser.getAllGames()

            self.assertEqual(len(games), 2)
            self.assertEqual(len(calls), 2, "the library was read more than once")

    def test_no_caller_reloads_a_freshly_constructed_tableparser(self) -> None:
        """Constructing loads, so a reload on the next line reads the whole library twice.

        Cheap to reintroduce and invisible at runtime, so it is checked in the source
        rather than left to review.
        """
        offenders = []
        for path in sorted(REPO_ROOT.rglob("*.py")):
            if any(part in {".venv", "build", "third_party"} for part in path.parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                body = getattr(node, "body", None)
                if not isinstance(body, list):
                    continue
                for first, second in zip(body, body[1:], strict=False):
                    name = _tableparser_target(first)
                    if name and _is_reload_of(second, name):
                        offenders.append(f"{path.relative_to(REPO_ROOT)}:{second.lineno}")

        self.assertEqual(offenders, [], "TableParser is constructed then reloaded at: "
                                        + ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()


class DisplayGeometryNormalizationTests(unittest.TestCase):
    """`[Displays]` is free text, and every theme compared it exactly.

    `[Media] playfieldvariant` has always lowercased on read; `[Displays]` never did, so a
    capitalized `Portrait` silently meant landscape, and a rotation of 45 reached themes
    that only test for 90 or 270.
    """

    def _displays(self, orientation, rotation):
        parser = configparser.ConfigParser()
        parser.read_dict({"Displays": {
            "playfieldorientation": str(orientation),
            "playfieldrotation": str(rotation),
        }})
        return DisplayConfig.from_config(parser)

    def test_orientation_is_matched_without_regard_to_case_or_padding(self) -> None:
        for written in ("Portrait", "PORTRAIT", "  portrait  "):
            with self.subTest(written=written):
                self.assertEqual(self._displays(written, 0).playfield_orientation, "portrait")

    def test_an_unrecognized_orientation_falls_back_to_landscape(self) -> None:
        self.assertEqual(self._displays("portait", 0).playfield_orientation, "landscape")

    def test_rotation_is_one_of_four_turns(self) -> None:
        for written, expected in ((0, 0), (90, 90), (180, 180), (270, 270),
                                  (-90, 270), (450, 90), (720, 0)):
            with self.subTest(written=written):
                self.assertEqual(self._displays("portrait", written).playfield_rotation, expected)

    def test_a_rotation_that_is_not_a_quarter_turn_falls_back_to_none(self) -> None:
        self.assertEqual(self._displays("portrait", 45).playfield_rotation, 0)
