"""The Hub UI: a control plane for the hub, served at /hub."""

from __future__ import annotations


def register() -> None:
    """Import the page module so its @ui.page decorator registers the route."""
    from hubui import page  # noqa: F401
