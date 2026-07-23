import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from common.iniconfig import IniConfig
from frontend import last_table


@dataclass
class FakeTable:
    fullPathTable: str = ""
    tableDirName: str = ""


def _config(tmp: str) -> IniConfig:
    return IniConfig(str(Path(tmp) / "vpinfe.ini"))


class TestLastTable(unittest.TestCase):
    def test_save_then_resolve_round_trips(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            tables = [
                FakeTable(fullPathTable="/tables/AAA", tableDirName="AAA"),
                FakeTable(fullPathTable="/tables/BBB", tableDirName="BBB"),
                FakeTable(fullPathTable="/tables/CCC", tableDirName="CCC"),
            ]

            last_table.save_last_table(config, tables[2])

            self.assertEqual(config.config.get("State", "lasttable"), "/tables/CCC")
            self.assertEqual(last_table.resolve_last_table_index(config, tables), 2)

    def test_resolve_survives_reordering(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            table = FakeTable(fullPathTable="/tables/BBB", tableDirName="BBB")
            last_table.save_last_table(config, table)

            reordered = [
                FakeTable(fullPathTable="/tables/CCC", tableDirName="CCC"),
                FakeTable(fullPathTable="/tables/BBB", tableDirName="BBB"),
                FakeTable(fullPathTable="/tables/AAA", tableDirName="AAA"),
            ]
            self.assertEqual(last_table.resolve_last_table_index(config, reordered), 1)

    def test_resolve_returns_zero_when_not_found(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            config.config.set("State", "lasttable", "/tables/GONE")

            tables = [FakeTable(fullPathTable="/tables/AAA", tableDirName="AAA")]
            self.assertEqual(last_table.resolve_last_table_index(config, tables), 0)

    def test_resolve_returns_zero_when_nothing_saved(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            tables = [FakeTable(fullPathTable="/tables/AAA", tableDirName="AAA")]
            self.assertEqual(last_table.resolve_last_table_index(config, tables), 0)

    def test_disabled_skips_save_and_resolve(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            config.config.set("Settings", "restorelasttable", "false")

            tables = [
                FakeTable(fullPathTable="/tables/AAA", tableDirName="AAA"),
                FakeTable(fullPathTable="/tables/BBB", tableDirName="BBB"),
            ]
            last_table.save_last_table(config, tables[1])

            # Nothing persisted, and resolution is short-circuited to 0.
            self.assertEqual(config.config.get("State", "lasttable"), "")
            self.assertEqual(last_table.resolve_last_table_index(config, tables), 0)

    def test_falls_back_to_dir_name_when_path_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            config = _config(tmp)
            table = FakeTable(fullPathTable="", tableDirName="OnlyDirName")
            last_table.save_last_table(config, table)

            self.assertEqual(config.config.get("State", "lasttable"), "OnlyDirName")
            self.assertEqual(
                last_table.resolve_last_table_index(config, [FakeTable(tableDirName="Other"), table]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
