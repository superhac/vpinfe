"""PATCH a collection, and set the order of its games.

The order is the part worth pinning. A manual collection's member array *is* its order,
but only when the collection records `manual` - otherwise the resolver sorts by title and
the array is written and never read. That made the reorder route silently do nothing, and
a write nobody can see is worse than one that fails.
"""

from __future__ import annotations

import contextlib
import unittest

from common.games.collection_store import MANUAL_ORDER
from httpapi import collections as api
from httpapi.errors import ConflictError, InvalidRequestError, NotFoundError
from httpapi.models import CollectionOrderRequest, PatchCollectionRequest


class Manager:
    """Enough CollectionStore for the write routes."""

    def __init__(self, members, is_filter=False, name="Coll"):
        self.name = name
        self.members = list(members)
        self.filter = is_filter
        self.filters = {}
        self.excluded = []
        self.paging = None
        self.order = None
        self.direction = None
        self.limit = None
        self.image = None
        self.renamed_to = None

    # -- reads the routes make
    def get_collections_name(self):
        return [self.name]

    def is_filter_based(self, section):
        return self.filter

    def get_members(self, section):
        """Game ids, de-duplicated - what the store's own accessor returns."""
        seen = []
        for ref in self._refs():
            if ref["game"] not in seen:
                seen.append(ref["game"])
        return seen

    def get_member_refs(self, section):
        return [dict(ref) for ref in self._refs()]

    def _refs(self):
        return [m if isinstance(m, dict) else {"game": m} for m in self.members]

    # -- writes
    def add_member(self, section, game_id, table_id="", after_table=None):
        ref = {"game": game_id} | ({"table": table_id} if table_id else {})
        if ref in self._refs():
            return
        at = None
        if after_table is not None:
            sibling = {"game": game_id} | ({"table": after_table} if after_table else {})
            at = next((i for i, m in enumerate(self._refs()) if m == sibling), None)
        if at is None:
            self.members.append(ref)
        else:
            self.members.insert(at + 1, ref)

    def remove_member(self, section, game_id, table_id=""):
        self.members = [r for r in self._refs()
                        if not (r["game"] == game_id
                                and (not table_id or r.get("table") == table_id))]

    def get_excluded_refs(self, section):
        return [dict(r) for r in self.excluded]

    def exclude(self, section, game_id, table_id=""):
        ref = {"game": game_id} | ({"table": table_id} if table_id else {})
        if ref not in self.excluded:
            self.excluded.append(ref)

    def unexclude(self, section, game_id, table_id=""):
        self.excluded = [r for r in self.excluded
                         if not (r["game"] == game_id
                                 and (not table_id or r.get("table") == table_id))]

    def set_members(self, section, members):
        """Normalised to refs, as the store does - a caller may hand it either, and a
        fake that kept bare ids would let a route pass here and lose tables in real
        use."""
        self.members = [m if isinstance(m, dict) else {"game": m} for m in members]

    def set_order(self, section, by, direction="asc", paging_group=None):
        """Normalised as the store does it: anything it cannot read - "" included -
        is the collection saying nothing, and the key is dropped rather than stored."""
        from common.games.collection_store import normalize_paging_group
        self.order = by
        self.direction = direction
        self.paging = normalize_paging_group(paging_group)

    def get_order(self, section):
        return {"by": self.order or "title", "direction": self.direction or "asc",
                "paging_group": self.paging}

    def set_limit(self, section, limit):
        self.limit = limit

    def set_image(self, section, filename):
        self.image = filename

    def has_filters(self, section):
        return self.filter

    def clear_filters(self, section):
        self.filter = False
        self.filters = {}

    def rename_collection(self, old, new):
        self.renamed_to = new
        self.name = new

    def make_filter_collection(self, section, filters, order=None, limit=None):
        self.filter = True

    @contextlib.contextmanager
    def mutate(self):
        yield self


class Harness(unittest.TestCase):
    def use(self, manager, catalog=("g1", "g2", "g3")):
        self.manager = manager
        self._mgr = api.get_collections_manager
        self._cat = api._catalog
        self._row = api._row_or_404
        self._res = api._resource_for
        # Restored too, or a test that relaxes the table check leaves it relaxed for
        # every test after it in the file. `game_id` is worse than that - it is a
        # module shared with everything else, so leaving it patched broke three
        # event-stream tests in a different file.
        self._one = api._one_table_of
        self._res_fn = api._resolved
        self._game_id = api.game_identity.game_id
        api.get_collections_manager = lambda: manager
        api._catalog = lambda: {g: object() for g in catalog}
        api._row_or_404 = lambda name: {"name": name}
        api._resource_for = lambda row: {"name": row["name"]}

    def tearDown(self):
        if hasattr(self, "_mgr"):
            api.get_collections_manager = self._mgr
            api._catalog = self._cat
            api._row_or_404 = self._row
            api._resource_for = self._res
            api._one_table_of = self._one
            api._resolved = self._res_fn
            api.game_identity.game_id = self._game_id


class OrderTests(Harness):
    def test_the_order_is_stored_and_recorded_as_manual(self):
        """Both halves. Storing the array without recording `manual` leaves the resolver
        sorting by title, which is the same as not having written it."""
        self.use(Manager(["g1", "g2", "g3"]))
        api.set_order("Coll", CollectionOrderRequest(games=["g3", "g1", "g2"]))
        self.assertEqual(self.manager.members,
                         [{"game": "g3"}, {"game": "g1"}, {"game": "g2"}])
        self.assertEqual(self.manager.order, MANUAL_ORDER)

    def test_an_order_missing_a_member_is_refused(self):
        """Otherwise a dropped id is indistinguishable from a deliberate removal."""
        self.use(Manager(["g1", "g2", "g3"]))
        with self.assertRaises(InvalidRequestError):
            api.set_order("Coll", CollectionOrderRequest(games=["g1", "g2"]))
        self.assertEqual(self.manager.members, ["g1", "g2", "g3"])

    def test_an_order_adding_a_member_is_refused(self):
        self.use(Manager(["g1", "g2"]))
        with self.assertRaises(InvalidRequestError):
            api.set_order("Coll", CollectionOrderRequest(games=["g1", "g2", "g3"]))
        self.assertEqual(self.manager.members, ["g1", "g2"])

    def test_a_filter_collection_has_no_order_to_set(self):
        self.use(Manager(["g1"], is_filter=True))
        with self.assertRaises(ConflictError):
            api.set_order("Coll", CollectionOrderRequest(games=["g1"]))


class OrderKeepsNamedTablesTests(Harness):
    """A member names a game and optionally one of its tables (section 2.10). Rebuilding
    the array from bare ids threw every named table away - measured, a three-ref
    tournament list came back as two bare games on a 204.

    **The list is one entry per row, changed 2026-08-30.** It used to name each game
    once and move that game's refs as a block, which cannot express the thing 2.10 opens
    by asking for - *"multiple tables for a single game, in an arbitrary order"* - and
    the route said so itself. hubui now draws one row per ref with its own handle, so a
    drag has to be able to move one of them; naming the game once could only move both.
    """

    def test_a_named_table_survives_a_reorder(self):
        self.use(Manager([{"game": "g1", "table": "t1"}, {"game": "g2"}]))
        api.set_order("Coll", CollectionOrderRequest(games=["g2", "g1"]))
        self.assertEqual(self.manager.members,
                         [{"game": "g2"}, {"game": "g1", "table": "t1"}])

    def test_two_tables_of_one_game_can_be_placed_apart(self):
        """The thing section 2.10 opens by asking for. Naming the game at two positions
        deals its refs out one each, in their own stored order."""
        self.use(Manager([{"game": "g1", "table": "t1"}, {"game": "g2"},
                          {"game": "g1", "table": "t2"}]))
        api.set_order("Coll", CollectionOrderRequest(games=["g1", "g1", "g2"]))
        self.assertEqual(self.manager.members,
                         [{"game": "g1", "table": "t1"},
                          {"game": "g1", "table": "t2"},
                          {"game": "g2"}])

    def test_the_membership_check_counts_refs_not_games(self):
        """A row is a ref, so a game holding two of them is named twice. Listing it once
        is a short order, and a short order drops what it left out - which is the silent
        removal this check exists to refuse."""
        self.use(Manager([{"game": "g1", "table": "t1"}, {"game": "g1", "table": "t2"}]))
        with self.assertRaises(InvalidRequestError):
            api.set_order("Coll", CollectionOrderRequest(games=["g1"]))
        self.assertEqual(len(self.manager.members), 2, "and nothing was written")


class PatchTests(Harness):
    def test_a_rename_leaves_everything_else_alone(self):
        self.use(Manager(["g1", "g2"]))
        api.patch_collection("Coll", PatchCollectionRequest(name="Renamed"))
        self.assertEqual(self.manager.renamed_to, "Renamed")
        self.assertEqual(self.manager.members, ["g1", "g2"])
        self.assertIsNone(self.manager.limit)

    def test_membership_replaces_in_the_order_given(self):
        self.use(Manager(["g1"]))
        api.patch_collection("Coll", PatchCollectionRequest(games=["g3", "g1"]))
        self.assertEqual(self.manager.members, [{"game": "g3"}, {"game": "g1"}])

    def test_an_unknown_game_is_refused_and_nothing_is_written(self):
        self.use(Manager(["g1"]))
        with self.assertRaises(InvalidRequestError):
            api.patch_collection("Coll", PatchCollectionRequest(games=["g1", "nope"]))
        self.assertEqual(self.manager.members, ["g1"])

    def test_games_and_filters_together_are_written(self):
        """Both, in one patch. COLLECTIONS 2.11 makes them combinable and the resolver
        applies members over what the criteria matched - refusing the pair was this API
        carrying 2.x's two kinds forward."""
        self.use(Manager(["g1"]))
        api.patch_collection("Coll", PatchCollectionRequest(
            games=["g1"], filters=api.models.CollectionFilters()))
        self.assertEqual(self.manager.members, [{"game": "g1"}])
        self.assertTrue(self.manager.filter)

    def test_a_cap_below_one_is_refused(self):
        self.use(Manager(["g1"]))
        with self.assertRaises(InvalidRequestError):
            api.patch_collection("Coll", PatchCollectionRequest(limit=0))
        self.assertIsNone(self.manager.limit)

    def test_clear_limit_lifts_the_cap(self):
        """Absent and null are the same thing over JSON, so lifting a cap needs a word
        of its own rather than a null nobody can distinguish."""
        self.use(Manager(["g1"]))
        api.patch_collection("Coll", PatchCollectionRequest(clear_limit=True))
        self.assertIsNone(self.manager.limit)

    def test_membership_can_be_set_on_a_collection_that_filters(self):
        """A member of a collection that also carries criteria states what the
        collection holds for that game, whether or not the criteria matched it."""
        self.use(Manager(["g1"], is_filter=True))
        api.patch_collection("Coll", PatchCollectionRequest(games=["g2", "g1"]))
        self.assertEqual(self.manager.members, [{"game": "g2"}, {"game": "g1"}])

    def test_renaming_onto_an_existing_name_is_refused(self):
        manager = Manager(["g1"])
        manager.get_collections_name = lambda: ["Coll", "Taken"]
        self.use(manager)
        with self.assertRaises(ConflictError):
            api.patch_collection("Coll", PatchCollectionRequest(name="Taken"))
        self.assertIsNone(manager.renamed_to)

    def test_a_collection_that_is_gone(self):
        manager = Manager(["g1"])
        manager.get_collections_name = lambda: []
        self.use(manager)
        with self.assertRaises(NotFoundError):
            api.patch_collection("Coll", PatchCollectionRequest(name="x"))


class PatchOrderTests(Harness):
    """A collection's order, set without restating anything else.

    Before this existed the only way a manual collection got an order was by being
    arranged, so every other sort was unreachable for one - the field was on the
    resource and there was no route that wrote it.
    """

    def test_the_order_is_written(self):
        self.use(Manager(["g1"]))
        api.patch_collection("Coll", PatchCollectionRequest(order_by="year",
                                                            direction="desc"))
        self.assertEqual(self.manager.order, "year")
        self.assertEqual(self.manager.direction, "desc")

    def test_a_direction_alone_keeps_the_field(self):
        """Only what is sent is written, so a direction must not reset the sort."""
        manager = Manager(["g1"])
        manager.order = "rating"
        self.use(manager)
        api.patch_collection("Coll", PatchCollectionRequest(direction="desc"))
        self.assertEqual(self.manager.order, "rating")
        self.assertEqual(self.manager.direction, "desc")

    def test_a_field_nothing_sorts_by_is_refused(self):
        self.use(Manager(["g1"]))
        with self.assertRaises(InvalidRequestError):
            api.patch_collection("Coll", PatchCollectionRequest(order_by="sideways"))
        self.assertIsNone(self.manager.order)

    def test_manual_is_offered_where_there_is_an_arrangement(self):
        self.use(Manager(["g1"]))
        api.patch_collection("Coll", PatchCollectionRequest(order_by="manual"))
        self.assertEqual(self.manager.order, "manual")

    def test_a_filter_collection_has_no_arrangement_to_follow(self):
        """`manual` is the stored member array, and a filter collection has none - so
        the order would name something that does not exist."""
        self.use(Manager(["g1"], is_filter=True))
        with self.assertRaises(ConflictError):
            api.patch_collection("Coll", PatchCollectionRequest(order_by="manual"))
        self.assertIsNone(self.manager.order)

    def test_an_order_beside_filters_is_the_one_that_wins(self):
        """Sent together, the explicit order is the answer - not the one carried in
        the filter block, which is where a filter collection's order also lives."""
        self.use(Manager(["g1"]))
        api.patch_collection("Coll", PatchCollectionRequest(
            filters=api.models.CollectionFilters(order_by="title"),
            order_by="last_played", direction="desc"))
        self.assertEqual(self.manager.order, "last_played")
        self.assertEqual(self.manager.direction, "desc")

    def test_saying_nothing_about_order_writes_nothing(self):
        self.use(Manager(["g1"]))
        api.patch_collection("Coll", PatchCollectionRequest(name="Renamed"))
        self.assertIsNone(self.manager.order)


class NamedTableTests(Harness):
    """A member names a game, or it names a table (COLLECTIONS 2.10). Until the route
    took a table it could only ever say the first."""

    def _tables(self, *ids):
        api._one_table_of = lambda game_id, table_id: (
            None if not table_id or table_id in ids
            else (_ for _ in ()).throw(NotFoundError(f"no table {table_id}")))

    def test_a_member_can_name_one_table(self):
        self.use(Manager([]))
        self._tables("t1")
        api.add_member("Coll", "g1", api.models.MemberRequest(table="t1"))
        self.assertEqual(self.manager.members, [{"game": "g1", "table": "t1"}])

    def test_no_table_names_the_game(self):
        """Which resolves to whichever table is its default, so the collection follows
        a replacement rather than holding the one that was there when it was added."""
        self.use(Manager([]))
        self._tables()
        api.add_member("Coll", "g1", None)
        self.assertEqual(self.manager.members, [{"game": "g1"}])

    def test_two_tables_of_one_game_are_two_members(self):
        self.use(Manager([]))
        self._tables("t1", "t2")
        api.add_member("Coll", "g1", api.models.MemberRequest(table="t1"))
        api.add_member("Coll", "g1", api.models.MemberRequest(table="t2"))
        self.assertEqual(self.manager.members,
                         [{"game": "g1", "table": "t1"}, {"game": "g1", "table": "t2"}])

    def test_removing_without_a_table_removes_every_ref_for_the_game(self):
        self.use(Manager([{"game": "g1", "table": "t1"},
                          {"game": "g1", "table": "t2"}, {"game": "g2"}]))
        api.remove_member("Coll", "g1")
        self.assertEqual(self.manager.members, [{"game": "g2"}])

    def test_removing_one_named_table_leaves_the_other(self):
        self.use(Manager([{"game": "g1", "table": "t1"},
                          {"game": "g1", "table": "t2"}]))
        api.remove_member("Coll", "g1", table="t1")
        self.assertEqual(self.manager.members, [{"game": "g1", "table": "t2"}])

    def test_removing_something_that_is_not_a_member(self):
        self.use(Manager([{"game": "g1"}]))
        with self.assertRaises(NotFoundError):
            api.remove_member("Coll", "g2")


class ExclusionTests(Harness):
    """The other half of COLLECTIONS 2.12. Naming a table freezes a choice; excluding
    one says "everything except this" and keeps tracking what is added later. Neither
    substitutes for the other, and only naming had a route."""

    def test_a_game_can_be_excluded(self):
        self.use(Manager([]))
        api._one_table_of = lambda game_id, table_id: None
        api.add_exclusion("Coll", "g1", None)
        self.assertEqual(self.manager.excluded, [{"game": "g1"}])

    def test_one_table_can_be_excluded(self):
        self.use(Manager([]))
        api._one_table_of = lambda game_id, table_id: None
        api.add_exclusion("Coll", "g1", api.models.MemberRequest(table="t2"))
        self.assertEqual(self.manager.excluded, [{"game": "g1", "table": "t2"}])

    def test_excluding_twice_is_idempotent(self):
        self.use(Manager([]))
        api._one_table_of = lambda game_id, table_id: None
        api.add_exclusion("Coll", "g1", None)
        api.add_exclusion("Coll", "g1", None)
        self.assertEqual(self.manager.excluded, [{"game": "g1"}])

    def test_an_exclusion_can_be_lifted(self):
        self.use(Manager([]))
        api._one_table_of = lambda game_id, table_id: None
        api.add_exclusion("Coll", "g1", None)
        api.remove_exclusion("Coll", "g1")
        self.assertEqual(self.manager.excluded, [])

    def test_lifting_one_that_is_not_there(self):
        self.use(Manager([]))
        with self.assertRaises(NotFoundError):
            api.remove_exclusion("Coll", "g1")


class KeepTheResultTests(Harness):
    """Criteria as a way of building a list rather than a rule to keep: what they match
    becomes the membership, naming the table each row resolved to, and the criteria go.
    """

    def _resolves_to(self, *pairs):
        class _Entry:
            def __init__(self, game, table):
                self.game, self.table = game, {"id": table}
        api._resolved = lambda name: [_Entry(g, t) for g, t in pairs]
        api.game_identity.game_id = lambda game: game

    def test_the_matches_become_members_naming_their_tables(self):
        self.use(Manager([], is_filter=True))
        self._resolves_to(("g1", "t1"), ("g2", "t2"))
        api.members_from_filters("Coll")
        self.assertEqual(self.manager.members,
                         [{"game": "g1", "table": "t1"}, {"game": "g2", "table": "t2"}])

    def test_the_criteria_are_dropped(self):
        """Which is what makes the collection static - it stops changing under its
        owner, and only then is a hand arrangement a coherent thing to store."""
        self.use(Manager([], is_filter=True))
        self._resolves_to(("g1", "t1"))
        api.members_from_filters("Coll")
        self.assertFalse(self.manager.filter)

    def test_the_cap_is_lifted(self):
        """It capped the rule's output. The membership now *is* that output, so leaving
        it in place would cut the same list a second time."""
        manager = Manager([], is_filter=True)
        manager.limit = 3
        self.use(manager)
        self._resolves_to(("g1", "t1"))
        api.members_from_filters("Coll")
        self.assertIsNone(self.manager.limit)

    def test_exclusions_go_with_the_criteria(self):
        """They said "everything except this" about a rule. With no rule left there is
        nothing to except, and keeping them would subtract from a hand-edited list."""
        manager = Manager([], is_filter=True)
        manager.excluded = [{"game": "g9"}]
        self.use(manager)
        self._resolves_to(("g1", "t1"))
        api.members_from_filters("Coll")
        self.assertEqual(self.manager.excluded, [])

    def test_a_collection_with_no_criteria_has_no_result_to_keep(self):
        self.use(Manager(["g1"]))
        with self.assertRaises(ConflictError):
            api.members_from_filters("Coll")


class PagingGroupTests(Harness):
    def test_a_group_is_written(self):
        self.use(Manager(["g1"]))
        api.patch_collection("Coll", PatchCollectionRequest(paging_group="sort"))
        self.assertEqual(self.manager.paging, "sort")

    def test_nonsense_is_refused_rather_than_normalised_away(self):
        """`normalize_paging_group` answers None for anything unreadable, so accepting
        this would turn a typo into "follow the player" and report success."""
        self.use(Manager(["g1"]))
        with self.assertRaises(InvalidRequestError):
            api.patch_collection("Coll", PatchCollectionRequest(paging_group="sideways"))

    def test_empty_clears_it(self):
        """"" is a value here - it says follow the player - so it is not the same as
        saying nothing about paging at all."""
        manager = Manager(["g1"])
        manager.paging = "sort"
        self.use(manager)
        api.patch_collection("Coll", PatchCollectionRequest(paging_group=""))
        self.assertIsNone(self.manager.paging)


if __name__ == "__main__":
    unittest.main()
