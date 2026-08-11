"""A wire entry wearing the shape the metadata accessors read.

Filtering and sorting read `meta_config` off a `Game`. A client holding a copy of the
library has no `meta_config` - it has entries, whose fields the hub already resolved.
Rebuilding the sections those fields came from lets the same axis registry and the same
sort keys answer on both sides.

`name` arrives already resolved, including any `alt_title` and any leading article the
hub moved. Putting it back under `Info.Title` is safe only because moving an article in
a title that has had one moved is a no-op.
"""

from __future__ import annotations

from typing import Any

from common.timestamps import iso_to_epoch


class WireGame:
    """One entry's game half, readable by everything that reads a `Game`.

    Only the fields the filter axes and sort keys ask for: a lens for matching and
    ordering, not a stand-in for the game.
    """

    __slots__ = ("gameDirName", "meta_config", "creation_time")

    def __init__(self, game: dict[str, Any]) -> None:
        user = game.get("user") or {}
        self.gameDirName = game.get("dir_name") or ""
        self.creation_time = iso_to_epoch(game.get("created_at"))
        self.meta_config = {
            "Info": {
                "Title": game.get("name") or "",
                "Manufacturer": game.get("manufacturer") or "",
                "Year": str(game.get("year") or ""),
                "Type": game.get("type") or "",
                "Themes": list(game.get("themes") or []),
            },
            # The flat `rating` is the same value; `user` is where it moved to, so it is
            # what gets read here.
            "User": {
                "Rating": user.get("rating", game.get("rating", 0)) or 0,
                "StartCount": user.get("play_count", 0) or 0,
                # Back to the epoch integer the key is specced as, because that is what
                # the sort reads it as.
                "LastRun": iso_to_epoch(user.get("last_played")) or 0,
            },
            # Seconds, which is what the sort uses - ordering on `User.RunTime`'s minutes
            # ties every game with under a minute on it.
            "vpinfe": {"run_time_seconds": user.get("play_time_seconds", 0) or 0},
        }


def game_of(entry: dict[str, Any]) -> WireGame:
    """The game half of a wire entry, as something the accessors can read."""
    return WireGame(entry.get("game") or {})
