"""A source file that could not be read is named in the note, and why is its detail."""

from __future__ import annotations

import errno
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from common import i18n
from common.extensions import host

host.Registry().load(host.BUNDLED_DIR / "library_importer")

from vpinfe_ext_library_importer import (  # noqa: E402
    emulationstation,
    gamestats,
    pinballx,
    popper,
    registry,
)


class ReadFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.addCleanup(i18n.set_language, i18n.language())
        i18n.set_language("en")

    def _file(self, *parts: str, data: bytes) -> Path:
        path = self.root.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_a_config_that_is_not_an_ini_names_its_line(self) -> None:
        self._file("Config", "PinballX.ini", data="garbage\n".encode("utf-16"))

        self.assertEqual(pinballx.read_config(self.root)[1],
                         [{"text": "PinballX.ini could not be parsed",
                           "detail": "Line 1 is not written as it should be"}])

    def test_a_config_in_no_encoding_it_reads_says_so(self) -> None:
        self._file("Config", "PinballX.ini", data=b"\xff\xfe\x00")

        self.assertEqual(pinballx.read_config(self.root)[1],
                         ["PinballX.ini is not in an encoding this can read"])

    def test_a_folder_where_a_file_should_be_says_so(self) -> None:
        database = self.root / "Visual Pinball X.xml"
        database.mkdir()
        settings = self.root / "Settings.txt"
        settings.mkdir()

        self.assertEqual([pinballx.read_database(database)[1],
                          pinballx.read_pinbally_config(settings)[1]],
                         [[{"text": "Visual Pinball X.xml could not be read",
                            "detail": f"{database} is a folder"}],
                          [{"text": "Settings.txt could not be read",
                            "detail": f"{settings} is a folder"}]])

    def test_a_database_that_is_not_xml_names_its_line(self) -> None:
        database = self._file("Visual Pinball X.xml",
                              data=b"<menu>\n<game name=\"A & B\"/></menu>")

        self.assertEqual(pinballx.read_database(database)[1],
                         [{"text": "Visual Pinball X.xml could not be read",
                           "detail": "Line 2 is not written as it should be"}])

    def test_a_gamelist_that_is_not_xml_names_its_line(self) -> None:
        self._file("gamelist.xml", data=b"<gameList>\n\n<game>&</game></gameList>")

        self.assertEqual(list(emulationstation.read(self.root).notes),
                         [{"text": "gamelist.xml could not be read",
                           "detail": "Line 3 is not written as it should be"}])

    def test_a_file_it_may_not_read_says_so(self) -> None:
        stats = self._file("GameStats.csv", data=b"")
        export = self._file("VPinMAME.reg", data=b"")
        refused = [PermissionError(errno.EACCES, "Permission denied", str(stats)),
                   PermissionError(errno.EACCES, "Permission denied", str(export))]

        with unittest.mock.patch.object(Path, "read_bytes", side_effect=refused[:1]), \
                unittest.mock.patch.object(Path, "read_text", side_effect=refused[1:]):
            said = [gamestats.read(stats)[1], registry.read_text(export)[1]]

        self.assertEqual(said, [
            [{"text": "GameStats.csv could not be read",
              "detail": f"VPinFE does not have permission for {stats}"}],
            {"text": "VPinMAME.reg could not be read",
             "detail": f"VPinFE does not have permission for {export}"}])

    def test_a_popper_database_that_is_not_one_says_what_sqlite_said(self) -> None:
        self._file(popper.DATABASE, data=b"not a database at all, just some text")

        self.assertEqual(list(popper.read(self.root).notes),
                         [{"text": "PUPDatabase.db could not be read to the end",
                           "detail": "file is not a database"}])


if __name__ == "__main__":
    unittest.main()
