import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from common.vpxcollections import VPXCollections

from frontend.api import API


def _table(title, vpsid, last_run=None, altvpsid="", alttitle=""):
    return SimpleNamespace(
        metaConfig={
            "Info": {
                "Title": title,
                "VPSId": vpsid,
            },
            "User": {
                "LastRun": last_run,
            },
            "VPinFE": {
                "altvpsid": altvpsid,
                "alttitle": alttitle,
            },
        },
        creation_time=0,
    )


class TestCollectionSorting(unittest.TestCase):
    def test_last_played_collection_sorts_by_user_last_run_desc(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "collections.ini"
            ini_path.write_text(
                "\n".join(
                    [
                        "[Last Played]",
                        "type = vpsid",
                        "vpsids = vps-1,vps-2,vps-3",
                    ]
                ),
                encoding="utf-8",
            )

            manager = VPXCollections(str(ini_path))
            tables = [
                _table("Bravo", "vps-1", last_run=100),
                _table("Alpha", "vps-2", last_run=300),
                _table("Charlie", "vps-3", last_run=None),
            ]

            result = manager.filter_tables(tables, "Last Played")

            self.assertEqual(
                [table.metaConfig["Info"]["Title"] for table in result],
                ["Alpha", "Bravo", "Charlie"],
            )

    def test_regular_vpsid_collection_still_sorts_alphabetically(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "collections.ini"
            ini_path.write_text(
                "\n".join(
                    [
                        "[Favorites]",
                        "type = vpsid",
                        "vpsids = vps-1,vps-2",
                    ]
                ),
                encoding="utf-8",
            )

            manager = VPXCollections(str(ini_path))
            tables = [
                _table("Zulu", "vps-1", last_run=999),
                _table("Alpha", "vps-2", last_run=1),
            ]

            result = manager.filter_tables(tables, "Favorites")

            self.assertEqual(
                [table.metaConfig["Info"]["Title"] for table in result],
                ["Alpha", "Zulu"],
            )

    def test_api_last_run_sort_orders_all_collections_by_user_last_run(self) -> None:
        api = API.__new__(API)
        api.filteredTables = [
            _table("Bravo", "vps-1", last_run=100),
            _table("Alpha", "vps-2", last_run=300),
            _table("Charlie", "vps-3", last_run="bad-value"),
        ]
        api.current_sort = "Alpha"

        count = API.apply_sort(api, "LastRun")

        self.assertEqual(count, 3)
        self.assertEqual(api.current_sort, "LastRun")
        self.assertEqual(
            [table.metaConfig["Info"]["Title"] for table in api.filteredTables],
            ["Alpha", "Bravo", "Charlie"],
        )


if __name__ == "__main__":
    unittest.main()
