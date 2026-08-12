"""The library as a player reads it off a hub.

A player with no library of its own asks the hub for entries and builds its own payload
from them. This turns the wire rows into the same objects `entries_for` produces locally,
so everything downstream - filters, sorts, the payload builder - cannot tell which side
the library came from.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urljoin

from common import http_client
from common.games.collection_resolver import Entry
from common.games.wire_entry import WireGame, table_of

logger = logging.getLogger("vpinfe.common.games.hub_library")

# A library is one request, and a cold one on a large library is not instant. Longer than
# the shared default, which is sized for a metadata lookup.
LIBRARY_TIMEOUT = 30

def entries_url(hub_url: str, collection: str = "", *, expanded: bool = False) -> str:
    """Where a player asks for entries. Empty means the whole library, which is its own
    endpoint rather than a collection: no stored collection means "all of it"."""
    name = collection.strip()
    path = f"api/v1/collections/{quote(name, safe='')}/entries" if name \
        else "api/v1/library/entries"
    query = "?expanded=true" if expanded else ""
    return urljoin(hub_url.rstrip("/") + "/", path + query)


def hub_services(hub_url: str, *, timeout: int = http_client.DEFAULT_TIMEOUT) -> dict[str, Any]:
    """What the hub says about its own servers, from its discovery document.

    The asset server is the one a player has to be told about: artwork is on a different
    port from the API, and assuming 8000 is right only until someone moves it. Empty when
    the hub cannot be reached or says nothing - the caller keeps its own answer, which is
    what a single-machine install has always used.
    """
    url = urljoin(hub_url.rstrip("/") + "/", "api/v1/")
    try:
        payload = http_client.get_json(url, timeout=timeout)
    except Exception:
        logger.debug("Could not read the hub's discovery document", exc_info=True)
        return {}
    services = payload.get("services") if isinstance(payload, dict) else None
    return services if isinstance(services, dict) else {}


def announce_to_hub(hub_url: str, config, *, timeout: int = http_client.DEFAULT_TIMEOUT) -> bool:
    """Tell the hub this player exists. True if it was recorded.

    Best effort on purpose: a hub that refuses or cannot be reached must not stop a player
    starting. The roster is for attribution - putting a name to the `install_id` an event
    already carries - so failing to register costs a label, not a capability.

    The address is not sent. The hub reads it off the socket, which is the only party that
    knows how this player was actually reached.
    """
    from common import install_identity

    # Minted here if this install has none. Announcing is the first thing that needs an
    # identity, and it runs before the API starts - which is the other place that mints
    # one. An id that is not on disk is not an identity, so this writes.
    try:
        install_id = install_identity.ensure_id(config)
    except Exception:
        logger.debug("Could not establish an install id; not announcing", exc_info=True)
        return False
    if not install_id:
        return False
    try:
        http_client.put_json(
            urljoin(hub_url.rstrip("/") + "/", "api/v1/players"),
            {"install_id": install_id,
             "display_name": install_identity.display_name(config),
             "roles": install_identity.roles(config)},
            timeout=timeout)
    except Exception:
        logger.debug("Could not announce this player to %s", hub_url, exc_info=True)
        return False
    return True


def _entry_from_wire(row: dict[str, Any]) -> Entry:
    """One wire row as the Entry the rest of the frontend already reads. `siblings` comes
    from the hub, which is the only side that can see a game's other tables."""
    return Entry(game=WireGame(row.get("game") or {}, row),
                 table=table_of(row),
                 siblings=int(row.get("siblings") or 1))


def fetch_entries(hub_url: str, collection: str = "", *, expanded: bool = False,
                  timeout: int = LIBRARY_TIMEOUT) -> list[Entry]:
    """The hub's entries for a collection, as local Entry objects.

    Raises rather than returning an empty list: a hub that cannot be reached is not a hub
    with no games, and a caller showing an empty wheel for it would be reporting the wrong
    thing.
    """
    payload = http_client.get_json(entries_url(hub_url, collection, expanded=expanded),
                                   timeout=timeout)
    rows = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(f"Hub at {hub_url} did not return an entry list")
    return [_entry_from_wire(row) for row in rows if isinstance(row, dict)]
