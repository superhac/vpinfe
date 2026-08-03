"""A table's id has to outlive its filename.

That is the whole reason it exists: a collection pins a table, play stats accrue against
one, and both have to survive somebody tidying up a `.vpx` name. So the tests that matter
are the ones about what happens when a file is renamed, copied, or rebuilt.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from common.games import ids, table_identity
from common.games.metaconfig import MetaConfig
from common.games.tables import TABLE_ID_KEY, TABLES_KEY, table_id


def _game(root: Path, name: str, meta: dict | None = None):
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    if meta is not None:
        (folder / f"{name}.info").write_text(json.dumps(meta), encoding="utf-8")
    return SimpleNamespace(
        fullPathGame=str(folder),
        fullPathVPXfile=str(folder / f"{name}.vpx"),
        gameDirName=name,
        metaConfig=meta or {},
    )


def _meta(*tables: tuple[str, dict]) -> dict:
    return {"vpinfe": {"schema": 2}, TABLES_KEY: dict(tables)}


class RebuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.info = self.root / "Example.info"

    def _rebuild(self, *files: tuple[str, dict]) -> dict:
        MetaConfig(str(self.info)).writeConfigMeta(
            {"vpsdata": {}, "gamefiles": dict(files)})
        return json.loads(self.info.read_text(encoding="utf-8"))[TABLES_KEY]

    def test_every_table_gets_an_id(self) -> None:
        built = self._rebuild(("a.vpx", {"file_hash": "aaa"}),
                              ("b.vpx", {"file_hash": "bbb"}))

        minted = {table_id(entry) for entry in built.values()}
        self.assertEqual(len(minted), 2, "two tables, two ids")
        for one in minted:
            self.assertEqual(len(one), ids.LENGTH)
            self.assertTrue(set(one) <= set(ids.ALPHABET))

    def test_a_rebuild_keeps_the_id_it_already_assigned(self) -> None:
        first = self._rebuild(("a.vpx", {"file_hash": "aaa"}))["a.vpx"][TABLE_ID_KEY]
        again = self._rebuild(("a.vpx", {"file_hash": "aaa"}))["a.vpx"][TABLE_ID_KEY]

        self.assertEqual(first, again)

    def test_a_renamed_file_keeps_its_id_and_everything_recorded_against_it(self) -> None:
        """The case the id exists for. Matched on content, because the name is what moved."""
        built = self._rebuild(("old.vpx", {"file_hash": "aaa"}))
        original = built["old.vpx"][TABLE_ID_KEY]

        # Whatever accumulated against the old name, as a rebuild would leave it.
        stored = json.loads(self.info.read_text(encoding="utf-8"))
        stored[TABLES_KEY]["old.vpx"].update(
            {"hidden": True, "user": {"start_count": 7}})
        self.info.write_text(json.dumps(stored), encoding="utf-8")

        renamed = self._rebuild(("new.vpx", {"file_hash": "aaa"}))

        self.assertNotIn("old.vpx", renamed)
        self.assertEqual(renamed["new.vpx"][TABLE_ID_KEY], original)
        self.assertTrue(renamed["new.vpx"]["hidden"])
        self.assertEqual(renamed["new.vpx"]["user"], {"start_count": 7})

    def test_a_copy_beside_the_original_is_a_new_table(self) -> None:
        """Both files are present, so neither is a rename - the second is genuinely new."""
        built = self._rebuild(("a.vpx", {"file_hash": "aaa"}),
                              ("copy.vpx", {"file_hash": "aaa"}))

        self.assertNotEqual(built["a.vpx"][TABLE_ID_KEY],
                            built["copy.vpx"][TABLE_ID_KEY])

    def test_a_changed_file_under_the_same_name_keeps_its_id(self) -> None:
        """Editing a .vpx is not a new table."""
        first = self._rebuild(("a.vpx", {"file_hash": "aaa"}))["a.vpx"][TABLE_ID_KEY]
        edited = self._rebuild(("a.vpx", {"file_hash": "zzz"}))["a.vpx"][TABLE_ID_KEY]

        self.assertEqual(first, edited)


class BackfillTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_entries_written_before_ids_existed_get_one(self) -> None:
        game = _game(self.root, "Old", _meta(("a.vpx", {"file_hash": "aaa"})))

        table_identity.ensure_unique_table_ids([game])

        on_disk = json.loads((self.root / "Old" / "Old.info").read_text(encoding="utf-8"))
        self.assertTrue(table_id(on_disk[TABLES_KEY]["a.vpx"]))

    def test_a_copied_folder_does_not_leave_two_tables_sharing_an_id(self) -> None:
        """The only collision that happens in practice: the .info was copied with the folder."""
        shared = {"file_hash": "aaa", TABLE_ID_KEY: "dupdupdup1"}
        first = _game(self.root, "First", _meta(("a.vpx", dict(shared))))
        second = _game(self.root, "Second", _meta(("a.vpx", dict(shared))))

        by_id = table_identity.ensure_unique_table_ids([first, second])

        self.assertEqual(len(by_id), 2)
        kept = json.loads((self.root / "First" / "First.info").read_text(encoding="utf-8"))
        remixed = json.loads((self.root / "Second" / "Second.info").read_text(encoding="utf-8"))
        self.assertEqual(table_id(kept[TABLES_KEY]["a.vpx"]), "dupdupdup1")
        self.assertNotEqual(table_id(remixed[TABLES_KEY]["a.vpx"]), "dupdupdup1")

    def test_a_game_that_needs_nothing_is_not_rewritten(self) -> None:
        """653 games on a network share: a needless write is a round trip each."""
        game = _game(self.root, "Done",
                     _meta(("a.vpx", {"file_hash": "aaa", TABLE_ID_KEY: "alreadyhere"})))
        info = self.root / "Done" / "Done.info"
        before = info.stat().st_mtime_ns

        table_identity.ensure_unique_table_ids([game])

        self.assertEqual(info.stat().st_mtime_ns, before)

    def test_an_id_addresses_one_table(self) -> None:
        game = _game(self.root, "Find",
                     _meta(("a.vpx", {TABLE_ID_KEY: "findme1234"}),
                           ("b.vpx", {TABLE_ID_KEY: "other12345"})))

        self.assertEqual(table_identity.find_table_by_id([game], "findme1234"),
                         (game, "a.vpx"))
        self.assertIsNone(table_identity.find_table_by_id([game], "nosuchid12"))


if __name__ == "__main__":
    unittest.main()
