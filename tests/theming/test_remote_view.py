"""A view whose library is on another machine.

`network.library_url` is the one setting that decides it: empty - the default, and every
single-machine setup - and this install reads its own disk exactly as it always has. Set,
and the list it holds is entries the other install already resolved.

The two are different kinds of thing, which is the whole of what the remote path has to
get right: a local view resolves a collection into entries, and a remote one holds entries
that cannot be re-resolved, because the table dicts the resolver reads stayed over there.
"""

from __future__ import annotations

import configparser
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from common.games import remote_library
from common.games.collection_resolver import Entry
from common.games.wire_entry import WireGame
from frontend import library_resolver as frontend_library
from frontend.library_resolver import LibraryResolver

TITLES = ("Attack from Mars", "Medieval Madness", "Twilight Zone")


def _ini(url: str = "") -> SimpleNamespace:
    config = configparser.ConfigParser()
    config.read_string(f"[general]\n[network]\nlibrary_url = {url}\n")
    return SimpleNamespace(config=config)


def _wire_entry(title: str, created: str) -> dict:
    """What a library sends: resolved, one row per entry, and carrying no local path."""
    return {"game": {"id": title[:4], "name": title, "manufacturer": "Bally",
                     "year": "1995", "type": "SS", "themes": ["Space"],
                     "dir_name": f"{title} (Bally 1995)", "created_at": created,
                     "user": {"rating": 4, "favorite": False, "tags": [],
                              "last_played": None, "play_count": 0,
                              "play_time_seconds": 0}},
            "table": {"id": f"t-{title[:4]}", "filename": f"{title}.vpx",
                      "version": "", "rom": "", "default": True, "authors": [],
                      "detects": {}, "user": {}},
            "assets": {"pup_pack": False, "alt_color": False, "alt_sound": False},
            "media": ["wheel"], "siblings": 1}


PAYLOAD = {"entries": [_wire_entry(title, f"2026-0{index + 1}-01T00:00:00Z")
                       for index, title in enumerate(TITLES)]}


class LibraryUrlTests(unittest.TestCase):
    def test_no_library_set_is_the_default_and_stays_local(self) -> None:
        """The parity requirement: an install that says nothing behaves as it always has."""
        for text in ("[general]\n", "[network]\nlibrary_url =\n", "[network]\nlibrary_url =    \n"):
            with self.subTest(config=text):
                config = configparser.ConfigParser()
                config.read_string(text)
                ini = SimpleNamespace(config=config)

                self.assertEqual(frontend_library.library_url(ini), "")
                self.assertFalse(LibraryResolver(ini, games=[])._remote)

    def test_a_library_url_makes_the_view_remote(self) -> None:
        self.assertEqual(frontend_library.library_url(_ini("http://elsewhere:8001")),
                         "http://elsewhere:8001")

    def test_config_that_cannot_be_read_is_local_rather_than_fatal(self) -> None:
        """An install that cannot read its setting holds its own library, which is the
        behavior that needs no network to work."""
        self.assertEqual(frontend_library.library_url(SimpleNamespace(config=None)), "")


class RemoteViewTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(remote_library.http_client, "get_json",
                               lambda *a, **k: PAYLOAD)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.library = LibraryResolver(_ini("http://library.example:8001"))

    def test_it_holds_what_the_library_sent(self) -> None:
        self.assertTrue(self.library._remote)
        self.assertEqual(len(self.library.entries), len(TITLES))
        self.assertTrue(all(isinstance(entry, Entry) for entry in self.library.entries))
        self.assertTrue(all(isinstance(entry.game, WireGame)
                            for entry in self.library.entries))

    def test_the_entries_are_kept_rather_than_re_derived(self) -> None:
        """The resolver reads a game's table dicts out of its `.info`, and the library
        kept those - re-resolving would quietly produce an empty wheel."""
        self.assertEqual([entry.table_id for entry in self.library.entries],
                         [f"t-{title[:4]}" for title in TITLES])
        self.assertEqual([entry.filename for entry in self.library.entries],
                         [f"{title}.vpx" for title in TITLES])

    def test_it_serializes_a_theme_payload(self) -> None:
        """What the wheel actually renders, built here from the library's answer."""
        payload = json.loads(self.library.payload(2))

        self.assertEqual(payload["count"], len(TITLES))
        self.assertEqual([entry["game"]["name"] for entry in payload["entries"]],
                         sorted(TITLES))
        for entry in payload["entries"]:
            self.assertEqual(entry["game"]["themes"], ["Space"])
            self.assertEqual(entry["media"], ["wheel"])

    def test_no_path_from_the_library_reaches_the_payload(self) -> None:
        payload = json.loads(self.library.payload(2))

        for entry in payload["entries"]:
            self.assertEqual(entry["game"]["path"], "")
            self.assertEqual(entry["table"]["path"], "")

    def test_every_sort_works_on_what_arrived(self) -> None:
        """The sorts read a title and a creation time off whatever they are handed, and
        an entry forwards both - so an install sorts its wheel without a local library."""
        for sort in ("Alpha", "Newest", "LastRun", "Highest StartCount", "RunTime"):
            with self.subTest(sort=sort):
                self.library.current_sort = sort
                self.library.current_order = "Ascending"
                self.library.reset_to_default()

                self.assertEqual(len(self.library.entries), len(TITLES))

    def test_newest_orders_by_what_the_library_stamped(self) -> None:
        """The one sort that cannot work without `created_at` crossing: the timestamps
        decide it, so a reversed order is the field arriving rather than a tiebreak."""
        from frontend import game_state

        rows = list(self.library.entries)
        game_state.apply_sort(rows, "Newest", "Descending")

        self.assertEqual([row.game.meta_config["Info"]["Title"] for row in rows],
                         list(reversed(TITLES)))


if __name__ == "__main__":
    unittest.main()
