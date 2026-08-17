from __future__ import annotations

import importlib
import unittest
from pathlib import Path
from unittest import mock

from common.games.archive_service import resolve_game_dir
from common.games.game_index_service import (
    add_collection_membership,
    find_by_path,
    search_rows,
    set_missing_rows,
    set_rows,
    update_row_by_path,
)
from common.games.game_service import normalize_game_rating, replace_table
from common.games.media_service import (
    get_media_cache,
    invalidate_media_cache,
    media_url,
    set_media_cache,
    update_cache_entry,
)
from managerui.config_fields import is_checkbox_field, sort_input_mapping_keys
from managerui.filters import ALL_VALUE, apply_game_filters, build_game_filter_options
from managerui.pages.collections import paging_labels
from managerui.services import theme_service
from managerui.services.collection_admin import get_filter_options, search_games
from managerui.services.game_catalog import build_mobile_game_rows
from managerui.services.system_service import format_bytes, metric_tone


class ManagerUiServiceTests(unittest.TestCase):
    def test_game_filter_options_and_apply_filters(self):
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

        options = build_game_filter_options(rows)
        self.assertEqual(options["manufacturers"], [ALL_VALUE, "Bally", "Williams"])
        self.assertEqual(options["themes"], [ALL_VALUE, "Fantasy", "Sci-Fi"])

        filtered = apply_game_filters(
            rows,
            {"search": "mars", "manufacturer": "Bally", "year": ALL_VALUE},
            search_fields=("name", "filename"),
        )
        self.assertEqual([row["name"] for row in filtered], ["Attack From Mars"])

    def test_normalize_game_rating(self):
        cases = [(None, 0), ("bad", 0), ("2.8", 2), (8, 5), (-1, 0)]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_game_rating(raw), expected)

    def test_replace_table_replaces_vpx_and_renames_directb2s(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir) / "Example"
            game_dir.mkdir()
            old_vpx = game_dir / "Old Table.vpx"
            old_b2s = game_dir / "Old Table.directb2s"
            old_vpx.write_bytes(b"old vpx")
            old_b2s.write_bytes(b"old b2s")

            with mock.patch("common.games.game_service.refresh_game"):
                result = replace_table(
                    game_dir,
                    "New Table.vpx",
                    b"new vpx",
                    "vpx",
                    "Old Table.vpx",
                )

            self.assertFalse(old_vpx.exists())
            self.assertEqual((game_dir / "New Table.vpx").read_bytes(), b"new vpx")
            self.assertFalse(old_b2s.exists())
            self.assertEqual((game_dir / "New Table.directb2s").read_bytes(), b"old b2s")
            self.assertEqual(result["filename"], "New Table.vpx")
            self.assertEqual(result["directb2s_filename"], "New Table.directb2s")

    def test_replace_table_directb2s_uses_existing_name_or_vpx_stem(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir) / "Example"
            game_dir.mkdir()
            (game_dir / "Example.vpx").write_bytes(b"vpx")
            existing_b2s = game_dir / "Custom Backglass.directb2s"
            existing_b2s.write_bytes(b"old b2s")

            with mock.patch("common.games.game_service.refresh_game"):
                result = replace_table(
                    game_dir,
                    "Uploaded.directb2s",
                    b"new b2s",
                    "directb2s",
                    "Example.vpx",
                )

            self.assertEqual(existing_b2s.read_bytes(), b"new b2s")
            self.assertFalse((game_dir / "Uploaded.directb2s").exists())
            self.assertEqual(result["filename"], "Custom Backglass.directb2s")

        with TemporaryDirectory() as temp_dir:
            game_dir = Path(temp_dir) / "Example"
            game_dir.mkdir()
            (game_dir / "Example.vpx").write_bytes(b"vpx")

            with mock.patch("common.games.game_service.refresh_game"):
                result = replace_table(
                    game_dir,
                    "Uploaded.directb2s",
                    b"new b2s",
                    "directb2s",
                    "Example.vpx",
                )

            self.assertEqual((game_dir / "Example.directb2s").read_bytes(), b"new b2s")
            self.assertEqual(result["filename"], "Example.directb2s")

    def test_resolve_game_dir_rejects_path_traversal(self):
        with self.subTest("valid table"):
            from pathlib import Path
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as temp_dir:
                games_root = Path(temp_dir) / "games"
                good_game = games_root / "Good Table"
                good_game.mkdir(parents=True)

                self.assertEqual(resolve_game_dir("Good Table", str(games_root)),
                                 good_game.resolve())

                with self.assertRaises(ValueError):
                    resolve_game_dir("../outside", str(games_root))

    def test_mobile_game_rows_format_display_names(self):
        rows = build_mobile_game_rows([
            {"name": "Centaur", "manufacturer": "Bally", "year": "1981",
             "game_dir_name": "Centaur"},
            {"name": "No Frills", "manufacturer": "", "year": "", "game_dir_name": "No Frills"},
        ])

        self.assertEqual(rows, [
            {"display_name": "Centaur (Bally 1981)", "game_dir_name": "Centaur", "vpinfe_id": ""},
            {"display_name": "No Frills", "game_dir_name": "No Frills", "vpinfe_id": ""},
        ])

    def test_config_field_metadata(self):
        self.assertTrue(is_checkbox_field("Settings", "muteaudio"))
        self.assertFalse(is_checkbox_field("Settings", "gamerootdir"))
        # previous sorts ahead of back because the registry lists it first; an action
        # the registry does not know keeps its place at the end. "keyleft" used to
        # stand in for previous here, and passed only because the order list was
        # still spelled the pre-rename way.
        self.assertEqual(sort_input_mapping_keys(["keyback", "keyprevious", "keycustom"], "key"), [
            "keyprevious",
            "keyback",
            "keycustom",
        ])

    def test_collections_service_filter_options_and_search(self):
        rows = [
            {"vpinfe_id": "a", "name": "Attack From Mars", "manufacturer": "Bally",
             "year": "1995", "type": "SS", "themes": ["Sci-Fi"]},
            {"vpinfe_id": "m", "name": "Medieval Madness", "manufacturer": "Williams",
             "year": "1997", "type": "SS", "themes": ["Fantasy"]},
        ]
        options = get_filter_options(rows)
        self.assertEqual(options["letters"], ["All", "A", "M"])
        self.assertEqual(options["manufacturers"], ["All", "Bally", "Williams"])
        self.assertEqual([row["vpinfe_id"] for row in search_games("mars", rows)], ["a"])

    def test_collections_filter_options_default_to_vpsdb(self):
        vpsdb_rows = [
            {"id": "a", "name": "Attack From Mars", "manufacturer": "Bally",
             "year": 1995, "type": "SS", "theme": ["Sci-Fi"]},
            {"id": "m", "name": "Medieval Madness", "manufacturer": "Williams",
             "year": 1997, "type": "SS", "theme": ["Fantasy"]},
        ]

        with mock.patch("common.games.game_service.load_vpsdb", return_value=vpsdb_rows), \
                mock.patch("common.games.game_service.ensure_vpsdb_downloaded") \
                        as ensure_vpsdb, \
                mock.patch("common.games.game_index_service.scan_rows") as scan_rows:
            options = get_filter_options()

        self.assertEqual(options["letters"], ["All", "A", "M"])
        self.assertEqual(options["themes"], ["All", "Fantasy", "Sci-Fi"])
        self.assertEqual(options["manufacturers"], ["All", "Bally", "Williams"])
        self.assertEqual(options["years"], ["All", "1995", "1997"])
        ensure_vpsdb.assert_not_called()
        scan_rows.assert_not_called()

    def test_common_collections_metadata_includes_image_urls(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest import mock

        import common.games.collections_service as common_collections

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
        self.assertEqual(metadata[0]["game_count"], 2)
        self.assertTrue(metadata[1]["is_filter"])
        self.assertEqual(metadata[1]["image_url"], "")

    def test_media_service_url_and_cache_update(self):
        invalidate_media_cache()
        self.assertEqual(media_url("media_games", "A B", "medias", "bg.png"),
                         "/media_games/A%20B/medias/bg.png")
        set_media_cache([{"game_dir_name": "A B", "media": {}, "thumbs": {},
                          "thumb_errors": {"bg": True}}])
        update_cache_entry("A B", "bg", "/media_games/A%20B/medias/bg.png",
                           "/media_thumbs/A%20B/bg.png")
        row = get_media_cache()[0]
        self.assertEqual(row["media"]["bg"], "/media_games/A%20B/medias/bg.png")
        self.assertTrue(row["has_bg"])
        self.assertNotIn("bg", row["thumb_errors"])

    def test_system_service_formatters(self):
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(metric_tone(90, warn=70, critical=85), "critical")

    def test_managerui_import_does_not_import_remote_keyboard_backend(self):
        importlib.import_module("managerui.managerui")

    def test_keysimulator_pynput_backend_includes_printable_keys(self):
        import sys
        import types

        class FakeKey:
            enter = "enter"
            esc = "esc"
            backspace = "backspace"
            tab = "tab"
            space = "space"
            f1 = "f1"
            f2 = "f2"
            f3 = "f3"
            f4 = "f4"
            f5 = "f5"
            f6 = "f6"
            f7 = "f7"
            f8 = "f8"
            f9 = "f9"
            f10 = "f10"
            f11 = "f11"
            f12 = "f12"
            home = "home"
            page_up = "page_up"
            delete = "delete"
            end = "end"
            page_down = "page_down"
            right = "right"
            left = "left"
            down = "down"
            up = "up"
            ctrl_l = "ctrl_l"
            shift_l = "shift_l"
            alt_l = "alt_l"
            cmd = "cmd"
            ctrl_r = "ctrl_r"
            shift_r = "shift_r"
            alt_r = "alt_r"
            print_screen = "print_screen"
            pause = "pause"
            insert = "insert"

        fake_keyboard = types.SimpleNamespace(Key=FakeKey, Controller=object)
        fake_pynput = types.SimpleNamespace(keyboard=fake_keyboard)
        original = sys.modules.pop("managerui.key_simulator", None)
        try:
            with mock.patch.dict(sys.modules, {"pynput": fake_pynput,
                                           "pynput.keyboard": fake_keyboard}):
                from managerui.key_simulator import KeySimulator

                # Built inside the stub: the map is a call rather than a class attribute,
                # so that a machine with no input backend can import the module at all.
                mapping = KeySimulator.key_id_to_pynput()
        finally:
            sys.modules.pop("managerui.key_simulator", None)
            if original is not None:
                sys.modules["managerui.key_simulator"] = original

        for key_id in ("0", "1", "5", "9", "a", "z", "-", "=", "[", "]", "\\",
                       ";", "'", "`", ",", ".", "/"):
            with self.subTest(key_id=key_id):
                self.assertEqual(mapping[key_id], key_id)

    def test_game_index_lookup_update_and_search(self):
        rows = set_rows([
            {"vpinfe_id": "afm", "name": "Attack From Mars", "filename": "afm.vpx",
             "game_dir": "/tmp/tables/Attack", "collections": []},
            {"vpinfe_id": "mm", "name": "Medieval Madness", "filename": "mm.vpx",
             "game_dir": "/tmp/tables/MM", "collections": []},
        ])
        set_missing_rows([{"folder": "Loose"}])

        self.assertEqual(find_by_path(Path("/tmp/tables/Attack"))["vpinfe_id"], "afm")
        self.assertEqual(search_rows("medieval")[0]["vpinfe_id"], "mm")
        update_row_by_path(Path("/tmp/tables/MM"), {"rating": 5})
        self.assertEqual(rows[1]["rating"], 5)
        add_collection_membership("afm", "Favorites")
        self.assertEqual(rows[0]["collections"], ["Favorites"])

    def test_theme_service_reads_the_schema_and_saves_values_outside_the_theme(self):
        """Values used to go into the theme's own file, which an update deletes."""
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from common import theme_options

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

            user_dir = themes_dir / "theme_user_options"
            with mock.patch.object(theme_service, "THEMES_DIR", themes_dir), \
                    mock.patch.object(theme_options, "USER_OPTIONS_DIR", user_dir):
                schema = theme_service.load_theme_option_schema("Example")
                values = theme_service.get_theme_option_values("Example")
                saved_path = theme_service.save_theme_option_values(
                    "Example",
                    {
                        "audio.enabled": False,
                        "layout.mode": "compact",
                    },
                )
                reread = theme_service.get_theme_option_values("Example")

            self.assertEqual(schema["title"], "Example Options")
            # A value still in the package is a pre-3.0 leftover and is read until the
            # migration lifts it out.
            self.assertEqual(values["audio.enabled"], True)
            self.assertEqual(values["layout.mode"], "wide")

            self.assertEqual(saved_path, user_dir / "Example.json")
            self.assertEqual(json.loads(saved_path.read_text(encoding="utf-8"))["values"],
                             {"audio.enabled": False, "layout.mode": "compact"})
            self.assertEqual(reread["audio.enabled"], False)
            self.assertEqual(reread["layout.mode"], "compact")

            untouched = json.loads((theme_dir / "theme.json").read_text(encoding="utf-8"))
            self.assertEqual({o["key"]: o["value"] for o in untouched["options"]},
                             {"audio.enabled": True, "layout.mode": "wide"},
                             "the author's file must not be written to")


class PageStylesheetTests(unittest.TestCase):
    """Every stylesheet a page asks for has to be on disk.

    load_page_style only writes a <link> tag, so a name that does not exist fails as a
    404 the browser never mentions and the page quietly renders unstyled. The games
    page did exactly that: it was renamed to ask for games.css while the file was
    still called tables.css.
    """

    def test_every_requested_stylesheet_exists(self) -> None:
        import ast

        managerui = Path(__file__).resolve().parent.parent.parent / "managerui"
        static = managerui / "static"

        missing = []
        for path in sorted(managerui.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "load_page_style" and node.args):
                    continue
                arg = node.args[0]
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                    continue  # computed at runtime; nothing to check statically
                if not (static / arg.value).is_file():
                    missing.append(f"{path.name}:{node.lineno} asks for {arg.value!r}")

        self.assertEqual(missing, [], "\n".join(missing))


if __name__ == "__main__":
    unittest.main()


class PagingOptionLabelTests(unittest.TestCase):
    """The `Page by` control warns in the option, not only in a caption beside it.

    The decision was "visible, disabled, with the reason". Disabling it would stop a user
    recording a preference that starts mattering the moment they re-sort the collection,
    so the warning rides on the option instead - which is still visible when the control
    is closed, unlike a caption.
    """

    def test_a_sort_with_groups_reads_plainly(self) -> None:
        for order_by in ("title", "year", "rating"):
            with self.subTest(order_by=order_by):
                self.assertEqual(paging_labels(order_by)["sort"], "By the sort")

    def test_a_sort_without_groups_says_it_will_step(self) -> None:
        """last_played, added and manual give every table its own value or no order."""
        for order_by in ("last_played", "added", "manual"):
            with self.subTest(order_by=order_by):
                self.assertIn("no groups", paging_labels(order_by)["sort"])

    def test_the_other_options_never_move(self) -> None:
        """Only the option that asks for groups can be wrong about this sort."""
        for order_by in ("title", "last_played"):
            labels = paging_labels(order_by)
            self.assertEqual(labels[""], "Follow my setting")
            self.assertEqual(labels["count"], "By a fixed number")

    def test_no_sort_at_all_is_the_default_sort(self) -> None:
        self.assertEqual(paging_labels("")["sort"], paging_labels("title")["sort"])
