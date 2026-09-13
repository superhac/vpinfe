"""Reading an EmulationStation library.

Here because it is the opposite shape to the first source read: a game says where its own
artwork is, rather than the artwork being found by convention from the game's name. If the
model had been built around PinballX there would be nowhere to put that, so these are as
much a check on `source.py` as on the reader.

Only path, name, desc and image are verified against EmulationStation's own readers. The
rest are from its documentation, and the fixture is written to that.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common.extensions import host

host.Registry().load(host.BUNDLED_DIR / "library_importer")

from vpinfe_ext_library_importer import emulationstation as es  # noqa: E402
from vpinfe_ext_library_importer import mapping  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "emulationstation"


class ReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.library = es.read(FIXTURE)
        self.by_key = {game.key: game for game in self.library.games}

    def test_it_detects_a_folder_by_its_gamelist(self) -> None:
        self.assertTrue(es.detect(FIXTURE))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(es.detect(Path(tmp)))

    def test_the_key_is_the_files_own_stem(self) -> None:
        """ES has no name attribute and derives nothing from one, so the filename is the
        only stable name an entry has."""
        self.assertEqual(sorted(self.by_key), ["afm", "taxi"])

    def test_a_game_names_where_its_own_artwork_is(self) -> None:
        """The whole reason this reader exists: no kind folders, no filename rule."""
        kinds = {item.source_kind: item.path for item in self.by_key["afm"].media}

        self.assertEqual(sorted(kinds), ["image", "marquee", "video"])
        self.assertTrue(kinds["image"].endswith("media/images/afm.png"))

    def test_a_relative_path_resolves_against_the_folder_it_was_read_from(self) -> None:
        found = self.by_key["afm"].table_file

        self.assertTrue(Path(found).is_absolute())
        self.assertTrue(Path(found).is_file())

    def test_a_release_date_becomes_the_year_we_hold(self) -> None:
        self.assertEqual(self.by_key["afm"].year, "1995")

    def test_the_publisher_stands_in_where_there_is_no_developer(self) -> None:
        """Both map onto the one field we have, and the closer answer wins."""
        self.assertEqual(self.by_key["afm"].manufacturer, "Bally")
        self.assertEqual(self.by_key["taxi"].manufacturer, "Williams")

    def test_an_entry_naming_no_file_is_counted_rather_than_dropped(self) -> None:
        self.assertTrue(any("cannot be imported" in note for note in self.library.notes))

    def test_a_file_the_list_names_but_the_disk_lacks_is_said_out_loud(self) -> None:
        """A library copied without its roms still describes them, and importing it
        silently as entries with nothing to play would not say why."""
        self.assertTrue(any("not reachable from here" in note
                            for note in self.library.notes))

    def test_a_folder_with_no_gamelist_answers_rather_than_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            found = es.read(Path(tmp))

        self.assertEqual(found.systems, ())
        self.assertTrue(found.notes)


class MappingTests(unittest.TestCase):
    KINDS = ("playfield", "playfield_video", "wheel", "backglass")

    def test_the_element_is_the_kind(self) -> None:
        game = es.read(FIXTURE).games[0]

        found = dict(mapping.media_for("emulationstation", game, self.KINDS))

        self.assertEqual(sorted(found), ["playfield", "playfield_video", "wheel"])

    def test_a_source_of_one_shape_does_not_answer_for_another(self) -> None:
        """The tables are per source, so an element name is never read as a PinballX
        folder or the other way round."""
        game = es.read(FIXTURE).games[0]

        self.assertEqual(mapping.media_for("pinballx", game, self.KINDS), [])


if __name__ == "__main__":
    unittest.main()
