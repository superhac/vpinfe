import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from common.config_store import ConfigStore
from frontend import last_game


@dataclass
class FakeGame:
    fullPathGame: str = ""
    gameDirName: str = ""


def _config(tmp: str) -> ConfigStore:
    return ConfigStore(str(Path(tmp) / "vpinfe.ini"))


class TestLastGame(unittest.TestCase):
    def test_save_then_resolve_round_trips(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            games = [
                FakeGame(fullPathGame="/games/AAA", gameDirName="AAA"),
                FakeGame(fullPathGame="/games/BBB", gameDirName="BBB"),
                FakeGame(fullPathGame="/games/CCC", gameDirName="CCC"),
            ]

            last_game.save_last_game(config, games[2])

            self.assertEqual(config.config.get("State", "lastgame"), "/games/CCC")
            self.assertEqual(last_game.resolve_last_game_index(config, games), 2)

    def test_resolve_survives_reordering(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            game = FakeGame(fullPathGame="/games/BBB", gameDirName="BBB")
            last_game.save_last_game(config, game)

            reordered = [
                FakeGame(fullPathGame="/games/CCC", gameDirName="CCC"),
                FakeGame(fullPathGame="/games/BBB", gameDirName="BBB"),
                FakeGame(fullPathGame="/games/AAA", gameDirName="AAA"),
            ]
            self.assertEqual(last_game.resolve_last_game_index(config, reordered), 1)

    def test_resolve_returns_zero_when_not_found(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            config.config.set("State", "lastgame", "/games/GONE")

            games = [FakeGame(fullPathGame="/games/AAA", gameDirName="AAA")]
            self.assertEqual(last_game.resolve_last_game_index(config, games), 0)

    def test_resolve_returns_zero_when_nothing_saved(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            games = [FakeGame(fullPathGame="/games/AAA", gameDirName="AAA")]
            self.assertEqual(last_game.resolve_last_game_index(config, games), 0)

    def test_disabled_skips_save_and_resolve(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            config.config.set("Settings", "restorelastgame", "false")

            games = [
                FakeGame(fullPathGame="/games/AAA", gameDirName="AAA"),
                FakeGame(fullPathGame="/games/BBB", gameDirName="BBB"),
            ]
            last_game.save_last_game(config, games[1])

            # Nothing persisted, and resolution is short-circuited to 0.
            self.assertEqual(config.config.get("State", "lastgame"), "")
            self.assertEqual(last_game.resolve_last_game_index(config, games), 0)

    def test_falls_back_to_dir_name_when_path_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            game = FakeGame(fullPathGame="", gameDirName="OnlyDirName")
            last_game.save_last_game(config, game)

            self.assertEqual(config.config.get("State", "lastgame"), "OnlyDirName")
            self.assertEqual(
                last_game.resolve_last_game_index(config, [FakeGame(gameDirName="Other"), game]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
