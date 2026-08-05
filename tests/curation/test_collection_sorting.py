import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from common.games.collection_store import CollectionStore
from frontend.api import API


def _game(title, vpsid, last_run=None, altvpsid="", alttitle="", runtime=0, start_count=0, creation_time=0):
    return SimpleNamespace(
        meta_config={
            "Info": {
                "Title": title,
                "VPSId": vpsid,
            },
            "User": {
                "LastRun": last_run,
                "RunTime": runtime,
                "StartCount": start_count,
            },
            "vpinfe": {
                "alt_vpsid": altvpsid,
                "alt_title": alttitle,
            },
        },
        creation_time=creation_time,
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

            manager = CollectionStore(str(ini_path))
            games = [
                _game("Bravo", "vps-1", last_run=100),
                _game("Alpha", "vps-2", last_run=300),
                _game("Charlie", "vps-3", last_run=None),
            ]

            result = manager.filter_games(games, "Last Played")

            self.assertEqual(
                [game.meta_config["Info"]["Title"] for game in result],
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

            manager = CollectionStore(str(ini_path))
            games = [
                _game("Zulu", "vps-1", last_run=999),
                _game("Alpha", "vps-2", last_run=1),
            ]

            result = manager.filter_games(games, "Favorites")

            self.assertEqual(
                [game.meta_config["Info"]["Title"] for game in result],
                ["Alpha", "Zulu"],
            )

    def test_api_last_run_sort_orders_all_collections_by_user_last_run(self) -> None:
        api = API.__new__(API)
        api.filteredGames = [
            _game("Bravo", "vps-1", last_run=100),
            _game("Alpha", "vps-2", last_run=300),
            _game("Charlie", "vps-3", last_run="bad-value"),
        ]
        api.current_sort = "Alpha"

        count = API.apply_sort(api, "LastRun")

        self.assertEqual(count, 3)
        self.assertEqual(api.current_sort, "LastRun")
        self.assertEqual(
            [game.meta_config["Info"]["Title"] for game in api.filteredGames],
            ["Alpha", "Bravo", "Charlie"],
        )

    def test_api_runtime_sort_supports_descending_and_ascending_order(self) -> None:
        api = API.__new__(API)
        api.filteredGames = [
            _game("Short", "vps-1", runtime=10),
            _game("Long", "vps-2", runtime=120),
            _game("Medium", "vps-3", runtime=45),
        ]
        api.current_sort = "Alpha"
        api.current_order = "Descending"

        count = API.apply_sort(api, "RunTime", "Descending")

        self.assertEqual(count, 3)
        self.assertEqual(api.current_sort, "RunTime")
        self.assertEqual(api.current_order, "Descending")
        self.assertEqual(
            [game.meta_config["Info"]["Title"] for game in api.filteredGames],
            ["Long", "Medium", "Short"],
        )

        API.apply_sort(api, "RunTime", "Ascending")

        self.assertEqual(api.current_order, "Ascending")
        self.assertEqual(
            [game.meta_config["Info"]["Title"] for game in api.filteredGames],
            ["Short", "Medium", "Long"],
        )

    def test_filter_collections_default_to_descending_order(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "collections.ini"
            manager = CollectionStore(str(ini_path))
            manager.add_filter_collection("Played", sort_by="RunTime")

            self.assertEqual(manager.get_filters("Played")["order_by"], "Descending")


if __name__ == "__main__":
    unittest.main()
