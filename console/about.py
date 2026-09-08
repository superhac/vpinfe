"""What this install and this machine are.

The facts a person is asked for when they report something: version, build, OS, browser,
and where this install keeps its files. Metrics answers what the machine is *doing*;
this answers what it *is*, and the two are on separate pages because one changes every
two seconds and the other does not change at all.

**The page exists for its copy button.** Reading fourteen fields off a screen and typing
them into an issue is where a report goes wrong, so the whole set travels as one block
of text, assembled by the install rather than by whoever is looking at it.

The copy happens in the browser at the moment of the click. A browser only allows one
while it still believes a person just asked, and this Console is server-rendered - a
click that goes to the server and comes back has spent that permission on the way.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from nicegui import run, ui

from console import panel

logger = logging.getLogger("vpinfe.console.about")

# Both halves run in the browser at the moment of the click, which is the whole point.
# The clipboard API is a secure-context feature and http://cab.local:8000 - the ordinary
# way this install is reached from another machine - is not one, so the old command is
# what is left there. It needs the click's own permission, and a Console click that goes
# to the server and back has spent it by the time anything runs.
_COPY_JS = """() => {
  const text = %s;
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => emit(true), () => emit(false));
    return;
  }
  const box = document.createElement('textarea');
  box.value = text;
  box.style.position = 'fixed';
  box.style.top = '-1000px';
  document.body.appendChild(box);
  box.focus();
  box.select();
  let done = false;
  try { done = document.execCommand('copy'); } catch (e) { done = false; }
  document.body.removeChild(box);
  emit(done);
}"""


def build(library, state: dict[str, Any], redraw: Callable[[], None]) -> None:
    """Read once when the page opens. None of it changes while VPinFE runs."""
    held: dict[str, Any] = {"text": ""}

    with ui.column().classes("w-full gap-3") as body:
        pass

    async def load(refresh: bool = False) -> None:
        try:
            found = await run.io_bound(library.about, refresh)
        except Exception as exc:  # noqa: BLE001 - this page says why, never 500s
            body.clear()
            with body:
                panel.facts(ui, [panel.intro(f"Could not read this install: {exc}")])
            return
        held["text"] = str(found.get("text") or "")
        _draw(body, found.get("groups") or [], held, load)

    ui.timer(0.01, load, once=True)


def _draw(body, groups: list[dict[str, Any]], held: dict[str, Any],
          reload: Callable[..., Any]) -> None:
    body.clear()
    with body:
        with ui.row().classes("items-center gap-2 w-full no-wrap"):
            ui.label("Everything a bug report asks for, in one block") \
                .classes("console-help grow min-w-0")
            panel.action("Copy", lambda event: _copied(bool(event.args), held["text"]),
                         icon="content_copy",
                         hint="Put all of it on the clipboard",
                         js=_COPY_JS % json.dumps(held["text"]))()
            panel.action("Refresh", lambda: reload(True), icon="refresh",
                         hint="Read it again")()
        # One list for all of them, headings inside it, the way Settings next door
        # draws its sections: a list per group sizes a label column per group, and the
        # values then start at four different places down one page.
        entries: list[tuple[Any, Any]] = []
        for group in groups:
            entries.append((panel.HEADING, str(group.get("heading") or "")))
            entries += [(str(fact.get("label") or ""), str(fact.get("value") or ""))
                        for fact in group.get("facts") or []]
        panel.facts(ui, entries)


def _copied(done: bool, text: str) -> None:
    """Copied, or shown so it can be copied by hand.

    A button that silently does nothing is worse than no button. Where the browser
    refused - an old command in a page it does not trust - the text goes on screen
    already selected.
    """
    if done:
        ui.notify("Copied", type="positive")
        return
    _show_to_copy(text)


def _show_to_copy(text: str) -> None:
    with ui.dialog() as dialog, ui.card().classes("console-card w-full max-w-2xl"):
        ui.label("This browser will not let a page write to the clipboard") \
            .classes("console-panel-heading")
        ui.label("Press the usual copy shortcut - it is already selected.") \
            .classes("console-help")
        ui.textarea(value=text).props("outlined readonly rows=18") \
            .classes("w-full console-log")
        panel.action("Close", dialog.close)()
    dialog.open()
    # Found in the document rather than through the element's own id: `getElement`
    # answers with the Vue component, whose root here is a fragment, so there is no
    # node on it to search. One dialog is open, and it holds one text box.
    #
    # Half a second in, because the dialog focuses itself on the way in and undoes an
    # earlier selection - which would leave the line above promising something untrue.
    # On focus as well, so a click into the box cannot leave it unselected.
    ui.timer(0.5, lambda: ui.run_javascript(
        '(() => { const t = document.querySelector(".q-dialog textarea"); '
        'if (!t) return; '
        'if (!t.dataset.selectAll) { t.dataset.selectAll = "1"; '
        't.addEventListener("focus", () => t.select()); } '
        't.focus(); t.select(); })()'), once=True)
