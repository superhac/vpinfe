"""A theme update must not reset the options the user chose.

They used to be written into the installed theme package, and updating a theme deletes
that package - so every update silently restored every default, with no backup and no
warning. The values live outside the theme now. The test that matters is the last one:
install, configure, update, and the choice is still there.
"""

from __future__ import annotations

import io
import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common import theme_options
from common.online.theme_installer import ThemeInstallStore

SCHEMA = {"title": "Reference", "options": [
    {"key": "showFlags", "name": "Show flags", "type": "boolean", "default": False},
    {"key": "wheelSpan", "name": "Wheel span", "type": "number", "default": 3},
]}


def _installed(root: Path, folder: str = "Reference", *, values: dict | None = None) -> Path:
    """A theme as a pre-3.0 build left it: values written into its own schema file."""
    theme_dir = root / folder
    theme_dir.mkdir(parents=True)
    schema = json.loads(json.dumps(SCHEMA))
    for option in schema["options"]:
        if values and option["key"] in values:
            option["value"] = values[option["key"]]
    (theme_dir / "theme.json").write_text(json.dumps(schema), encoding="utf-8")
    (theme_dir / "manifest.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")
    return theme_dir


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = mock.patch.object(theme_options, "USER_OPTIONS_DIR",
                                    self.root / "theme_user_options")
        patcher.start()
        self.addCleanup(patcher.stop)


class UserOptionStoreTests(_Base):
    def test_values_round_trip(self) -> None:
        theme_options.save("Reference", {"showFlags": True, "wheelSpan": 5})
        self.assertEqual(theme_options.load("Reference"),
                         {"showFlags": True, "wheelSpan": 5})

    def test_a_theme_nobody_configured_has_no_values(self) -> None:
        self.assertEqual(theme_options.load("Reference"), {})

    def test_the_file_is_keyed_by_folder_name(self) -> None:
        """Not the registry key - a local or side-loaded theme has no registry entry."""
        theme_options.save("My Local Theme", {"showFlags": True})
        self.assertTrue((theme_options.USER_OPTIONS_DIR / "My Local Theme.json").exists())

    def test_a_hostile_folder_name_cannot_escape_the_directory(self) -> None:
        theme_options.save("../../etc/passwd", {"showFlags": True})
        written = list(theme_options.USER_OPTIONS_DIR.glob("*.json"))
        self.assertEqual([p.parent for p in written], [theme_options.USER_OPTIONS_DIR])

    def test_an_unreadable_file_reads_as_no_values(self) -> None:
        theme_options.USER_OPTIONS_DIR.mkdir(parents=True)
        (theme_options.USER_OPTIONS_DIR / "Reference.json").write_text("{ broken",
                                                                       encoding="utf-8")
        self.assertEqual(theme_options.load("Reference"), {})


class MigrationTests(_Base):
    def test_values_are_lifted_out_of_an_installed_package(self) -> None:
        themes = self.root / "themes"
        _installed(themes, values={"showFlags": True, "wheelSpan": 7})

        moved = theme_options.migrate_from_packages(themes)

        self.assertEqual(moved, ["Reference"])
        self.assertEqual(theme_options.load("Reference"),
                         {"showFlags": True, "wheelSpan": 7})

    def test_a_theme_with_no_chosen_values_is_left_alone(self) -> None:
        themes = self.root / "themes"
        _installed(themes)

        self.assertEqual(theme_options.migrate_from_packages(themes), [])

    def test_an_existing_user_file_is_never_overwritten(self) -> None:
        """Second run, or a theme that already moved - the user's file wins."""
        themes = self.root / "themes"
        _installed(themes, values={"showFlags": True})
        theme_options.save("Reference", {"showFlags": False})

        theme_options.migrate_from_packages(themes)

        self.assertEqual(theme_options.load("Reference"), {"showFlags": False})

    def test_migrating_twice_changes_nothing(self) -> None:
        themes = self.root / "themes"
        _installed(themes, values={"wheelSpan": 9})

        theme_options.migrate_from_packages(themes)
        self.assertEqual(theme_options.migrate_from_packages(themes), [])
        self.assertEqual(theme_options.load("Reference"), {"wheelSpan": 9})


class SurvivesAnUpdateTests(_Base):
    def test_updating_a_theme_keeps_what_the_user_chose(self) -> None:
        """The whole point. This is the sequence that used to reset every option."""
        themes = self.root / "themes"
        themes.mkdir()
        _installed(themes, values={"showFlags": True, "wheelSpan": 7})
        theme_options.migrate_from_packages(themes)

        # A newer release of the same theme, exactly as the installer receives it.
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Reference-master/manifest.json", json.dumps({"version": "2.0.0"}))
            archive.writestr("Reference-master/theme.json", json.dumps(SCHEMA))
        buffer.seek(0)
        ThemeInstallStore(str(themes)).install_zip(
            "Reference", "https://github.com/someone/Reference", buffer)

        self.assertEqual(ThemeInstallStore(str(themes)).installed_version("Reference"),
                         "2.0.0", "precondition: the theme really was updated")
        self.assertEqual(theme_options.load("Reference"),
                         {"showFlags": True, "wheelSpan": 7})


if __name__ == "__main__":
    unittest.main()
