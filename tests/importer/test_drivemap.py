"""Finding where a foreign library's recorded paths actually are.

A source records the paths of the machine it ran on. Every one of them is wrong on the
machine reading the share, so without this an import brings across artwork and no games -
which is what it did until a real Popper install was read.

Built on temporary trees rather than a mount, so what is asserted is the rule and not one
person's drive letters.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from common.extensions import host

host.Registry().load(host.BUNDLED_DIR / "library_importer")

from vpinfe_ext_library_importer import drivemap  # noqa: E402


class ForeignTests(unittest.TestCase):
    def test_a_windows_path_is_recognised_as_written_elsewhere(self) -> None:
        """Said explicitly rather than inferred from "it does not exist": a path that is
        simply missing is a different problem with a different answer."""
        self.assertTrue(drivemap.looks_foreign(r"C:\vPinball\Tables"))
        self.assertTrue(drivemap.looks_foreign(r"\steamapps\common\thing"))
        self.assertFalse(drivemap.looks_foreign("/Volumes/share/Tables"))

    def test_the_drive_is_dropped_from_the_parts(self) -> None:
        self.assertEqual(drivemap.segments(r"C:\vPinball\visualpinball\Tables"),
                         ["vPinball", "visualpinball", "Tables"])


class ResolveCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.mount = Path(self._tmp.name) / "share"
        # The shape a mounted cabinet drive has: the library beside the things its
        # database points at.
        (self.mount / "PinUPSystem").mkdir(parents=True)
        (self.mount / "VisualPinball" / "Tables").mkdir(parents=True)
        (self.mount / "VisualPinball" / "VPinMAME" / "roms").mkdir(parents=True)
        self.source = self.mount / "PinUPSystem"


class ResolveTests(ResolveCase):
    def test_a_recorded_path_is_found_beside_the_source(self) -> None:
        found = drivemap.resolve(r"C:\share\VisualPinball\Tables", self.source)

        self.assertEqual(found.path, str(self.mount / "VisualPinball" / "Tables"))

    def test_it_says_what_it_worked_out(self) -> None:
        """One fact about where the share is, so a person can see the decision rather
        than only its result."""
        found = drivemap.resolve(r"C:\share\VisualPinball\Tables", self.source)

        self.assertTrue(found.recorded_prefix)
        self.assertTrue(found.local_prefix)

    def test_a_path_nothing_here_holds_is_not_guessed_at(self) -> None:
        """A guess imports the wrong files and says nothing, which is worse than saying
        the tables are somewhere this machine cannot see."""
        found = drivemap.resolve(r"G:\PC Games", self.source)

        self.assertFalse(found)
        self.assertEqual(found.path, "")

    def test_the_longest_match_wins(self) -> None:
        """A bare trailing name can exist in more than one place. The more of the
        recorded path that matches, the likelier it is the same place."""
        decoy = self.mount / "PinUPSystem" / "Tables"
        decoy.mkdir()

        found = drivemap.resolve(r"C:\share\VisualPinball\Tables", self.source)

        self.assertEqual(found.path, str(self.mount / "VisualPinball" / "Tables"))

    def test_the_real_name_is_taken_off_the_listing(self) -> None:
        """A case-insensitive mount says yes to the recorded spelling, so trusting it
        stores a name that is not the one on disk - fine there, wrong the day the
        library lands on a filesystem that cares."""
        found = drivemap.resolve(r"C:\share\visualpinball\tables", self.source)

        self.assertEqual(Path(found.path).name, "Tables")
        self.assertEqual(Path(found.path).parent.name, "VisualPinball")

    def test_a_local_path_that_is_there_is_left_alone(self) -> None:
        here = str(self.mount / "VisualPinball")

        self.assertEqual(drivemap.resolve(here, self.source).path, here)

    def test_nothing_recorded_resolves_to_nothing(self) -> None:
        self.assertFalse(drivemap.resolve("", self.source))

    def test_it_does_not_wander_up_the_whole_filesystem(self) -> None:
        """Bounded on purpose: past a few ancestors this would be searching somebody's
        machine for a folder whose name happens to match."""
        deep = self.mount / "a" / "b" / "c" / "d" / "e"
        deep.mkdir(parents=True)
        (self.mount / "Elsewhere").mkdir()

        found = drivemap.resolve(r"C:\share\Elsewhere", deep)

        self.assertFalse(found)


class SymlinkTests(ResolveCase):
    def test_it_follows_where_the_share_is_actually_mounted(self) -> None:
        linked = Path(self._tmp.name) / "mnt"
        os.symlink(self.mount, linked)

        found = drivemap.resolve(r"C:\share\VisualPinball\Tables",
                                 linked / "PinUPSystem")

        self.assertTrue(found)
        self.assertTrue(Path(found.path).is_dir())


if __name__ == "__main__":
    unittest.main()
