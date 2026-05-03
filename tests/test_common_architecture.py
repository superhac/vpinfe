import configparser
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from common.config_access import DisplayConfig, MediaConfig, NetworkConfig, SettingsConfig, VPinPlayConfig
from common.external_service import find_named_path, import_module_from_path
from common.jobs import JobReporter
from common.media_paths import apply_media_paths, media_filename_map, table_media_payload
from common.metadata_service import claim_media_for_table
from common.standalonescripts import StandaloneScripts
from common.table_metadata import table_themes, table_title, table_type
from common.tableparser import TableParser
from common.theme_installer import ThemeInstallStore
from common.vpsdb_cache import VPSDatabaseCache


class _FakeIni:
    def __init__(self) -> None:
        self.config = configparser.ConfigParser()
        self.saved = False

    def save(self) -> None:
        self.saved = True


class TestCommonArchitecture(unittest.TestCase):
    def test_external_service_helpers_find_and_import_module(self) -> None:
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

    def test_table_parser_accessors_return_copies(self) -> None:
        parser = TableParser.__new__(TableParser)
        parser.tables = [SimpleNamespace(name="one")]
        parser.missing_tables = [{"folder": "missing"}]

        tables = parser.getAllTables()
        missing = parser.getMissingTables()
        tables.clear()
        missing[0]["folder"] = "changed"

        self.assertEqual(len(parser.tables), 1)
        self.assertEqual(parser.missing_tables[0]["folder"], "missing")

    def test_metadata_display_helpers_handle_legacy_fields(self) -> None:
        table = SimpleNamespace(
            tableDirName="Fallback",
            metaConfig={
                "VPSdb": {
                    "name": "Legacy Name",
                    "theme": "['Music', 'Movies']",
                    "type": "SS",
                }
            },
        )

        self.assertEqual(table_title(table), "Legacy Name")
        self.assertEqual(table_themes(table), ["Music", "Movies"])
        self.assertEqual(table_type(table), "SS")

    def test_standalone_scripts_can_be_constructed_without_running_network_work(self) -> None:
        with mock.patch("common.standalonescripts.StandaloneScripts.apply_patches") as apply_patches:
            scripts = StandaloneScripts([], auto_run=False)

        self.assertIsNone(scripts.hashes)
        apply_patches.assert_not_called()

    def test_typed_config_accessors_normalize_common_sections(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_dict({
            "Settings": {
                "tablerootdir": "/tables",
                "theme": "",
                "autoupdatemediaonstartup": "yes",
                "cabmode": "true",
            },
            "Media": {
                "tabletype": "FSS",
                "tableresolution": "4K",
                "tablevideoresolution": "1080p",
            },
            "Network": {
                "wsport": "9002",
                "themeassetsport": "bad",
            },
            "Displays": {
                "tablescreenid": "2",
                "tablerotation": "270",
            },
            "vpinplay": {
                "apiendpoint": " http://example.test ",
                "synconexit": "1",
            },
        })

        self.assertEqual(SettingsConfig.from_config(parser).table_root_dir, "/tables")
        self.assertEqual(SettingsConfig.from_config(parser).theme, "Revolution")
        self.assertTrue(SettingsConfig.from_config(parser).auto_update_media_on_startup)
        self.assertEqual(MediaConfig.from_config(parser).table_type, "fss")
        self.assertEqual(NetworkConfig.from_config(parser).ws_port, 9002)
        self.assertEqual(NetworkConfig.from_config(parser).theme_assets_port, 8000)
        self.assertEqual(DisplayConfig.from_config(parser).table_screen_id, 2)
        self.assertEqual(DisplayConfig.from_config(parser).window_screen_id("tablescreenid"), "2")
        self.assertTrue(DisplayConfig.from_config(parser).cab_mode)
        self.assertEqual(VPinPlayConfig.from_config(parser).api_endpoint, "http://example.test")
        self.assertTrue(VPinPlayConfig.from_config(parser).sync_on_exit)

    def test_display_config_preserves_empty_table_screen_for_window_discovery(self) -> None:
        parser = configparser.ConfigParser()
        parser.read_dict({"Displays": {"tablescreenid": ""}})

        display = DisplayConfig.from_config(parser)

        self.assertEqual(display.table_screen_id, 0)
        self.assertEqual(display.window_screen_id("tablescreenid"), "")

    def test_settings_config_defaults_splashscreen_off(self) -> None:
        parser = configparser.ConfigParser()

        self.assertFalse(SettingsConfig.from_config(parser).splashscreen)

    def test_media_paths_apply_and_payload_use_shared_specs(self) -> None:
        table = SimpleNamespace(fullPathTable="/tmp/Table", TableImagePath=None, BGImagePath=None)

        apply_media_paths(
            table,
            table_contents={"bg.png"},
            medias_contents={"fss.png"},
            table_type="fss",
        )

        self.assertEqual(table.BGImagePath, "/tmp/Table/bg.png")
        self.assertEqual(table.TableImagePath, "/tmp/Table/medias/fss.png")
        self.assertEqual(media_filename_map("fss")["fss"], "fss.png")
        self.assertEqual(table_media_payload(table)["TableImagePath"], "/tmp/Table/medias/fss.png")

    def test_claim_media_for_table_uses_dynamic_table_type_keys(self) -> None:
        with TemporaryDirectory() as tmp:
            table_dir = Path(tmp) / "Example"
            medias_dir = table_dir / "medias"
            medias_dir.mkdir(parents=True)
            (medias_dir / "fss.png").write_bytes(b"image")
            info_path = table_dir / "Example.info"
            info_path.write_text(json.dumps({"Medias": {}}), encoding="utf-8")
            table = SimpleNamespace(fullPathTable=str(table_dir), tableDirName="Example")

            claimed = claim_media_for_table(table, "fss")
            saved = json.loads(info_path.read_text(encoding="utf-8"))

            self.assertEqual(claimed, 1)
            self.assertEqual(saved["Medias"]["fss"]["Path"], "fss.png")

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


if __name__ == "__main__":
    unittest.main()
