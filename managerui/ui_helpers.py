from __future__ import annotations

from nicegui import ui


def load_manager_styles() -> None:
    """Load the shared Manager UI stylesheet for the current page."""
    ui.add_head_html('<link rel="stylesheet" href="/static/manager.css">')


def nav_button(label: str, icon: str, on_click, tooltip: str | None = None):
    button = (
        ui.button(label, icon=icon, on_click=on_click)
        .classes("w-full nav-btn")
        .props("flat align=left")
        .tooltip(tooltip or label)
    )
    return button


def outline_action_button(label: str, icon: str | None = None, *, color_var: str = "--neon-purple", on_click=None):
    button = ui.button(label, icon=icon, on_click=on_click)
    return button.style(
        f"color: var({color_var}) !important; "
        "background: var(--surface) !important; "
        f"border: 1px solid var({color_var}); "
        "border-radius: 18px; "
        "padding: 4px 10px;"
    )
