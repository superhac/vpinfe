from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from nicegui import ui
from nicegui.events import ValueChangeEventArguments

from common.i18n import t
from console import verbs


@contextmanager
def opened(title: str, *, wide: bool = False, full: bool = False,
           persistent: bool = False, classes: str = "") -> Iterator[ui.dialog]:
    """Draw the dialog's contents inside; the caller awaits the dialog it yields.

    A title of "" draws none, for a dialog whose title changes as it goes.
    """
    props = " ".join(p for p in ("persistent" if persistent else "",
                                 "maximized" if full else "") if p)
    dialog = made().props(props)
    with dialog, ui.card().classes(" ".join(("console-dialog",
                                             "console-dialog--wide" if wide else "",
                                             "console-dialog--full" if full else "",
                                             classes)).strip()):
        if title:
            ui.label(title).classes("console-dialog-title")
        yield dialog


def made() -> ui.dialog:
    """An empty dialog, for one that is not a question and draws its own card.

    It is deleted once hidden, so it opens once; a `hide` listener goes on before that.
    """
    with ui.element() as origin:
        origin.visible = False
        dialog = ui.dialog()

    def gone() -> None:
        if dialog.value:
            return
        dialog.delete()
        if not origin.is_deleted:
            origin.delete()

    def opening(event: ValueChangeEventArguments) -> None:
        if event.value and not listening:
            listening.append(True)
            dialog.on("hide", gone)

    listening: list[bool] = []
    dialog.on_value_change(opening)
    return dialog


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


def quiet(label: str, on_click: Callable[[], Any], *, icon: str) -> ui.button:
    return ui.button(label, icon=icon, on_click=on_click).props("flat no-caps")


def cancel(on_click: Callable[[], Any], label: str = "") -> ui.button:
    return quiet(label or t("word.cancel"), on_click, icon=verbs.CANCEL)


def aside(label: str, on_click: Callable[[], Any], *, icon: str) -> ui.button:
    """A second act, quiet and on the far left, away from the answer."""
    return quiet(label, on_click, icon=icon).classes("console-dialog-aside")


def answer(label: str, on_click: Callable[[], Any], *, icon: str,
           danger: bool = False) -> ui.button:
    return ui.button(label, icon=icon, on_click=on_click) \
        .props("no-caps" + (" color=negative" if danger else ""))


def focus(box: ui.dialog, control: Any, *, select: bool = False) -> None:
    """The caret in `control` once the dialog is up, or with `select` its text selected
    so typing replaces it. Quasar's autofocus does not land in a dialog, and anything
    earlier than `show` is overridden by its own focus.

    Steps down to the first `input` or `textarea` inside `control`, or focuses `control`
    itself where there is none.
    """
    then = ";requestAnimationFrame(() => target.select())" if select else ""
    box.on("show", lambda: ui.run_javascript(
        "((field) => { const target = field.matches('input,textarea') ? field"
        f" : (field.querySelector('input,textarea') || field); target.focus(){then}; }})"
        f"(document.getElementById('c{control.id}'))"))


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
