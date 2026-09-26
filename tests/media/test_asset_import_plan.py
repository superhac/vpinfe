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
    only_kind,
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
            plan = build_import_plan(analysis, game_dir=game_dir, rom_name="mm")
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


class AddTablePlanTests(unittest.TestCase):
    """A table dropped on a game to join the tables it has, not to replace one."""

    def setUp(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory
        held = TemporaryDirectory()
        self.addCleanup(held.cleanup)
        self.tmp = Path(held.name)
        self.game_dir = self.tmp / "Foo (Bar 1999)"
        self.game_dir.mkdir()
        (self.game_dir / "Foo.vpx").write_bytes(b"x")

    def _plan(self, names, add_table=True):
        zip_path = self.tmp / "drop.zip"
        make_zip(zip_path, names)
        return build_import_plan(analyze_path(zip_path), game_dir=self.game_dir,
                                 add_table=add_table)

    def _names(self, plan):
        from pathlib import Path
        return {item.asset.kind: Path(item.destination).name for item in plan.items}

    def test_the_table_is_added(self):
        plan = self._plan(["Foo 1.2.vpx"])

        self.assertEqual(plan_kinds_by_action(plan), {"table": "add_table"})

    def test_one_the_game_holds_by_that_name_is_refused(self):
        from common.i18n import t

        plan = self._plan(["Foo.vpx"])

        self.assertEqual(blocked_reasons(plan),
                         {"table": t("error.games.game_already_file_name")})

    def test_what_comes_with_it_is_named_for_it(self):
        plan = self._plan(["Foo 1.2.vpx", "Foo 1.2.directb2s", "settings.ini",
                           "Foo 1.2.vbs", "Foo 1.2.pov"])

        self.assertEqual(self._names(plan), {
            "table": "Foo 1.2.vpx", "backglass": "Foo 1.2.directb2s",
            "ini": "Foo 1.2.ini", "script": "Foo 1.2.vbs", "pov": "Foo 1.2.pov"})

    def test_a_replacing_drop_names_them_for_the_table_it_brings(self):
        plan = self._plan(["Foo 1.2.vpx", "Other.directb2s"], add_table=False)

        self.assertEqual(self._names(plan)["backglass"], "Foo 1.2.directb2s")

    def test_without_a_table_they_are_named_for_the_game_s(self):
        plan = self._plan(["Other.directb2s"])

        self.assertEqual(self._names(plan), {"backglass": "Foo.directb2s"})


class OnlyKindTests(unittest.TestCase):
    """A slot's Add or a drop on its cell brings that kind and nothing else."""

    def _plan(self, tmp, names):
        from pathlib import Path
        game_dir = Path(tmp) / "Foo (Bar 1999)"
        game_dir.mkdir()
        (game_dir / "Foo.vpx").write_bytes(b"x")
        zip_path = Path(tmp) / "assets.zip"
        make_zip(zip_path, names)
        return build_import_plan(analyze_path(zip_path), game_dir=game_dir, rom_name="mm")

    def test_a_slot_takes_its_own_kind_and_lists_the_rest(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            plan = only_kind(self._plan(tmp, ["MyPup/screens.pup", "MyPup/s1/a.mp4",
                                              "wheel.png", "Foo.directb2s"]), "pup_pack")

            self.assertEqual(["pup_pack"], [item.asset.kind for item in plan.items])
            left = blocked_reasons(plan)
            self.assertIn("media", left)
            self.assertIn("backglass", left)
            self.assertIn("PUP Pack", left["media"])

    def test_the_lens_name_takes_the_registry_kinds_it_folds(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            plan = only_kind(self._plan(tmp, ["mm.crz", "wheel.png"]), "alt_color")

            self.assertEqual(["altcolor_serum"], [item.asset.kind for item in plan.items])

    def test_no_kind_keeps_the_plan(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            plan = self._plan(tmp, ["MyPup/screens.pup", "MyPup/s1/a.mp4", "wheel.png"])

            self.assertIs(plan, only_kind(plan, ""))


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
            for filename, media_kind, ok in [
                ("art.png", "wheel", True),
                ("art.jpg", "backglass", True),
                ("clip.mp4", "scoreview_video", True),
                ("song.mp3", "audio", True),
                ("art.png", "scoreview_video", False),   # image into a video slot
                ("clip.mp4", "wheel", False),      # video into an image slot
                ("song.mp3", "backglass", False),
            ]:
                with self.subTest(filename=filename, media_kind=media_kind):
                    src = Path(tmp) / filename
                    src.write_bytes(b"x")
                    plan = build_media_slot_plan(src, game_dir=Path(tmp), media_kind=media_kind)
                    if ok:
                        self.assertEqual(len(plan.items), 1)
                        self.assertEqual(plan.items[0].action, "replace_media")
                        self.assertEqual(plan.items[0].asset.media_kind, media_kind)
                    else:
                        self.assertEqual(plan.items, ())
                        self.assertTrue(plan.blocked)

    def test_archive_and_unknown_slot_rejected(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            archive = Path(tmp) / "pack.zip"
            archive.write_bytes(b"x")
            plan = build_media_slot_plan(archive, game_dir=Path(tmp), media_kind="wheel")
            self.assertEqual(plan.items, ())
            with self.assertRaises(ValueError):
                build_media_slot_plan(archive, game_dir=Path(tmp), media_kind="not_a_slot")

    def test_a_drop_is_the_games_own_file_and_the_games_remove_takes_it(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from common.games import media_placement
        with TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Foo (Bar 1999)"
            (game_dir / "medias").mkdir(parents=True)
            fixed = game_dir / "medias" / "logo.png"
            fixed.write_bytes(b"from a catalog")
            src = Path(tmp) / "cool-art.jpg"
            src.write_bytes(b"jpg-bytes")

            plan = build_media_slot_plan(src, game_dir=game_dir, media_kind="logo")
            report = execute_import_plan(plan, src)

            own = game_dir / "medias" / "(Logo) Foo (Bar 1999).jpg"
            self.assertEqual((plan.items[0].destination, own.read_bytes()),
                             (str(own), b"jpg-bytes"))
            self.assertEqual(report["media_kinds"], ["logo"])
            self.assertEqual(fixed.read_bytes(), b"from a catalog")
            self.assertEqual(media_placement.remove(game_dir, "logo", game_dir.name),
                             ["medias/(Logo) Foo (Bar 1999).jpg"])

    def test_a_package_media_file_takes_the_same_name_as_a_drop(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Foo (Bar 1999)"
            game_dir.mkdir()
            (game_dir / "Foo.vpx").write_bytes(b"x")
            zip_path = Path(tmp) / "assets.zip"
            make_zip(zip_path, ["wheel.png"])

            plan = build_import_plan(analyze_path(zip_path), game_dir=game_dir)

            self.assertEqual([item.destination for item in plan.items],
                             [str(game_dir / "medias" / "(Wheel) Foo (Bar 1999).png")])


class MediaSlotReplacesTests(unittest.TestCase):
    """What the confirm says a drop does to the slot, asked of the name it is written at."""

    def _said(self, *present: str) -> str:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from common.uploads import upload_ops
        with TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Foo (Bar 1999)"
            (game_dir / "medias").mkdir(parents=True)
            for name in present:
                (game_dir / "medias" / name).write_bytes(b"x")
            src = Path(tmp) / "art.png"
            src.write_bytes(b"x")
            plan = build_media_slot_plan(src, game_dir=game_dir, media_kind="wheel")
            return upload_ops._plan_to_dict(plan)["items"][0]["replaces"]

    def test_nothing_showing_is_an_empty_slot(self):
        self.assertEqual(self._said(), "slot is empty")

    def test_the_games_own_file_in_another_extension_is_replaced(self):
        self.assertEqual(self._said("(Wheel) Foo (Bar 1999).jpg"), "replaces current")

    def test_a_file_at_a_lower_tier_is_neither_replaced_nor_an_empty_slot(self):
        self.assertEqual(self._said("wheel.png"), "")


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
