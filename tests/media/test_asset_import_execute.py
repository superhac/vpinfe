"""What an import actually writes, and what it refuses to write outside the game folder."""

from __future__ import annotations

import unittest
from unittest import mock

from common.games.tables import entry_for_filename, table_filenames
from common.uploads import asset_import_service
from common.uploads.asset_analyzer_service import analyze_path
from common.uploads.asset_import_service import (
    _safe_dest,
    build_import_plan,
    execute_import_plan,
    merge_info,
    select_plan_items,
)
from tests.support.uploads import make_zip


class MergeInfoTests(unittest.TestCase):
    def test_info_adopted_only_when_unmatched(self):
        incoming = {"Info": {"VPSId": "new1", "Title": "New"}}
        self.assertEqual(merge_info(incoming, {})["Info"]["VPSId"], "new1")
        self.assertEqual(
            merge_info(incoming, {"Info": {"VPSId": "old1"}})["Info"]["VPSId"], "old1")

    def test_user_fills_gaps_never_replaces(self):
        incoming = {"User": {"Rating": 4, "StartCount": 300, "Tags": ["fav"]}}
        existing = {"User": {"Rating": 0, "StartCount": 7, "Tags": []}}
        merged = merge_info(incoming, existing)["User"]
        self.assertEqual(merged["Rating"], 4)        # local was empty -> filled
        self.assertEqual(merged["StartCount"], 7)    # local had history -> kept
        self.assertEqual(merged["Tags"], ["fav"])    # local empty list -> filled

    def test_vpxfile_and_assets_always_local(self):
        incoming = {"VPXFile": {"filename": "old.vpx"},
                    "assets": {"medias/wheel.png": {"source": {"host": "user"}}}}
        existing = {"VPXFile": {"filename": "local.vpx"}, "assets": {}}
        merged = merge_info(incoming, existing)
        self.assertEqual(merged["VPXFile"]["filename"], "local.vpx")
        self.assertEqual(merged["assets"], {},
                         "an imported list describes files that are not in this folder")

    def test_an_imported_medias_section_does_not_come_back(self):
        """Nothing writes Medias any more, but a .info from a 2.x build still carries
        one. It must not slip in as an unmanaged section and be preserved forever."""
        merged = merge_info({"Medias": {"wheel": {"Source": "user"}}}, {})
        self.assertNotIn("Medias", merged)

    def test_machine_local_overrides_must_resolve(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            real_launcher = Path(tmp) / "vpx-custom"
            real_launcher.write_bytes(b"x")
            incoming = {"vpinfe": {"alt_launcher": "/nonexistent/vpx", "alt_title": "Cool Name"}}
            merged = merge_info(incoming, {"vpinfe": {"alt_launcher": "", "alt_title": ""}})
            self.assertEqual(merged["vpinfe"]["alt_launcher"], "")   # dropped, does not resolve
            self.assertEqual(merged["vpinfe"]["alt_title"], "Cool Name")
            incoming2 = {"vpinfe": {"alt_launcher": str(real_launcher)}}
            merged2 = merge_info(incoming2, {"vpinfe": {"alt_launcher": ""}})
            self.assertEqual(merged2["vpinfe"]["alt_launcher"], str(real_launcher))

    def test_unknown_sections_added_not_replaced(self):
        incoming = {"CustomTool": {"a": 1}, "Shared": {"x": "incoming"}}
        existing = {"Shared": {"x": "local"}}
        merged = merge_info(incoming, existing)
        self.assertEqual(merged["CustomTool"], {"a": 1})
        self.assertEqual(merged["Shared"]["x"], "local")


class GameInfoImportTests(unittest.TestCase):
    def _bundle(self, tmp, info: dict):
        import json
        import zipfile
        from pathlib import Path
        zip_path = Path(tmp) / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("Old Name (Mfg 1999).vpx", b"x")
            archive.writestr("Old Name (Mfg 1999).info", json.dumps(info))
        return zip_path

    def test_new_game_adopts_and_renames_info(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with mock.patch.object(asset_import_service, "refresh_game"):
            with TemporaryDirectory() as tmp:
                zip_path = self._bundle(tmp, {"Info": {"VPSId": "abc"}, "User": {"Rating": 5}})
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, allow_new_game=True, games_path=tmp)
                plan = select_plan_items(plan, None, "New Name (Mfg 2000)")
                execute_import_plan(plan, zip_path)
                dest = Path(tmp) / "New Name (Mfg 2000)" / "New Name (Mfg 2000).info"
                self.assertTrue(dest.exists())
                data = json.loads(dest.read_text())
                self.assertEqual(data["User"]["Rating"], 5)

    def test_existing_game_merges_and_backs_up(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with mock.patch.object(asset_import_service, "refresh_game"):
            with TemporaryDirectory() as tmp:
                game_dir = Path(tmp) / "Foo (Bar 1999)"
                game_dir.mkdir()
                (game_dir / "Foo.vpx").write_bytes(b"x")
                local = {"Info": {"VPSId": "local-id"}, "User": {"Rating": 3, "StartCount": 12}}
                info_path = game_dir / "Foo (Bar 1999).info"
                info_path.write_text(json.dumps(local))
                zip_path = self._bundle(
                    tmp, {"Info": {"VPSId": "foreign-id"}, "User": {"Rating": 5, "StartCount": 99}})
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, game_dir=game_dir)
                execute_import_plan(plan, zip_path)

                data = json.loads(info_path.read_text())
                self.assertEqual(data["Info"]["VPSId"], "local-id")     # association kept
                self.assertEqual(data["User"]["Rating"], 3)             # history kept
                self.assertEqual(data["User"]["StartCount"], 12)
                backup = game_dir / "Foo (Bar 1999).info.bak"
                self.assertTrue(backup.exists())
                self.assertEqual(json.loads(backup.read_text()), local)


class ImportExecuteTests(unittest.TestCase):
    def test_execute_places_assets_in_existing_game(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with mock.patch.object(asset_import_service, "refresh_game"):
            with TemporaryDirectory() as tmp:
                game_dir = Path(tmp) / "Foo (Bar 1999)"
                game_dir.mkdir()
                (game_dir / "Foo.vpx").write_bytes(b"old")
                (game_dir / "Foo.directb2s").write_bytes(b"old-b2s")
                zip_path = Path(tmp) / "assets.zip"
                make_zip(zip_path, [
                    "Foo.vpx",
                    "roms/mm.zip",
                    "MyPup/screens.pup",
                    "MyPup/s1/a.mp4",
                    "mm.crz",
                ])
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, game_dir=game_dir, rom_name="mm_rom")
                report = execute_import_plan(plan, zip_path)

                self.assertTrue((game_dir / "pinmame" / "roms" / "mm.zip").exists())
                self.assertTrue((game_dir / "pupvideos" / "s1" / "a.mp4").exists())
                self.assertTrue((game_dir / "serum" / "mm_rom" / "mm.crz").exists())
                self.assertIn("rom", report["imported"])

    def test_execute_replace_vpx_restems_backglass(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with mock.patch.object(asset_import_service, "refresh_game"):
            with TemporaryDirectory() as tmp:
                game_dir = Path(tmp) / "Foo (Bar 1999)"
                game_dir.mkdir()
                (game_dir / "Old.vpx").write_bytes(b"old")
                (game_dir / "Old.directb2s").write_bytes(b"b2s")
                zip_path = Path(tmp) / "new.zip"
                make_zip(zip_path, ["New.vpx"])
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, game_dir=game_dir)
                execute_import_plan(plan, zip_path)

                self.assertTrue((game_dir / "New.vpx").exists())
                self.assertFalse((game_dir / "Old.vpx").exists())
                # sibling backglass follows the new vpx stem
                self.assertTrue((game_dir / "New.directb2s").exists())
                self.assertFalse((game_dir / "Old.directb2s").exists())

    def _replace_game(self, tmp, game_dir, info: dict, new_name: str, parsed):
        """Drop new_name onto an existing game, and hand back the resulting .info."""
        import json
        from pathlib import Path
        (game_dir / "Old.vpx").write_bytes(b"old")
        info_path = game_dir / f"{game_dir.name}.info"
        info_path.write_text(json.dumps(info))
        zip_path = Path(tmp) / "new.zip"
        make_zip(zip_path, [new_name])

        plan = build_import_plan(analyze_path(zip_path), game_dir=game_dir)
        with mock.patch.object(asset_import_service, "refresh_game"), \
                mock.patch.object(asset_import_service, "VPXParser") as parser:
            parser.return_value.singleFileExtract.return_value = parsed
            execute_import_plan(plan, zip_path)
        return json.loads(info_path.read_text())

    def test_a_replaced_game_is_described_and_the_old_entry_dropped(self):
        """The new .vpx had no entry until the next metadata build, and the old one kept
        an entry for a file that is gone."""
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Foo (Bar 1999)"
            game_dir.mkdir()
            saved = self._replace_game(
                tmp, game_dir,
                {"tables": {"Old.vpx": {"file_hash": "old-hash", "rom": "old_rom"}}},
                "New.vpx", {"file_hash": "new-hash", "rom": "new_rom"})

            self.assertEqual(table_filenames(saved["tables"]), ["New.vpx"])
            self.assertEqual(
                entry_for_filename(saved["tables"], "New.vpx")[1]["rom"], "new_rom")

    def test_replacing_the_default_table_still_drops_the_vps_override(self):
        """Writing the new hash in at import time must not rob the rebuild of the change
        it clears alt_vpsid on."""
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Foo (Bar 1999)"
            game_dir.mkdir()
            saved = self._replace_game(
                tmp, game_dir,
                {"vpinfe": {"alt_vpsid": "chosen-against-the-old-file"},
                 "tables": {"Old.vpx": {"file_hash": "old-hash"}}},
                "Old.vpx", {"file_hash": "new-hash"})

            self.assertEqual(saved["vpinfe"]["alt_vpsid"], "")

    def test_adding_a_table_does_not_drop_the_vps_override(self):
        """A second table is not a reason to discard the user's match."""
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            game_dir = Path(tmp) / "Foo (Bar 1999)"
            game_dir.mkdir()
            saved = self._replace_game(
                tmp, game_dir,
                {"vpinfe": {"alt_vpsid": "still-this-machine",
                            "default_table": "Old.vpx"},
                 "tables": {"Old.vpx": {"file_hash": "old-hash"}}},
                "Old.vpx", {"file_hash": "old-hash"})

            self.assertEqual(saved["vpinfe"]["alt_vpsid"], "still-this-machine")

    def test_execute_new_bundle_creates_folder(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with mock.patch.object(asset_import_service, "refresh_game"):
            with TemporaryDirectory() as tmp:
                zip_path = Path(tmp) / "Medieval Madness.zip"
                make_zip(zip_path, ["Medieval Madness.vpx", "wheel.png"])
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, allow_new_game=True, games_path=tmp)
                report = execute_import_plan(plan, zip_path)
                new_dir = Path(tmp) / "Medieval Madness"
                self.assertTrue((new_dir / "Medieval Madness.vpx").exists())
                self.assertTrue((new_dir / "medias" / "wheel.png").exists())
                self.assertTrue(report["new_game"])

    def test_execute_new_bundle_collision_raises(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "Medieval Madness").mkdir()
            zip_path = Path(tmp) / "Medieval Madness.zip"
            make_zip(zip_path, ["Medieval Madness.vpx"])
            analysis = analyze_path(zip_path)
            plan = build_import_plan(analysis, allow_new_game=True, games_path=tmp)
            with self.assertRaises(ValueError):
                execute_import_plan(plan, zip_path)


class TraversalGuardTests(unittest.TestCase):
    def test_safe_dest_rejects_traversal(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            for bad in ["../evil.txt", "/abs/path", "a/../../b", "C:/win"]:
                with self.subTest(path=bad):
                    with self.assertRaises(ValueError):
                        _safe_dest(base, bad)

    def test_safe_dest_allows_nested(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            dest = _safe_dest(base, "a/b/c.txt")
            self.assertTrue(str(dest).startswith(str(base.resolve())))

    def test_malicious_archive_member_blocked_on_extract(self):
        import zipfile
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with mock.patch.object(asset_import_service, "refresh_game"):
            with TemporaryDirectory() as tmp:
                game_dir = Path(tmp) / "Foo (Bar 1999)"
                game_dir.mkdir()
                (game_dir / "Foo.vpx").write_bytes(b"x")
                zip_path = Path(tmp) / "evil.zip"
                with zipfile.ZipFile(zip_path, "w") as archive:
                    archive.writestr("Pack/screens.pup", b"x")
                    archive.writestr("Pack/../../escape.mp4", b"x")
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, game_dir=game_dir)
                with self.assertRaises(ValueError):
                    execute_import_plan(plan, zip_path)


if __name__ == "__main__":
    unittest.main()
