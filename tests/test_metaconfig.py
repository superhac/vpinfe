import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.tables.metaconfig import (
    CURRENT_VPINFE_SCHEMA,
    InvalidMetaConfigError,
    MetaConfig,
    migrate_vpinfe_section,
)


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
                    "file_hash": filehash,
                    "version": "1.0",
                    "release_date": "2026-01-01",
                    "save_date": "2026-01-02",
                    "save_rev": "123",
                    "manufacturer": "Bally",
                    "year": "1992",
                    "type": "SS",
                    "vbs_hash": "vbshash",
                    "rom": "example",
                    "author_name": "Author One, Author Two",
                    "table_blurb": "Line 1\nLine 2",
                    "detect_nfozzy": False,
                    "detect_fleep": False,
                    "detect_ssf": True,
                    "detect_lut": False,
                    "detect_scorbit": False,
                    "detect_fastflips": True,
                    "detect_flex": False,
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
                        "game_files": {
                            "Example Table.vpx": {"file_hash": "old-filehash"},
                        },
                        "VPinFE": {
                            "alt_vpsid": "12345",
                            "alt_launcher": "/custom/launcher",
                            "alt_title": "Example Alt Title",
                            "delete_nvram_on_close": True,
                        }
                    }
                ),
                encoding="utf-8",
            )

            saved = self._write_meta(info_path)

            self.assertEqual(saved["VPinFE"]["alt_vpsid"], "")
            self.assertEqual(saved["VPinFE"]["alt_launcher"], "/custom/launcher")
            self.assertEqual(saved["VPinFE"]["alt_title"], "Example Alt Title")
            self.assertTrue(saved["VPinFE"]["delete_nvram_on_close"])

    def test_write_config_meta_preserves_altvpsid_when_filehash_is_unchanged(self) -> None:
        with TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "Example Table.info"
            info_path.write_text(
                json.dumps(
                    {
                        "game_files": {
                            "Example Table.vpx": {"file_hash": "same-filehash"},
                        },
                        "VPinFE": {
                            "alt_vpsid": "12345",
                            "alt_launcher": "/custom/launcher",
                            "alt_title": "Example Alt Title",
                            "delete_nvram_on_close": True,
                        }
                    }
                ),
                encoding="utf-8",
            )

            saved = self._write_meta(info_path, filehash="same-filehash")

            self.assertEqual(saved["VPinFE"]["alt_vpsid"], "12345")
            self.assertEqual(saved["VPinFE"]["alt_launcher"], "/custom/launcher")
            self.assertEqual(saved["VPinFE"]["alt_title"], "Example Alt Title")
            self.assertTrue(saved["VPinFE"]["delete_nvram_on_close"])

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

    def test_write_config_meta_preserves_unknown_top_level_sections(self) -> None:
        with TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "Example Table.info"
            info_path.write_text(
                json.dumps(
                    {
                        "game_files": {
                            "Example Table.vpx": {"file_hash": "old-filehash"},
                        },
                        "ThirdParty": {
                            "source": "vpforums",
                            "fileId": "12210",
                        },
                    }
                ),
                encoding="utf-8",
            )

            saved = self._write_meta(info_path)

            self.assertEqual(saved["ThirdParty"], {"source": "vpforums", "fileId": "12210"})
            self.assertEqual(saved["Info"]["Title"], "Example Table")

    def test_empty_info_file_reports_path(self) -> None:
        with TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "Empty Table.info"
            info_path.write_text("", encoding="utf-8")

            with self.assertRaises(InvalidMetaConfigError) as ctx:
                MetaConfig(str(info_path))

            self.assertEqual(ctx.exception.path, str(info_path))
            self.assertIn(str(info_path), str(ctx.exception))
            self.assertIn("file is empty", str(ctx.exception))

    def test_invalid_json_info_file_reports_path_and_location(self) -> None:
        with TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "Broken Table.info"
            info_path.write_text("{not json", encoding="utf-8")

            with self.assertRaises(InvalidMetaConfigError) as ctx:
                MetaConfig(str(info_path))

            self.assertEqual(ctx.exception.path, str(info_path))
            self.assertIn(str(info_path), str(ctx.exception))
            self.assertIn("invalid JSON at line 1 column 2", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()


class VPinFESchemaTests(unittest.TestCase):
    """The VPinFE section carries a schema version; the rest of the file does not."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_an_unversioned_section_migrates_to_current(self) -> None:
        migrated = migrate_vpinfe_section({"alt_title": "Example"})

        self.assertEqual(migrated["schema"], CURRENT_VPINFE_SCHEMA)
        self.assertEqual(migrated["alt_title"], "Example", "existing settings survive")
        self.assertIn("id", migrated, "v2 declares the local id key")
        self.assertEqual(migrated["id"], "", "declaring is not minting")

    def test_migration_is_idempotent(self) -> None:
        once = migrate_vpinfe_section({"alt_title": "Example"})
        twice = migrate_vpinfe_section(dict(once))

        self.assertEqual(once, twice)

    def test_a_newer_schema_is_left_untouched(self) -> None:
        """Running an older build must not downgrade or strip a newer file."""
        future = {"schema": CURRENT_VPINFE_SCHEMA + 5, "somethingNew": "keep me"}

        with self.assertLogs("vpinfe.common.tables.metaconfig", level="WARNING"):
            migrated = migrate_vpinfe_section(dict(future))

        self.assertEqual(migrated, future)

    def test_a_corrupt_schema_value_is_treated_as_oldest(self) -> None:
        migrated = migrate_vpinfe_section({"schema": "not-a-number"})

        self.assertEqual(migrated["schema"], CURRENT_VPINFE_SCHEMA)

    def test_reading_migrates_in_memory_without_writing(self) -> None:
        info = self.root / "Example.info"
        info.write_text(json.dumps({"Info": {"VPSId": "vps-1"}, "VPinFE": {"alt_title": "x"}}),
                        encoding="utf-8")
        before = info.read_text(encoding="utf-8")

        meta = MetaConfig(str(info))

        self.assertEqual(meta.data["VPinFE"]["schema"], CURRENT_VPINFE_SCHEMA)
        self.assertEqual(info.read_text(encoding="utf-8"), before, "reading must not write")

    def test_writing_persists_the_stamp_and_mints_an_id(self) -> None:
        info = self.root / "Example.info"
        TestMetaConfig()._write_meta(info)
        saved = json.loads(info.read_text(encoding="utf-8"))

        self.assertEqual(saved["VPinFE"]["schema"], CURRENT_VPINFE_SCHEMA)
        self.assertTrue(saved["VPinFE"]["id"])

    def test_other_sections_are_not_versioned(self) -> None:
        info = self.root / "Example.info"
        TestMetaConfig()._write_meta(info)
        saved = json.loads(info.read_text(encoding="utf-8"))

        for name in ("Info", "User", "game_files", "Medias"):
            self.assertNotIn("schema", saved.get(name, {}),
                             f"{name} is not ours alone; it stays shape-driven")
