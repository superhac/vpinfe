"""Reading a library that is in more than one place."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common.games import game_repository
from common.games.locations import KIND_ROOT, Location


def _game_folder(root: Path, name: str) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / f"{name}.vpx").write_text("")
    return folder


class ManyLocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        self.first = self.root / "share"
        self.second = self.root / "local"
        _game_folder(self.first, "One (Bally 1990)")
        _game_folder(self.second, "Two (Gottlieb 1975)")

        game_repository._PARSERS.clear()
        self.addCleanup(game_repository._PARSERS.clear)

    def _configured(self, *paths: Path) -> list[Location]:
        return [Location(location_id=f"loc{n}", path=str(path), kind=KIND_ROOT)
                for n, path in enumerate(paths)]

    def _with(self, *paths: Path):
        return mock.patch.object(game_repository.locations, "configured",
                                 return_value=self._configured(*paths))

    def test_every_location_is_read_and_each_game_says_where_it_came_from(self) -> None:
        with self._with(self.first, self.second):
            games = game_repository.all_games()

        self.assertEqual({g.gameDirName: g.location_id for g in games},
                         {"One (Bally 1990)": "loc0", "Two (Gottlieb 1975)": "loc1"})

    def test_one_unreachable_location_does_not_empty_the_library(self) -> None:
        """The whole point: a share that has not mounted is one location reading as
        unreachable, not four hundred tables vanishing."""
        with self._with(self.root / "never-mounted", self.second):
            games = game_repository.all_games()

        self.assertEqual([g.gameDirName for g in games], ["Two (Gottlieb 1975)"])

    def test_dropping_a_location_drops_its_games(self) -> None:
        with self._with(self.first, self.second):
            game_repository.all_games()
        with self._with(self.second):
            games = game_repository.all_games()

        self.assertEqual([g.gameDirName for g in games], ["Two (Gottlieb 1975)"])
        self.assertEqual(list(game_repository._PARSERS), [str(self.second)])

    def test_a_location_is_read_once_and_held(self) -> None:
        with self._with(self.first, self.second):
            game_repository.all_games()
            with mock.patch.object(game_repository, "GameParser") as built:
                game_repository.all_games()

        built.assert_not_called()

    def test_refreshing_one_folder_asks_the_location_holding_it(self) -> None:
        """Asking the wrong parser to re-read it would add the game to a location it is
        not in."""
        with self._with(self.first, self.second):
            game_repository.all_games()
            found = game_repository.refresh_game(self.second / "Two (Gottlieb 1975)")

        self.assertEqual([g.gameDirName for g in found], ["Two (Gottlieb 1975)"])
        self.assertEqual([g.location_id for g in found], ["loc1"])


if __name__ == "__main__":
    unittest.main()
