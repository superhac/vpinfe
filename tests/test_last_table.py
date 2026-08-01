import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from common.iniconfig import IniConfig
from frontend import last_table


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
            tables = [
                FakeGame(fullPathTable="/tables/AAA", tableDirName="AAA"),
                FakeGame(fullPathTable="/tables/BBB", tableDirName="BBB"),
                FakeGame(fullPathTable="/tables/CCC", tableDirName="CCC"),
            ]

            last_table.save_last_game(config, tables[2])

            self.assertEqual(config.config.get("State", "lasttable"), "/tables/CCC")
            self.assertEqual(last_table.resolve_last_game_index(config, tables), 2)

    def test_resolve_survives_reordering(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            game = FakeGame(fullPathTable="/tables/BBB", tableDirName="BBB")
            last_table.save_last_game(config, game)

            reordered = [
                FakeGame(fullPathTable="/tables/CCC", tableDirName="CCC"),
                FakeGame(fullPathTable="/tables/BBB", tableDirName="BBB"),
                FakeGame(fullPathTable="/tables/AAA", tableDirName="AAA"),
            ]
            self.assertEqual(last_table.resolve_last_game_index(config, reordered), 1)

    def test_resolve_returns_zero_when_not_found(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            config.config.set("State", "lasttable", "/tables/GONE")

            tables = [FakeGame(fullPathTable="/tables/AAA", tableDirName="AAA")]
            self.assertEqual(last_table.resolve_last_game_index(config, tables), 0)

    def test_resolve_returns_zero_when_nothing_saved(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            tables = [FakeGame(fullPathTable="/tables/AAA", tableDirName="AAA")]
            self.assertEqual(last_table.resolve_last_game_index(config, tables), 0)

    def test_disabled_skips_save_and_resolve(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            config.config.set("Settings", "restorelasttable", "false")

            tables = [
                FakeGame(fullPathTable="/tables/AAA", tableDirName="AAA"),
                FakeGame(fullPathTable="/tables/BBB", tableDirName="BBB"),
            ]
            last_table.save_last_game(config, tables[1])

            # Nothing persisted, and resolution is short-circuited to 0.
            self.assertEqual(config.config.get("State", "lasttable"), "")
            self.assertEqual(last_table.resolve_last_game_index(config, tables), 0)

    def test_falls_back_to_dir_name_when_path_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            game = FakeGame(fullPathTable="", tableDirName="OnlyDirName")
            last_table.save_last_game(config, game)

            self.assertEqual(config.config.get("State", "lasttable"), "OnlyDirName")
            self.assertEqual(
                last_table.resolve_last_game_index(config, [FakeGame(tableDirName="Other"), game]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
