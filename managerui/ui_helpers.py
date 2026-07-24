from __future__ import annotations

from nicegui import ui


def load_page_style(filename: str) -> None:
    """Load a stylesheet from managerui/static for the current client page."""
    href = f"/static/{filename.lstrip('/')}"
    ui.add_head_html(f'<link rel="stylesheet" href="{href}">')


def load_manager_styles() -> None:
    """Load the shared Manager UI stylesheet for the current page."""
    load_page_style("manager.css")


# Per-client teardown callbacks for elements that live outside content_container
# (e.g. a native ui.footer, which attaches to the page QLayout and so is not
# removed by content_container.clear()). The shell runs these when navigating
# between pages so such elements don't leak onto the next page.
_page_teardowns: dict[str, list] = {}


def register_page_teardown(fn) -> None:
    """Register a callback to run when the shell navigates away from this page."""
    _page_teardowns.setdefault(ui.context.client.id, []).append(fn)


# The shell owns a single native ui.footer (a top-level layout element, which
# NiceGUI requires to be a direct child of the page). Pages that need a sticky
# save bar borrow it: fill it on render, empty + hide it on teardown.
_shell_save_bars: dict[str, object] = {}


def set_shell_save_bar(footer) -> None:
    _shell_save_bars[ui.context.client.id] = footer


def get_shell_save_bar():
    return _shell_save_bars.get(ui.context.client.id)


def attach_shell_save_bar(*, count, on_save, on_discard, target_label=None):
    """Fill the shell footer with the slide-up save bar for the current page.

    The page supplies its own dirty-state logic:
      - count():        number of unsaved edits (0 = clean)
      - on_save():      persist the edits and re-baseline
      - on_discard():   revert the inputs to the last-saved values
      - target_label(): optional str shown after the count (e.g. a profile name)

    Returns an update() callable; call it whenever an edit may have changed so the
    bar restyles and slides in/out. The footer is emptied and hidden on teardown.
    """
    footer = get_shell_save_bar()
    if footer is None:
        return lambda: None

    footer.clear()
    footer.value = False
    with footer:
        with ui.element('div').classes('w-full save-bar is-clean') as bar:
            with ui.element('div').classes('save-bar-status'):
                ui.element('div').classes('save-bar-pip')
                status = ui.label('All changes saved')
            discard_btn = ui.button('Discard', icon='undo', on_click=lambda: _discard()).props('flat')
            discard_btn.style('color: var(--ink-muted) !important; border-radius: 18px; padding: 4px 10px;')
            discard_btn.set_visibility(False)
            save_btn = outline_action_button('Save Changes', 'save', on_click=lambda: _save())
            save_btn.classes('save-bar-save')
            save_btn.disable()

    def update():
        n = count()
        dirty = n > 0
        bar.classes(remove='is-clean is-dirty', add='is-dirty' if dirty else 'is-clean')
        (save_btn.enable if dirty else save_btn.disable)()
        discard_btn.set_visibility(dirty)
        if dirty:
            text = f"{n} unsaved change{'s' if n != 1 else ''}"
            label = target_label() if target_label else None
            if label:
                text += f" → {label}"
            status.set_text(text)
        else:
            status.set_text('All changes saved')
        # Slide-up: Quasar animates the footer in only when there are edits.
        footer.value = dirty

    def _save():
        on_save()
        update()

    def _discard():
        on_discard()
        update()

    register_page_teardown(lambda: (footer.clear(), setattr(footer, 'value', False)))
    return update


def run_page_teardowns() -> None:
    """Run and clear the teardown callbacks registered for the current client."""
    for fn in _page_teardowns.pop(ui.context.client.id, []):
        try:
            fn()
        except Exception:
            pass


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


def danger_action_button(label: str, icon: str | None = None, *, on_click=None):
    return outline_action_button(label, icon, color_var="--bad", on_click=on_click)


def primary_action_button(label: str, icon: str | None = None, *, on_click=None):
    return outline_action_button(label, icon, color_var="--neon-cyan", on_click=on_click)


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


def section_card(*, classes: str = "w-full p-4", style: str = ""):
    base_style = "background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);"
    if style:
        base_style = f"{base_style} {style}"
    return ui.card().classes(classes).style(base_style)


def debounced_input(element, milliseconds: int = 250):
    """Apply client-side debounce to NiceGUI/Quasar input-like elements."""
    return element.props(f"debounce={milliseconds}")
