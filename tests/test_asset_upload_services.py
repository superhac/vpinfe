from __future__ import annotations

import os

import unittest
from unittest import mock

from managerui.services import asset_analyzer_service, asset_import_service, upload_session_service
from managerui.services.asset_analyzer_service import analyze_path, analyze_upload_session
from managerui.services.asset_import_service import (
    build_import_plan,
    build_media_slot_plan,
    execute_import_plan,
    find_vps_entry,
    merge_info,
    select_plan_items,
    vps_folder_name,
    _safe_dest,
)
from managerui.services.asset_registry import (
    classify_bare_extension,
    match_media_key,
    spec_for,
)


def _make_zip(path, names):
    import zipfile
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"x" * 16)


def _kinds(result):
    return sorted(asset.kind for asset in result.assets)


class RomArchiveTests(unittest.TestCase):
    def test_pinmame_rom_zip_is_recognized(self):
        """Chip names run to three characters. A two-character cap accepted .u7 and
        rejected .u21/.106/.112, and since every member must match, one rejection sank
        the whole archive."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lah_112.zip")
            _make_zip(path, ["lahsnd.u7", "lahsnd.u21", "lahsnd.u17",
                             "lahdispa.106", "lahcpua.112"])
            self.assertEqual(_kinds(analyze_path(path)), ["rom"])

    def test_flat_audio_archive_is_not_a_rom(self):
        """The three-character rule must not swallow .mp3: an altsound pack is a flat
        archive of audio, and would otherwise be claimed as a ROM."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sounds.zip")
            _make_zip(path, ["1.mp3", "2.mp3", "3.mp3"])
            self.assertNotIn("rom", _kinds(analyze_path(path)))


class PatchAssetTests(unittest.TestCase):
    def test_dif_is_claimed_as_a_patch(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mod.zip")
            _make_zip(path, ["CactusCanyon.dif", "CactusCanyon.ini"])
            self.assertEqual(_kinds(analyze_path(path)), ["ini", "patch"])

    def test_patch_needs_a_table_to_apply_to(self):
        """A .dif is a delta against one exact base. Without a table there is nothing
        to patch, and applying it to the wrong one corrupts rather than errors."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mod.zip")
            _make_zip(path, ["CactusCanyon.dif"])
            plan = build_import_plan(analyze_path(path), table_path=tmp)
            self.assertFalse(plan.items)
            self.assertTrue(any("base table" in b.reason for b in plan.blocked))

    def test_the_patched_table_takes_the_patch_name(self):
        """A mod's .ini, .directb2s and artwork are named for the mod, and all of them
        are found by matching the .vpx stem."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Table.vpx").write_bytes(b"x" * 64)
            path = os.path.join(tmp, "mod.zip")
            _make_zip(path, ["CactusCanyon VPW Mod 1.2.dif"])
            plan = build_import_plan(analyze_path(path), table_path=tmp)
            self.assertEqual([i.action for i in plan.items], ["apply_patch"])
            dest = Path(plan.items[0].destination)
            self.assertEqual(dest.name, "CactusCanyon VPW Mod 1.2.vpx")

    def test_a_patch_named_after_its_base_is_tagged_instead(self):
        """Writing over the base would destroy it, and it has to survive - the patched
        table cannot be rebuilt without it."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Cactus Canyon.vpx").write_bytes(b"x" * 64)
            path = os.path.join(tmp, "mod.zip")
            _make_zip(path, ["cactus canyon.dif"])   # same name, other case
            plan = build_import_plan(analyze_path(path), table_path=tmp)
            dest = Path(plan.items[0].destination)
            self.assertEqual(dest.name, "cactus canyon [patched].vpx")

    def test_a_patch_named_after_another_build_is_tagged_too(self):
        """The base is whichever .vpx the patch applies to; any other build in the
        folder is just as much somebody's table."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Cactus Canyon.vpx").write_bytes(b"x" * 64)
            Path(tmp, "Cactus Canyon (VR).vpx").write_bytes(b"x" * 32)
            path = os.path.join(tmp, "mod.zip")
            _make_zip(path, ["Cactus Canyon (VR).dif"])
            plan = build_import_plan(analyze_path(path), table_path=tmp)
            dest = Path(plan.items[0].destination)
            self.assertEqual(dest.name, "Cactus Canyon (VR) [patched].vpx")

    def test_a_patched_build_records_its_base_and_patch(self):
        """Construction is the one origin we witness, and the result cannot be rebuilt
        without the exact base it was made from."""
        import hashlib
        import json
        import tempfile
        import zipfile
        from pathlib import Path

        from common.jdiffpatch import EQL, ESC
        with tempfile.TemporaryDirectory() as tmp:
            table_dir = Path(tmp) / "Foo (Bar 1999)"
            table_dir.mkdir()
            base_vpx = table_dir / "Table.vpx"
            base_vpx.write_bytes(b"ABCDEF")
            zip_path = Path(tmp) / "mod.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("Mod.dif", bytes([ESC, EQL, 5]))   # copy all six bytes

            plan = build_import_plan(analyze_path(zip_path), table_path=str(table_dir))
            execute_import_plan(plan, zip_path)

            patched = table_dir / "Mod.vpx"
            self.assertEqual(patched.read_bytes(), b"ABCDEF")
            saved = json.loads((table_dir / "Foo (Bar 1999).info").read_text())
            source = saved["game_files"][patched.name]["source"]
            self.assertEqual(source["base"], {"file": "Table.vpx",
                                              "hash": hashlib.sha256(b"ABCDEF").hexdigest()})
            self.assertEqual(source["patch"]["format"], "jojodiff")

    def test_an_unrecordable_source_does_not_fail_the_import(self):
        """The patched table is on disk and playable by then. Losing the provenance is
        worth a warning, not an import the user has to redo."""
        import tempfile
        import zipfile
        from pathlib import Path

        from common.jdiffpatch import EQL, ESC
        with tempfile.TemporaryDirectory() as tmp:
            table_dir = Path(tmp) / "Foo (Bar 1999)"
            table_dir.mkdir()
            (table_dir / "Table.vpx").write_bytes(b"ABCDEF")
            (table_dir / "Foo (Bar 1999).info").write_text("{not json")
            zip_path = Path(tmp) / "mod.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("Mod.dif", bytes([ESC, EQL, 5]))

            plan = build_import_plan(analyze_path(zip_path), table_path=str(table_dir))
            with self.assertLogs("vpinfe.manager.asset_import", level="WARNING"):
                execute_import_plan(plan, zip_path)

            self.assertTrue((table_dir / "Mod.vpx").exists())


class AssetRegistryTests(unittest.TestCase):
    def test_classify_bare_extension(self):
        cases = [
            ("Medieval Madness.vpx", "table"),
            ("Medieval Madness.directb2s", "backglass"),
            ("mm_105b.crz", "altcolor_serum"),
            ("mm_105b.CRZ", "altcolor_serum"),
            ("mm_105b.cROMc", "altcolor_serum"),   # Serum's other format
            ("mm_105b.vni", "altcolor_vni"),
            ("mm_105b.PAL", "altcolor_vni"),
            ("mm_105b.pac", "altcolor_vni"),
            ("Medieval Madness.ini", "ini"),
            ("wheel.png", "media"),
            ("bg.mp4", "media"),
            ("audio.mp3", "media"),
            ("roms.zip", None),        # archives are inspected, not bare-classified
            ("pack.7z", None),
            ("readme.txt", None),
            ("noext", None),
        ]
        for filename, expected in cases:
            with self.subTest(filename=filename):
                spec = classify_bare_extension(filename)
                self.assertEqual(spec.key if spec else None, expected)

    def test_match_media_key_canonical_names(self):
        cases = [
            ("bg.png", "bg"),
            ("dmd.png", "dmd"),
            ("dmd.mp4", "dmd_video"),
            ("table.png", "table"),
            ("table.mp4", "table_video"),
            ("wheel.png", "wheel"),
            ("audio.mp3", "audio"),
            ("realdmd-color.png", "realdmd_color"),
        ]
        for filename, expected in cases:
            with self.subTest(filename=filename):
                self.assertEqual(match_media_key(filename), expected)

    def test_match_media_key_keyword_fallback(self):
        cases = [
            ("MyTable_wheel.png", "wheel"),
            ("Table_backglass.png", "bg"),
            ("Game_dmd.mp4", "dmd_video"),
            ("realdmd.png", "realdmd"),
            ("song.mp3", "audio"),        # any recognized audio file -> audio slot
            ("photo.png", None),          # no keyword -> unrecognized
            ("notes.txt", None),          # non-media extension
        ]
        for filename, expected in cases:
            with self.subTest(filename=filename):
                self.assertEqual(match_media_key(filename), expected)

    def test_realdmd_not_claimed_by_dmd_rule(self):
        # "realdmd" contains "dmd"; the realdmd rule must win, and a realdmd video
        # (no such slot) must not fall through to dmd_video.
        self.assertEqual(match_media_key("realdmd.png"), "realdmd")
        self.assertIsNone(match_media_key("realdmd.mp4"))

    def test_spec_for_flags(self):
        self.assertFalse(spec_for("table").requires_table)
        self.assertTrue(spec_for("backglass").requires_table)
        self.assertTrue(spec_for("altcolor_serum").requires_rom)
        self.assertFalse(spec_for("pup_pack").requires_rom)
        self.assertTrue(spec_for("media").allow_multiple)
        with self.assertRaises(KeyError):
            spec_for("nonexistent")


class AssetAnalyzerTests(unittest.TestCase):
    def test_table_bundle(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "bundle.zip"
            _make_zip(zip_path, ["Foo.vpx", "Foo.directb2s", "Foo.ini"])
            result = analyze_path(zip_path)
            self.assertTrue(result.has_table)
            self.assertEqual(_kinds(result), ["backglass", "ini", "table"])
            self.assertEqual(result.error, "")

    def test_pup_marker_and_root(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "pup.zip"
            _make_zip(zip_path, ["MyPup/screens.pup", "MyPup/S1/a.mp4", "MyPup/S2/b.mp4"])
            result = analyze_path(zip_path)
            self.assertEqual(_kinds(result), ["pup_pack"])
            self.assertEqual(result.assets[0].root, "MyPup")
            self.assertEqual(len(result.assets[0].entries), 3)

    def test_pup_fallback_by_shape(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        names = [f"Pack/screen{i}/clip.mp4" for i in range(12)]
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "shape.zip"
            _make_zip(zip_path, names)
            result = analyze_path(zip_path)
            self.assertEqual(_kinds(result), ["pup_pack"])
            self.assertEqual(result.assets[0].root, "Pack")

    def test_altsound_nested_marker(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "as.zip"
            _make_zip(zip_path, ["altsound/altsound.csv", "altsound/1/x.ogg", "altsound/2/y.ogg"])
            result = analyze_path(zip_path)
            self.assertEqual(_kinds(result), ["altsound"])
            self.assertEqual(result.assets[0].root, "altsound")

    def test_flat_rom_archive(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "rom.zip"
            _make_zip(zip_path, ["mm_105.bin", "mm_snd.u7", "mm.cpu"])
            result = analyze_path(zip_path)
            self.assertEqual(_kinds(result), ["rom"])
            self.assertEqual(len(result.assets[0].entries), 3)

    def test_nested_zip_is_rom_blob(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import io
        import zipfile
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "nested.zip"
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, "w") as iz:
                iz.writestr("a.bin", b"x")
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("Foo.vpx", b"x")
                archive.writestr("roms/mm.zip", inner.getvalue())
            result = analyze_path(zip_path)
            self.assertEqual(_kinds(result), ["rom", "table"])

    def test_music_folder(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "music.zip"
            _make_zip(zip_path, ["music/song1.mp3", "music/song2.ogg"])
            result = analyze_path(zip_path)
            self.assertEqual(_kinds(result), ["music"])
            self.assertEqual(result.assets[0].root, "music")

    def test_music_with_video_is_not_music(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "mv.zip"
            _make_zip(zip_path, ["stuff/song1.mp3", "stuff/clip.mp4"])
            result = analyze_path(zip_path)
            self.assertNotIn("music", _kinds(result))

    def test_junk_entries_skipped(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "junk.zip"
            _make_zip(zip_path, ["Foo.vpx", "__MACOSX/._Foo.vpx", ".DS_Store"])
            result = analyze_path(zip_path)
            self.assertEqual(_kinds(result), ["table"])

    def test_unrecognized_only_is_error(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "empty.zip"
            # Genuinely unclaimable names - readme.txt is recognized now.
            _make_zip(zip_path, ["notes.md", "random.xyz"])
            result = analyze_path(zip_path)
            self.assertEqual(result.assets, ())
            self.assertTrue(result.error)

    def test_readme_files_are_claimed_with_a_preview(self):
        """The author's notes reach the person installing the table."""
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "bundle.zip"
            _make_zip(zip_path, ["Table X.vpx", "README.txt", "extra.nfo", "alias.txt"])
            result = analyze_path(zip_path)

        kinds = sorted(a.kind for a in result.assets)
        self.assertEqual(kinds.count("readme"), 2, "README.txt and extra.nfo")
        self.assertIn("alias.txt", result.unrecognized,
                      "a bare .txt never claims as anything")
        readme = next(a for a in result.assets if a.detail == "README.txt")
        self.assertEqual(readme.preview, "x" * 16, "preview text extracted best-effort")

    def test_dir_source_parity_with_zip(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import zipfile
        names = ["Foo.vpx", "MyPup/screens.pup", "MyPup/s1/a.mp4"]
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "parity.zip"
            _make_zip(zip_path, names)
            from_zip = sorted((a.kind, a.root) for a in analyze_path(zip_path).assets)
            tree = Path(tmp) / "tree"
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(tree)
            from_dir = sorted((a.kind, a.root) for a in analyze_path(tree).assets)
            self.assertEqual(from_zip, from_dir)

    def test_single_bare_files(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            wheel = Path(tmp) / "wheel.png"
            wheel.write_bytes(b"x")
            result = analyze_path(wheel)
            self.assertEqual(_kinds(result), ["media"])
            self.assertEqual(result.assets[0].media_key, "wheel")

    def test_rar_tool_hint_is_platform_aware(self):
        from managerui.services.asset_analyzer_service import rar_tool_hint
        with mock.patch.object(asset_analyzer_service.sys, "platform", "win32"):
            self.assertIn("UnRAR.exe", rar_tool_hint())
        with mock.patch.object(asset_analyzer_service.sys, "platform", "darwin"):
            self.assertIn("brew install unar", rar_tool_hint())
        with mock.patch.object(asset_analyzer_service.sys, "platform", "linux"):
            hint = rar_tool_hint()
            self.assertIn("package manager", hint)
            self.assertNotIn("apt", hint)   # never assume a specific distro's tool
        self.assertIn("Configuration", rar_tool_hint())   # points at the configurable path

    def test_configure_rar_tool_targets_right_global(self):
        from managerui.services.asset_analyzer_service import configure_rar_tool
        fake = mock.Mock()
        with mock.patch.object(asset_analyzer_service, "rarfile", fake):
            configure_rar_tool("/opt/bin/unar")
            self.assertEqual(fake.UNAR_TOOL, "/opt/bin/unar")
            configure_rar_tool("/usr/bin/unrar")
            self.assertEqual(fake.UNRAR_TOOL, "/usr/bin/unrar")
        # empty path is a no-op (keeps rarfile's PATH auto-detect)
        with mock.patch.object(asset_analyzer_service, "rarfile", None):
            configure_rar_tool("")   # must not raise when rarfile is absent

    def test_missing_rar_tool_reported_before_dialog(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from managerui.services.asset_analyzer_service import rar_tool_hint
        with TemporaryDirectory() as tmp:
            fake_rar = Path(tmp) / "x.rar"
            fake_rar.write_bytes(b"x")
            with mock.patch.object(asset_analyzer_service, "open_source") as fake_open, \
                    mock.patch.object(asset_analyzer_service, "rar_tool_available", return_value=False):
                fake_open.return_value = mock.Mock(kind="rar", name="x.rar")
                result = analyze_path(fake_rar)
            self.assertEqual(result.assets, ())
            self.assertIn(rar_tool_hint(), result.error)

    def test_rar_backend_missing_is_graceful(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            fake_rar = Path(tmp) / "x.rar"
            fake_rar.write_bytes(b"not really a rar")
            with mock.patch.object(asset_analyzer_service, "rarfile", None):
                result = analyze_path(fake_rar)
            self.assertEqual(result.assets, ())
            self.assertIn("rarfile", result.error)

    def test_upload_session_single_archive(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            session = Path(tmp) / "session"
            session.mkdir()
            _make_zip(session / "bundle.zip", ["Foo.vpx"])
            result, source_path = analyze_upload_session(session)
            self.assertEqual(_kinds(result), ["table"])
            self.assertEqual(source_path.name, "bundle.zip")

    def test_upload_session_folder(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            session = Path(tmp) / "session"
            (session / "MyPup").mkdir(parents=True)
            (session / "MyPup" / "screens.pup").write_bytes(b"x")
            (session / "Foo.vpx").write_bytes(b"x")
            result, source_path = analyze_upload_session(session)
            self.assertEqual(_kinds(result), ["pup_pack", "table"])
            self.assertEqual(source_path, session)


def _plan_kinds_by_action(plan):
    return {item.asset.kind: item.action for item in plan.items}


def _blocked_reasons(plan):
    return {item.asset.kind: item.reason for item in plan.blocked}


class ImportPlanTests(unittest.TestCase):
    def test_new_table_bundle_routes_vpx_and_blocks_rom_color(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "Medieval Madness.zip"
            _make_zip(zip_path, ["Medieval Madness.vpx", "Medieval Madness.directb2s", "mm.crz"])
            analysis = analyze_path(zip_path)
            plan = build_import_plan(analysis, allow_new_table=True, tables_path=tmp)
            self.assertEqual(plan.new_table_dir_name, "Medieval Madness")
            actions = _plan_kinds_by_action(plan)
            self.assertEqual(actions["table"], "copy")
            self.assertEqual(actions["backglass"], "replace_b2s")
            # serum color needs a ROM name the fresh table doesn't have yet
            self.assertIn("altcolor_serum", _blocked_reasons(plan))

    def test_existing_table_routing(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            table_dir = Path(tmp) / "Foo (Bar 1999)"
            table_dir.mkdir()
            (table_dir / "Foo.vpx").write_bytes(b"x")
            zip_path = Path(tmp) / "assets.zip"
            _make_zip(zip_path, ["new.vpx", "MyPup/screens.pup", "MyPup/s1/a.mp4", "wheel.png"])
            analysis = analyze_path(zip_path)
            plan = build_import_plan(analysis, table_path=str(table_dir), rom_name="mm")
            actions = _plan_kinds_by_action(plan)
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
            self.assertIn("media", _blocked_reasons(plan))


class SelectPlanItemsTests(unittest.TestCase):
    def _bundle_plan(self, tmp):
        from pathlib import Path
        zip_path = Path(tmp) / "Medieval Madness.zip"
        _make_zip(zip_path, ["Medieval Madness.vpx", "wheel.png", "MyPup/screens.pup", "MyPup/s/a.mp4"])
        analysis = analyze_path(zip_path)
        return build_import_plan(analysis, allow_new_table=True, tables_path=tmp)

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
            renamed = select_plan_items(plan, new_table_dir_name="Renamed MM")
            self.assertEqual(renamed.new_table_dir_name, "Renamed MM")
            for item in renamed.items:
                self.assertIn(f"{os.sep}Renamed MM{os.sep}", item.destination)

    def test_blank_rename_raises(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            plan = self._bundle_plan(tmp)
            with self.assertRaises(ValueError):
                select_plan_items(plan, new_table_dir_name='<>:"/\\|?*')


class MediaSlotPlanTests(unittest.TestCase):
    def test_family_validation(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            for filename, media_key, ok in [
                ("art.png", "wheel", True),
                ("art.jpg", "bg", True),
                ("clip.mp4", "dmd_video", True),
                ("song.mp3", "audio", True),
                ("art.png", "dmd_video", False),   # image into a video slot
                ("clip.mp4", "wheel", False),      # video into an image slot
                ("song.mp3", "bg", False),
            ]:
                with self.subTest(filename=filename, media_key=media_key):
                    src = Path(tmp) / filename
                    src.write_bytes(b"x")
                    plan = build_media_slot_plan(src, table_path=tmp, media_key=media_key)
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
            plan = build_media_slot_plan(archive, table_path=tmp, media_key="wheel")
            self.assertEqual(plan.items, ())
            with self.assertRaises(ValueError):
                build_media_slot_plan(archive, table_path=tmp, media_key="not_a_slot")

    def test_execute_slot_plan_calls_replace(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            table_dir = Path(tmp) / "Foo (Bar 1999)"
            table_dir.mkdir()
            src = Path(tmp) / "cool-art.png"
            src.write_bytes(b"png-bytes")
            plan = build_media_slot_plan(src, table_path=str(table_dir), media_key="wheel")
            with mock.patch("managerui.services.asset_import_service.replace_media_file") as fake:
                report = execute_import_plan(plan, src)
            self.assertEqual(fake.call_args.args[2], "wheel")
            self.assertEqual(report["media_keys"], ["wheel"])


class TableInfoDetectionTests(unittest.TestCase):
    def test_info_beside_vpx_is_claimed_and_parsed(self):
        import json
        import zipfile
        from pathlib import Path
        from tempfile import TemporaryDirectory
        info = {"Info": {"VPSId": "abc123"}, "User": {"Rating": 4}}
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "bundle.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("Foo (Bar 1999)/Foo.vpx", b"x")
                archive.writestr("Foo (Bar 1999)/Foo (Bar 1999).info", json.dumps(info))
            result = analyze_path(zip_path)
            self.assertIn("table_info", _kinds(result))
            self.assertEqual(result.bundle_info["Info"]["VPSId"], "abc123")

    def test_lone_info_stays_unrecognized(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            info_file = Path(tmp) / "Foo.info"
            info_file.write_text(json.dumps({"Info": {}}))
            result = analyze_path(info_file)
            self.assertNotIn("table_info", _kinds(result))

    def test_invalid_info_is_dropped_with_note(self):
        import zipfile
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "bundle.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("Foo.vpx", b"x")
                archive.writestr("Foo.info", b"this is not json {{{")
            result = analyze_path(zip_path)
            self.assertNotIn("table_info", _kinds(result))
            self.assertIsNone(result.bundle_info)
            self.assertIn("Foo.info", result.unrecognized)


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
            incoming = {"VPinFE": {"alt_launcher": "/nonexistent/vpx", "alt_title": "Cool Name"}}
            merged = merge_info(incoming, {"VPinFE": {"alt_launcher": "", "alt_title": ""}})
            self.assertEqual(merged["VPinFE"]["alt_launcher"], "")   # dropped, does not resolve
            self.assertEqual(merged["VPinFE"]["alt_title"], "Cool Name")
            incoming2 = {"VPinFE": {"alt_launcher": str(real_launcher)}}
            merged2 = merge_info(incoming2, {"VPinFE": {"alt_launcher": ""}})
            self.assertEqual(merged2["VPinFE"]["alt_launcher"], str(real_launcher))

    def test_unknown_sections_added_not_replaced(self):
        incoming = {"CustomTool": {"a": 1}, "Shared": {"x": "incoming"}}
        existing = {"Shared": {"x": "local"}}
        merged = merge_info(incoming, existing)
        self.assertEqual(merged["CustomTool"], {"a": 1})
        self.assertEqual(merged["Shared"]["x"], "local")


class TableInfoImportTests(unittest.TestCase):
    def _bundle(self, tmp, info: dict):
        import json
        import zipfile
        from pathlib import Path
        zip_path = Path(tmp) / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("Old Name (Mfg 1999).vpx", b"x")
            archive.writestr("Old Name (Mfg 1999).info", json.dumps(info))
        return zip_path

    def test_new_table_adopts_and_renames_info(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with mock.patch.object(asset_import_service, "refresh_table"):
            with TemporaryDirectory() as tmp:
                zip_path = self._bundle(tmp, {"Info": {"VPSId": "abc"}, "User": {"Rating": 5}})
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, allow_new_table=True, tables_path=tmp)
                plan = select_plan_items(plan, None, "New Name (Mfg 2000)")
                execute_import_plan(plan, zip_path)
                dest = Path(tmp) / "New Name (Mfg 2000)" / "New Name (Mfg 2000).info"
                self.assertTrue(dest.exists())
                data = json.loads(dest.read_text())
                self.assertEqual(data["User"]["Rating"], 5)

    def test_existing_table_merges_and_backs_up(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with mock.patch.object(asset_import_service, "refresh_table"):
            with TemporaryDirectory() as tmp:
                table_dir = Path(tmp) / "Foo (Bar 1999)"
                table_dir.mkdir()
                (table_dir / "Foo.vpx").write_bytes(b"x")
                local = {"Info": {"VPSId": "local-id"}, "User": {"Rating": 3, "StartCount": 12}}
                info_path = table_dir / "Foo (Bar 1999).info"
                info_path.write_text(json.dumps(local))
                zip_path = self._bundle(
                    tmp, {"Info": {"VPSId": "foreign-id"}, "User": {"Rating": 5, "StartCount": 99}})
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, table_path=str(table_dir))
                execute_import_plan(plan, zip_path)

                data = json.loads(info_path.read_text())
                self.assertEqual(data["Info"]["VPSId"], "local-id")     # association kept
                self.assertEqual(data["User"]["Rating"], 3)             # history kept
                self.assertEqual(data["User"]["StartCount"], 12)
                backup = table_dir / "Foo (Bar 1999).info.bak"
                self.assertTrue(backup.exists())
                self.assertEqual(json.loads(backup.read_text()), local)


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
        with mock.patch("managerui.services.table_service.load_vpsdb", return_value=rows):
            self.assertEqual(find_vps_entry("def456")["name"], "Bar")
            self.assertIsNone(find_vps_entry("nope"))
            self.assertIsNone(find_vps_entry(""))


class ImportExecuteTests(unittest.TestCase):
    def test_execute_places_assets_in_existing_table(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with mock.patch.object(asset_import_service, "refresh_table"):
            with TemporaryDirectory() as tmp:
                table_dir = Path(tmp) / "Foo (Bar 1999)"
                table_dir.mkdir()
                (table_dir / "Foo.vpx").write_bytes(b"old")
                (table_dir / "Foo.directb2s").write_bytes(b"old-b2s")
                zip_path = Path(tmp) / "assets.zip"
                _make_zip(zip_path, [
                    "Foo.vpx",
                    "roms/mm.zip",
                    "MyPup/screens.pup",
                    "MyPup/s1/a.mp4",
                    "mm.crz",
                ])
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, table_path=str(table_dir), rom_name="mm_rom")
                report = execute_import_plan(plan, zip_path)

                self.assertTrue((table_dir / "pinmame" / "roms" / "mm.zip").exists())
                self.assertTrue((table_dir / "pupvideos" / "s1" / "a.mp4").exists())
                self.assertTrue((table_dir / "serum" / "mm_rom" / "mm.crz").exists())
                self.assertIn("rom", report["imported"])

    def test_execute_replace_vpx_restems_backglass(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with mock.patch.object(asset_import_service, "refresh_table"):
            with TemporaryDirectory() as tmp:
                table_dir = Path(tmp) / "Foo (Bar 1999)"
                table_dir.mkdir()
                (table_dir / "Old.vpx").write_bytes(b"old")
                (table_dir / "Old.directb2s").write_bytes(b"b2s")
                zip_path = Path(tmp) / "new.zip"
                _make_zip(zip_path, ["New.vpx"])
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, table_path=str(table_dir))
                execute_import_plan(plan, zip_path)

                self.assertTrue((table_dir / "New.vpx").exists())
                self.assertFalse((table_dir / "Old.vpx").exists())
                # sibling backglass follows the new vpx stem
                self.assertTrue((table_dir / "New.directb2s").exists())
                self.assertFalse((table_dir / "Old.directb2s").exists())

    def test_execute_new_bundle_creates_folder(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with mock.patch.object(asset_import_service, "refresh_table"):
            with TemporaryDirectory() as tmp:
                zip_path = Path(tmp) / "Medieval Madness.zip"
                _make_zip(zip_path, ["Medieval Madness.vpx", "wheel.png"])
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, allow_new_table=True, tables_path=tmp)
                report = execute_import_plan(plan, zip_path)
                new_dir = Path(tmp) / "Medieval Madness"
                self.assertTrue((new_dir / "Medieval Madness.vpx").exists())
                self.assertTrue((new_dir / "medias" / "wheel.png").exists())
                self.assertTrue(report["new_table"])

    def test_execute_new_bundle_collision_raises(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "Medieval Madness").mkdir()
            zip_path = Path(tmp) / "Medieval Madness.zip"
            _make_zip(zip_path, ["Medieval Madness.vpx"])
            analysis = analyze_path(zip_path)
            plan = build_import_plan(analysis, allow_new_table=True, tables_path=tmp)
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
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import zipfile
        with mock.patch.object(asset_import_service, "refresh_table"):
            with TemporaryDirectory() as tmp:
                table_dir = Path(tmp) / "Foo (Bar 1999)"
                table_dir.mkdir()
                (table_dir / "Foo.vpx").write_bytes(b"x")
                zip_path = Path(tmp) / "evil.zip"
                with zipfile.ZipFile(zip_path, "w") as archive:
                    archive.writestr("Pack/screens.pup", b"x")
                    archive.writestr("Pack/../../escape.mp4", b"x")
                analysis = analyze_path(zip_path)
                plan = build_import_plan(analysis, table_path=str(table_dir))
                with self.assertRaises(ValueError):
                    execute_import_plan(plan, zip_path)


class UploadSessionServiceTests(unittest.TestCase):
    def test_begin_store_finish_reassembles_tree(self):
        import io
        session = upload_session_service.begin_session()
        try:
            upload_session_service.store_file(session.upload_id, "a/b/c.txt", io.BytesIO(b"hello"))
            upload_session_service.store_file(session.upload_id, "top.txt", io.BytesIO(b"hi"))
            info = upload_session_service.finish_session(session.upload_id)
            self.assertEqual(info["file_count"], 2)
            directory = upload_session_service.get_session_dir(session.upload_id)
            self.assertEqual((directory / "a" / "b" / "c.txt").read_bytes(), b"hello")
        finally:
            upload_session_service.cleanup_session(session.upload_id)

    def test_unknown_session_raises(self):
        with self.assertRaises(upload_session_service.UnknownSession):
            upload_session_service.get_session_dir("does-not-exist")

    def test_unsafe_relpath_rejected(self):
        import io
        session = upload_session_service.begin_session()
        try:
            for bad in ["../escape.txt", "/abs.txt", "a/../../b.txt"]:
                with self.subTest(path=bad):
                    with self.assertRaises(upload_session_service.UnsafePath):
                        upload_session_service.store_file(session.upload_id, bad, io.BytesIO(b"x"))
        finally:
            upload_session_service.cleanup_session(session.upload_id)

    def test_over_limit_rejected(self):
        import io
        session = upload_session_service.begin_session()
        self.addCleanup(upload_session_service.cleanup_session, session.upload_id)
        with mock.patch.object(upload_session_service, "MAX_TOTAL_BYTES", 4):
            with self.assertRaises(upload_session_service.UploadTooLarge):
                upload_session_service.store_file(session.upload_id, "big.bin", io.BytesIO(b"toolong"))

    def test_cleanup_removes_directory(self):
        session = upload_session_service.begin_session()
        directory = upload_session_service.get_session_dir(session.upload_id)
        self.assertTrue(directory.exists())
        upload_session_service.cleanup_session(session.upload_id)
        self.assertFalse(directory.exists())

    def test_expired_sessions_are_swept(self):
        session = upload_session_service.begin_session()
        directory = upload_session_service.get_session_dir(session.upload_id)
        # Force the session to look old, then a new begin() sweeps it.
        with mock.patch.object(upload_session_service, "time") as fake_time:
            fake_time.time.return_value = session.created + upload_session_service.SESSION_TTL_SECONDS + 1
            other = upload_session_service.begin_session()
        self.addCleanup(upload_session_service.cleanup_session, other.upload_id)
        self.assertFalse(directory.exists())
        with self.assertRaises(upload_session_service.UnknownSession):
            upload_session_service.get_session_dir(session.upload_id)


if __name__ == "__main__":
    unittest.main()
