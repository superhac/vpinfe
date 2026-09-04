import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from common.games.info_file import (
    INFO_SCHEMA,
    InvalidMetaConfigError,
    MetaConfig,
    migrate_vpinfe_section,
)
from common.games.tables import entry_for_filename
from tests.support.library import TempTree, write_game


class TestMetaConfig(unittest.TestCase):
    def _write_meta(self, info_path: Path, *, filehash: str = "filehash",
                    tutorial_files=None) -> dict:
        meta = MetaConfig(str(info_path))
        meta.write_config_meta(
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
                    "game_blurb": "Line 1\nLine 2",
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
                        "tables": {
                            "Example Table.vpx": {"file_hash": "old-filehash"},
                        },
                        "vpinfe": {
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

            self.assertEqual(saved["vpinfe"]["alt_vpsid"], "")
            self.assertEqual(saved["vpinfe"]["alt_launcher"], "/custom/launcher")
            self.assertEqual(saved["vpinfe"]["alt_title"], "Example Alt Title")
            self.assertTrue(saved["vpinfe"]["delete_nvram_on_close"])

    def test_write_config_meta_preserves_altvpsid_when_filehash_is_unchanged(self) -> None:
        with TemporaryDirectory() as tmp:
            info_path = Path(tmp) / "Example Table.info"
            info_path.write_text(
                json.dumps(
                    {
                        "tables": {
                            "Example Table.vpx": {"file_hash": "same-filehash"},
                        },
                        "vpinfe": {
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

            self.assertEqual(saved["vpinfe"]["alt_vpsid"], "12345")
            self.assertEqual(saved["vpinfe"]["alt_launcher"], "/custom/launcher")
            self.assertEqual(saved["vpinfe"]["alt_title"], "Example Alt Title")
            self.assertTrue(saved["vpinfe"]["delete_nvram_on_close"])

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
                        "tables": {
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


class VPinFESchemaTests(TempTree):
    """The VPinFE section carries a schema version; the rest of the file does not."""

    def setUp(self) -> None:
        super().setUp()

    def test_an_unversioned_section_migrates_to_current(self) -> None:
        migrated = migrate_vpinfe_section({"alt_title": "Example"})

        self.assertEqual(migrated["schema"], INFO_SCHEMA)
        self.assertEqual(migrated["alt_title"], "Example", "existing settings survive")
        self.assertIn("game_id", migrated, "v2 declares the local game id key")
        self.assertEqual(migrated["game_id"], "", "declaring is not minting")

    def test_migration_is_idempotent(self) -> None:
        once = migrate_vpinfe_section({"alt_title": "Example"})
        twice = migrate_vpinfe_section(dict(once))

        self.assertEqual(once, twice)

    def test_a_newer_schema_is_left_untouched(self) -> None:
        """Running an older build must not downgrade or strip a newer file."""
        future = {"schema": INFO_SCHEMA + 5, "somethingNew": "keep me"}

        with self.assertLogs("vpinfe.common.games.info_file", level="WARNING"):
            migrated = migrate_vpinfe_section(dict(future))

        self.assertEqual(migrated, future)

    def test_a_corrupt_schema_value_is_treated_as_oldest(self) -> None:
        migrated = migrate_vpinfe_section({"schema": "not-a-number"})

        self.assertEqual(migrated["schema"], INFO_SCHEMA)

    def test_reading_migrates_in_memory_without_writing(self) -> None:
        info = self.root / "Example.info"
        info.write_text(json.dumps({"Info": {"VPSId": "vps-1"}, "vpinfe": {"alt_title": "x"}}),
                        encoding="utf-8")
        before = info.read_text(encoding="utf-8")

        meta = MetaConfig(str(info))

        self.assertEqual(meta.data["vpinfe"]["schema"], INFO_SCHEMA)
        self.assertEqual(info.read_text(encoding="utf-8"), before, "reading must not write")

    def test_writing_persists_the_stamp_and_mints_an_id(self) -> None:
        info = self.root / "Example.info"
        TestMetaConfig()._write_meta(info)
        saved = json.loads(info.read_text(encoding="utf-8"))

        self.assertEqual(saved["vpinfe"]["schema"], INFO_SCHEMA)
        self.assertTrue(saved["vpinfe"]["game_id"])

    def test_other_sections_are_not_versioned(self) -> None:
        info = self.root / "Example.info"
        TestMetaConfig()._write_meta(info)
        saved = json.loads(info.read_text(encoding="utf-8"))

        for name in ("Info", "User", "tables", "assets"):
            self.assertNotIn("schema", saved.get(name, {}),
                             f"{name} is not ours alone; it stays shape-driven")


class PatchSourceTests(TempTree):
    """A build we constructed records what it was made from. Nothing else does -
    an ordinary .vpx came from wherever the user got it, which we never saw."""

    def setUp(self) -> None:
        super().setUp()
        self.root = write_game(self.root, "Example Table", vpx=False, info={})
        self.info = self.root / "Example Table.info"

    def _source(self, filename: str = "Example Table VPW Mod.vpx") -> dict:
        saved = json.loads(self.info.read_text(encoding="utf-8"))
        return entry_for_filename(saved["tables"], filename)[1]["source"]

    def test_the_base_is_named_and_hashed(self) -> None:
        meta = MetaConfig(str(self.info))
        meta.record_patch_source("Example Table VPW Mod.vpx", "Example Table.vpx",
                                 "3a77427e", "jojodiff")

        source = self._source()
        self.assertEqual(source["base"], {"file": "Example Table.vpx", "hash": "3a77427e"})
        self.assertEqual(source["patch"]["format"], "jojodiff")

    def test_applied_is_utc(self) -> None:
        """The .info travels with its folder, so a local time says nothing once it
        lands on another machine."""
        meta = MetaConfig(str(self.info))
        meta.record_patch_source("Example Table VPW Mod.vpx", "Example Table.vpx",
                                 "3a77427e", "jojodiff")

        applied = self._source()["patch"]["applied"]
        self.assertTrue(applied.endswith("Z"), applied)
        self.assertEqual(datetime.fromisoformat(applied).tzinfo, UTC)

    def test_a_rebuild_keeps_it(self) -> None:
        """The parse describes what a build says about itself and knows nothing about
        how it was made, so a refresh must not take the origin with it."""
        meta = MetaConfig(str(self.info))
        meta.record_patch_source("Example Table.vpx", "Base.vpx", "3a77427e", "jojodiff")

        TestMetaConfig()._write_meta(self.info)

        self.assertEqual(self._source("Example Table.vpx")["base"]["file"], "Base.vpx")


class AssetLedgerTests(TempTree):
    """assets records one entry per file VPinFE placed, keyed by where it went."""

    def setUp(self) -> None:
        super().setUp()
        self.root = write_game(self.root, "Cactus Canyon (Bally 1998)", vpx=False, info={})
        (self.root / "medias").mkdir()
        self.info = self.root / "Cactus Canyon (Bally 1998).info"

    def _saved(self) -> dict:
        return json.loads(self.info.read_text(encoding="utf-8"))["assets"]

    def test_the_key_is_the_path_inside_the_folder(self) -> None:
        """Not a basename: medias/wheel.png and a wheel.png at the folder root are
        different files, and the old kind-keyed ledger could hold only one of them."""
        meta = MetaConfig(str(self.info))
        meta.add_asset(str(self.root / "medias" / "wheel.png"), "vpinmediadb", "d80f67")
        meta.add_asset(str(self.root / "wheel.png"), "user")

        self.assertEqual(sorted(self._saved()), ["medias/wheel.png", "wheel.png"])

    def test_a_download_records_its_host_and_the_hash_it_published(self) -> None:
        meta = MetaConfig(str(self.info))
        meta.add_asset(str(self.root / "medias" / "bg.png"), "vpinmediadb", "d80f67")

        self.assertEqual(self._saved()["medias/bg.png"],
                         {"source": {"host": "vpinmediadb", "hash": "d80f67"}})

    def test_an_upload_records_no_hash(self) -> None:
        """A hash is only meaningful as a comparison against a remote, and a file the
        user handed us has none."""
        meta = MetaConfig(str(self.info))
        meta.add_asset(str(self.root / "medias" / "bg.png"), "user")

        self.assertEqual(self._saved()["medias/bg.png"], {"source": {"host": "user"}})

    def test_a_per_build_asset_is_describable(self) -> None:
        """The reason the ledger moved off media kinds: two wheels, one game."""
        meta = MetaConfig(str(self.info))
        meta.add_asset(str(self.root / "medias" / "(Wheel) Cactus Canyon.png"), "user")
        meta.add_asset(str(self.root / "medias" / "(Wheel) Cactus Canyon VR.png"), "user")

        self.assertEqual(len(self._saved()), 2)

    def test_a_rebuild_keeps_assets_and_drops_the_old_medias_section(self) -> None:
        meta = MetaConfig(str(self.info))
        meta.add_asset(str(self.root / "medias" / "bg.png"), "vpinmediadb", "d80f67")
        meta.data["Medias"] = {"bg": {"Source": "vpinmediadb"}}
        meta.write_config()

        TestMetaConfig()._write_meta(self.info)
        saved = json.loads(self.info.read_text(encoding="utf-8"))

        self.assertIn("medias/bg.png", saved["assets"])
        self.assertNotIn("Medias", saved,
                         "superseded and ours, so it must not survive as unmanaged")


class ForgetTableTests(unittest.TestCase):
    """Dropping the record of a table whose file is gone.

    There is no file to delete - only the entry describing one - so the guard is that
    the entry says it is absent. Putting the .vpx back and refreshing is the undo.
    """

    def setUp(self) -> None:
        self._dir = TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.info = Path(self._dir.name) / "T.info"

    def _meta(self, default_id: str = "") -> MetaConfig:
        self.info.write_text(json.dumps({
            "Info": {"Title": "T"}, "User": {},
            "vpinfe": {"game_id": "g", "default_table": default_id,
                       "alt_vpsid": "USER-TYPED"},
            "tables": {
                "keep": {"id": "keep", "filename": "a.vpx", "file_hash": "h1"},
                "gone": {"id": "gone", "filename": "b.vpx", "file_hash": "h2",
                         "absent_since": "2026-08-23T18:24:08Z"},
            },
        }))
        return MetaConfig(str(self.info))

    def _stored(self) -> dict:
        return json.loads(self.info.read_text())

    def test_a_table_still_on_disk_is_refused(self) -> None:
        """Its entry holds stats and match records, and hiding is what takes it
        out of play."""
        self.assertFalse(self._meta().forget_table("keep"))
        self.assertIn("keep", self._stored()["tables"])

    def test_an_absent_table_is_dropped(self) -> None:
        self.assertTrue(self._meta().forget_table("gone"))
        self.assertEqual(list(self._stored()["tables"]), ["keep"])

    def test_an_unknown_id_is_refused(self) -> None:
        self.assertFalse(self._meta().forget_table("nope"))

    def test_forgetting_the_default_clears_it_and_parks_the_vps_override(self) -> None:
        """The stored default is a table id, so leaving it would name a table nothing
        describes - and the manual VPS match was claimed against that table."""
        self._meta(default_id="gone").forget_table("gone")

        vpinfe = self._stored()["vpinfe"]
        self.assertEqual(vpinfe["default_table"], "")
        self.assertEqual(vpinfe["alt_vpsid"], "")
        self.assertEqual(vpinfe["alt_vpsid_previous"]["value"], "USER-TYPED")
        self.assertEqual(vpinfe["alt_vpsid_previous"]["table"], "b.vpx")

    def test_forgetting_another_table_leaves_the_default_alone(self) -> None:
        self._meta(default_id="keep").forget_table("gone")

        vpinfe = self._stored()["vpinfe"]
        self.assertEqual(vpinfe["default_table"], "keep")
        self.assertEqual(vpinfe["alt_vpsid"], "USER-TYPED",
                         "adding or losing a peer is not a reason to drop the match")
