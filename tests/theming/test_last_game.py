import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from common.config_store import ConfigStore
from frontend import last_game
from tests.support.library import fake_game


def _config(tmp: str) -> ConfigStore:
    return ConfigStore(str(Path(tmp) / "vpinfe.ini"))


class TestLastGame(unittest.TestCase):
    def test_save_then_resolve_round_trips(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            games = [
                fake_game("/games/AAA", "AAA"),
                fake_game("/games/BBB", "BBB"),
                fake_game("/games/CCC", "CCC"),
            ]

            last_game.save_last_game(config, games[2])

            self.assertEqual(config.config.get("State", "last_game"), "/games/CCC")
            self.assertEqual(last_game.resolve_last_game_index(config, games), 2)

    def test_resolve_survives_reordering(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            game = fake_game("/games/BBB", "BBB")
            last_game.save_last_game(config, game)

            reordered = [
                fake_game("/games/CCC", "CCC"),
                fake_game("/games/BBB", "BBB"),
                fake_game("/games/AAA", "AAA"),
            ]
            self.assertEqual(last_game.resolve_last_game_index(config, reordered), 1)

    def test_resolve_returns_zero_when_not_found(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            config.config.set("State", "last_game", "/games/GONE")

            games = [fake_game("/games/AAA", "AAA")]
            self.assertEqual(last_game.resolve_last_game_index(config, games), 0)

    def test_resolve_returns_zero_when_nothing_saved(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            games = [fake_game("/games/AAA", "AAA")]
            self.assertEqual(last_game.resolve_last_game_index(config, games), 0)

    def test_disabled_skips_save_and_resolve(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            config.config.set("Settings", "restore_last_game", "false")

            games = [
                fake_game("/games/AAA", "AAA"),
                fake_game("/games/BBB", "BBB"),
            ]
            last_game.save_last_game(config, games[1])

            # Nothing persisted, and resolution is short-circuited to 0.
            self.assertEqual(config.config.get("State", "last_game"), "")
            self.assertEqual(last_game.resolve_last_game_index(config, games), 0)

    def test_falls_back_to_dir_name_when_path_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            game = fake_game("", "OnlyDirName")
            last_game.save_last_game(config, game)

            self.assertEqual(config.config.get("State", "last_game"), "OnlyDirName")
            self.assertEqual(
                last_game.resolve_last_game_index(config, [fake_game("", "Other"), game]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
