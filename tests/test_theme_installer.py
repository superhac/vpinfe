"""Installing a theme must not destroy a folder the user owns.

Two ways it did. `remove_existing_install` deleted every entry whose name merely
started with the repo's, and `install_zip` then rmtree'd the destination outright, so
a registry key colliding with a local theme erased it silently. Both are data loss and
neither asked, which is why these are pinned rather than left to review.
"""

from __future__ import annotations

import io
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from common.online.theme_installer import ASIDE_SUFFIX, ThemeInstallStore

BASE_URL = "https://github.com/someone/Reference"


def _archive(folder: str = "Reference-master", version: str = "2.0.0") -> io.BytesIO:
    """A GitHub source zip: one top-level <repo>-<branch> folder."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{folder}/manifest.json", json.dumps({"version": version}))
        archive.writestr(f"{folder}/index_playfield.html", "<html></html>")
    buffer.seek(0)
    return buffer


def _theme(root: Path, name: str, marker: str = "mine") -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"version": "1.0.0"}))
    (folder / "marker.txt").write_text(marker, encoding="utf-8")
    return folder


class ThemeInstallStoreTests(unittest.TestCase):
    def test_replacing_a_theme_keeps_the_folder_it_replaced(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _theme(root, "Reference", marker="the user's edits")
            store = ThemeInstallStore(str(root))

            store.install_zip("Reference", BASE_URL, _archive())

            self.assertEqual(store.installed_version("Reference"), "2.0.0")
            kept = root / f"Reference{ASIDE_SUFFIX}" / "marker.txt"
            self.assertTrue(kept.exists(), "the replaced folder must survive")
            self.assertEqual(kept.read_text(encoding="utf-8"), "the user's edits")

    def test_a_theme_sharing_a_prefix_is_left_alone(self) -> None:
        """`Reference-mine` used to go with `Reference`, on a startswith match."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _theme(root, "Reference-mine", marker="not the one being installed")
            store = ThemeInstallStore(str(root))

            store.install_zip("Reference", BASE_URL, _archive())

            survivor = root / "Reference-mine" / "marker.txt"
            self.assertTrue(survivor.exists(), "an unrelated theme must not be removed")
            self.assertEqual(survivor.read_text(encoding="utf-8"),
                             "not the one being installed")

    def test_the_promoted_folder_is_the_one_this_extraction_created(self) -> None:
        """Found by diffing the directory - the name match is what went wrong."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _theme(root, "Reference-leftover", marker="older, unrelated")
            store = ThemeInstallStore(str(root))

            store.install_zip("Reference", BASE_URL, _archive())

            self.assertTrue((root / "Reference" / "index_playfield.html").exists())
            self.assertEqual((root / "Reference-leftover" / "marker.txt")
                             .read_text(encoding="utf-8"), "older, unrelated")

    def test_a_failed_install_puts_the_old_theme_back(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _theme(root, "Reference", marker="still here afterwards")
            store = ThemeInstallStore(str(root))

            with self.assertRaises(zipfile.BadZipFile):
                store.install_zip("Reference", BASE_URL, io.BytesIO(b"not a zip"))

            restored = root / "Reference" / "marker.txt"
            self.assertTrue(restored.exists(), "a failed install must not lose the theme")
            self.assertEqual(restored.read_text(encoding="utf-8"),
                             "still here afterwards")

    def test_a_set_aside_folder_is_not_mistaken_for_the_install(self) -> None:
        """It shares the theme's name, so the prefix match would claim it."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _theme(root, f"Reference{ASIDE_SUFFIX}")
            store = ThemeInstallStore(str(root))

            self.assertIsNone(store.installed_folder("Reference", BASE_URL))

    def test_a_symlinked_theme_is_moved_aside_not_followed(self) -> None:
        """The reference theme's dev workflow symlinks the folder in."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = _theme(root / "elsewhere", "Reference", marker="the working copy")
            (root / "Reference").symlink_to(real, target_is_directory=True)
            store = ThemeInstallStore(str(root))

            store.install_zip("Reference", BASE_URL, _archive())

            self.assertEqual((real / "marker.txt").read_text(encoding="utf-8"),
                             "the working copy")
            self.assertTrue((root / f"Reference{ASIDE_SUFFIX}").is_symlink())


if __name__ == "__main__":
    unittest.main()
