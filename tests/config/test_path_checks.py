"""Whether a setting that names something on disk finds it.

A path is the one setting that can be perfectly well-formed and still wrong, and it
fails much later - at launch, as a file-not-found, on the machine nobody is at.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

from common import config_schema, path_checks
from tests.support.library import TempTree


class PathCheckTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.file = self.root / "a-file.ini"
        self.file.write_text("x", encoding="utf-8")
        self.folder = self.root / "a-folder"
        self.folder.mkdir()

    def test_a_blank_value_is_not_a_failure(self) -> None:
        """Most of these are optional, and blank means the default."""
        self.assertEqual(path_checks.check("file", ""), (path_checks.UNSET, ""))
        self.assertEqual(path_checks.check("dir", "   "), (path_checks.UNSET, ""))

    def test_a_setting_that_names_nothing_on_disk_is_not_checked(self) -> None:
        self.assertEqual(path_checks.check("", "/nowhere"), (path_checks.UNSET, ""))

    def test_a_file_that_is_there(self) -> None:
        state, reason = path_checks.check("file", str(self.file))

        self.assertEqual(state, path_checks.OK)
        self.assertEqual(reason, "")

    def test_a_folder_that_is_there(self) -> None:
        self.assertEqual(path_checks.check("dir", str(self.folder))[0], path_checks.OK)

    def test_nothing_at_that_path(self) -> None:
        state, reason = path_checks.check("file", str(self.root / "nope.ini"))

        self.assertEqual(state, path_checks.MISSING)
        self.assertIn("Nothing", reason)

    def test_a_folder_where_a_file_was_wanted(self) -> None:
        state, reason = path_checks.check("file", str(self.folder))

        self.assertEqual(state, path_checks.WRONG_KIND)
        self.assertIn("folder", reason)

    def test_a_file_where_a_folder_was_wanted(self) -> None:
        state, reason = path_checks.check("dir", str(self.file))

        self.assertEqual(state, path_checks.WRONG_KIND)
        self.assertIn("file", reason)

    def test_a_program_that_cannot_be_run_is_its_own_state(self) -> None:
        """The path is right and the file is there. That is a permissions problem, not
        a typo, and the two are fixed differently."""
        state, reason = path_checks.check("exe", str(self.file))

        self.assertEqual(state, path_checks.NOT_EXECUTABLE)
        self.assertIn("executable", reason)

    def test_a_program_that_can_be_run(self) -> None:
        os.chmod(self.file, 0o755)

        self.assertEqual(path_checks.check("exe", str(self.file))[0], path_checks.OK)

    @unittest.skipUnless(sys.platform == "darwin", "macOS bundle layout")
    def test_a_mac_app_bundle_is_a_program_not_a_folder(self) -> None:
        """What a person picks is the .app, which is a directory - and reporting the one
        right answer as a mistake is worse than not checking at all."""
        bundle = self.root / "VPinballX.app"
        inner = bundle / "Contents" / "MacOS"
        inner.mkdir(parents=True)
        binary = inner / "VPinballX"
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
        os.chmod(binary, 0o755)

        self.assertEqual(path_checks.check("exe", str(bundle))[0], path_checks.OK)

    def test_a_home_relative_path_is_expanded(self) -> None:
        with mock.patch.dict(os.environ, {"HOME": str(self.root)}):
            self.assertEqual(path_checks.check("file", "~/a-file.ini")[0],
                             path_checks.OK)


class PathOptionTests(unittest.TestCase):
    def test_the_settings_that_name_something_on_disk(self) -> None:
        """Declared on the option rather than matched on the key: vpx_bin_path and
        vpx_ini_path end the same way and want different answers."""
        found = {(o.section, o.key): o.path for o in path_checks.path_options()}

        self.assertEqual(found.get(("general", "vpx_bin_path")), "exe")
        self.assertEqual(found.get(("general", "vpx_ini_path")), "file")
        self.assertEqual(found.get(("general", "game_root_dir")), "dir")

    def test_every_declared_kind_is_one_the_checker_knows(self) -> None:
        """A kind with no checker silently passes everything it is given."""
        for option in path_checks.path_options():
            self.assertIn(option.path, config_schema.PATH_KINDS,
                          f"{option.section}.{option.key}")

    def test_nothing_internal_is_offered(self) -> None:
        self.assertTrue(all(not o.internal for o in path_checks.path_options()))


if __name__ == "__main__":
    unittest.main()
