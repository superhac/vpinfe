"""The Console: the web surface an install serves, at / and /console.

What it contains depends on the install - one curating a library and one
running games do not need the same screens.
"""

from __future__ import annotations


def register() -> None:
    """Import the page module so its @ui.page decorator registers the route."""
    from console import page  # noqa: F401
