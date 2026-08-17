"""One collection resolved into the entries every window shows, cached.

Three windows onto one library were three copies that happened to agree, each deriving
the same answer. Only the controller takes input, so only one could ever change it. The
window keeps its name, its socket and its browser; this is everything else.
"""

from __future__ import annotations

import logging
import threading

from common.config_access import NetworkConfig
from common.games import collection_resolver, hub_library
from common.games.collection_store import (
    BUILTIN_ALL,
    DEFAULT_DIRECTION,
    DEFAULT_ORDER_BY,
    public_name,
)
from common.games.collections_service import get_collections_manager
from common.games.game_repository import all_games
from frontend import game_state

logger = logging.getLogger("vpinfe.frontend.library_resolver")


def hub_url(ini_config) -> str:
    """The hub this install reads its library from, or "" when it holds its own."""
    try:
        return NetworkConfig.from_config(ini_config.config).hub_url
    except Exception:
        logger.debug("Could not read the hub URL; holding a local library", exc_info=True)
        return ""


class LibraryResolver:
    """The library, the filter, the sort, and the list they produce.

    Mutation is serialized: the bridge runs each window's call on its own thread, so
    one shared view makes a sort and a read genuinely concurrent.
    """

    def __init__(self, ini_config, games=None):
        self._ini_config = ini_config
        self.lock = threading.RLock()

        # With a hub set, this install is a player: the list it holds is entries the hub
        # resolved, not games off a disk it may not have.
        self._hub_url = hub_url(ini_config)
        self._remote = bool(self._hub_url)

        # An unreadable library is empty, not fatal: a first run before the scan has
        # none, and wants a view it can fill in rather than an exception.
        if games is not None:
            self.all_games = games
        else:
            try:
                self.all_games = self._load()
            except Exception:
                logger.debug("No library to build a view from yet", exc_info=True)
                self.all_games = []
        self.filtered_games: list = []
        self.current_filters = game_state.default_filter_state()
        self.current_collection = BUILTIN_ALL
        self.current_sort = DEFAULT_ORDER_BY
        self.current_order = DEFAULT_DIRECTION

        self._entries: list | None = None
        self._entries_source: list | None = None
        self._payload: str | None = None
        self._payload_key: tuple | None = None
        self._stale = True

        self.reset_to_default()

    def _load(self, collection: str = ""):
        """The library: the hub's entries, or the local games. Different kinds of thing,
        which `rebuild_entries` knows."""
        if self._remote:
            return hub_library.fetch_entries(self._hub_url, collection)
        return all_games()

    def reload(self):
        """The library again. A hub that has gone quiet leaves the list alone: a stale
        wheel beats a player emptying its screen because one request failed."""
        try:
            self.all_games = self._load(public_name(self.current_collection))
        except Exception:
            logger.debug("Could not reload the library; keeping what is shown",
                         exc_info=True)
        return self.all_games

    def collections(self):
        """This install's collections. One place to ask, so the view and the resolver
        behind it cannot end up reading two different files."""
        return get_collections_manager()

    def resolve_view(self, collection: str, criteria: dict | None = None) -> list:
        """The entries a collection holds, off this install's library.

        A player's are the hub's answer, kept as it arrived: the resolver reads a game's
        table dicts out of its `.info` and those stayed on the hub, so re-resolving here
        would quietly produce an empty wheel.

        `criteria` is the filter menu's controls, which make a collection out of the
        library rather than narrowing one - so they only arrive with `builtin:all`.
        """
        if self._remote:
            return list(self.all_games)
        store = self.collections()
        if criteria:
            store.set_view_filters(criteria)
        return collection_resolver.resolve(collection, store, self.all_games)

    # -- staleness -----------------------------------------------------------

    def mark_stale(self) -> None:
        """Say the library may have moved. One broadcast, one refresh - not one per
        window answering it."""
        with self.lock:
            self._stale = True

    def refresh_if_stale(self, refresh) -> None:
        """Run `refresh` only if nothing has since. `refresh` takes no arguments."""
        with self.lock:
            if not self._stale:
                return
            self._stale = False
        refresh()

    # -- derivation ----------------------------------------------------------

    def rebuild_entries(self) -> None:
        """Recompute the list the wheel steps through. Call after a sort: it mutates in
        place, so the change is otherwise undetectable."""
        games = self.filtered_games or []
        self._entries = list(games)
        self._entries_source = games
        self._payload = None

    @property
    def entries(self):
        """What an index from a theme addresses. Rebuilt when the source list is
        replaced, so swapping `filtered_games` cannot leave a stale view behind.

        Under the lock: a sort mutates `filtered_games` in place, so a rebuild racing one
        walks a list being reordered - and a reader can otherwise see `_entries` assigned
        before `_entries_source` catches up. The window that produced that is small enough
        to pass on a laptop and fail on a shared CI runner.
        """
        with self.lock:
            games = self.filtered_games or []
            if self._entries is None or self._entries_source is not games:
                self.rebuild_entries()
            return self._entries

    def reset_to_default(self) -> None:
        """The whole library, by the (article-reordered) title, ascending. Resetting
        drops whatever collection or filter was on screen - that is what it is for. The
        list is the resolver's own, so an in-place sort never disturbs the library behind
        it; the Game objects stay shared, so a rating update still reaches every reader."""
        with self.lock:
            self.current_collection = BUILTIN_ALL
            self.current_sort = DEFAULT_ORDER_BY
            self.current_order = DEFAULT_DIRECTION
            self.filtered_games = self.resolve_view(BUILTIN_ALL)
            self.rebuild_entries()

    # -- the payload ---------------------------------------------------------

    def payload(self, contract: int, *, collection: str = "") -> str:
        """The theme payload, built once however many windows ask. Cleared by
        `rebuild_entries`, which every change to the list goes through."""
        # The order is in the key because it decides the groups stamped on each entry.
        key = (contract, collection, self.current_sort)
        with self.lock:
            if self._payload is None or self._payload_key != key:
                self._payload = game_state.games_json(
                    self.entries, contract, collection=collection,
                    order_by=self.current_sort)
                self._payload_key = key
            return self._payload

    def invalidate_payload(self) -> None:
        """Drop the built payload without rebuilding the list behind it."""
        with self.lock:
            self._payload = None
