import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from common.games.collection_store import CollectionStore
from frontend.api import API


def _game(title, vpsid, last_run=None, altvpsid="", alttitle="", runtime=0,
          start_count=0, creation_time=0):
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
    # A collection's own order is the resolver's, and tested there. What is left here is
    # the sort a player applies on top of it, which is the frontend's.

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
        api.current_order = "desc"

        count = API.apply_sort(api, "RunTime", "desc")

        self.assertEqual(count, 3)
        self.assertEqual(api.current_sort, "RunTime")
        self.assertEqual(api.current_order, "desc")
        self.assertEqual(
            [game.meta_config["Info"]["Title"] for game in api.filteredGames],
            ["Long", "Medium", "Short"],
        )

        API.apply_sort(api, "RunTime", "Ascending")

        # The 2.x spelling still arrives from a stored filter and has to resolve.
        self.assertEqual(api.current_order, "asc")
        self.assertEqual(
            [game.meta_config["Info"]["Title"] for game in api.filteredGames],
            ["Short", "Medium", "Long"],
        )

    def test_filter_collections_default_to_descending_order(self) -> None:
        with TemporaryDirectory() as tmp:
            ini_path = Path(tmp) / "collections.ini"
            manager = CollectionStore(str(ini_path))
            manager.add_filter_collection("Played", sort_by="RunTime")

            self.assertEqual(manager.get_filters("Played")["order_by"], "desc")


if __name__ == "__main__":
    unittest.main()
