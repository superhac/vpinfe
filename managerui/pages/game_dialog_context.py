from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class GameDialogContext:
    """Shared callbacks/state access used while moving game dialogs out of games.py."""

    refresh_games: Callable[[], None] | None = None
    refresh_missing: Callable[[], None] | None = None


def default_context() -> GameDialogContext:
    return GameDialogContext()
