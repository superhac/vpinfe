import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.metaconfig import MetaConfig


class TestMetaConfig(unittest.TestCase):
    def _write_meta(self, info_path: Path, *, filehash: str = "filehash", tutorial_files=None) -> dict:
        meta = MetaConfig(str(info_path))
        meta.writeConfigMeta(
            {
                "vpsdata": {
                    "ipdbUrl": "https://www.ipdb.org/machine.cgi?id=42",
                    "name": "Example Table",
                    "manufacturer": "Bally",
                    "year": "1992",
                    "type": "SS",
                    "theme": ["Sci-Fi"],
                    "id": "vps-42",
                    "tutorialFiles": tutorial_files or [],
                },
                "vpxdata": {
                    "filename": "Example Table.vpx",
                    "fileHash": filehash,
                    "tableVersion": "1.0",
                    "releaseDate": "2026-01-01",
                    "tableSaveDate": "2026-01-02",
                    "tableSaveRev": "123",
                    "companyName": "Bally",
                    "companyYear": "1992",
                    "tableType": "SS",
                    "codeSha256Hash": "vbshash",
                    "rom": "example",
                    "authorName": "Author One, Author Two",
                    "tableBlurb": "Line 1\nLine 2",
                    "detectnfozzy": False,
                    "detectfleep": False,
                    "detectssf": True,
                    "detectlut": False,
                    "detectscorebit": False,
                    "detectfastflips": True,
                    "detectflex": False,
                },
            }
        )
        return json.loads(info_path.read_text(encoding="utf-8"))

    def test_write_config_meta_clears_altvpsid_when_filehash_changes(self) -> None:
        with TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "Example Table.info"
            info_path.write_text(
                json.dumps(
                    {
                        "VPXFile": {
                            "filehash": "old-filehash",
                        },
                        "VPinFE": {
                            "altvpsid": "12345",
                            "altlauncher": "/custom/launcher",
                            "alttitle": "Example Alt Title",
                            "deletedNVRamOnClose": True,
                        }
                    }
                ),
                encoding="utf-8",
            )

            saved = self._write_meta(info_path)

            self.assertEqual(saved["VPinFE"]["altvpsid"], "")
            self.assertEqual(saved["VPinFE"]["altlauncher"], "/custom/launcher")
            self.assertEqual(saved["VPinFE"]["alttitle"], "Example Alt Title")
            self.assertTrue(saved["VPinFE"]["deletedNVRamOnClose"])

    def test_write_config_meta_preserves_altvpsid_when_filehash_is_unchanged(self) -> None:
        with TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "Example Table.info"
            info_path.write_text(
                json.dumps(
                    {
                        "VPXFile": {
                            "filehash": "same-filehash",
                        },
                        "VPinFE": {
                            "altvpsid": "12345",
                            "altlauncher": "/custom/launcher",
                            "alttitle": "Example Alt Title",
                            "deletedNVRamOnClose": True,
                        }
                    }
                ),
                encoding="utf-8",
            )

            saved = self._write_meta(info_path, filehash="same-filehash")

            self.assertEqual(saved["VPinFE"]["altvpsid"], "12345")
            self.assertEqual(saved["VPinFE"]["altlauncher"], "/custom/launcher")
            self.assertEqual(saved["VPinFE"]["alttitle"], "Example Alt Title")
            self.assertTrue(saved["VPinFE"]["deletedNVRamOnClose"])

    def test_write_config_meta_adds_pinball_primer_tutorial(self) -> None:
        with TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "Example Table.info"

            saved = self._write_meta(
                info_path,
                tutorial_files=[
                    {
                        "title": "Pinball Primer: Example Table",
                        "url": "https://pinballprimer.github.io/example_table.html",
                    }
                ],
            )

            self.assertEqual(
                saved["Info"]["PinballPrimerTut"],
                "https://pinballprimer.github.io/example_table.html",
            )

    def test_write_config_meta_omits_pinball_primer_tutorial_when_no_match(self) -> None:
        with TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "Example Table.info"

            saved = self._write_meta(
                info_path,
                tutorial_files=[
                    {
                        "title": "Example Table Tutorial",
                        "url": "https://example.com/tutorial",
                    },
                    {
                        "title": "YouTube Tutorial",
                        "urls": [{"url": "https://www.youtube.com/watch?v=abc123"}],
                    },
                ],
            )

            self.assertNotIn("PinballPrimerTut", saved["Info"])

    def test_write_config_meta_uses_first_pinball_primer_tutorial_found(self) -> None:
        with TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "Example Table.info"

            saved = self._write_meta(
                info_path,
                tutorial_files=[
                    {
                        "title": "Other Tutorial",
                        "url": "https://example.com/tutorial",
                    },
                    {
                        "title": "Nested Primer Tutorial",
                        "urls": [{"url": "https://pinballprimer.github.io/from_nested.html"}],
                    },
                    {
                        "title": "Direct Primer Tutorial",
                        "url": "https://pinballprimer.github.io/from_direct.html",
                    },
                ],
            )

            self.assertEqual(
                saved["Info"]["PinballPrimerTut"],
                "https://pinballprimer.github.io/from_nested.html",
            )


if __name__ == "__main__":
    unittest.main()
