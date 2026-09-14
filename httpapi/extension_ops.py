"""What core lets an extension do to the library.

One table, kept beside the routes rather than inside the extension host, because these
are core's functions and adding a route is the moment somebody should be deciding whether
extensions get it too.

**Every operation here is the service the matching route calls.** The route is a thin
adapter over the same function - it adds the path, the scope gate in its
`dependencies=[...]`, and the response model, and nothing else. So an extension reaches
exactly the code an HTTP client reaches, and the two cannot drift; the host cannot end up
with a smaller copy of the library, which it silently had once before. The scope gate is
not lost by going straight to the service: `offer` below names the scope for each one, and
the host is what checks it.

The names are what an extension calls them, not what the service is called. A service is
named for the noun it acts on; an extension author is reading a list of things they can do.
"""

from __future__ import annotations

from typing import Any

from common.extensions.games import offer
from common.games import game_lens, game_ops, library_vps_state, media_ops, table_ops
from common.host import play_service

from . import scopes


def _vps_state(game_id: str) -> dict:
    return library_vps_state.state_of(game_lens.game_or_refuse(game_id), game_id)


def _launch(game_id: str, table: str = "") -> dict:
    """Start a game. `table` picks one of its tables; left out, the default one."""
    return play_service.start(game_id, table or None)


def _set_details(game_id: str, **fields: Any) -> dict:
    return game_ops.set_details(game_id, dict(fields))


# Reading is one scope and writing another. Taking an entry's details from a catalog is
# a write, because it changes the record.
#
# Launching is neither, and has its own. It takes over the cabinet rather than editing
# something, and the scope vocabulary already said so before extensions existed: reading
# what is happening is not the same as causing it to happen, and stopping a table
# somebody may be mid-game on is a third thing again. An extension that wants to start a
# game asks for that by name, and whoever installs it reads it by name.
READS = {
    "list_games": game_lens.listing,
    "get_game": game_lens.detail,
    "game_tables": table_ops.rows_of,
    "game_media": media_ops.game_media,
    "table_media": media_ops.table_media,
    "media_detail": media_ops.detail,
    "vps_state": _vps_state,
    "vps_details": game_ops.vps_details,
}

LAUNCHES = {
    "launch_game": _launch,
}

WRITES = {
    "set_details": _set_details,
    "rate_game": game_ops.set_rating,
    "rate_table": table_ops.set_rating,
    "set_tags": game_ops.set_tags,
    "set_favorite": game_ops.set_favorite,
    "set_default_table": table_ops.set_default,
    "set_play_record": game_ops.set_play_record,
    "reset_play_record": game_ops.reset_play_record,
    "take_vps_details": game_ops.adopt_details,
    "remove_media": media_ops.remove,
    "forget_table": table_ops.forget,
    "add_keyed_table": table_ops.add_keyed,
}


def offer_all() -> None:
    """Hand the whole table to the extension host. Once, before anything loads."""
    for name, run in READS.items():
        offer(name, scopes.GAMES_READ, run)
    for name, run in WRITES.items():
        offer(name, scopes.GAMES_WRITE, run)
    for name, run in LAUNCHES.items():
        offer(name, scopes.LAUNCH_INVOKE, run)
