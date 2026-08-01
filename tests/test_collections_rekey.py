import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from common.tables import table_repository
from common.tables.metaconfig import MetaConfig
from common.tables.vpxcollections import (
    CURRENT_SCHEMA,
    SCHEMA_SECTION,
    VPXCollections,
    collections_schema,
    restorable_collections_backup,
)


def _table(root: Path, name: str, *, vpsid: str = "", altvpsid: str = "", table_id: str = ""):
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"Info": {"VPSId": vpsid, "Title": name}, "vpinfe": {}}
    if altvpsid:
        meta["vpinfe"]["alt_vpsid"] = altvpsid
    if table_id:
        meta["vpinfe"]["id"] = table_id
    (folder / f"{name}.info").write_text(json.dumps(meta), encoding="utf-8")
    return SimpleNamespace(fullPathTable=str(folder), tableDirName=name, metaConfig=meta)


def _collections(path: Path, sections: dict) -> VPXCollections:
    lines = []
    for name, members in sections.items():
        lines.append(f"[{name}]")
        lines.append(f"vpsids = {','.join(members)}")
        lines.append("type = vpsid")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return VPXCollections(str(path))


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.ini = self.root / "collections.ini"

    def test_membership_moves_onto_table_ids(self) -> None:
        table = _table(self.root, "Medieval Madness", vpsid="vps-mm", table_id="id-mm")
        collections = _collections(self.ini, {"Favorites": ["vps-mm"]})

        moved = collections.migrate_membership_to_table_ids([table])

        self.assertEqual(moved, 1)
        self.assertEqual(collections.get_members("Favorites"), ["id-mm"])

    def test_it_runs_once(self) -> None:
        table = _table(self.root, "MM", vpsid="vps-mm", table_id="id-mm")
        collections = _collections(self.ini, {"Favorites": ["vps-mm"]})
        collections.migrate_membership_to_table_ids([table])

        again = VPXCollections(str(self.ini))

        self.assertEqual(again.schema_version(), CURRENT_SCHEMA)
        self.assertEqual(again.migrate_membership_to_table_ids([table]), 0)
        self.assertEqual(again.get_members("Favorites"), ["id-mm"])

    def test_a_newer_file_is_left_alone(self) -> None:
        """An older build must not rewrite membership it does not understand."""
        table = _table(self.root, "MM", vpsid="vps-mm", table_id="id-mm")
        collections = _collections(self.ini, {"Favorites": ["something-new"]})
        collections._stamp_schema(CURRENT_SCHEMA + 5)
        collections.save()

        reopened = VPXCollections(str(self.ini))
        with self.assertLogs("vpinfe.common.tables.vpxcollections", level="WARNING"):
            moved = reopened.migrate_membership_to_table_ids([table])

        self.assertEqual(moved, 0)
        self.assertEqual(reopened.get_members("Favorites"), ["something-new"])

    def test_an_entry_with_no_matching_table_is_kept(self) -> None:
        """The table may just not be here now; dropping it loses the membership."""
        table = _table(self.root, "MM", vpsid="vps-mm", table_id="id-mm")
        collections = _collections(self.ini, {"Favorites": ["vps-mm", "vps-gone"]})

        collections.migrate_membership_to_table_ids([table])

        self.assertEqual(sorted(collections.get_members("Favorites")), ["id-mm", "vps-gone"])

    def test_the_reserved_section_is_not_a_collection(self) -> None:
        table = _table(self.root, "MM", vpsid="vps-mm", table_id="id-mm")
        collections = _collections(self.ini, {"Favorites": ["vps-mm"]})
        collections.migrate_membership_to_table_ids([table])

        reopened = VPXCollections(str(self.ini))

        self.assertEqual(reopened.get_collections_name(), ["Favorites"])
        self.assertIn(SCHEMA_SECTION, reopened.config.sections())

    def test_membership_recorded_under_an_alt_vpsid_still_migrates(self) -> None:
        table = _table(self.root, "MM", vpsid="vps-base", altvpsid="vps-alt", table_id="id-mm")
        collections = _collections(self.ini, {"Favorites": ["vps-alt"]})

        collections.migrate_membership_to_table_ids([table])

        self.assertEqual(collections.get_members("Favorites"), ["id-mm"])


class MembershipTests(unittest.TestCase):
    """The four defects that made VPS-keyed membership unusable."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.ini = self.root / "collections.ini"

    def test_a_table_vpsdb_never_matched_can_join_a_collection(self) -> None:
        """Defect 1: its VPS id is empty, so it could not be a member at all."""
        table = _table(self.root, "Homebrew", vpsid="", table_id="id-home")
        collections = _collections(self.ini, {"Favorites": ["id-home"]})

        self.assertTrue(collections.is_member(table, set(collections.get_members("Favorites"))))

    def test_two_tables_sharing_a_vps_id_are_distinguishable(self) -> None:
        """Defect 2: one VPS id, two tables - membership could not tell them apart."""
        a = _table(self.root, "A", vpsid="shared", table_id="id-a")
        b = _table(self.root, "B", vpsid="shared", table_id="id-b")
        collections = _collections(self.ini, {"Favorites": ["id-a"]})
        members = set(collections.get_members("Favorites"))

        self.assertTrue(collections.is_member(a, members))
        self.assertFalse(collections.is_member(b, members))

    def test_membership_survives_a_vpx_update_clearing_altvpsid(self) -> None:
        """Defects 3 and 4: a rebuild after a .vpx change clears altvpsid, and
        membership recorded under it used to be orphaned."""
        info = self.root / "MM.info"

        def rebuild(filehash):
            meta = MetaConfig(str(info))
            meta.writeConfigMeta({
                "vpsdata": {"id": "vps-mm", "name": "MM", "manufacturer": "Williams",
                            "year": "1997", "type": "SS", "theme": [], "ipdbUrl": ""},
                "vpxdata": {"filename": "MM.vpx", "file_hash": filehash, "version": "1",
                            "release_date": "", "save_date": "", "save_rev": "",
                            "manufacturer": "", "year": "", "type": "",
                            "vbs_hash": "", "rom": "", "author_name": "",
                            "detect_nfozzy": False, "detect_fleep": False, "detect_ssf": False,
                            "detect_lut": False, "detect_scorbit": False,
                            "detect_fastflips": False, "detect_flex": False},
            })
            return json.loads(info.read_text(encoding="utf-8"))

        first = rebuild("hash-a")
        table_id_value = first["vpinfe"]["id"]

        # User re-points the table, then updates the .vpx - which clears altvpsid.
        data = json.loads(info.read_text(encoding="utf-8"))
        data["vpinfe"]["alt_vpsid"] = "vps-override"
        info.write_text(json.dumps(data), encoding="utf-8")
        after = rebuild("hash-b")

        self.assertEqual(after["vpinfe"]["alt_vpsid"], "", "precondition: altvpsid cleared")

        table = SimpleNamespace(fullPathTable=str(self.root), tableDirName="MM",
                                metaConfig=after)
        collections = _collections(self.ini, {"Favorites": []})

        # Keyed the old way - the alt VPS id the user had set - membership is gone,
        # because that value now matches neither the base nor the (cleared) alt.
        self.assertFalse(collections.is_member(table, {"vps-override"}),
                         "this is the orphaning the re-key exists to fix")

        # Keyed by the table's own id, it survives.
        self.assertTrue(collections.is_member(table, {table_id_value}))


class DisplayPathTests(unittest.TestCase):
    """The Manager UI resolves collections by map lookup, not is_member().

    Both paths have to agree. When they did not, migrating simply emptied the
    collections column - membership was intact on disk and correct in the frontend,
    and the only symptom was a table row that had stopped saying what it belonged to.
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.ini = self.root / "collections.ini"

    def _row_for(self, table):
        with mock.patch.object(table_repository, "COLLECTIONS_PATH", self.ini):
            mapping = table_repository.collections_by_table_id()
        return table_repository.table_to_row(table, mapping)

    def test_a_migrated_collection_still_shows_on_the_table_row(self) -> None:
        table = _table(self.root, "Medieval Madness", vpsid="vps-mm", table_id="id-mm")
        table.fullPathVPXfile = str(self.root / "Medieval Madness" / "MM.vpx")
        collections = _collections(self.ini, {"Favorites": ["vps-mm"]})

        collections.migrate_membership_to_table_ids([table])

        self.assertEqual(self._row_for(table)["collections"], ["Favorites"],
                         "the migration must not empty the collections column")

    def test_an_entry_the_migration_could_not_resolve_still_shows(self) -> None:
        """It stays VPS-keyed, and the migration will not run again to fix it.

        Happens when the table was not installed at migration time. is_member()
        tolerates this, so the row lookup has to as well or the two disagree.
        """
        table = _table(self.root, "Late Arrival", vpsid="vps-late", table_id="id-late")
        table.fullPathVPXfile = str(self.root / "Late Arrival" / "Late.vpx")
        collections = _collections(self.ini, {"Favorites": ["vps-late"]})
        collections._stamp_schema()
        collections.save()

        self.assertEqual(collections.get_members("Favorites"), ["vps-late"],
                         "precondition: the entry was never rewritten")
        self.assertEqual(self._row_for(table)["collections"], ["Favorites"])

    def test_an_entry_keyed_by_alt_vps_id_still_shows(self) -> None:
        table = _table(self.root, "Repointed", vpsid="vps-base",
                       altvpsid="vps-alt", table_id="id-repointed")
        table.fullPathVPXfile = str(self.root / "Repointed" / "Repointed.vpx")
        _collections(self.ini, {"Favorites": ["vps-alt"]})

        self.assertEqual(self._row_for(table)["collections"], ["Favorites"])

    def test_a_table_with_no_vps_id_shows_its_collections(self) -> None:
        """The row lookup has to key on the table id, not on anything VPS-derived."""
        table = _table(self.root, "Homebrew", vpsid="", table_id="id-home")
        table.fullPathVPXfile = str(self.root / "Homebrew" / "Homebrew.vpx")
        _collections(self.ini, {"Favorites": ["id-home"]})

        self.assertEqual(self._row_for(table)["collections"], ["Favorites"])

    def test_filter_collections_are_not_in_the_map(self) -> None:
        """They have no member list; membership is decided per table when displayed."""
        self.ini.write_text("[Recent]\ntype = filter\nletter = All\n", encoding="utf-8")

        with mock.patch.object(table_repository, "COLLECTIONS_PATH", self.ini):
            self.assertEqual(table_repository.collections_by_table_id(), {})


if __name__ == "__main__":
    unittest.main()


class BackupTests(unittest.TestCase):
    """Collections are the other file this branch rewrites.

    The .info migration has kept a copy since the start; this one did not, and it moves
    membership onto ids an older build cannot resolve - so without a copy a downgrade left
    every collection reading as empty with nothing to go back to.
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.ini = self.root / "collections.ini"

    def _backups(self):
        return sorted(p for p in self.root.iterdir() if ".vpinfe-" in p.name)

    def test_the_migration_keeps_the_file_it_is_about_to_rewrite(self):
        collections = _collections(self.ini, {"Favorites": ["vps-1"]})
        before = self.ini.read_text(encoding="utf-8")

        collections.migrate_membership_to_table_ids(
            [_table(self.root, "Dr. Dude", vpsid="vps-1", table_id="tid-1")])

        backups = self._backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), before)

    def test_a_run_that_changes_nothing_leaves_no_backup(self):
        """It records that it has run, so a second startup does no work and keeps no copy."""
        collections = _collections(self.ini, {"Favorites": ["vps-1"]})
        collections.migrate_membership_to_table_ids(
            [_table(self.root, "Dr. Dude", vpsid="vps-1", table_id="tid-1")])

        VPXCollections(str(self.ini)).migrate_membership_to_table_ids([])

        self.assertEqual(len(self._backups()), 1)

    def test_the_saved_copy_is_the_one_this_build_would_restore(self):
        collections = _collections(self.ini, {"Favorites": ["vps-1"]})
        collections.migrate_membership_to_table_ids(
            [_table(self.root, "Dr. Dude", vpsid="vps-1", table_id="tid-1")])

        chosen = restorable_collections_backup(self.root)

        self.assertIsNotNone(chosen)
        self.assertIsNone(collections_schema(chosen),
                          "the pre-migration copy predates versioning")

    def test_an_interrupted_save_leaves_the_previous_file_intact(self):
        collections = _collections(self.ini, {"Favorites": ["vps-1"]})
        before = self.ini.read_text(encoding="utf-8")

        with mock.patch.object(collections.config, "write",
                               side_effect=OSError("disk went away")):
            with self.assertRaises(OSError):
                collections.save()

        self.assertEqual(self.ini.read_text(encoding="utf-8"), before)
        self.assertEqual([p.name for p in self.root.iterdir()], ["collections.ini"])
