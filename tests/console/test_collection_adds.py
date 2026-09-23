"""The one add every surface shares: what it writes, what it leaves, and its Undo."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from common.games import collection_ops
from common.games.collection_store import CollectionStore
from console import collection_adds
from console.collection_adds import GAMES, TABLES, Row, Wrote
from tests.support.library import TempTree, fake_game, game_info, write_game


class _Library:
    """The Console's library, answered by the service instead of over HTTP."""

    def load_collections(self) -> list[dict[str, Any]]:
        return collection_ops.listing()["collections"]

    def collection_members(self, name: str) -> dict[str, Any]:
        return collection_ops.members_of(name)

    def add_to_collection(self, name: str, game: str, table: str = "") -> None:
        collection_ops.add_member(name, game, table)

    def remove_from_collection(self, name: str, game: str,
                               table: str | None = None) -> None:
        collection_ops.remove_member(name, game, table)

    def exclude_from_collection(self, name: str, game: str, table: str = "") -> None:
        collection_ops.exclude(name, game, table)

    def unexclude_from_collection(self, name: str, game: str,
                                  table: str | None = None) -> None:
        collection_ops.unexclude(name, game, table)

    def set_collection_order(self, name: str, games: list[str]) -> None:
        collection_ops.set_arrangement(name, games)

    def patch_collection(self, name: str, changes: dict[str, Any]) -> dict[str, Any]:
        return collection_ops.patch(name, **changes)


def _game(root: Path, game_id: str, title: str, maker: str,
          tables: dict | None = None, default: str = "") -> Any:
    tables = tables or {game_id: {"id": game_id, "filename": f"{title}.vpx"}}
    info = game_info(title, vps_id="", game_id=game_id, tables=tables,
                     Info={"Manufacturer": maker, "Year": "1995"})
    if default:
        info["vpinfe"]["default_table"] = default
    folder = write_game(root, title, info=info, vpx=False,
                        files={one["filename"]: b"x" for one in tables.values()})
    return fake_game(folder, title, meta=info)


class AddingToACollection(TempTree):
    def setUp(self) -> None:
        super().setUp()
        store = CollectionStore(str(self.root / "collections.json"))
        self.store = store
        with store.mutate():
            store.add_collection("Friday Night", ["mm", "bk"])
            store.add_filter_collection("Bally", manufacturer="Bally", sort_by="Alpha")
        games = self.root / "games"
        catalog = {"mm": _game(games, "mm", "Medieval Madness", "Williams"),
                   "afm": _game(games, "afm", "Attack from Mars", "Bally",
                                {"a1": {"id": "a1", "filename": "AFM 1.vpx"},
                                 "a2": {"id": "a2", "filename": "AFM 2.vpx"}},
                                default="a2"),
                   "taf": _game(games, "taf", "The Addams Family", "Bally"),
                   "bk": _game(games, "bk", "Black Knight", "Williams"),
                   "xen": _game(games, "xen", "Xenon", "Williams")}
        for target in ("common.games.collection_ops.get_collections_manager",
                       "common.games.collections_service.get_collections_manager"):
            patcher = patch(target, lambda: store)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("common.games.game_repository.catalog", lambda: catalog)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.library = _Library()

    def _refs(self, name: str) -> list[dict]:
        return self.store.get_member_refs(name)

    def test_a_game_it_holds_is_left_alone_and_counted(self) -> None:
        wrote = collection_adds.write(self.library, "Friday Night", [Row("mm"), Row("xen")])

        self.assertEqual((1, [Row("xen")]), (wrote.held, wrote.written))
        self.assertEqual([{"game": "mm"}, {"game": "bk"}, {"game": "xen"}],
                         self._refs("Friday Night"))

    def test_a_table_is_held_to_that_table(self) -> None:
        collection_adds.write(self.library, "Friday Night", [Row("afm", "a1")])

        self.assertIn({"game": "afm", "table": "a1"}, self._refs("Friday Night"))

    def test_a_table_it_already_plays_by_default_is_held(self) -> None:
        with self.store.mutate():
            self.store.add_member("Friday Night", "afm")

        wrote = collection_adds.write(self.library, "Friday Night", [Row("afm", "a2")])

        self.assertEqual((1, []), (wrote.held, wrote.written))

    def test_a_game_its_rules_match_is_held_by_a_smart_one(self) -> None:
        wrote = collection_adds.write(self.library, "Bally", [Row("afm")])

        self.assertEqual((1, 0), (wrote.held, wrote.added))

    def test_a_game_its_rules_do_not_bring_in_is_an_exception(self) -> None:
        wrote = collection_adds.write(self.library, "Bally", [Row("xen")])

        self.assertTrue(collection_adds.is_exception(wrote))
        self.assertEqual([{"game": "xen"}], self._refs("Bally"))

    def test_a_game_taken_out_is_put_back_rather_than_added(self) -> None:
        with self.store.mutate():
            self.store.exclude("Bally", "taf")

        wrote = collection_adds.write(self.library, "Bally", [Row("taf")])

        self.assertEqual((1, [], [Row("taf")]), (wrote.put_back, wrote.written, wrote.lifted))
        self.assertFalse(collection_adds.is_exception(wrote))
        self.assertEqual([], self.store.get_excluded_refs("Bally"))

    def test_undo_takes_back_exactly_what_was_written(self) -> None:
        with self.store.mutate():
            self.store.exclude("Bally", "taf")
        wrote = collection_adds.write(self.library, "Bally", [Row("taf"), Row("xen")])

        collection_adds.unwrite(self.library, "Bally", wrote)

        self.assertEqual([], self._refs("Bally"))
        self.assertEqual([{"game": "taf"}], self.store.get_excluded_refs("Bally"))

    def test_undo_leaves_a_row_that_was_there_before(self) -> None:
        wrote = collection_adds.write(self.library, "Friday Night", [Row("mm"), Row("xen")])

        collection_adds.unwrite(self.library, "Friday Night", wrote)

        self.assertEqual([{"game": "mm"}, {"game": "bk"}], self._refs("Friday Night"))

    def test_a_place_makes_the_order_custom_and_undo_puts_it_back(self) -> None:
        wrote = collection_adds.write(self.library, "Friday Night", [Row("xen")], at=1)

        # As listed, by title: Black Knight, then Medieval Madness.
        self.assertEqual(["bk", "xen", "mm"],
                         [ref["game"] for ref in self._refs("Friday Night")])
        self.assertEqual("manual", self.store.get_order("Friday Night")["by"])

        collection_adds.unwrite(self.library, "Friday Night", wrote)

        self.assertEqual("title", self.store.get_order("Friday Night")["by"])
        self.assertEqual(["bk", "mm"], [ref["game"] for ref in self._refs("Friday Night")])

    def test_a_smart_one_takes_no_place(self) -> None:
        wrote = collection_adds.write(self.library, "Bally", [Row("xen")], at=0)

        self.assertIsNone(wrote.order)
        self.assertNotEqual("manual", self.store.get_order("Bally")["by"])


class TheWords(TempTree):
    def test_one_game(self) -> None:
        self.assertEqual("Added to “Friday Night”", collection_adds.said(
            "Friday Night", Wrote(written=[Row("a")]), GAMES))

    def test_several_tables_and_how_many_were_already_in_it(self) -> None:
        self.assertEqual("Added 2 tables to “Friday Night”, 1 already in it",
                         collection_adds.said("Friday Night",
                                              Wrote(written=[Row("a", "1"), Row("b", "2")],
                                                    held=1), TABLES))

    def test_an_exception_says_so(self) -> None:
        self.assertEqual("Added 2 games to “Bally” as exceptions to its rules",
                         collection_adds.said("Bally", Wrote(
                             smart=True, written=[Row("a"), Row("b")]), GAMES))

    def test_a_game_put_back_in_a_smart_one_is_no_exception(self) -> None:
        self.assertEqual("Added to “Bally”", collection_adds.said(
            "Bally", Wrote(smart=True, put_back=1), GAMES))

    def test_nothing_added_says_they_were_there(self) -> None:
        self.assertEqual("All 3 already in “Bally”",
                         collection_adds.said("Bally", Wrote(held=3), GAMES))
