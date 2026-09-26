"""A Console handler called from a test the way a click calls it: from a slot on the page.

An async test runs in a task of its own, and a task starts with no slot, so a handler
that takes the page it is called from finds none there.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

# Made at import, outside any task, where NiceGUI still hands out the script's own page.
_PRESSED = ui.element()


async def press(handler: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
    """`handler(*args, **kwargs)`, called and awaited from a slot on the page."""
    with _PRESSED:
        return await handler(*args, **kwargs)
