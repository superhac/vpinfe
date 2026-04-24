from __future__ import annotations

from nicegui import ui


def load_page_style(filename: str) -> None:
    """Load a stylesheet from managerui/static for the current client page."""
    href = f"/static/{filename.lstrip('/')}"
    ui.add_head_html(f'<link rel="stylesheet" href="{href}">')


def load_manager_styles() -> None:
    """Load the shared Manager UI stylesheet for the current page."""
    load_page_style("manager.css")


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


def dialog_card(width: str = "650px", *, classes: str = "", style: str = ""):
    """Create the standard dark Manager UI dialog card."""
    merged_classes = f"w-[{width}] manager-dialog-card {classes}".strip()
    merged_style = "background: var(--surface); border-radius: var(--radius);"
    if style:
        merged_style = f"{merged_style} {style}"
    return ui.card().classes(merged_classes).style(merged_style)


def page_header(title: str):
    """Create the standard compact page header container."""
    with ui.card().classes("w-full mb-4 manager-page-header"):
        with ui.row().classes("w-full justify-between items-center p-4 gap-4") as row:
            ui.label(title).classes("text-2xl font-bold").style("color: var(--ink); flex-shrink: 0;")
            return row
