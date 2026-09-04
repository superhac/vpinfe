"""The library as one install reads it off another.

An install with no library of its own asks for entries and builds its own payload from
them. This turns the wire rows into the same objects the resolver produces locally, so
everything downstream - filters, sorts, the payload builder - cannot tell which side the
library came from.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urljoin

from common import http_client
from common.games.collection_resolver import Entry
from common.games.wire_entry import WireGame, table_of

logger = logging.getLogger("vpinfe.common.games.remote_library")

# A library is one request, and a cold one on a large library is not instant. Longer than
# the shared default, which is sized for a metadata lookup.
LIBRARY_TIMEOUT = 30

def entries_url(library_url: str, collection: str = "") -> str:
    """Where to ask for entries. Empty means the whole library, which is its own endpoint
    rather than a collection: no stored collection means "all of it"."""
    name = collection.strip()
    path = f"api/v1/collections/{quote(name, safe='')}/entries" if name \
        else "api/v1/library/entries"
    return urljoin(library_url.rstrip("/") + "/", path)


def remote_services(library_url: str, *,
                    timeout: int = http_client.DEFAULT_TIMEOUT) -> dict[str, Any]:
    """What that install says about its own servers, from its discovery document.

    The asset server is the one a reader has to be told about: artwork is on a different
    port from the API, and assuming 8000 is right only until someone moves it. Empty when
    it cannot be reached or says nothing - the caller keeps its own answer, which is what
    a single-machine install has always used.
    """
    url = urljoin(library_url.rstrip("/") + "/", "api/v1/")
    try:
        payload = http_client.get_json(url, timeout=timeout)
    except Exception:
        logger.debug("Could not read that install's discovery document", exc_info=True)
        return {}
    services = payload.get("services") if isinstance(payload, dict) else None
    return services if isinstance(services, dict) else {}


def verify_shared_library(entries, local_games) -> dict[str, Any]:
    """Whether this install's own copy of the library is the one it reads, by content.

    Shared storage is what the split assumes and nothing checks: a `game_root_dir` that is
    wrong or unmounted fails one game at a time, at launch, as a file-not-found. This asks
    the question up front and by hash rather than by path, because the same share is
    mounted at different places on different machines - a path comparison would report
    every install as broken.

    Reports rather than decides. `matched`, `missing` (the library has a table this
    install cannot resolve) and `differs` (both have it, the bytes differ) are three
    different problems for a caller to act on, and what to do about each is a policy
    question this does not answer.
    """
    from common.games.tables import table_entries

    local: dict[str, str] = {}
    for game in local_games or ():
        for table in table_entries(getattr(game, "meta_config", {})).values():
            table_id = str(table.get("id", "") or "")
            if table_id:
                local[table_id] = str(table.get("file_hash", "") or "")

    matched, missing, differs, unverifiable = 0, [], [], 0
    for entry in entries or ():
        table_id = getattr(entry, "table_id", "")
        wanted = str((entry.table or {}).get("file_hash", "") or "")
        if not table_id or not wanted:
            # A table the library has not hashed says nothing either way. Counted rather
            # than dropped, so "everything matched" cannot mean "nothing was checked".
            unverifiable += 1
            continue
        if table_id not in local:
            missing.append(table_id)
        elif local[table_id] != wanted:
            differs.append(table_id)
        else:
            matched += 1

    return {"matched": matched, "missing": missing, "differs": differs,
            "unverifiable": unverifiable,
            "shared": not missing and not differs and matched > 0}


def _entry_from_wire(row: dict[str, Any]) -> Entry:
    """One wire row as the Entry the rest of the frontend already reads. `siblings` comes
    from the library, which is the only side that can see a game's other tables."""
    return Entry(game=WireGame(row.get("game") or {}, row),
                 table=table_of(row),
                 siblings=int(row.get("siblings") or 1))


def fetch_entries(library_url: str, collection: str = "",
                  timeout: int = LIBRARY_TIMEOUT) -> list[Entry]:
    """Another install's entries for a collection, as local Entry objects.

    Raises rather than returning an empty list: a library that cannot be reached is not a
    library with no games, and a caller showing an empty wheel for it would be reporting
    the wrong thing.
    """
    payload = http_client.get_json(entries_url(library_url, collection), timeout=timeout)
    rows = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(f"{library_url} did not return an entry list")
    return [_entry_from_wire(row) for row in rows if isinstance(row, dict)]
