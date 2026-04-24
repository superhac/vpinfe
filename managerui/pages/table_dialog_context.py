from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class TableDialogContext:
    """Shared callbacks/state access used while moving table dialogs out of tables.py."""

    refresh_tables: Optional[Callable[[], None]] = None
    refresh_missing: Optional[Callable[[], None]] = None


def default_context() -> TableDialogContext:
    return TableDialogContext()
