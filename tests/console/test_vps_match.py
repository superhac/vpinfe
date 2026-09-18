"""The walk over a selection: what it writes, and what it leaves alone.

The picker itself is a dialog and is driven in the browser; what is worth pinning here is
the part a person's fingers cannot easily prove - that a game passed over is not rewritten
because it happened to be in the selection.
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest.mock import patch

from console import vps_match


async def _ran_here(fn, *args, **kwargs):
    """Stands in for `run.io_bound`, and must stay awaitable: a plain value makes the
    walk's `await` raise into its own except, and every assertion still passes."""
    return fn(*args, **kwargs)


class FakeLibrary:
    """Records the writes rather than making them."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, dict]] = []

    def set_game_overrides(self, game_id: str, changes: dict) -> dict:
        self.writes.append((game_id, changes))
        return {}


def games(*names: str) -> list[dict[str, Any]]:
    return [{"id": f"id-{name}", "name": name} for name in names]


def walk_answering(answers: list, chosen: list[dict[str, Any]]) -> FakeLibrary:
    """Run a walk where the picker returns `answers` in order."""
    library = FakeLibrary()
    handed = iter(answers)

    async def fake_ask(_library, _game, place="", walking=False):
        assert walking, "the walk must ask in walking mode, or there is no Skip"
        assert place, "every game in a walk says where it is in the run"
        return next(handed)

    with patch.object(vps_match, "ask", fake_ask), \
            patch.object(vps_match.ui, "notify", lambda *a, **k: None), \
            patch.object(vps_match.run, "io_bound",
                         _ran_here):
        asyncio.run(vps_match.walk(library, chosen))
    return library


class TheWalk(unittest.TestCase):

    def test_a_pick_is_written_against_the_game_it_was_asked_for(self) -> None:
        library = walk_answering(["vps-1"], games("A"))
        self.assertEqual(library.writes, [("id-A", {"alt_vps_id": "vps-1"})])

    def test_skipping_writes_nothing_at_all(self) -> None:
        """The reason this walks rather than running: a game in the selection that the
        user passes over keeps whatever match it already had."""
        library = walk_answering([vps_match.CANCELLED, vps_match.CANCELLED],
                                 games("A", "B"))
        self.assertEqual(library.writes, [])

    def test_stopping_leaves_the_rest_of_the_selection_untouched(self) -> None:
        library = walk_answering(["vps-1", vps_match.STOPPED], games("A", "B", "C"))
        self.assertEqual(library.writes, [("id-A", {"alt_vps_id": "vps-1"})])

    def test_clearing_is_a_write_and_not_a_skip(self) -> None:
        """An empty answer means "drop the binding", which is a decision; `CANCELLED`
        means "I did not decide". Two outcomes that look alike and are not."""
        library = walk_answering([vps_match.CLEARED], games("A"))
        self.assertEqual(library.writes, [("id-A", {"alt_vps_id": ""})])

    def test_a_failed_write_does_not_end_the_run(self) -> None:
        """Thirty games in, one bad write should cost that game and not the other
        twenty-nine."""
        library = FakeLibrary()
        handed = iter(["vps-1", "vps-2"])
        calls: list[str] = []

        def sometimes(game_id: str, changes: dict) -> dict:
            calls.append(game_id)
            if game_id == "id-A":
                raise RuntimeError("no")
            return {}

        library.set_game_overrides = sometimes  # type: ignore[method-assign]

        async def fake_ask(_l, _g, place="", walking=False):
            return next(handed)

        with patch.object(vps_match, "ask", fake_ask), \
                patch.object(vps_match.ui, "notify", lambda *a, **k: None), \
                patch.object(vps_match.run, "io_bound",
                             _ran_here):
            asyncio.run(vps_match.walk(library, games("A", "B")))

        self.assertEqual(calls, ["id-A", "id-B"])

    def test_the_stop_sentinel_can_never_be_a_catalog_id(self) -> None:
        """It travels the same return as an id, so it has to be something the catalog
        cannot answer with."""
        self.assertIn("\x00", vps_match.STOPPED)


if __name__ == "__main__":
    unittest.main()
