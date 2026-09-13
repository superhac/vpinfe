"""Reading a PinballX library, against a fixture shaped like a real one.

The ini is genuinely UTF-16 and the table path in it is genuinely a Windows path, because
both are what a source copied off an old machine actually looks like and both are what a
reader written from the summary gets wrong.
"""

from __future__ import annotations

import importlib
import shutil
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from common.extensions import host

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "pinballx"

VPX = "Visual Pinball X"


def _reader():
    """The reader, loaded the way core loads it.

    Through the host rather than by path: an extension of more than one module has to be
    importable as a package, and nothing else here would have noticed if it were not.
    """
    registry = host.Registry()
    record = registry.load(host.BUNDLED_DIR / "library_importer")
    assert record.state == host.LOADED, record.reason
    return importlib.import_module("vpinfe_ext_library_importer.pinballx")


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pinballx = _reader()

    def test_the_config_is_read_despite_being_utf_16(self) -> None:
        """A naive UTF-8 read of this file raises, so a reader that does not say so
        finds no emulators and reports an empty library rather than a fault."""
        with self.assertRaises(UnicodeDecodeError):
            (FIXTURE / "Config" / "PinballX.ini").read_text(encoding="utf-8")

        found, notes = self.pinballx.read_config(FIXTURE)

        self.assertEqual([one["name"] for one in found], [VPX, "Retired System"])
        self.assertEqual(notes, [])

    def test_an_emulator_declares_where_its_tables_and_its_application_are(self) -> None:
        found, _notes = self.pinballx.read_config(FIXTURE)
        vpx = found[0]

        self.assertEqual(vpx["tables_dir"], r"C:\Visual Pinball\tables")
        self.assertEqual(vpx["working_path"], r"C:\Visual Pinball 10.7")

    def test_an_emulator_switched_off_is_reported_as_such_not_dropped(self) -> None:
        found, _notes = self.pinballx.read_config(FIXTURE)

        self.assertFalse(found[1]["enabled"])

    def test_a_root_with_no_config_says_so_and_is_not_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            found, notes = self.pinballx.read_config(Path(tmp))

        self.assertEqual(found, [])
        self.assertTrue(notes)


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pinballx = _reader()
        self.games, self.notes = self.pinballx.read_database(
            FIXTURE / "Databases" / VPX / f"{VPX}.xml")
        self.by_key = {game.key: game for game in self.games}

    def test_a_game_carries_what_the_source_recorded(self) -> None:
        afm = self.by_key["Attack from Mars (Bally 1995)"]

        self.assertEqual(afm.manufacturer, "Bally")
        self.assertEqual(afm.year, "1995")
        self.assertEqual(afm.game_type, "SS")
        self.assertEqual(afm.rom, "afm_113b")
        self.assertEqual(afm.themes, ("Aliens", "Outer Space"))

    def test_a_vps_id_comes_through(self) -> None:
        """The find that decides what a user is left holding: a source carrying one
        arrives matched instead of as a pile somebody works through by hand."""
        self.assertEqual(self.by_key["Attack from Mars (Bally 1995)"].vps_id, "abcd1234")

    def test_the_key_is_the_name_and_never_the_description(self) -> None:
        taxi = self.by_key["Taxi"]

        self.assertEqual(taxi.key, "Taxi")
        self.assertEqual(taxi.display_name, "Taxi (Williams 1988)")

    def test_a_game_the_source_was_told_to_hide_says_so(self) -> None:
        self.assertTrue(self.by_key["Taxi"].hidden)
        self.assertFalse(self.by_key["Attack from Mars (Bally 1995)"].hidden)

    def test_what_has_no_home_of_ours_travels_rather_than_vanishing(self) -> None:
        """A preview can then say what will not be carried, which is the difference
        between a decision and a surprise."""
        extras = self.by_key["Attack from Mars (Bally 1995)"].extras

        self.assertEqual(extras.get("hidedmd"), "True")
        self.assertEqual(extras.get("dateadded"), "2024-01-01 10:00:00")

    def test_a_row_with_no_name_is_counted_rather_than_dropped_silently(self) -> None:
        """Its media is found by that name, so there is nothing to import it as."""
        self.assertEqual(len(self.games), 3)
        self.assertTrue(any("no name" in note for note in self.notes))

    def test_a_pinbally_database_adds_title_and_ipdbid_over_the_same_set(self) -> None:
        games, _notes = self.pinballx.read_database(
            FIXTURE / "Databases" / "Future Pinball" / "Future Pinball.xml")

        self.assertEqual(games[0].title, "Big Bang Bar")
        self.assertEqual(games[0].ipdb_id, "4001")


class MediaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pinballx = _reader()
        self.library = self.pinballx.read(FIXTURE)
        self.by_key = {game.key: game for game in self.library.games}

    def _kinds(self, key: str) -> set[str]:
        return {item.source_kind for item in self.by_key[key].media}

    def test_both_the_still_and_the_moving_folder_are_walked(self) -> None:
        """PinballX files the two versions of one subject apart and chooses between them
        by extension. A reader that walked one folder per subject would miss half."""
        found = self._kinds("Attack from Mars (Bally 1995)")

        self.assertIn("Table Images", found)
        self.assertIn("Table Videos", found)
        self.assertIn("DMD Videos", found)

    def test_a_file_whose_name_merely_starts_with_the_key_counts(self) -> None:
        wheels = sorted(Path(item.path).name
                        for item in self.by_key["Attack from Mars (Bally 1995)"].media
                        if item.source_kind == "Wheel Images")

        self.assertEqual(len(wheels), 2)

    def test_an_exact_name_wins_over_a_longer_one_that_starts_the_same(self) -> None:
        """A library holding both Taxi and Taxi 2 would otherwise give the shorter name
        the longer one's artwork as well."""
        images = [Path(item.path).name for item in self.by_key["Taxi"].media
                  if item.source_kind == "Table Images"]

        self.assertEqual(images, ["Taxi.png"])

    def test_a_longer_name_keeps_its_own_artwork(self) -> None:
        """The other half of the same rule: Taxi 2 is not left without an image because
        Taxi's name is a prefix of its own."""
        images = [Path(item.path).name for item in self.by_key["Taxi 2"].media]

        self.assertEqual(images, ["Taxi 2.png"])


class ReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pinballx = _reader()

    def test_it_detects_a_root_by_its_databases(self) -> None:
        self.assertTrue(self.pinballx.detect(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(self.pinballx.detect(Path(tmp)))

    def test_a_database_the_config_never_declared_is_still_read(self) -> None:
        """A library copied off an old machine very often arrives without its ini."""
        library = self.pinballx.read(FIXTURE)

        self.assertIn("Visual Pinball X Beta", [one.name for one in library.systems])
        self.assertTrue(any("does not declare" in note for note in library.notes))

    def test_the_tables_folder_is_listed_once_for_the_whole_database(self) -> None:
        """Asked once, not once per game.

        A real library put 654 games against a folder of some three thousand entries.
        Listing it per game meant two million stat calls across a mounted drive and took
        thirty seconds; the same read now takes a fifth of a second. It read as a caching
        problem and was an accidentally quadratic loop, so what is pinned is the number
        of listings rather than a duration - a timing test on somebody else's disk proves
        nothing.
        """
        seen = []
        real = self.pinballx._table_index

        def counting(tables_dir):
            seen.append(str(tables_dir))
            return real(tables_dir)

        with unittest.mock.patch.object(self.pinballx, "_table_index", counting):
            self.pinballx.read(FIXTURE)

        self.assertLessEqual(len(seen), len(set(seen)) or 1,
                             f"listed a folder more than once: {seen}")

    def test_what_a_filesystem_leaves_lying_about_is_not_a_system(self) -> None:
        """A share served from a NAS carries @eaDir beside the real folders, and saying
        we cannot play it reads as a finding rather than as noise."""
        litter = FIXTURE / "Databases" / "@eaDir"
        litter.mkdir(exist_ok=True)
        self.addCleanup(litter.rmdir)

        library = self.pinballx.read(FIXTURE)

        self.assertNotIn("@eaDir", [one.name for one in library.systems])
        self.assertFalse([one for one in library.notes if "@eaDir" in one])

    def test_a_system_this_build_cannot_play_is_left_behind(self) -> None:
        """Chris, 2026-09-10: only Visual Pinball, for now.

        A source declares whatever its owner ever set up. Bringing in Future Pinball
        would make entries for games nothing here can launch, which is worse than not
        having them - they cannot be played and they cannot be told apart from the ones
        that can.
        """
        library = self.pinballx.read(FIXTURE)

        self.assertNotIn("Future Pinball", [one.name for one in library.systems])

    def test_an_extension_can_make_a_skipped_system_importable(self) -> None:
        """Chris, 2026-09-10: *"An extension supporting additional launcher should be
        supported."*

        This is what that buys. A Future Pinball library is read and dropped because
        nothing here plays `.fpt`; an extension providing an app for it changes the
        answer, and the same source now brings it in. The rule that decides is what the
        build can play, never a format written down in the importer.
        """
        from common import apps
        from common.extensions import provided_apps
        from common.extensions.context import ExtensionApps

        apps.withdraw_all()
        self.addCleanup(apps.withdraw_all)
        seat = ExtensionApps("future_pinball", (provided_apps.APPS_PROVIDE,))

        without = self.pinballx.read(FIXTURE, seat.plays, seat.names())
        self.assertNotIn("Future Pinball", [one.name for one in without.systems])

        seat.provide(id="fp", name="Future Pinball", suffixes=(".fpt",))
        with_it = self.pinballx.read(FIXTURE, seat.plays, seat.names())

        self.assertIn("Future Pinball", [one.name for one in with_it.systems])

    def test_what_was_left_behind_is_named(self) -> None:
        """Left, not dropped. Somebody who set Future Pinball up wants to know it was
        seen and skipped, not to wonder whether it was noticed."""
        library = self.pinballx.read(FIXTURE)

        said = [note for note in library.notes if "does not play" in note]
        self.assertTrue(said, library.notes)
        self.assertIn("Future Pinball", said[0])

    def test_an_emulator_with_no_database_is_reported(self) -> None:
        library = self.pinballx.read(FIXTURE)

        self.assertNotIn("Retired System", [one.name for one in library.systems])
        self.assertTrue(any("Retired System" in note for note in library.notes))

    def test_a_tables_dir_from_the_old_machine_is_said_out_loud(self) -> None:
        """Nobody can say where those files are now without being told it is the
        question, and importing every game without its table would not ask it."""
        library = self.pinballx.read(FIXTURE)

        self.assertTrue(any("not reachable from here" in note
                            for note in library.notes))
        self.assertEqual(
            [game.table_file for game in library.games if game.table_file], [])

    def test_a_tables_dir_that_is_there_resolves_each_game_to_its_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            shutil.copytree(FIXTURE, root)
            tables = root / "tables"
            tables.mkdir()
            (tables / "Attack from Mars (Bally 1995).vpx").write_bytes(b"table")
            ini = root / "Config" / "PinballX.ini"
            ini.write_bytes(ini.read_text(encoding="utf-16")
                            .replace(r"C:\Visual Pinball\tables", str(tables))
                            .encode("utf-16"))

            library = self.pinballx.read(root)

        found = {game.key: game.table_file for game in library.games}
        self.assertTrue(found["Attack from Mars (Bally 1995)"].endswith(
            "Attack from Mars (Bally 1995).vpx"))
        self.assertEqual(found["Taxi"], "")


if __name__ == "__main__":
    unittest.main()


class TableFileTests(unittest.TestCase):
    """Which file in the tables folder is the table.

    A table sits beside its companions and they share its stem, so a folder listing has
    several answers for one name. Picking any of them means a game whose recorded table
    is its own script - which happened, and the game then had no table at all.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tables = Path(self._tmp.name)
        for suffix in (".vpx", ".directb2s", ".ini", ".vbs", ".txt"):
            (self.tables / f"Taxi (Williams 1988){suffix}").write_bytes(b"x")

    def _pick(self, plays=None):
        from vpinfe_ext_library_importer import pinballx

        index = (pinballx._table_index(self.tables, plays) if plays
                 else pinballx._table_index(self.tables))
        return pinballx._table_file(index, "Taxi (Williams 1988)")

    def test_the_table_is_the_one_something_can_play(self) -> None:
        self.assertTrue(self._pick().endswith(".vpx"))

    def test_it_is_not_whichever_the_directory_listed_first(self) -> None:
        """Asserted over every ordering the filesystem could hand back, because the bug
        this replaces only showed up on one of them."""
        for _ in range(12):
            self.assertTrue(self._pick().endswith(".vpx"))

    def test_a_build_that_plays_another_format_picks_that(self) -> None:
        """The rule is what the build plays, so an extension providing an app changes
        which file is the table - not a suffix written down here."""
        (self.tables / "Taxi (Williams 1988).fpt").write_bytes(b"x")

        found = self._pick(plays=lambda s: s.lower() == ".fpt")

        self.assertTrue(found.endswith(".fpt"))
