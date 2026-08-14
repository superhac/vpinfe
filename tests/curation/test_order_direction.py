"""`order.direction` applies to every sort, and stored collections do not reorder.

A collection stored with a non-title sort and `Ascending` *behaved* as descending: the
sort key negated its value and the reverse step only ever named title and year. Honouring
the stored value now would turn such a list around to express an intent the user could
not have had, because the value never meant anything. The migration writes down the
direction those collections were already being shown in.
"""

import json
from types import SimpleNamespace

from common.games.collection_migration import (
    ORDER_DIRECTION_MIGRATION,
    ensure_order_direction,
)
from common.games.collection_resolver import resolve
from common.games.collection_store import (
    COLLECTIONS_SCHEMA,
    DIRECTION_LABELS,
    ORDER_ALIASES,
    SORT_LABELS,
    THEME_SORT_NAMES,
    CollectionStore,
)
from common.games.game_metadata import play_record
from frontend.game_state import SORT_FOR_ORDER
from tests.support.library import TempTree


def _game(gid, title, last_run=0):
    return SimpleNamespace(
        gameDirName=title,
        creation_time=0,
        meta_config={
            "Info": {"Title": title, "Manufacturer": "Bally", "Year": "1995",
                     "Type": "SS", "Themes": []},
            "User": {"Rating": 0, "LastRun": last_run, "StartCount": 0, "RunTime": 0},
            "vpinfe": {"game_id": gid},
            "tables": {f"{gid}-t": {"id": f"{gid}-t", "filename": f"{title}.vpx"}},
        },
    )


class SortVocabularyTests(TempTree):
    """One declaration, so a surface cannot offer a name the store cannot resolve."""

    # What a collection can sort on that is not part of a play record. Everything else
    # it offers is a field of one, and has to be spelled the way that record spells it.
    LIBRARY_SORTS = {"title", "year", "added"}

    def test_a_sort_on_a_play_record_field_is_spelled_the_way_it_is_reported(self) -> None:
        """`play_record` says its names match the sort axes, and `play_time` had drifted
        from the `play_time_seconds` it reports - the same field named twice with nothing
        comparing them. Durations name their unit; a count and a timestamp do not need to.
        """
        reported = set(play_record({}))

        self.assertEqual(set(SORT_LABELS) - self.LIBRARY_SORTS - reported, set())

    def test_the_theme_is_still_answered_with_its_own_sort_names(self) -> None:
        """ORDER_ALIASES carries token aliases as well as the published spellings, so
        inverting the whole map would answer `get_current_sort_state` with one of them."""
        self.assertEqual(SORT_FOR_ORDER["play_time_seconds"], "RunTime")
        self.assertEqual(set(SORT_FOR_ORDER.values()), set(THEME_SORT_NAMES))

    def test_the_bare_duration_token_still_reads(self) -> None:
        """A dev install could have stored it before the sort named its unit."""
        self.assertEqual(ORDER_ALIASES["play_time"], "play_time_seconds")


class StoredSpellingTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.path = self.root / "collections.json"

    def _order_of(self, block):
        self.path.write_text(json.dumps({
            "schema": COLLECTIONS_SCHEMA,
            "collections": [{"name": "T", "type": "filter", "filters": {},
                             "order": block}]}), encoding="utf-8")
        return CollectionStore(str(self.path)).get_order("T")

    def test_an_old_spelling_in_the_order_block_still_names_its_sort(self) -> None:
        """The block is read verbatim, so an alias only applied to the criteria left the
        bare token matching no branch - the list came back in title order, silently."""
        self.assertEqual(self._order_of({"by": "play_time", "direction": "desc"}),
                         {"by": "play_time_seconds", "direction": "desc"})

    def test_a_2x_spelling_in_the_order_block_reads_too(self) -> None:
        self.assertEqual(self._order_of({"by": "RunTime", "direction": "desc"})["by"],
                         "play_time_seconds")

    def test_a_current_token_is_unchanged(self) -> None:
        self.assertEqual(self._order_of({"by": "last_played", "direction": "asc"}),
                         {"by": "last_played", "direction": "asc"})

    def test_every_2x_spelling_maps_onto_an_offered_sort(self) -> None:
        self.assertEqual(set(ORDER_ALIASES.values()) - set(SORT_LABELS), set())

    def test_every_offered_sort_has_a_label_and_a_direction_has_both(self) -> None:
        self.assertTrue(all(label.strip() for label in SORT_LABELS.values()))
        self.assertEqual(set(DIRECTION_LABELS), {"asc", "desc"})

    def test_manual_is_not_offered(self) -> None:
        """It means the member array, which is not a choice for a collection that
        filters - and the editor builds its dropdown straight off this."""
        self.assertNotIn("manual", SORT_LABELS)


class OrderBlockTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.path = self.root / "collections.json"
        self.store = CollectionStore(str(self.path))

    def test_setting_an_order_drops_the_criteria_that_said_it(self) -> None:
        """`get_order` reads the block first, so a leftover `sort_by` is a second and
        now-stale answer in the same file."""
        self.store.add_filter_collection("Recent", sort_by="LastRun",
                                         order_by="Ascending")
        self.store.set_order("Recent", "play_count", "desc")
        self.store.save()

        stored = json.loads(self.path.read_text())["collections"][0]
        self.assertNotIn("sort_by", stored["filters"])
        self.assertNotIn("order_by", stored["filters"])
        self.assertEqual(self.store.get_order("Recent"),
                         {"by": "play_count", "direction": "desc"})


class OrderDirectionMigrationTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.path = self.root / "collections.json"

    def _store(self):
        return CollectionStore(str(self.path))

    def _with_order(self, name, by, direction):
        store = self._store()
        store.add_filter_collection(name)
        store.set_order(name, by, direction)
        store.save()
        return store

    def test_a_sort_that_ignored_direction_is_written_down_as_descending(self) -> None:
        self._with_order("Recent", "last_played", "asc")

        self.assertEqual(ensure_order_direction(self._store()), 1)

        self.assertEqual(self._store().get_order("Recent"),
                         {"by": "last_played", "direction": "desc"})

    def test_the_list_the_user_had_comes_back_in_the_same_order(self) -> None:
        """The point of the whole conversion, end to end: `asc` was showing a
        most-recent-first list, and it still does."""
        self._with_order("Recent", "last_played", "asc")
        ensure_order_direction(self._store())
        games = [_game("old", "Apollo 13", last_run=50),
                 _game("new", "Zaccaria", last_run=300)]

        entries = resolve("Recent", self._store(), games)

        self.assertEqual([e.game.gameDirName for e in entries],
                         ["Zaccaria", "Apollo 13"])

    def test_the_sorts_that_honoured_direction_are_left_alone(self) -> None:
        """Title and year already reversed, so `asc` there is a real choice."""
        for by in ("title", "year"):
            with self.subTest(by=by):
                self.path.unlink(missing_ok=True)
                self._with_order("Everything", by, "asc")

                self.assertEqual(ensure_order_direction(self._store()), 0)
                self.assertEqual(self._store().get_order("Everything")["direction"],
                                 "asc")

    def test_a_curated_order_is_left_alone(self) -> None:
        """`manual` is the member array; direction does not describe it."""
        store = self._store()
        store.add_collection("Friday Night")
        store.set_order("Friday Night", "manual", "asc")
        store.save()

        self.assertEqual(ensure_order_direction(self._store()), 0)
        self.assertEqual(self._store().get_order("Friday Night")["by"], "manual")

    def test_it_runs_once_so_a_later_ascending_choice_survives(self) -> None:
        """Direction is a real control now. Re-running this would take it back off the
        user every time they picked it."""
        self._with_order("Recent", "last_played", "asc")
        ensure_order_direction(self._store())

        store = self._store()
        store.set_order("Recent", "last_played", "asc")
        store.save()

        self.assertEqual(ensure_order_direction(self._store()), 0)
        self.assertEqual(self._store().get_order("Recent")["direction"], "asc")

    def test_it_records_that_it_ran_even_when_nothing_moved(self) -> None:
        self._with_order("Everything", "title", "asc")

        ensure_order_direction(self._store())

        self.assertTrue(self._store().has_migrated(ORDER_DIRECTION_MIGRATION))

    def test_a_file_from_a_newer_build_is_left_alone(self) -> None:
        """Same rule the other conversions follow: this build cannot know what else a
        newer one put in the file."""
        self.path.write_text(json.dumps({
            "schema": COLLECTIONS_SCHEMA + 1,
            "collections": [{"name": "Recent", "type": "filter", "filters": {},
                             "order": {"by": "last_played", "direction": "asc"}}],
        }), encoding="utf-8")

        self.assertEqual(ensure_order_direction(self._store()), 0)
        self.assertEqual(self._store().get_order("Recent")["direction"], "asc")
