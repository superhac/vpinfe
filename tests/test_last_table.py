import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from common.iniconfig import IniConfig
from frontend import last_game


@dataclass
class FakeGame:
    fullPathTable: str = ""
    tableDirName: str = ""


def _config(tmp: str) -> IniConfig:
    return IniConfig(str(Path(tmp) / "vpinfe.ini"))


class TestLastGame(unittest.TestCase):
    def test_save_then_resolve_round_trips(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            games = [
                FakeGame(fullPathTable="/games/AAA", tableDirName="AAA"),
                FakeGame(fullPathTable="/games/BBB", tableDirName="BBB"),
                FakeGame(fullPathTable="/games/CCC", tableDirName="CCC"),
            ]

            last_game.save_last_game(config, games[2])

            self.assertEqual(config.config.get("State", "lastgame"), "/games/CCC")
            self.assertEqual(last_game.resolve_last_game_index(config, games), 2)

    def test_resolve_survives_reordering(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            game = FakeGame(fullPathTable="/games/BBB", tableDirName="BBB")
            last_game.save_last_game(config, game)

            reordered = [
                FakeGame(fullPathTable="/games/CCC", tableDirName="CCC"),
                FakeGame(fullPathTable="/games/BBB", tableDirName="BBB"),
                FakeGame(fullPathTable="/games/AAA", tableDirName="AAA"),
            ]
            self.assertEqual(last_game.resolve_last_game_index(config, reordered), 1)

    def test_resolve_returns_zero_when_not_found(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            config.config.set("State", "lastgame", "/games/GONE")

            games = [FakeGame(fullPathTable="/games/AAA", tableDirName="AAA")]
            self.assertEqual(last_game.resolve_last_game_index(config, games), 0)

    def test_resolve_returns_zero_when_nothing_saved(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            games = [FakeGame(fullPathTable="/games/AAA", tableDirName="AAA")]
            self.assertEqual(last_game.resolve_last_game_index(config, games), 0)

    def test_disabled_skips_save_and_resolve(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            config.config.set("Settings", "restorelastgame", "false")

            games = [
                FakeGame(fullPathTable="/games/AAA", tableDirName="AAA"),
                FakeGame(fullPathTable="/games/BBB", tableDirName="BBB"),
            ]
            last_game.save_last_game(config, games[1])

            # Nothing persisted, and resolution is short-circuited to 0.
            self.assertEqual(config.config.get("State", "lastgame"), "")
            self.assertEqual(last_game.resolve_last_game_index(config, games), 0)

    def test_falls_back_to_dir_name_when_path_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            game = FakeGame(fullPathTable="", tableDirName="OnlyDirName")
            last_game.save_last_game(config, game)

            self.assertEqual(config.config.get("State", "lastgame"), "OnlyDirName")
            self.assertEqual(
                last_game.resolve_last_game_index(config, [FakeGame(tableDirName="Other"), game]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
