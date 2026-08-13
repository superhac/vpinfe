"""The play lens over the whole library, and reading it back as local entries.

A player with no library of its own shows everything before a collection is chosen, and
there is no stored collection meaning "all of it" - so `GET /collections/{name}/entries`
cannot answer for that view. `GET /library/entries` is the same lens, unnarrowed.

`hub_library` is the other half: what a player does with the answer. It turns the wire
rows back into the `Entry` objects the frontend already builds locally, so nothing
downstream can tell which side the library came from.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpapi
from common.games import hub_library
from common.games.collection_resolver import Entry, entries_for
from common.games.game_metadata import game_title
from common.media_specs import MEDIA_SPECS
from frontend import game_state
from httpapi.collections import _entry_resource
from tests.support.library import TempTree, fake_game, write_game

try:
    from starlette.testclient import TestClient
except ImportError:  # pragma: no cover - the API tests skip the same way
    TestClient = None

LIBRARY = (("Attack from Mars (Bally 1995)", "Aaaa111111"),
           ("Medieval Madness (Williams 1997)", "Bbbb222222"),
           ("Twilight Zone (Bally 1993)", "Cccc333333"))


@unittest.skipIf(TestClient is None, "starlette test client unavailable")
class LibraryEntriesTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.games = []
        for name, game_id in LIBRARY:
            meta = {"Info": {"Title": name.split(" (")[0], "Manufacturer": "Bally",
                             "Year": "1995", "Type": "SS", "Themes": ["Space"]},
                    "User": {"Rating": 4},
                    "vpinfe": {"game_id": game_id}}
            self.games.append(
                fake_game(write_game(self.root, name, info=meta), name, meta=meta))

        loader = patch("common.games.game_repository.ensure_games_loaded",
                       lambda *a, **k: self.games)
        loader.start()
        self.addCleanup(loader.stop)
        self.client = TestClient(httpapi.create_api_app(), raise_server_exceptions=False)

    def test_the_whole_library_answers_as_entries(self) -> None:
        response = self.client.get("/library/entries")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], len(LIBRARY))
        self.assertEqual(body["collection"], "")
        self.assertEqual(len(body["entries"]), len(LIBRARY))

    def test_it_is_the_same_lens_a_collection_serves(self) -> None:
        """Same helper, so the two cannot drift into different answers."""
        wire = self.client.get("/library/entries").json()["entries"]

        self.assertEqual([row["game"]["name"] for row in wire],
                         [game_title(e.game) for e in entries_for(self.games)])

    def test_a_player_reads_the_answer_back_as_local_entries(self) -> None:
        """The round trip that makes a remote library indistinguishable from a local one:
        what the hub sent has to arrive as what `entries_for` would have built."""
        payload = self.client.get("/library/entries").json()

        with patch.object(hub_library.http_client, "get_json", lambda *a, **k: payload):
            remote = hub_library.fetch_entries("http://hub.example:8001")

        local = entries_for(self.games)
        self.assertEqual([game_title(e.game) for e in remote],
                         [game_title(e.game) for e in local])
        # The table half too, by a field that actually carries a value here - comparing
        # ids would be two empty lists agreeing, and would pass with the table dropped.
        self.assertEqual([e.filename for e in remote], [e.filename for e in local])
        self.assertTrue(all(e.filename for e in remote))
        self.assertEqual([e.siblings for e in remote], [e.siblings for e in local])

    def test_a_player_with_no_library_builds_the_theme_payload(self) -> None:
        """The separation test, in one process: everything the wheel renders comes from
        what the hub sent, and the local library is not consulted to build it."""
        payload = self.client.get("/library/entries").json()

        with patch.object(hub_library.http_client, "get_json", lambda *a, **k: payload):
            remote = hub_library.fetch_entries("http://hub.example:8001")
        theme = json.loads(game_state.games_json(remote, contract=2))

        self.assertEqual(theme["count"], len(LIBRARY))
        self.assertEqual([e["game"]["name"] for e in theme["entries"]],
                         [name.split(" (")[0] for name, _ in LIBRARY])
        for entry in theme["entries"]:
            self.assertEqual(entry["game"]["themes"], ["Space"])
            self.assertEqual(entry["game"]["user"]["rating"], 4)

    def test_no_path_from_the_hub_reaches_the_rendered_payload(self) -> None:
        """A player holding the hub's paths would be holding addresses it cannot reach,
        so they arrive empty rather than wrong."""
        payload = self.client.get("/library/entries").json()

        with patch.object(hub_library.http_client, "get_json", lambda *a, **k: payload):
            remote = hub_library.fetch_entries("http://hub.example:8001")
        theme = json.loads(game_state.games_json(remote, contract=2))

        for entry in theme["entries"]:
            self.assertEqual(entry["game"]["path"], "")
            self.assertEqual(entry["table"]["path"], "")
        self.assertNotIn(str(self.root), json.dumps(theme))

    def test_what_the_hub_resolved_arrives_resolved(self) -> None:
        """Media kinds and asset flags are a stat of the hub's disk. A player cannot
        redo that lookup, so the answer has to survive the trip rather than be recomputed
        against a filesystem that does not have the files."""
        game = self.games[0]
        for attribute in ("pupPackExists", "altColorExists", "altSoundExists"):
            setattr(game, attribute, True)
        by_key = {spec.key: spec.attr for spec in MEDIA_SPECS}
        for kind in ("wheel", "playfield", "backglass"):
            setattr(game, by_key[kind], f"/on/the/hub/{kind}.png")

        entry = entries_for([game])[0]
        local = json.loads(game_state.games_json([entry], contract=2))["entries"][0]
        row = _entry_resource(entry)
        with patch.object(hub_library.http_client, "get_json",
                          lambda *a, **k: {"entries": [row]}):
            remote_entries = hub_library.fetch_entries("http://hub.example:8001")
        remote = json.loads(game_state.games_json(remote_entries, contract=2))["entries"][0]

        self.assertEqual(remote["media"], ["backglass", "playfield", "wheel"])
        self.assertEqual(remote["media"], local["media"])
        self.assertEqual(remote["assets"], local["assets"])
        self.assertTrue(all(remote["assets"].values()))

    def test_a_hub_that_answers_with_nonsense_is_an_error(self) -> None:
        """Not an empty wheel: a hub that cannot be understood is not a hub with no
        games, and showing one as the other reports the wrong thing."""
        with patch.object(hub_library.http_client, "get_json", lambda *a, **k: "nope"):
            with self.assertRaises(ValueError):
                hub_library.fetch_entries("http://hub.example:8001")


class SharedLibraryTests(unittest.TestCase):
    """Whether a player's own copy of the library is the hub's, asked by content.

    Shared storage is what the split assumes and nothing checked. A path comparison
    cannot answer it - the same share is mounted at different places on different
    machines - so this compares the hashes the hub already publishes per table.
    """

    @staticmethod
    def _game(table_id: str, file_hash: str):
        return SimpleNamespace(
            meta_config={"tables": {table_id: {"id": table_id, "file_hash": file_hash}}})

    @staticmethod
    def _entry(table_id: str, file_hash: str) -> Entry:
        return Entry(game=SimpleNamespace(meta_config={}),
                     table={"id": table_id, "file_hash": file_hash}, siblings=1)

    def test_the_same_share_verifies(self) -> None:
        report = hub_library.verify_shared_library(
            [self._entry("T1", "aaa"), self._entry("T2", "bbb")],
            [self._game("T1", "aaa"), self._game("T2", "bbb")])

        self.assertTrue(report["shared"])
        self.assertEqual(report["matched"], 2)

    def test_a_share_that_is_not_mounted_is_reported_as_missing(self) -> None:
        """The failure this exists to catch: today it shows up one game at a time, at
        launch, as a file-not-found."""
        report = hub_library.verify_shared_library([self._entry("T1", "aaa")], [])

        self.assertFalse(report["shared"])
        self.assertEqual(report["missing"], ["T1"])

    def test_a_table_whose_bytes_differ_is_not_the_same_table(self) -> None:
        """Same id, different content - a local edit, a half-finished copy, a different
        build of the same table. Distinct from missing, because the fix is different."""
        report = hub_library.verify_shared_library(
            [self._entry("T1", "aaa")], [self._game("T1", "zzz")])

        self.assertFalse(report["shared"])
        self.assertEqual(report["differs"], ["T1"])
        self.assertEqual(report["missing"], [])

    def test_nothing_verifiable_is_not_a_pass(self) -> None:
        """A hub that has hashed nothing says nothing either way, and 'everything
        matched' must not be able to mean 'nothing was checked'."""
        report = hub_library.verify_shared_library(
            [self._entry("T1", "")], [self._game("T1", "aaa")])

        self.assertFalse(report["shared"])
        self.assertEqual(report["unverifiable"], 1)
        self.assertEqual(report["matched"], 0)

    def test_an_empty_library_is_not_a_verified_one(self) -> None:
        self.assertFalse(hub_library.verify_shared_library([], [])["shared"])


class HubUrlTests(unittest.TestCase):
    def test_the_url_names_the_collection_or_the_whole_library(self) -> None:
        self.assertEqual(hub_library.entries_url("http://hub:8001"),
                         "http://hub:8001/api/v1/library/entries")
        self.assertEqual(hub_library.entries_url("http://hub:8001", "Favorites"),
                         "http://hub:8001/api/v1/collections/Favorites/entries")

    def test_a_name_with_a_space_or_a_slash_survives(self) -> None:
        """A collection is named by a user, so it is not a safe path segment."""
        self.assertEqual(hub_library.entries_url("http://hub:8001", "Last Played"),
                         "http://hub:8001/api/v1/collections/Last%20Played/entries")
        self.assertIn("A%2FB", hub_library.entries_url("http://hub:8001", "A/B"))

    def test_a_trailing_slash_on_the_hub_does_not_double(self) -> None:
        self.assertEqual(hub_library.entries_url("http://hub:8001/"),
                         "http://hub:8001/api/v1/library/entries")


if __name__ == "__main__":
    unittest.main()
