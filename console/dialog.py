from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from nicegui import ui

from common.i18n import t
from console import verbs


@contextmanager
def opened(title: str, *, wide: bool = False, persistent: bool = False,
           classes: str = "") -> Iterator[ui.dialog]:
    """Draw the dialog's contents inside; the caller awaits the dialog it yields."""
    with ui.dialog().props("persistent" if persistent else "") as dialog, \
            ui.card().classes(" ".join(("console-dialog", "console-dialog--wide" if wide else "",
                                        classes)).strip()):
        ui.label(title).classes("console-dialog-title")
        yield dialog


def footer() -> ui.row:
    return ui.row().classes("console-dialog-footer")


def field(value: str = "", *, placeholder: str = "", lines: int = 0) -> Any:
    """The panel's own field, answering nothing until the dialog does."""
    with ui.element("div").classes("console-fact-edit"):
        if lines:
            return ui.textarea(value=value, placeholder=placeholder) \
                .props(f"dense borderless rows={lines} debounce=0") \
                .classes("console-edit-field")
        return ui.input(value=value, placeholder=placeholder) \
            .props("dense borderless debounce=0").classes("console-edit-field")


def cancel(on_click: Callable[[], Any], label: str = "") -> ui.button:
    return ui.button(label or t("word.cancel"), icon=verbs.CANCEL, on_click=on_click) \
        .props("flat no-caps")


def answer(label: str, on_click: Callable[[], Any], *, icon: str,
           danger: bool = False) -> ui.button:
    return ui.button(label, icon=icon, on_click=on_click) \
        .props("no-caps" + (" color=negative" if danger else ""))


def focus(box: ui.dialog, control: Any) -> None:
    """The caret in `control` once the dialog is up. Quasar's autofocus does not land
    in a dialog, and anything earlier than `show` is overridden by its own focus."""
    box.on("show", lambda: ui.run_javascript(
        f"document.getElementById('c{control.id}').focus()"))


def enter_presses(button: ui.button) -> None:
    """Enter anywhere in the dialog but a textarea presses `button`. Bound in the
    browser: NiceGUI does not forward a keyup from a Quasar input inside a dialog."""
    ui.run_javascript(f"""
        (() => {{
          let tries = 0;
          const wire = () => {{
            const button = document.getElementById('c{button.id}');
            if (!button) {{ if (++tries < 40) setTimeout(wire, 25); return; }}
            button.closest('.q-dialog').addEventListener('keyup', (event) => {{
              if (event.key === 'Enter' && event.target.tagName !== 'TEXTAREA') button.click();
            }});
          }};
          wire();
        }})()
    """)
