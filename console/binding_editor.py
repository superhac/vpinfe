"""What a player presses to do something, said by pressing it.

The bindings for one action, as chips, with a capture that listens for the next key or
controller button. A binding is a selector - `pad:0/button:3` - and typing ten of those
into a text field is what made input feel like configuration rather than a choice.

**A binding two actions claim is the defect this exists to close.** Dispatch resolves a
key to the first action that lists it, so the second one silently does nothing and no
surface ever said so. Here a claimed binding is marked on every action holding it and
named in the tooltip, and taking one is refused before it is stored.

Capture runs in the browser. A key press is a browser event and a gamepad is only
readable there, so the whole listen happens client-side and emits the selector it heard.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from nicegui import ui

from common import input_registry
from console import confirm, panel

logger = logging.getLogger("vpinfe.console.binding_editor")

# Listens until everything is let go, then stores what was held together. So a chord is
# made by pressing two things and a hold by keeping one down - the gesture is the
# notation, and there is no mode to choose first.
#
# Escape cancels rather than binding, so there is a way out that does not cost a binding.
# Somebody who wants Escape itself can still hold it past the hold threshold, which is
# not a cancel.
_CAPTURE_JS = """() => {
  const HOLD_AT = %(hold_at)d;
  const down = new Map();          // token -> when it went down
  const held = [];                 // in the order they arrived
  let longest = 0;
  let settled = null;

  const note = document.createElement('div');
  note.className = 'console-capture';
  document.body.appendChild(note);
  window.__captureOverlay = note;
  const say = (text) => { note.textContent = text; };
  say(%(asking)s);

  const stop = (value) => {
    if (settled) return;
    settled = true;
    window.removeEventListener('keydown', onKey, true);
    window.removeEventListener('keyup', onKeyUp, true);
    clearInterval(pads);
    clearInterval(tick);
    note.remove();
    window.__captureOverlay = null;
    emit(value);
  };

  const arrived = (token) => {
    if (down.has(token)) return;
    down.set(token, Date.now());
    if (!held.includes(token)) held.push(token);
    say(%(holding)s + held.length + (held.length > 1 ? ' inputs' : ' input'));
  };

  const left = (token) => {
    const at = down.get(token);
    if (at === undefined) return;
    longest = Math.max(longest, Date.now() - at);
    down.delete(token);
    // Everything let go: what was held together is the binding.
    if (down.size === 0) stop(assemble());
  };

  const assemble = () => {
    if (!held.length) return '';
    const one = held.length === 1 ? held[0] : 'chord(' + held.join('+') + ')';
    return longest >= HOLD_AT ? one + '@hold:' + Math.round(longest / 100) * 100 : one;
  };

  const onKey = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.repeat) return;
    if (e.code === 'Escape' && !held.length) { stop(''); return; }
    arrived('key:' + e.code);
  };
  const onKeyUp = (e) => { e.preventDefault(); left('key:' + e.code); };

  // Which buttons were already down when this opened, so a held flipper does not bind
  // itself the instant the overlay appears.
  const already = new Set();
  const gamepads = () => [...(navigator.getGamepads ? navigator.getGamepads() : [])]
    .filter(Boolean);
  gamepads().forEach(p => p.buttons.forEach((b, i) => {
    if (b.pressed) already.add(p.index + ':' + i);
  }));
  const pads = setInterval(() => {
    for (const pad of gamepads()) {
      pad.buttons.forEach((b, i) => {
        const seat = pad.index + ':' + i;
        const token = 'pad:' + pad.index + '/button:' + i;
        if (!b.pressed) { already.delete(seat); left(token); return; }
        if (already.has(seat)) return;
        arrived(token);
      });
    }
  }, 40);

  // While something is down, say when it becomes a hold - so a hold is discovered by
  // holding rather than by being told about.
  const tick = setInterval(() => {
    if (!down.size) return;
    const oldest = Math.min(...down.values());
    const ms = Date.now() - oldest;
    if (ms >= HOLD_AT) say(%(hold_said)s);
  }, 80);

  window.addEventListener('keydown', onKey, true);
  window.addEventListener('keyup', onKeyUp, true);
  setTimeout(() => stop(assemble()), 15000);
}"""


def rows(option: dict[str, Any], value: Any, save: Callable[[Any], Any], *,
         section: dict[str, Any] | None = None,
         writable: bool = True,
         rerender: Callable[[], None] | None = None) -> Callable[[], None]:
    """One action's bindings, and the way to add another.

    `section` is every action's bindings, because a collision is a fact about two rows
    and this one cannot see it alone - and `rerender` redraws the page rather than this
    row, for the same reason: taking a binding off one action can clear a mark on
    another, and a row that only refreshed itself would leave the other one lying.
    """
    held = _selectors(value)
    # Who holds each binding, not just what clashes: refusing a binding another action
    # already holds is the whole point, and a clash list only names what is *already*
    # broken.
    claimed = input_registry.holders(
        {name: _selectors(one) for name, one in (section or {}).items()})

    async def store(wanted: list[str], *, redraw: bool = True) -> None:
        """Write, and redraw unless the caller is going to stay on screen.

        A redraw rebuilds the page, which takes any menu open on it with it - so an
        editor that saved through this closed itself on the first thing you changed.
        What it edits it updates in place instead, and asks for the redraw when it is
        dismissed.
        """
        if await save(list(wanted)) is False:
            return
        held[:] = list(wanted)
        if redraw and rerender is not None:
            rerender()

    def draw() -> None:
        with ui.element("div").classes("console-chips"):
            for binding in held:
                # By identity, not by the text somebody typed: a chord written in the
                # other order is the same binding, and looking it up raw marks one of
                # the two rows holding it and leaves the other one silent.
                _chip(binding, store,
                      claimed.get(input_registry.identity(binding)) or [], held,
                      writable=writable, rerender=rerender)
            if not held:
                # Amber, because this action cannot be triggered at all - which is the
                # one thing on this page worth going and fixing. Drawn quiet, it read
                # as a binding whose name happened to be "Nothing bound".
                ui.label("Nothing bound") \
                    .classes("console-member-chip console-tier console-tier--warn") \
                    .tooltip("Nothing triggers this - bind something to it")
            if writable:
                _capture(option, held, store, claimed)

    return draw


def _selectors(value: Any) -> list[str]:
    """A binding list, whatever shape it arrived in.

    A stored value is a list and a schema default is the comma-joined string the config
    file would hold. Taking `list()` of the second gives one chip per character, which is
    what this exists to stop.
    """
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(one).strip() for one in (value or []) if str(one).strip()]


def _chip(binding: str, store: Callable[..., Any], claimed_by: list[str],
          held: list, *, writable: bool,
          rerender: Callable[[], None] | None = None) -> None:
    """One binding, and the way into what a gesture could not say.

    Marked where another action claims it too, because the one that loses is invisible
    everywhere else.
    """
    text = str(binding)
    shown = input_registry.describe(text)
    tone = "console-chip-warn" if len(claimed_by) > 1 else "console-chip-quiet"
    # The chip sits in a holder so the remove mark can be placed against its corner
    # without the chip itself becoming a positioning context for its own text.
    holder = ui.element("div").classes("console-chip-holder")
    with holder:
        chip = ui.label(shown).classes(f"console-member-chip {tone}")
    if len(claimed_by) > 1:
        others = [_label_for(name) for name in claimed_by]
        chip.tooltip(f"Also bound to {_and(others)} - only the first one gets it")
    elif text != shown:
        chip.tooltip(text)
    if not writable:
        return

    chip.classes("cursor-pointer")
    with chip:
        _menu(chip, text, store, held, rerender)
    with holder:
        # `click.stop`, or taking a binding off would also open the editor for the
        # binding that is no longer there.
        ui.label("✕").classes("console-chip-remove") \
            .on("click.stop", lambda: _remove(text, shown, store, held)) \
            .tooltip(f"Remove {shown}")


def _menu(chip: Any, binding: str, store: Callable[..., Any], held: list,
          rerender: Callable[[], None] | None) -> None:
    """What a gesture cannot say, on the binding it belongs to.

    A duration is the case: you can hold a button for about a second and a half, and you
    cannot hold it for exactly 1,500ms - so what was captured is a starting point and
    this is where it is set. Adding a hold to a binding that has none is the same edit,
    which is why there is no separate way to do it.

    Opened from the chip rather than sitting in the row: a hold is an exception, and
    charging every binding a duration field for the few that want one is what the
    workbench pattern exists to avoid.

    Edits land on the chip and not through a redraw. The page is rebuilt when the menu
    is dismissed, so a mark that another row's binding now clashes still arrives - just
    not while somebody is still turning the dial.
    """
    # The binding changes under this menu as it is edited, so the current one is held
    # rather than captured: a second edit has to start from the first one's result.
    now = {"text": binding}

    with ui.menu().props("auto-close=false") as menu, \
            ui.column().classes("console-binding-menu gap-2"):
        title = ui.label(input_registry.describe(binding)).classes("console-setting")
        selector = ui.label(binding).classes("console-help")

        async def set_hold(ms: int) -> None:
            wanted = input_registry.with_hold(now["text"], ms)
            if wanted == now["text"]:
                return
            await store([wanted if str(one) == now["text"] else one for one in held],
                        redraw=False)
            was, now["text"] = now["text"], wanted
            shown = input_registry.describe(wanted)
            chip.text = shown
            title.text = shown
            selector.text = wanted
            logger.debug("Rebound %s as %s", was, wanted)

        holding = input_registry.hold_ms(binding)
        with ui.row().classes("items-center gap-2 no-wrap"):
            ui.label("Held for").classes("console-setting grow min-w-0")
            switch = ui.switch(value=bool(holding)) \
                .props("dense color=positive").classes("console-fact-switch")
        seconds = ui.number(value=(holding or DEFAULT_HOLD_MS) / 1000,
                            min=0.1, max=10, step=0.1, suffix="s") \
            .props("dense outlined").classes("console-edit-narrow")
        seconds.bind_visibility_from(switch, "value")

        switch.on_value_change(
            lambda event: set_hold(
                round(float(seconds.value or 0) * 1000) if event.value else 0))
        seconds.on_value_change(
            lambda: set_hold(round(float(seconds.value or 0) * 1000))
            if switch.value else None)
        ui.label("How long it has to be held before it counts") \
            .classes("console-help")

        panel.action("Remove",
                     lambda: _remove(now["text"], input_registry.describe(now["text"]),
                                     store, held),
                     icon="close", danger=True)()

    # Dismissed is when the rest of the page catches up.
    if rerender is not None:
        menu.on("hide", lambda: rerender())


async def _remove(text: str, shown: str, store: Callable[[list], Any],
                  held: list) -> None:
    # Asked about only where pressing something could not make it again. A modifier and
    # an axis have no gesture, so removing one here is a door that opens one way - the
    # case `unrenderable` was written for, back when the same bindings were merely
    # invisible rather than one click from gone.
    if not input_registry.capturable(text) and not await confirm.ask(
            f"Remove {shown}?",
            detail="Nothing here can bind that again yet - it would have to go back "
                   "into the settings file by hand.",
            confirm="Remove"):
        return
    await store([one for one in held if str(one) != text])


# Past this, holding is what the person meant rather than a slow press. Announced on
# screen as it passes, so a hold is found by holding rather than read about. A second,
# because half of one is an ordinary press and nobody means it as a hold.
HOLD_AT_MS = 1000

# What a hold starts at when one is added on the chip rather than performed.
DEFAULT_HOLD_MS = 1000


def _capture(option: dict[str, Any], held: list, store: Callable[[list], Any],
             claimed: dict[str, list[str]]) -> None:
    label = str(option.get("label") or option.get("key") or "this")

    async def heard(event: Any) -> None:
        selector = str(event.args or "").strip()
        if not selector:
            return
        shown = input_registry.describe(selector)
        if input_registry.identity(selector) in [
                input_registry.identity(one) for one in held]:
            ui.notify(f"{shown} already does this.", type="warning")
            return
        # Refused rather than taken with a warning. Dispatch gives a key to the first
        # action that lists it, so taking one that is spoken for would not move it - it
        # would make a binding that looks set and never fires.
        owner = _owner(selector, claimed, option)
        if owner:
            ui.notify(f"{shown} is already {owner}. Take it off there first.",
                      type="warning")
            return
        await store([*held, selector])

    panel.action("Bind", heard, icon="add", inline=True,
                 hint="Press one input, two together, or hold to bind a hold",
                 js=_CAPTURE_JS % {
                     "hold_at": HOLD_AT_MS,
                     "asking": json.dumps(
                         f"Press what should do {label}. Two together makes a chord, "
                         "and keeping it down makes a hold. Esc cancels."),
                     "holding": json.dumps("Holding "),
                     "hold_said": json.dumps("Keep holding for a hold. "
                                             "Let go to bind it."),
                 })()


def _owner(selector: str, claimed: dict[str, list[str]],
           option: dict[str, Any]) -> str:
    """Which other action holds this binding, said as a person would name it."""
    names = [name for name in claimed.get(input_registry.identity(selector), [])
             if name != option.get("key")]
    return _and([_label_for(name) for name in names]) if names else ""


def _label_for(name: str) -> str:
    found = next((one for one in input_registry.actions() if one.name == name), None)
    return found.label if found is not None else name


def _and(names: list[str]) -> str:
    if len(names) < 3:
        return " and ".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"
