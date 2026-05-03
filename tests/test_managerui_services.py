from __future__ import annotations

import unittest
import importlib
from unittest import mock

from managerui.config_fields import is_checkbox_field, sort_input_mapping_keys
from managerui.filters import ALL_VALUE, apply_table_filters, build_table_filter_options
from managerui.services.archive_service import resolve_table_dir
from managerui.services.collections_service import get_filter_options, search_tables
from managerui.services.media_service import media_url, update_cache_entry, set_media_cache, get_media_cache, invalidate_media_cache
from managerui.services.system_service import format_bytes, metric_tone
from managerui.services.table_catalog import build_mobile_table_rows
from managerui.services import theme_service
from managerui.services.table_index_service import (
    add_collection_membership,
    find_by_path,
    search_rows,
    set_missing_rows,
    set_rows,
    update_row_by_path,
)
from managerui.services.table_service import normalize_table_rating, replace_table_file


class ManagerUiServiceTests(unittest.TestCase):
    def test_table_filter_options_and_apply_filters(self):
        rows = [
            {
                "name": "Attack From Mars",
                "filename": "afm.vpx",
                "manufacturer": "Bally",
                "year": "1995",
                "themes": ["Sci-Fi"],
                "type": "SS",
            },
            {
                "name": "Medieval Madness",
                "filename": "mm.vpx",
                "manufacturer": "Williams",
                "year": "1997",
                "themes": ["Fantasy"],
                "type": "SS",
            },
        ]

        options = build_table_filter_options(rows)
        self.assertEqual(options["manufacturers"], [ALL_VALUE, "Bally", "Williams"])
        self.assertEqual(options["themes"], [ALL_VALUE, "Fantasy", "Sci-Fi"])

        filtered = apply_table_filters(
            rows,
            {"search": "mars", "manufacturer": "Bally", "year": ALL_VALUE},
            search_fields=("name", "filename"),
        )
        self.assertEqual([row["name"] for row in filtered], ["Attack From Mars"])

    def test_normalize_table_rating(self):
        cases = [(None, 0), ("bad", 0), ("2.8", 2), (8, 5), (-1, 0)]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_table_rating(raw), expected)

    def test_replace_table_file_replaces_vpx_and_renames_directb2s(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as temp_dir:
            table_dir = Path(temp_dir) / "Example"
            table_dir.mkdir()
            old_vpx = table_dir / "Old Table.vpx"
            old_b2s = table_dir / "Old Table.directb2s"
            old_vpx.write_bytes(b"old vpx")
            old_b2s.write_bytes(b"old b2s")

            with mock.patch("managerui.services.table_service.refresh_table"):
                result = replace_table_file(
                    str(table_dir),
                    "New Table.vpx",
                    b"new vpx",
                    "vpx",
                    "Old Table.vpx",
                )

            self.assertFalse(old_vpx.exists())
            self.assertEqual((table_dir / "New Table.vpx").read_bytes(), b"new vpx")
            self.assertFalse(old_b2s.exists())
            self.assertEqual((table_dir / "New Table.directb2s").read_bytes(), b"old b2s")
            self.assertEqual(result["filename"], "New Table.vpx")
            self.assertEqual(result["directb2s_filename"], "New Table.directb2s")

    def test_replace_table_file_directb2s_uses_existing_name_or_vpx_stem(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as temp_dir:
            table_dir = Path(temp_dir) / "Example"
            table_dir.mkdir()
            (table_dir / "Example.vpx").write_bytes(b"vpx")
            existing_b2s = table_dir / "Custom Backglass.directb2s"
            existing_b2s.write_bytes(b"old b2s")

            with mock.patch("managerui.services.table_service.refresh_table"):
                result = replace_table_file(
                    str(table_dir),
                    "Uploaded.directb2s",
                    b"new b2s",
                    "directb2s",
                    "Example.vpx",
                )

            self.assertEqual(existing_b2s.read_bytes(), b"new b2s")
            self.assertFalse((table_dir / "Uploaded.directb2s").exists())
            self.assertEqual(result["filename"], "Custom Backglass.directb2s")

        with TemporaryDirectory() as temp_dir:
            table_dir = Path(temp_dir) / "Example"
            table_dir.mkdir()
            (table_dir / "Example.vpx").write_bytes(b"vpx")

            with mock.patch("managerui.services.table_service.refresh_table"):
                result = replace_table_file(
                    str(table_dir),
                    "Uploaded.directb2s",
                    b"new b2s",
                    "directb2s",
                    "Example.vpx",
                )

            self.assertEqual((table_dir / "Example.directb2s").read_bytes(), b"new b2s")
            self.assertEqual(result["filename"], "Example.directb2s")

    def test_resolve_table_dir_rejects_path_traversal(self):
        with self.subTest("valid table"):
            from tempfile import TemporaryDirectory
            from pathlib import Path

            with TemporaryDirectory() as temp_dir:
                tables_root = Path(temp_dir) / "tables"
                good_table = tables_root / "Good Table"
                good_table.mkdir(parents=True)

                self.assertEqual(resolve_table_dir("Good Table", str(tables_root)), good_table.resolve())

                with self.assertRaises(ValueError):
                    resolve_table_dir("../outside", str(tables_root))

    def test_mobile_table_rows_format_display_names(self):
        rows = build_mobile_table_rows([
            {"name": "Centaur", "manufacturer": "Bally", "year": "1981", "table_dir_name": "Centaur"},
            {"name": "No Frills", "manufacturer": "", "year": "", "table_dir_name": "No Frills"},
        ])

        self.assertEqual(rows, [
            {"display_name": "Centaur (Bally 1981)", "table_dir_name": "Centaur"},
            {"display_name": "No Frills", "table_dir_name": "No Frills"},
        ])

    def test_config_field_metadata(self):
        self.assertTrue(is_checkbox_field("Settings", "muteaudio"))
        self.assertFalse(is_checkbox_field("Settings", "tablerootdir"))
        self.assertEqual(sort_input_mapping_keys(["keyback", "keyleft", "keycustom"], "key"), [
            "keyleft",
            "keyback",
            "keycustom",
        ])

    def test_collections_service_filter_options_and_search(self):
        rows = [
            {"id": "a", "name": "Attack From Mars", "manufacturer": "Bally", "year": "1995", "type": "SS", "themes": ["Sci-Fi"]},
            {"id": "m", "name": "Medieval Madness", "manufacturer": "Williams", "year": "1997", "type": "SS", "themes": ["Fantasy"]},
        ]
        options = get_filter_options(rows)
        self.assertEqual(options["letters"], ["All", "A", "M"])
        self.assertEqual(options["manufacturers"], ["All", "Bally", "Williams"])
        self.assertEqual([row["id"] for row in search_tables("mars", rows)], ["a"])

    def test_common_collections_metadata_includes_image_urls(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest import mock
        import common.collections_service as common_collections

        with TemporaryDirectory() as temp_dir:
            collections_ini = Path(temp_dir) / "collections.ini"
            collections_ini.write_text(
                "[Favorites]\n"
                "type = vpsid\n"
                "vpsids = a,b\n"
                "image = favorites.png\n"
                "\n"
                "[Bally]\n"
                "type = filter\n"
                "manufacturer = Bally\n",
                encoding="utf-8",
            )
            with mock.patch.object(common_collections, "COLLECTIONS_PATH", collections_ini):
                metadata = common_collections.get_collections_metadata()

        self.assertEqual(metadata[0]["name"], "Favorites")
        self.assertEqual(metadata[0]["image_url"], "/collection_icons/favorites.png")
        self.assertEqual(metadata[0]["table_count"], 2)
        self.assertTrue(metadata[1]["is_filter"])
        self.assertEqual(metadata[1]["image_url"], "")

    def test_media_service_url_and_cache_update(self):
        invalidate_media_cache()
        self.assertEqual(media_url("media_tables", "A B", "medias", "bg.png"), "/media_tables/A%20B/medias/bg.png")
        set_media_cache([{"table_dir": "A B", "media": {}, "thumbs": {}, "thumb_errors": {"bg": True}}])
        update_cache_entry("A B", "bg", "/media_tables/A%20B/medias/bg.png", "/media_thumbs/A%20B/bg.png")
        row = get_media_cache()[0]
        self.assertEqual(row["media"]["bg"], "/media_tables/A%20B/medias/bg.png")
        self.assertTrue(row["has_bg"])
        self.assertNotIn("bg", row["thumb_errors"])

    def test_system_service_formatters(self):
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(metric_tone(90, warn=70, critical=85), "critical")

    def test_managerui_import_does_not_import_remote_keyboard_backend(self):
        importlib.import_module("managerui.managerui")

    def test_table_index_lookup_update_and_search(self):
        rows = set_rows([
            {"id": "afm", "name": "Attack From Mars", "filename": "afm.vpx", "table_path": "/tmp/tables/Attack", "collections": []},
            {"id": "mm", "name": "Medieval Madness", "filename": "mm.vpx", "table_path": "/tmp/tables/MM", "collections": []},
        ])
        set_missing_rows([{"folder": "Loose"}])

        self.assertEqual(find_by_path("/tmp/tables/Attack")["id"], "afm")
        self.assertEqual(search_rows("medieval")[0]["id"], "mm")
        update_row_by_path("/tmp/tables/MM", {"rating": 5})
        self.assertEqual(rows[1]["rating"], 5)
        add_collection_membership("afm", "Favorites")
        self.assertEqual(rows[0]["collections"], ["Favorites"])

    def test_theme_service_reads_schema_and_writes_values_into_theme_json(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json

        with TemporaryDirectory() as temp_dir:
            themes_dir = Path(temp_dir)
            theme_dir = themes_dir / "Example"
            theme_dir.mkdir()
            (theme_dir / "theme.json").write_text(
                json.dumps(
                    {
                        "title": "Example Options",
                        "options": [
                            {
                                "key": "audio.enabled",
                                "name": "Audio Enabled",
                                "description": "Turn table audio on or off.",
                                "type": "boolean",
                                "value": True,
                            },
                            {
                                "key": "layout.mode",
                                "name": "Layout Mode",
                                "type": "select",
                                "value": "wide",
                                "options": ["compact", "wide"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(theme_service, "THEMES_DIR", themes_dir):
                schema = theme_service.load_theme_option_schema("Example")
                values = theme_service.get_theme_option_values("Example")
                saved_path = theme_service.save_theme_option_values(
                    "Example",
                    {
                        "audio.enabled": False,
                        "layout.mode": "compact",
                    },
                )

            self.assertEqual(schema["title"], "Example Options")
            self.assertEqual(values["audio.enabled"], True)
            self.assertEqual(values["layout.mode"], "wide")
            self.assertEqual(saved_path, theme_dir / "theme.json")

            saved = json.loads(saved_path.read_text(encoding="utf-8"))
            options_by_key = {item["key"]: item for item in saved["options"]}
            self.assertEqual(options_by_key["audio.enabled"]["value"], False)
            self.assertEqual(options_by_key["layout.mode"]["value"], "compact")


if __name__ == "__main__":
    unittest.main()
