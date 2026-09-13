"""The web surfaces an install serves: the Console at / and /console, the remote at
/remote.

What the Console contains depends on the install - one curating a library and one
running games do not need the same screens. The remote is the same install seen from a
phone, and it is a second shell rather than the same one narrowed: a workbench is a list
beside an inspector, and one hand cannot hold two panes.
"""

from __future__ import annotations


def register() -> None:
    """Put the Console on the app: its routes, and the stylesheet they all link.

    The mount is not under /console, which is a page. A mount there would match every
    path below it and sit beside a route of the same name, and which of the two answered
    would depend on the order they were added.
    """
    from nicegui import app as nicegui_app

    from console import page, remote, theme  # noqa: F401

    nicegui_app.add_static_files(theme.BASE_MOUNT, str(theme.BASE_CSS.parent))
