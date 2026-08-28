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
        return list(self.members)

    # -- writes
    def set_members(self, section, members):
        self.members = list(members)

    def set_order(self, section, by, direction="asc", paging_group=None):
        self.order = by
        self.direction = direction

    def get_order(self, section):
        return {"by": self.order or "title", "direction": self.direction or "asc"}

    def set_limit(self, section, limit):
        self.limit = limit

    def set_image(self, section, filename):
        self.image = filename

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


class OrderTests(Harness):
    def test_the_order_is_stored_and_recorded_as_manual(self):
        """Both halves. Storing the array without recording `manual` leaves the resolver
        sorting by title, which is the same as not having written it."""
        self.use(Manager(["g1", "g2", "g3"]))
        api.set_order("Coll", CollectionOrderRequest(games=["g3", "g1", "g2"]))
        self.assertEqual(self.manager.members, ["g3", "g1", "g2"])
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
        self.assertEqual(self.manager.members, ["g3", "g1"])

    def test_an_unknown_game_is_refused_and_nothing_is_written(self):
        self.use(Manager(["g1"]))
        with self.assertRaises(InvalidRequestError):
            api.patch_collection("Coll", PatchCollectionRequest(games=["g1", "nope"]))
        self.assertEqual(self.manager.members, ["g1"])

    def test_games_and_filters_together_are_refused(self):
        self.use(Manager(["g1"]))
        with self.assertRaises(InvalidRequestError):
            api.patch_collection("Coll", PatchCollectionRequest(
                games=["g1"], filters=api.models.CollectionFilters()))

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

    def test_setting_membership_on_a_filter_collection_is_refused(self):
        self.use(Manager(["g1"], is_filter=True))
        with self.assertRaises(ConflictError):
            api.patch_collection("Coll", PatchCollectionRequest(games=["g1"]))

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


if __name__ == "__main__":
    unittest.main()
