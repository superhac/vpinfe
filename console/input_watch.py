"""The input detector: what this machine's inputs are doing, bound to nothing.

Somebody with `pad:0/button:7` in a config file, or an unlabelled encoder board, has no
way to learn which physical thing that is. Capture answers *what did I just press*; this
answers the harder one - *what is this button* - and until now nothing in VPinFE answered
it at all. A flipper that does nothing is the case it exists for, and it is the first
thing to check before anything else.

**It commits nothing.** Pressing something here changes no setting, which is what lets it
sit on a page next to the bindings without being a trap.

**It reads the browser's inputs**, so it is about the machine somebody is sitting at
rather than the one whose settings are on screen. Configuring a cabinet from a laptop
shows the laptop, and the line under the strip says so - the alternative is somebody
pressing a flipper on the cab and concluding the readout is broken.

**It draws itself in the browser.** A gamepad is only readable there, and a button held
down is a stream - sending each poll to the server would spend a round trip per frame to
show a chip that is already on screen. The names come from Python so there is one table
and not two.
"""

from __future__ import annotations

import json
import logging

from nicegui import ui

from common import input_registry

logger = logging.getLogger("vpinfe.console.input_watch")

# Long enough to read a name after a quick tap, short enough that the strip is about now
# rather than about the last few minutes.
KEEP = 8

_WATCH_JS = """
(() => {
  const root = document.getElementById(%(id)s);
  if (!root || root.dataset.watching) return;
  root.dataset.watching = '1';
  const NAMES = %(names)s;
  const KEEP = %(keep)d;
  // Most recent first. One entry per input: pressing the same thing again moves it back
  // to the front rather than filling the strip with one button.
  const seen = [];

  const keyName = (code) => {
    if (NAMES[code]) return NAMES[code];
    if (/^Key.$/.test(code)) return code.slice(3);
    if (/^Digit.$/.test(code)) return code.slice(5);
    if (code.startsWith('Numpad')) return 'Numpad ' + code.slice(6);
    return code;
  };

  const note = (id, name, down) => {
    const found = seen.find(one => one.id === id);
    if (found) {
      found.down = down;
      if (down) { seen.splice(seen.indexOf(found), 1); seen.unshift(found); }
    } else {
      seen.unshift({id, name, down});
      while (seen.length > KEEP) seen.pop();
    }
    render();
  };

  const render = () => {
    root.textContent = '';
    if (!seen.length) {
      const empty = document.createElement('span');
      empty.className = 'console-member-chip console-chip-quiet';
      empty.textContent = 'Nothing yet';
      root.appendChild(empty);
      return;
    }
    for (const one of seen) {
      const chip = document.createElement('span');
      chip.className = 'console-member-chip console-tier '
        + (one.down ? 'console-tier--on' : 'console-tier--off');
      chip.textContent = one.name;
      chip.title = one.id;
      root.appendChild(chip);
    }
  };

  // Not prevented: this is a readout on a page with other controls, and swallowing keys
  // here would stop somebody typing in the field next to it.
  window.addEventListener('keydown', (e) => {
    if (e.repeat) return;
    note('key:' + e.code, keyName(e.code), true);
  }, true);
  window.addEventListener('keyup', (e) => note('key:' + e.code, keyName(e.code), false),
                          true);

  setInterval(() => {
    const pads = [...(navigator.getGamepads ? navigator.getGamepads() : [])]
      .filter(Boolean);
    for (const pad of pads) {
      pad.buttons.forEach((button, i) => {
        const id = 'pad:' + pad.index + '/button:' + i;
        const known = seen.find(one => one.id === id);
        if (button.pressed === !!(known && known.down)) return;
        // Pads are numbered from zero on the wire and from one in the hand.
        note(id, 'Pad ' + (pad.index + 1) + ' button ' + i, button.pressed);
      });
    }
  }, 60);

  render();
})()
"""


def strip() -> None:
    """The readout itself, for a caller that has already headed it.

    Drawn as a fact row's value so it joins the page's one list rather than starting a
    second grid beside it - which is the same reason a settings foot is rows and not a
    drawing.
    """
    where = ui.element("div").classes("console-chips")
    # Whose inputs, said plainly: this reads the browser's gamepads and keyboard, which
    # is the machine somebody is sitting at - not necessarily the one whose settings are
    # on screen. Configuring a cabinet from a laptop shows the laptop.
    ui.label("Press anything to see what it is. These are the inputs on the machine "
             "you are using, and pressing one binds nothing.").classes("console-help")
    # After the element exists in the document. Its own id is how the script finds it,
    # so two of these on one page do not write into each other.
    ui.timer(0.05, lambda: ui.run_javascript(_WATCH_JS % {
        "id": json.dumps(f"c{where.id}"),
        "names": json.dumps(input_registry.key_names()),
        "keep": KEEP,
    }), once=True)


def watch(*, heading: str = "Input detector") -> None:
    """The readout with its own heading, for a page that is not a list of settings."""
    ui.label(heading).classes("console-group")
    strip()
