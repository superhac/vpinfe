"""What core lets an extension do to the library.

One table, kept beside the routes rather than inside the extension host, because these
are core's functions and adding a route is the moment somebody should be deciding whether
extensions get it too.

**The route handlers are called directly, not over HTTP.** They are plain functions; the
scope gate lives in each route's `dependencies=[...]`, which only applies to a request
arriving over the wire. So an extension reaches exactly the code an HTTP client reaches,
and the two cannot drift - which they had, silently, while the host kept its own smaller
copy of the library.

The names are what an extension calls them, not what the handler is called. A handler is
named for its route; an extension author is reading a list of things they can do.
"""

from __future__ import annotations

from common.extensions.games import offer

from . import games, models, scopes


def _details(game_id: str, **fields):
    return games.put_game_details(game_id, models.GameDetails(**fields))


def _rate_game(game_id: str, rating):
    return games.put_game_rating(game_id, models.RatingRequest(rating=rating))


def _rate_table(game_id: str, table_id: str, rating):
    return games.put_table_rating(game_id, table_id, models.RatingRequest(rating=rating))


def _tag(game_id: str, tags):
    return games.put_game_tags(game_id, models.TagsRequest(tags=list(tags)))


def _favorite(game_id: str, favorite: bool):
    return games.put_game_favorite(game_id, models.FavoriteRequest(favorite=favorite))


def _play_record(game_id: str, play_count=None, play_time_seconds=None,
                 last_played=None):
    """Set what a game arrives already having done. A field left out is left alone."""
    return games.put_play_record(game_id, models.PlayRecordUpdate(
        play_count=play_count, play_time_seconds=play_time_seconds,
        last_played=last_played))


def _default_table(game_id: str, table_id: str):
    return games.put_default_table(game_id, models.TableDefault(table_id=table_id))


def _launch(game_id: str, table: str = ""):
    """Start a game. `table` picks one of its tables; left out, the default one."""
    return games.launch_game(
        game_id, models.LaunchRequest(file=table) if table else None)


# Reading is one scope and writing another. Taking an entry's details from a catalog is
# a write, because it changes the record.
#
# Launching is neither, and has its own. It takes over the cabinet rather than editing
# something, and the scope vocabulary already said so before extensions existed: reading
# what is happening is not the same as causing it to happen, and stopping a table
# somebody may be mid-game on is a third thing again. An extension that wants to start a
# game asks for that by name, and whoever installs it reads it by name.
READS = {
    "list_games": games.list_games,
    "get_game": games.get_game,
    "game_tables": games.get_games,
    "game_media": games.get_game_media,
    "table_media": games.get_table_media,
    "media_detail": games.get_game_media_detail,
    "vps_state": games.get_vps_state,
    "vps_details": games.get_vps_details,
}

LAUNCHES = {
    "launch_game": _launch,
}

WRITES = {
    "set_details": _details,
    "rate_game": _rate_game,
    "rate_table": _rate_table,
    "set_tags": _tag,
    "set_favorite": _favorite,
    "set_default_table": _default_table,
    "set_play_record": _play_record,
    "reset_play_record": games.reset_play_record,
    "take_vps_details": games.put_vps_details,
    "remove_media": games.delete_game_media,
    "forget_table": games.delete_table,
    "add_keyed_table": games.add_keyed_table,
}


def offer_all() -> None:
    """Hand the whole table to the extension host. Once, before anything loads."""
    for name, run in READS.items():
        offer(name, scopes.GAMES_READ, run)
    for name, run in WRITES.items():
        offer(name, scopes.GAMES_WRITE, run)
    for name, run in LAUNCHES.items():
        offer(name, scopes.LAUNCH_INVOKE, run)
