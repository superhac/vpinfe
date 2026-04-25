import configparser
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from common.external_service import find_named_path, import_module_from_path
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


if __name__ == "__main__":
    unittest.main()
