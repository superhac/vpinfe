"""What an import proposes: which items, which action each, and what it refuses."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from common.uploads.asset_analyzer_service import analyze_path
from common.uploads.asset_import_service import (
    build_import_plan,
    build_media_slot_plan,
    execute_import_plan,
    find_vps_entry,
    select_plan_items,
    vps_folder_name,
)
from tests.support.uploads import blocked_reasons, make_zip, plan_kinds_by_action


class ImportPlanTests(unittest.TestCase):
    def test_new_game_bundle_routes_vpx_and_blocks_rom_color(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "Medieval Madness.zip"
            make_zip(zip_path, ["Medieval Madness.vpx", "Medieval Madness.directb2s", "mm.crz"])
            analysis = analyze_path(zip_path)
            plan = build_import_plan(analysis, allow_new_game=True, games_path=tmp)
            self.assertEqual(plan.new_game_dir_name, "Medieval Madness")
            actions = plan_kinds_by_action(plan)
            self.assertEqual(actions["table"], "copy")
            self.assertEqual(actions["backglass"], "replace_b2s")
            # serum color needs a ROM name the fresh game doesn't have yet
            self.assertIn("altcolor_serum", blocked_reasons(plan))

    def test_existing_game_routing(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Foo (Bar 1999)"
            game_dir.mkdir()
            (game_dir / "Foo.vpx").write_bytes(b"x")
            zip_path = Path(tmp) / "assets.zip"
            make_zip(zip_path, ["new.vpx", "MyPup/screens.pup", "MyPup/s1/a.mp4", "wheel.png"])
            analysis = analyze_path(zip_path)
            plan = build_import_plan(analysis, game_path=str(game_dir), rom_name="mm")
            actions = plan_kinds_by_action(plan)
            self.assertEqual(actions["table"], "replace_vpx")
            self.assertEqual(actions["pup_pack"], "extract_tree")
            self.assertEqual(actions["media"], "replace_media")

    def test_no_context_blocks_all(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            wheel = Path(tmp) / "wheel.png"
            wheel.write_bytes(b"x")
            analysis = analyze_path(wheel)
            plan = build_import_plan(analysis)
            self.assertEqual(plan.items, ())
            self.assertIn("media", blocked_reasons(plan))


class SelectPlanItemsTests(unittest.TestCase):
    def _bundle_plan(self, tmp):
        from pathlib import Path
        zip_path = Path(tmp) / "Medieval Madness.zip"
        make_zip(zip_path, ["Medieval Madness.vpx", "wheel.png",
                            "MyPup/screens.pup", "MyPup/s/a.mp4"])
        analysis = analyze_path(zip_path)
        return build_import_plan(analysis, allow_new_game=True, games_path=tmp)

    def test_none_keeps_all_items(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            plan = self._bundle_plan(tmp)
            self.assertEqual(len(select_plan_items(plan).items), len(plan.items))

    def test_indices_filter_items(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            plan = self._bundle_plan(tmp)
            narrowed = select_plan_items(plan, indices=[0])
            self.assertEqual(len(narrowed.items), 1)
            self.assertEqual(narrowed.items[0].asset.kind, "table")

    def test_rename_rebases_destinations(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            plan = self._bundle_plan(tmp)
            renamed = select_plan_items(plan, new_game_dir_name="Renamed MM")
            self.assertEqual(renamed.new_game_dir_name, "Renamed MM")
            for item in renamed.items:
                self.assertIn(f"{os.sep}Renamed MM{os.sep}", item.destination)

    def test_blank_rename_raises(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            plan = self._bundle_plan(tmp)
            with self.assertRaises(ValueError):
                select_plan_items(plan, new_game_dir_name='<>:"/\\|?*')


class MediaSlotPlanTests(unittest.TestCase):
    def test_family_validation(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            for filename, media_key, ok in [
                ("art.png", "wheel", True),
                ("art.jpg", "backglass", True),
                ("clip.mp4", "scoreview_video", True),
                ("song.mp3", "audio", True),
                ("art.png", "scoreview_video", False),   # image into a video slot
                ("clip.mp4", "wheel", False),      # video into an image slot
                ("song.mp3", "backglass", False),
            ]:
                with self.subTest(filename=filename, media_key=media_key):
                    src = Path(tmp) / filename
                    src.write_bytes(b"x")
                    plan = build_media_slot_plan(src, game_path=tmp, media_key=media_key)
                    if ok:
                        self.assertEqual(len(plan.items), 1)
                        self.assertEqual(plan.items[0].action, "replace_media")
                        self.assertEqual(plan.items[0].asset.media_key, media_key)
                    else:
                        self.assertEqual(plan.items, ())
                        self.assertTrue(plan.blocked)

    def test_archive_and_unknown_slot_rejected(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            archive = Path(tmp) / "pack.zip"
            archive.write_bytes(b"x")
            plan = build_media_slot_plan(archive, game_path=tmp, media_key="wheel")
            self.assertEqual(plan.items, ())
            with self.assertRaises(ValueError):
                build_media_slot_plan(archive, game_path=tmp, media_key="not_a_slot")

    def test_execute_slot_plan_calls_replace(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Foo (Bar 1999)"
            game_dir.mkdir()
            src = Path(tmp) / "cool-art.png"
            src.write_bytes(b"png-bytes")
            plan = build_media_slot_plan(src, game_path=str(game_dir), media_key="wheel")
            with mock.patch("common.uploads.asset_import_service.replace_media_file") as fake:
                report = execute_import_plan(plan, src)
            self.assertEqual(fake.call_args.args[2], "wheel")
            self.assertEqual(report["media_keys"], ["wheel"])


class VpsHelperTests(unittest.TestCase):
    def test_vps_folder_name_variants(self):
        cases = [
            ({"name": "Medieval Madness", "manufacturer": "Bally", "year": "1997"},
             "Medieval Madness (Bally 1997)"),
            ({"name": "Foo", "manufacturer": "Bally", "year": ""}, "Foo (Bally)"),
            ({"name": "Foo", "year": "1997"}, "Foo (1997)"),
            ({"name": "Foo"}, "Foo"),
            ({"name": 'Bad<>:"/\\|?*Name', "manufacturer": "X", "year": "2000"},
             "BadName (X 2000)"),
        ]
        for entry, expected in cases:
            with self.subTest(entry=entry):
                self.assertEqual(vps_folder_name(entry), expected)

    def test_find_vps_entry(self):
        rows = [{"id": "abc123", "name": "Foo"}, {"id": "def456", "name": "Bar"}]
        with mock.patch("common.games.game_service.load_vpsdb", return_value=rows):
            self.assertEqual(find_vps_entry("def456")["name"], "Bar")
            self.assertIsNone(find_vps_entry("nope"))
            self.assertIsNone(find_vps_entry(""))


if __name__ == "__main__":
    unittest.main()
