import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from common import table_identity
from common.metaconfig import MetaConfig
from common.table_repository import table_to_row


def _table(root: Path, name: str = "Example", meta: dict | None = None):
    """A table folder with a .info file, shaped like TableParser produces."""
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    if meta is not None:
        (folder / f"{name}.info").write_text(json.dumps(meta), encoding="utf-8")
    return SimpleNamespace(
        fullPathTable=str(folder),
        fullPathVPXfile=str(folder / f"{name}.vpx"),
        tableDirName=name,
        metaConfig=meta or {},
    )


class TableIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_reading_an_unassigned_table_returns_empty_and_writes_nothing(self) -> None:
        table = _table(self.root, meta={"Info": {"VPSId": "vps-1"}})
        info = Path(table.fullPathTable) / "Example.info"
        before = info.read_text(encoding="utf-8")

        self.assertEqual(table_identity.table_id(table), "")
        self.assertEqual(info.read_text(encoding="utf-8"), before)

    def test_ensure_id_mints_and_persists(self) -> None:
        table = _table(self.root, meta={"Info": {"VPSId": "vps-1"}})

        minted = table_identity.ensure_id(table)
        info = Path(table.fullPathTable) / "Example.info"
        on_disk = json.loads(info.read_text(encoding="utf-8"))

        self.assertTrue(minted)
        self.assertEqual(on_disk["VPinFE"]["id"], minted)
        self.assertEqual(table_identity.table_id(table), minted)

    def test_ensure_id_is_stable_across_calls(self) -> None:
        table = _table(self.root, meta={"Info": {"VPSId": "vps-1"}})

        first = table_identity.ensure_id(table)
        second = table_identity.ensure_id(table)

        self.assertEqual(first, second)

    def test_ensure_id_adopts_an_id_already_on_disk(self) -> None:
        """The in-memory copy can be stale; disk wins over minting a second id."""
        table = _table(self.root, meta={"Info": {"VPSId": "vps-1"}})
        info = Path(table.fullPathTable) / "Example.info"
        info.write_text(json.dumps({"Info": {"VPSId": "vps-1"}, "VPinFE": {"id": "already-here"}}),
                        encoding="utf-8")

        self.assertEqual(table_identity.ensure_id(table), "already-here")

    def test_ensure_id_preserves_the_rest_of_the_meta(self) -> None:
        table = _table(self.root, meta={
            "Info": {"VPSId": "vps-1", "Title": "Example"},
            "User": {"Rating": 4},
            "VPinFE": {"alttitle": "My Example"},
        })

        table_identity.ensure_id(table)
        info = Path(table.fullPathTable) / "Example.info"
        on_disk = json.loads(info.read_text(encoding="utf-8"))

        self.assertEqual(on_disk["User"]["Rating"], 4)
        self.assertEqual(on_disk["VPinFE"]["alttitle"], "My Example")
        self.assertEqual(on_disk["Info"]["Title"], "Example")


class IdentityOutlivesVpsIdTests(unittest.TestCase):
    """The cases that make the VPS-derived id unusable as a primary key."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _rebuild(self, path: Path, filehash: str) -> dict:
        """Run a metadata rebuild the way build_metadata does."""
        meta = MetaConfig(str(path))
        meta.writeConfigMeta({
            "vpsdata": {"id": "vps-1", "name": "Example", "manufacturer": "Bally",
                        "year": "1990", "type": "SS", "theme": [], "ipdbUrl": ""},
            "vpxdata": {"filename": "Example.vpx", "fileHash": filehash, "tableVersion": "1.0",
                        "releaseDate": "", "tableSaveDate": "", "tableSaveRev": "",
                        "companyName": "Bally", "companyYear": "1990", "tableType": "SS",
                        "codeSha256Hash": "", "rom": "", "authorName": "",
                        "detectnfozzy": False, "detectfleep": False, "detectssf": False,
                        "detectlut": False, "detectscorebit": False, "detectfastflips": False,
                        "detectflex": False},
        })
        return json.loads(path.read_text(encoding="utf-8"))

    def test_a_metadata_rebuild_mints_an_id(self) -> None:
        info = self.root / "Example.info"

        rebuilt = self._rebuild(info, "hash-a")

        self.assertTrue(rebuilt["VPinFE"]["id"])

    def test_the_id_survives_a_table_file_update_that_clears_altvpsid(self) -> None:
        """altvpsid is cleared when the .vpx changes; the table id must not be."""
        info = self.root / "Example.info"
        first = self._rebuild(info, "hash-a")
        table_id = first["VPinFE"]["id"]

        # User re-points the table at different VPSdb metadata, then updates the .vpx.
        data = json.loads(info.read_text(encoding="utf-8"))
        data["VPinFE"]["altvpsid"] = "vps-override"
        info.write_text(json.dumps(data), encoding="utf-8")
        after = self._rebuild(info, "hash-b")

        self.assertEqual(after["VPinFE"]["altvpsid"], "", "precondition: altvpsid is cleared")
        self.assertEqual(after["VPinFE"]["id"], table_id)

    def test_the_id_survives_repeated_rebuilds(self) -> None:
        info = self.root / "Example.info"

        first = self._rebuild(info, "hash-a")["VPinFE"]["id"]
        second = self._rebuild(info, "hash-a")["VPinFE"]["id"]

        self.assertEqual(first, second)

    def test_a_table_vpsdb_never_matched_still_gets_an_id(self) -> None:
        """The VPS-derived id is empty here, which is why it can't be the key."""
        table = _table(self.root, "Unmatched", meta={"Info": {"VPSId": ""}})

        minted = table_identity.ensure_id(table)
        row = table_to_row(table)

        self.assertTrue(minted)
        self.assertEqual(row["vpsid"], "", "precondition: no VPS-derived id")
        self.assertEqual(row["vpinfe_id"], minted)


class UniquenessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_ensure_unique_ids_assigns_every_table(self) -> None:
        tables = [_table(self.root, n, meta={"Info": {}}) for n in ("A", "B", "C")]

        by_id = table_identity.ensure_unique_ids(tables)

        self.assertEqual(len(by_id), 3)
        self.assertTrue(all(table_identity.table_id(t) for t in tables))

    def test_a_copied_table_folder_gets_a_fresh_id(self) -> None:
        original = _table(self.root, "Original", meta={"Info": {}})
        assigned = table_identity.ensure_id(original)
        # Copying the folder copies the .info, and with it the id.
        copy = _table(self.root, "Copy", meta={"Info": {}, "VPinFE": {"id": assigned}})

        with self.assertLogs("vpinfe.common.table_identity", level="WARNING"):
            by_id = table_identity.ensure_unique_ids([original, copy])

        self.assertNotEqual(table_identity.table_id(copy), assigned)
        self.assertEqual(table_identity.table_id(original), assigned)
        self.assertEqual(len(by_id), 2)


class LookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_find_by_id_returns_the_matching_table(self) -> None:
        wanted = _table(self.root, "Wanted", meta={"Info": {}})
        other = _table(self.root, "Other", meta={"Info": {}})
        wanted_id = table_identity.ensure_id(wanted)
        table_identity.ensure_id(other)

        self.assertIs(table_identity.find_by_id([other, wanted], wanted_id), wanted)

    def test_find_by_id_rejects_missing_and_blank_ids(self) -> None:
        unassigned = _table(self.root, "Unassigned", meta={"Info": {}})

        self.assertIsNone(table_identity.find_by_id([unassigned], "no-such-id"))
        self.assertIsNone(table_identity.find_by_id([unassigned], ""))


class RowFieldTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_a_row_carries_correlation_ids_and_identity_separately(self) -> None:
        """VPS ids correlate with other services; vpinfe_id is what identifies the table."""
        table = _table(self.root, meta={
            "Info": {"VPSId": "vps-1"},
            "VPinFE": {"altvpsid": "vps-override"},
        })
        assigned = table_identity.ensure_id(table)

        row = table_to_row(table)

        self.assertEqual(row["vpsid"], "vps-1")
        self.assertEqual(row["altvpsid"], "vps-override")
        self.assertEqual(row["vpinfe_id"], assigned)
        # There is no derived "id" to pick up by accident.
        self.assertNotIn("id", row)

    def test_row_reports_an_empty_table_id_before_one_is_assigned(self) -> None:
        table = _table(self.root, meta={"Info": {"VPSId": "vps-1"}})

        self.assertEqual(table_to_row(table)["vpinfe_id"], "")


if __name__ == "__main__":
    unittest.main()
