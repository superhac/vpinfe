"""The export allowlist: a bundle is one game, not one folder.

Both transports - the VPXZ download and the mobile Web Send - ask
export_bundle the same question, so what ships cannot depend on which button
was pressed.
"""

from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from managerui.services.archive_service import create_vpxz_archive
from managerui.services.export_bundle import bundle_paths, is_readme, prune_info

FOLDER = "Cactus Canyon (Bally 1998)"
CHOSEN = "Cactus Canyon (Bally 1998) - VPW 1.2.vpx"
OTHER = "Cactus Canyon (Bally 1998) - other build.vpx"


def _library(tmp) -> Path:
    root = Path(tmp) / FOLDER
    (root / "medias").mkdir(parents=True)
    (root / "pinmame" / "roms").mkdir(parents=True)
    (root / "music").mkdir()
    for name in (CHOSEN, OTHER):
        (root / name).write_bytes(b"vpx")
    stem = Path(CHOSEN).stem
    (root / f"{stem}.directb2s").write_bytes(b"b2s")
    (root / f"{stem}.ini").write_text("[Player]", encoding="utf-8")
    (root / f"{Path(OTHER).stem}.directb2s").write_bytes(b"other b2s")
    (root / f"{FOLDER}.directb2s").write_bytes(b"shared b2s")
    (root / "pinmame" / "roms" / "cc_13.zip").write_bytes(b"rom")
    (root / "music" / "theme.ogg").write_bytes(b"music")
    (root / "medias" / "wheel.png").write_bytes(b"wheel")
    (root / "README.txt").write_text("by the author", encoding="utf-8")
    (root / "table.nfo").write_text("notes", encoding="utf-8")
    (root / f"{FOLDER}.info").write_text(json.dumps({
        "Info": {"Title": "Cactus Canyon"},
        "vpinfe": {"default_table": CHOSEN},
        "assets": {"medias/wheel.png": {"source": {"host": "user"}},
                   "medias/bg.png": {"source": {"host": "vpinmediadb", "hash": "abc"}}},
    }), encoding="utf-8")
    return root


class BundleTests(unittest.TestCase):
    def _names(self, root, **kwargs):
        return {arcname for _, arcname in bundle_paths(root, **kwargs)}

    def test_the_bundle_is_one_game_not_one_folder(self) -> None:
        with TemporaryDirectory() as tmp:
            names = self._names(_library(tmp))

        self.assertIn(CHOSEN, names)
        self.assertNotIn(OTHER, names, "alternate builds stay home")
        self.assertNotIn(f"{Path(OTHER).stem}.directb2s", names,
                         "and so do their companions")

    def test_the_chosen_builds_companions_and_shared_fallbacks_ride_along(self) -> None:
        with TemporaryDirectory() as tmp:
            names = self._names(_library(tmp))

        stem = Path(CHOSEN).stem
        self.assertIn(f"{stem}.directb2s", names)
        self.assertIn(f"{stem}.ini", names)
        self.assertIn(f"{FOLDER}.directb2s", names,
                      "the folder-named fallback the engine would resolve")

    def test_the_game_dirs_ship_and_media_does_not(self) -> None:
        with TemporaryDirectory() as tmp:
            names = self._names(_library(tmp))

        self.assertIn("pinmame/roms/cc_13.zip", {n.replace("\\", "/") for n in names})
        self.assertIn("music/theme.ogg", {n.replace("\\", "/") for n in names})
        self.assertFalse(any(n.startswith("medias") for n in names),
                         "artwork is for browsing, not playing")

    def test_the_authors_notes_ride_along(self) -> None:
        with TemporaryDirectory() as tmp:
            names = self._names(_library(tmp))

        self.assertIn("README.txt", names)
        self.assertIn("table.nfo", names)

    def test_readme_detection_is_narrow(self) -> None:
        """alias.txt and friends must never look like a readme."""
        self.assertTrue(is_readme("README.md"))
        self.assertTrue(is_readme("readme"))
        self.assertTrue(is_readme("table.nfo"))
        self.assertFalse(is_readme("alias.txt"))
        self.assertFalse(is_readme("notes.txt"))

    def test_everything_means_everything(self) -> None:
        with TemporaryDirectory() as tmp:
            names = self._names(_library(tmp), everything=True)

        self.assertIn(OTHER, names)
        self.assertIn(str(Path("medias") / "wheel.png"), names)

    def test_a_caller_may_pick_the_table(self) -> None:
        with TemporaryDirectory() as tmp:
            names = self._names(_library(tmp), table=OTHER)

        self.assertIn(OTHER, names)
        self.assertNotIn(CHOSEN, names)


class PrunedInfoTests(unittest.TestCase):
    def test_asset_entries_shrink_to_what_ships(self) -> None:
        info = json.dumps({"Info": {"Title": "X"},
                           "assets": {"medias/wheel.png": {"source": {"host": "user"}},
                                      "medias/bg.png": {"source": {"host": "user"}}}})

        pruned = json.loads(prune_info(info, {"medias/wheel.png"}))

        self.assertEqual(list(pruned["assets"]), ["medias/wheel.png"])
        self.assertEqual(pruned["Info"], {"Title": "X"},
                         "everything else passes through untouched")

    def test_a_folder_root_file_is_not_confused_with_one_under_medias(self) -> None:
        """What the old basename match could not do: both entries end in wheel.png,
        and only one of them is in the bundle."""
        info = json.dumps({"assets": {"medias/wheel.png": {"source": {"host": "user"}},
                                      "wheel.png": {"source": {"host": "user"}}}})

        pruned = json.loads(prune_info(info, {"wheel.png"}))

        self.assertEqual(list(pruned["assets"]), ["wheel.png"])

    def test_a_broken_info_passes_through_rather_than_vanishing(self) -> None:
        self.assertEqual(prune_info("not json", set()), "not json")


class FullExportScopeTests(unittest.TestCase):
    def test_the_full_export_scope_is_reserved_and_granted_locally(self) -> None:
        """full=true carries its own permission, so a future token holding only
        tables:read cannot pull whole folders. Local trust grants everything, so
        nothing changes for anyone today."""
        from httpapi import scopes
        from httpapi.auth import LocalTrustPolicy

        self.assertIn(scopes.GAMES_EXPORT_FULL, scopes.CORE)
        identity = LocalTrustPolicy().identify(None)
        self.assertTrue(identity.can(scopes.GAMES_EXPORT_FULL))


class ArchiveTests(unittest.TestCase):
    def test_the_vpxz_holds_the_bundle_and_a_true_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            _library(tmp)
            archive = create_vpxz_archive(FOLDER, tmp)
            with zipfile.ZipFile(archive.path) as z:
                names = set(z.namelist())
                info = json.loads(z.read(f"{FOLDER}/{FOLDER}.info"))

        self.assertIn(f"{FOLDER}/{CHOSEN}", names)
        self.assertNotIn(f"{FOLDER}/{OTHER}", names)
        self.assertFalse(any("/medias/" in n for n in names))
        self.assertEqual(info["assets"], {},
                         "the manifest describes the archive, and no media shipped")

    def test_everything_mode_archives_the_folder(self) -> None:
        with TemporaryDirectory() as tmp:
            _library(tmp)
            archive = create_vpxz_archive(FOLDER, tmp, everything=True)
            with zipfile.ZipFile(archive.path) as z:
                names = set(z.namelist())

        self.assertIn(f"{FOLDER}/{OTHER}", names)
        self.assertIn(f"{FOLDER}/medias/wheel.png", names)


if __name__ == "__main__":
    unittest.main()
