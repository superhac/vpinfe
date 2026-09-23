"""Filter criteria, translated from the wire into what the store and matcher read.

One translation, shared by what writes a collection and what previews one, so a rule
cannot resolve differently before and after it is saved. `game_type` is stored as
`table_type`, the spelling on disk from before the vocabulary alignment.
"""

from __future__ import annotations

from typing import Any

from common.games.collection_filters import UNCONSTRAINED


def many_in(value: Any) -> str:
    """A criterion as it is stored. A list joins; a string is already stored form."""
    if isinstance(value, list):
        joined = ",".join(str(part).strip() for part in value if str(part).strip())
        return joined or UNCONSTRAINED
    return str(value or UNCONSTRAINED)


def criteria_for(f: Any) -> dict:
    """A criteria block in the shape the store and the matcher read."""
    if f is None:
        return {}
    return {"letter": many_in(f.letter), "theme": many_in(f.theme),
            "table_type": many_in(f.game_type),
            "manufacturer": many_in(f.manufacturer), "year": many_in(f.year),
            "rating": f.rating,
            "rating_or_higher": "true" if f.rating_or_higher else "false",
            "played": f.played, "favorite": f.favorite, "tags": many_in(f.tags)}
