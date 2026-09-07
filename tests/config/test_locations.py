"""Where this install looks for entries: the list, and what the disk says about each."""

from __future__ import annotations

import json
import os
import unittest
from configparser import ConfigParser
from pathlib import Path
from tempfile import TemporaryDirectory

from common.games import locations
from common.games.locations import (
    KIND_GAME,
    KIND_ROOT,
    Location,
    LocationStore,
    canonical,
    state_of,
)


def _config(**values) -> ConfigParser:
    parser = ConfigParser()
    parser["general"] = {k: str(v) for k, v in values.items()}
    return parser


class _WithStore:
    """Shared setup. Not a TestCase, so subclassing it does not re-run its tests."""

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = LocationStore(self.root / "locations.json")

    def _location(self, name: str, kind: str = KIND_ROOT) -> Location:
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        return self.store.put(Location(location_id=locations.mint_location_id(),
                                       path=str(folder), kind=kind))


class StoreTests(_WithStore, unittest.TestCase):
    def test_a_missing_file_is_an_empty_list_rather_than_an_error(self) -> None:
        """A first run has none, and that is not a fault."""
        self.assertEqual(LocationStore(self.root / "nope.json").locations(), [])

    def test_roots_and_single_game_folders_coexist(self) -> None:
        self._location("share")
        self._location("One Table (Bally 1990)", kind=KIND_GAME)

        self.assertEqual(sorted(one.kind for one in self.store.locations()),
                         [KIND_GAME, KIND_ROOT])

    def test_adding_the_same_folder_twice_is_one_row(self) -> None:
        """Two rows for one place would each report their own state."""
        first = self._location("share")
        again = self.store.put(Location(location_id=locations.mint_location_id(),
                                        path=str(self.root / "share")))

        self.assertEqual(len(self.store.locations()), 1)
        self.assertEqual(again.location_id, first.location_id)

    def test_a_second_row_for_one_place_is_dropped_on_read(self) -> None:
        """A file edited by hand can hold it twice."""
        folder = self.root / "share"
        folder.mkdir()
        path = self.root / "locations.json"
        path.write_text(json.dumps({"schema": 1, "locations": [
            {"location_id": "a", "path": str(folder), "kind": KIND_ROOT},
            {"location_id": "b", "path": str(folder), "kind": KIND_ROOT},
        ]}))

        self.assertEqual([one.location_id for one in LocationStore(path).locations()],
                         ["a"])

    def test_removing_one_forgets_it_and_the_write_target_with_it(self) -> None:
        held = self._location("share")
        self.store.set_write_to(held.location_id)

        self.assertTrue(self.store.remove(held.location_id))
        self.assertEqual(self.store.locations(), [])
        self.assertIsNone(self.store.write_to())

    def test_removing_one_that_is_not_there_says_so(self) -> None:
        self.assertFalse(self.store.remove("nothing"))

    def test_an_unknown_id_cannot_become_the_write_target(self) -> None:
        self.assertFalse(self.store.set_write_to("nothing"))


class WriteTargetTests(_WithStore, unittest.TestCase):
    def test_the_named_one_wins(self) -> None:
        self._location("first")
        second = self._location("second")
        self.store.set_write_to(second.location_id)

        self.assertEqual(self.store.write_to().location_id, second.location_id)

    def test_an_unwritable_target_falls_back_to_one_that_works(self) -> None:
        """An install that has never been asked still has to be able to create
        something."""
        readonly = self._location("readonly")
        writable = self._location("writable")
        self.store.set_write_to(readonly.location_id)
        os.chmod(readonly.path, 0o500)
        self.addCleanup(os.chmod, readonly.path, 0o700)

        self.assertEqual(self.store.write_to().location_id, writable.location_id)

    def test_a_single_game_folder_is_never_the_write_target(self) -> None:
        """A new entry's folder is created inside a root. There is no room in a
        location that is itself one game."""
        self._location("One Table (Bally 1990)", kind=KIND_GAME)

        self.assertIsNone(self.store.write_to())


class StateTests(unittest.TestCase):
    def test_a_folder_that_is_not_there_is_unreachable_with_a_reason(self) -> None:
        state = state_of(Location("id", "/nowhere/at/all"))

        self.assertFalse(state.reachable)
        self.assertTrue(state.reason)

    def test_a_read_only_share_is_reachable_and_not_writable(self) -> None:
        """A read-only export is a real case, and it belongs on the row beside
        reachable."""
        with TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o500)
            try:
                state = state_of(Location("id", tmp))
            finally:
                os.chmod(tmp, 0o700)

        self.assertTrue(state.reachable)
        self.assertFalse(state.writable)
        self.assertTrue(state.reason)

    def test_a_working_folder_reports_no_reason(self) -> None:
        with TemporaryDirectory() as tmp:
            state = state_of(Location("id", tmp))

        self.assertTrue(state.reachable and state.writable)
        self.assertEqual(state.reason, "")


class CanonicalTests(unittest.TestCase):
    def test_one_spelling_per_place(self) -> None:
        with TemporaryDirectory() as tmp:
            inner = Path(tmp) / "share"
            inner.mkdir()

            self.assertEqual(canonical(str(inner)),
                             canonical(f"{tmp}/./share/"))

    def test_nothing_canonicalizes_to_nothing(self) -> None:
        self.assertEqual(canonical("   "), "")


class SeedTests(_WithStore, unittest.TestCase):
    def test_the_configured_root_becomes_the_first_location(self) -> None:
        games = self.root / "games"
        games.mkdir()

        self.assertTrue(locations.seed(self.store, _config(game_root_dir=str(games))))

        held = self.store.locations()
        self.assertEqual([one.path for one in held], [str(games)])
        self.assertEqual(held[0].kind, KIND_ROOT)
        self.assertEqual(self.store.write_to().location_id, held[0].location_id)

    def test_it_runs_once(self) -> None:
        """Somebody who removes a location should not find it back on the next start."""
        games = self.root / "games"
        games.mkdir()
        config = _config(game_root_dir=str(games))
        locations.seed(self.store, config)
        self.store.remove(self.store.locations()[0].location_id)

        self.assertFalse(locations.seed(self.store, config))
        self.assertEqual(self.store.locations(), [])

    def test_an_install_with_no_root_yet_is_not_marked(self) -> None:
        """The first root it is given still has to seed."""
        self.assertFalse(locations.seed(self.store, _config()))
        self.assertEqual(self.store.migrations(), [])

        games = self.root / "games"
        games.mkdir()
        self.assertTrue(locations.seed(self.store, _config(game_root_dir=str(games))))


if __name__ == "__main__":
    unittest.main()
