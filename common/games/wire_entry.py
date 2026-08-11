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

from common.media_specs import MEDIA_SPECS
from common.timestamps import iso_to_epoch


class WireGame:
    """One entry's game half, readable by everything that reads a `Game`.

    Only the fields the filter axes and sort keys ask for: a lens for matching and
    ordering, not a stand-in for the game.
    """


    def __init__(self, game: dict[str, Any], entry: dict[str, Any] | None = None) -> None:
        user = game.get("user") or {}
        entry = entry or {}
        assets = entry.get("assets") or {}
        self.gameDirName = game.get("dir_name") or ""
        self.creation_time = iso_to_epoch(game.get("created_at"))
        # Empty, not missing: they name the hub's disk, so a player holding them would
        # hold an address it cannot reach - but a reader still expects the attribute.
        self.fullPathGame = ""
        self.fullPathVPXfile = ""
        self.pupPackExists = bool(assets.get("pup_pack"))
        self.altColorExists = bool(assets.get("alt_color"))
        self.altSoundExists = bool(assets.get("alt_sound"))
        # `resolved_kinds` reports a kind when its attribute is non-empty and never reads
        # the value, so the kind's own name stands in for the path the hub did not send.
        present = set(entry.get("media") or [])
        for spec in MEDIA_SPECS:
            setattr(self, spec.attr, spec.key if spec.key in present else "")
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
    """A wire entry's game, as something the accessors can read. The whole entry is
    passed because assets and media are resolved per entry, not per game."""
    return WireGame(entry.get("game") or {}, entry)
