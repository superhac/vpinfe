import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from common.games import game_identity
from common.games.game_repository import game_to_row
from common.games.metaconfig import MetaConfig


def _game(root: Path, name: str = "Example", meta: dict | None = None):
    """A game folder with a .info file, shaped like GameParser produces."""
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


class MintedIdTests(unittest.TestCase):
    """Short enough to read down a phone, long enough not to collide."""

    def test_an_id_is_short_and_unambiguous(self) -> None:
        minted = game_identity.new_id()

        self.assertEqual(len(minted), game_identity.ID_LENGTH)
        self.assertTrue(set(minted) <= set(game_identity.ID_ALPHABET))
        self.assertFalse(set(minted) & set("0OIl"), "these are misread out loud")

    def test_ids_do_not_repeat(self) -> None:
        minted = [game_identity.new_id() for _ in range(5000)]

        self.assertEqual(len(set(minted)), len(minted))

    def test_a_metadata_rebuild_mints_the_same_shape(self) -> None:
        """Two writers assign ids; only one format may come out of them."""
        info = self.root / "Example.info"
        MetaConfig(str(info)).writeConfigMeta({"vpsdata": {}, "vpxdata": {"filename": "x.vpx"}})

        minted = json.loads(info.read_text(encoding="utf-8"))["vpinfe"]["game_id"]
        self.assertEqual(len(minted), game_identity.ID_LENGTH)
        self.assertTrue(set(minted) <= set(game_identity.ID_ALPHABET))

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)


class GameIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_reading_an_unassigned_game_returns_empty_and_writes_nothing(self) -> None:
        game = _game(self.root, meta={"Info": {"VPSId": "vps-1"}})
        info = Path(game.fullPathGame) / "Example.info"
        before = info.read_text(encoding="utf-8")

        self.assertEqual(game_identity.game_id(game), "")
        self.assertEqual(info.read_text(encoding="utf-8"), before)

    def test_ensure_id_mints_and_persists(self) -> None:
        game = _game(self.root, meta={"Info": {"VPSId": "vps-1"}})

        minted = game_identity.ensure_id(game)
        info = Path(game.fullPathGame) / "Example.info"
        on_disk = json.loads(info.read_text(encoding="utf-8"))

        self.assertTrue(minted)
        self.assertEqual(on_disk["vpinfe"]["game_id"], minted)
        self.assertEqual(game_identity.game_id(game), minted)

    def test_ensure_id_is_stable_across_calls(self) -> None:
        game = _game(self.root, meta={"Info": {"VPSId": "vps-1"}})

        first = game_identity.ensure_id(game)
        second = game_identity.ensure_id(game)

        self.assertEqual(first, second)

    def test_ensure_id_adopts_an_id_already_on_disk(self) -> None:
        """The in-memory copy can be stale; disk wins over minting a second id."""
        game = _game(self.root, meta={"Info": {"VPSId": "vps-1"}})
        info = Path(game.fullPathGame) / "Example.info"
        info.write_text(json.dumps({"Info": {"VPSId": "vps-1"},
                                    "vpinfe": {"game_id": "already-here"}}),
                        encoding="utf-8")

        self.assertEqual(game_identity.ensure_id(game), "already-here")

    def test_ensure_id_preserves_the_rest_of_the_meta(self) -> None:
        game = _game(self.root, meta={
            "Info": {"VPSId": "vps-1", "Title": "Example"},
            "User": {"Rating": 4},
            "vpinfe": {"alt_title": "My Example"},
        })

        game_identity.ensure_id(game)
        info = Path(game.fullPathGame) / "Example.info"
        on_disk = json.loads(info.read_text(encoding="utf-8"))

        self.assertEqual(on_disk["User"]["Rating"], 4)
        self.assertEqual(on_disk["vpinfe"]["alt_title"], "My Example")
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
            "vpxdata": {"filename": "Example.vpx", "file_hash": filehash, "version": "1.0",
                        "release_date": "", "save_date": "", "save_rev": "",
                        "manufacturer": "Bally", "year": "1990", "type": "SS",
                        "vbs_hash": "", "rom": "", "author_name": "",
                        "detect_nfozzy": False, "detect_fleep": False, "detect_ssf": False,
                        "detect_lut": False, "detect_scorbit": False, "detect_fastflips": False,
                        "detect_flex": False},
        })
        return json.loads(path.read_text(encoding="utf-8"))

    def test_a_metadata_rebuild_mints_an_id(self) -> None:
        info = self.root / "Example.info"

        rebuilt = self._rebuild(info, "hash-a")

        self.assertTrue(rebuilt["vpinfe"]["game_id"])

    def test_the_id_survives_a_table_update_that_clears_altvpsid(self) -> None:
        """alt_vpsid is cleared when the .vpx changes; the game id must not be."""
        info = self.root / "Example.info"
        first = self._rebuild(info, "hash-a")
        game_id = first["vpinfe"]["game_id"]

        # User re-points the game at different VPSdb metadata, then updates the .vpx.
        data = json.loads(info.read_text(encoding="utf-8"))
        data["vpinfe"]["alt_vpsid"] = "vps-override"
        info.write_text(json.dumps(data), encoding="utf-8")
        after = self._rebuild(info, "hash-b")

        self.assertEqual(after["vpinfe"]["alt_vpsid"], "", "precondition: altvpsid is cleared")
        self.assertEqual(after["vpinfe"]["game_id"], game_id)

    def test_the_id_survives_repeated_rebuilds(self) -> None:
        info = self.root / "Example.info"

        first = self._rebuild(info, "hash-a")["vpinfe"]["game_id"]
        second = self._rebuild(info, "hash-a")["vpinfe"]["game_id"]

        self.assertEqual(first, second)

    def test_a_game_vpsdb_never_matched_still_gets_an_id(self) -> None:
        """The VPS-derived id is empty here, which is why it can't be the key."""
        game = _game(self.root, "Unmatched", meta={"Info": {"VPSId": ""}})

        minted = game_identity.ensure_id(game)
        row = game_to_row(game)

        self.assertTrue(minted)
        self.assertEqual(row["vpsid"], "", "precondition: no VPS-derived id")
        self.assertEqual(row["vpinfe_id"], minted)


class UniquenessTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_ensure_unique_ids_assigns_every_game(self) -> None:
        games = [_game(self.root, n, meta={"Info": {}}) for n in ("A", "B", "C")]

        by_id = game_identity.ensure_unique_ids(games)

        self.assertEqual(len(by_id), 3)
        self.assertTrue(all(game_identity.game_id(t) for t in games))

    def test_a_copied_game_folder_gets_a_fresh_id(self) -> None:
        original = _game(self.root, "Original", meta={"Info": {}})
        assigned = game_identity.ensure_id(original)
        # Copying the folder copies the .info, and with it the id.
        copy = _game(self.root, "Copy", meta={"Info": {}, "vpinfe": {"game_id": assigned}})

        with self.assertLogs("vpinfe.common.games.game_identity", level="WARNING"):
            by_id = game_identity.ensure_unique_ids([original, copy])

        self.assertNotEqual(game_identity.game_id(copy), assigned)
        self.assertEqual(game_identity.game_id(original), assigned)
        self.assertEqual(len(by_id), 2)


class LookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_find_by_id_returns_the_matching_game(self) -> None:
        wanted = _game(self.root, "Wanted", meta={"Info": {}})
        other = _game(self.root, "Other", meta={"Info": {}})
        wanted_id = game_identity.ensure_id(wanted)
        game_identity.ensure_id(other)

        self.assertIs(game_identity.find_by_id([other, wanted], wanted_id), wanted)

    def test_find_by_id_rejects_missing_and_blank_ids(self) -> None:
        unassigned = _game(self.root, "Unassigned", meta={"Info": {}})

        self.assertIsNone(game_identity.find_by_id([unassigned], "no-such-id"))
        self.assertIsNone(game_identity.find_by_id([unassigned], ""))


class RowFieldTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_a_row_carries_correlation_ids_and_identity_separately(self) -> None:
        """VPS ids correlate with other services; vpinfe_id is what identifies the game."""
        game = _game(self.root, meta={
            "Info": {"VPSId": "vps-1"},
            "vpinfe": {"alt_vpsid": "vps-override"},
        })
        assigned = game_identity.ensure_id(game)

        row = game_to_row(game)

        self.assertEqual(row["vpsid"], "vps-1")
        self.assertEqual(row["alt_vpsid"], "vps-override")
        self.assertEqual(row["vpinfe_id"], assigned)
        # There is no derived "id" to pick up by accident.
        self.assertNotIn("id", row)

    def test_row_reports_an_empty_game_id_before_one_is_assigned(self) -> None:
        game = _game(self.root, meta={"Info": {"VPSId": "vps-1"}})

        self.assertEqual(game_to_row(game)["vpinfe_id"], "")


if __name__ == "__main__":
    unittest.main()
