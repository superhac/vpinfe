from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class GameDialogContext:
    """Shared callbacks/state access used while moving table dialogs out of tables.py."""

    refresh_games: Optional[Callable[[], None]] = None
    refresh_missing: Optional[Callable[[], None]] = None


def default_context() -> GameDialogContext:
    return GameDialogContext()
