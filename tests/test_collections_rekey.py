import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from common.metaconfig import MetaConfig
from common.vpxcollections import CURRENT_SCHEMA, SCHEMA_SECTION, VPXCollections


def _table(root: Path, name: str, *, vpsid: str = "", altvpsid: str = "", table_id: str = ""):
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"Info": {"VPSId": vpsid, "Title": name}, "VPinFE": {}}
    if altvpsid:
        meta["VPinFE"]["altvpsid"] = altvpsid
    if table_id:
        meta["VPinFE"]["id"] = table_id
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
        self.assertEqual(collections.get_vpsids("Favorites"), ["id-mm"])

    def test_it_runs_once(self) -> None:
        table = _table(self.root, "MM", vpsid="vps-mm", table_id="id-mm")
        collections = _collections(self.ini, {"Favorites": ["vps-mm"]})
        collections.migrate_membership_to_table_ids([table])

        again = VPXCollections(str(self.ini))

        self.assertEqual(again.schema_version(), CURRENT_SCHEMA)
        self.assertEqual(again.migrate_membership_to_table_ids([table]), 0)
        self.assertEqual(again.get_vpsids("Favorites"), ["id-mm"])

    def test_a_newer_file_is_left_alone(self) -> None:
        """An older build must not rewrite membership it does not understand."""
        table = _table(self.root, "MM", vpsid="vps-mm", table_id="id-mm")
        collections = _collections(self.ini, {"Favorites": ["something-new"]})
        collections._stamp_schema(CURRENT_SCHEMA + 5)
        collections.save()

        reopened = VPXCollections(str(self.ini))
        with self.assertLogs("vpinfe.common.vpxcollections", level="WARNING"):
            moved = reopened.migrate_membership_to_table_ids([table])

        self.assertEqual(moved, 0)
        self.assertEqual(reopened.get_vpsids("Favorites"), ["something-new"])

    def test_an_entry_with_no_matching_table_is_kept(self) -> None:
        """The table may just not be here now; dropping it loses the membership."""
        table = _table(self.root, "MM", vpsid="vps-mm", table_id="id-mm")
        collections = _collections(self.ini, {"Favorites": ["vps-mm", "vps-gone"]})

        collections.migrate_membership_to_table_ids([table])

        self.assertEqual(sorted(collections.get_vpsids("Favorites")), ["id-mm", "vps-gone"])

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

        self.assertEqual(collections.get_vpsids("Favorites"), ["id-mm"])


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

        self.assertTrue(collections.is_member(table, set(collections.get_vpsids("Favorites"))))

    def test_two_tables_sharing_a_vps_id_are_distinguishable(self) -> None:
        """Defect 2: one VPS id, two tables - membership could not tell them apart."""
        a = _table(self.root, "A", vpsid="shared", table_id="id-a")
        b = _table(self.root, "B", vpsid="shared", table_id="id-b")
        collections = _collections(self.ini, {"Favorites": ["id-a"]})
        members = set(collections.get_vpsids("Favorites"))

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
                "vpxdata": {"filename": "MM.vpx", "fileHash": filehash, "tableVersion": "1",
                            "releaseDate": "", "tableSaveDate": "", "tableSaveRev": "",
                            "companyName": "", "companyYear": "", "tableType": "",
                            "codeSha256Hash": "", "rom": "", "authorName": "",
                            "detectnfozzy": False, "detectfleep": False, "detectssf": False,
                            "detectlut": False, "detectscorebit": False,
                            "detectfastflips": False, "detectflex": False},
            })
            return json.loads(info.read_text(encoding="utf-8"))

        first = rebuild("hash-a")
        table_id_value = first["VPinFE"]["id"]

        # User re-points the table, then updates the .vpx - which clears altvpsid.
        data = json.loads(info.read_text(encoding="utf-8"))
        data["VPinFE"]["altvpsid"] = "vps-override"
        info.write_text(json.dumps(data), encoding="utf-8")
        after = rebuild("hash-b")

        self.assertEqual(after["VPinFE"]["altvpsid"], "", "precondition: altvpsid cleared")

        table = SimpleNamespace(fullPathTable=str(self.root), tableDirName="MM",
                                metaConfig=after)
        collections = _collections(self.ini, {"Favorites": []})

        # Keyed the old way - the alt VPS id the user had set - membership is gone,
        # because that value now matches neither the base nor the (cleared) alt.
        self.assertFalse(collections.is_member(table, {"vps-override"}),
                         "this is the orphaning the re-key exists to fix")

        # Keyed by the table's own id, it survives.
        self.assertTrue(collections.is_member(table, {table_id_value}))


if __name__ == "__main__":
    unittest.main()
