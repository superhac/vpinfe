"""Every input action VPinFE understands, declared once.

Ten actions, each with one ordered list of bindings. The names say what the player
*meant* rather than which way a stick moved: three surfaces - the wheel, a vertical menu
and a scrolling page - already disagreed about what "left" pointed at, and every overlay
carried a fall-through case as the evidence.

A binding names its own input - `key:<name>`, `pad:<index>/button:<n>` - so an action
needs one list rather than a key per input. Richer selectors - modifiers, axes, hold,
chord - go in this same list, so adding them is a parser change rather than another
migration.
"""

from __future__ import annotations

from dataclasses import dataclass

SECTION = "input"

# Selector prefixes. A binding that starts with neither is not one we can read.
KEY_PREFIX = "key:"
PAD_PREFIX = "pad:"


@dataclass(frozen=True)
class InputAction:
    """One thing a player can ask for, and what is bound to it out of the box."""

    name: str
    bindings: tuple[str, ...]
    label: str
    # What this used to be called, so an existing [Input] section still resolves.
    legacy: tuple[str, ...] = ()
    # What kind of thing it does, for a page that has to show ten of these. Here rather
    # than on the settings schema because this registry is what knows what an action is
    # for - the schema is generated from it and would be restating the answer.
    group: str = ""

    @property
    def config_key(self) -> str:
        return self.name

    @property
    def legacy_joy_key(self) -> str:
        """The `joy*` key this action used to have, for the projections that still answer."""
        return next((k for k in self.legacy if k.startswith("joy")), "")

    @property
    def legacy_key_key(self) -> str:
        """The `key*` key this action used to have."""
        return next((k for k in self.legacy if k.startswith("key")), "")


INPUT_ACTIONS: tuple[InputAction, ...] = (
    InputAction(
        "previous",
        group="Moving through the library",
        bindings=("key:ArrowLeft", "key:ShiftLeft"),
        label="Previous",
        legacy=("joyleft", "keyleft"),
    ),
    InputAction(
        "next",
        group="Moving through the library",
        bindings=("key:ArrowRight", "key:ShiftRight"),
        label="Next",
        legacy=("joyright", "keyright"),
    ),
    # up/down and pageup/pagedown were the same intent under two names: carousel-desktop
    # used up/down for a page-sized jump, which is what paging is. Named for where the
    # selection goes, not the key: "page up" has no answer on a horizontal wheel, and
    # core answered it two ways.
    InputAction(
        "page_previous",
        group="Moving through the library",
        bindings=("key:PageUp", "key:ArrowUp"),
        label="Page Previous",
        legacy=("joypageup", "keypageup", "joyup", "keyup"),
    ),
    InputAction(
        "page_next",
        group="Moving through the library",
        bindings=("key:PageDown", "key:ArrowDown"),
        label="Page Next",
        legacy=("joypagedown", "keypagedown", "joydown", "keydown"),
    ),
    InputAction(
        "select",
        group="Playing",
        bindings=("key:Enter",),
        label="Select",
        legacy=("joyselect", "keyselect"),
    ),
    InputAction(
        "back",
        group="Playing",
        bindings=("key:KeyB",),
        label="Back",
        legacy=("joyback", "keyback"),
    ),
    InputAction(
        "menu",
        group="Opening something",
        bindings=("key:KeyM",),
        label="Menu",
        legacy=("joymenu", "keymenu"),
    ),
    InputAction(
        "collection_menu",
        group="Opening something",
        bindings=("key:KeyC",),
        label="Collection Menu",
        legacy=("joycollectionmenu", "keycollectionmenu"),
    ),
    InputAction(
        "tutorial",
        group="Opening something",
        bindings=("key:KeyT",),
        label="Tutorial",
        legacy=("joytutorial", "keytutorial"),
    ),
    InputAction(
        "exit",
        group="Playing",
        bindings=("key:Escape", "key:KeyQ"),
        label="Exit",
        legacy=("joyexit", "keyexit"),
    ),
)


def actions() -> tuple[InputAction, ...]:
    return INPUT_ACTIONS


def defaults() -> dict[str, tuple[str, ...]]:
    """The bindings a fresh install ships, keyed by action."""
    return {action.name: action.bindings for action in INPUT_ACTIONS}


def action_for_legacy_key(key: str) -> str:
    """The action an old `[Input]` key bound, or "" when it bound none."""
    wanted = str(key or "").strip().lower()
    for action in INPUT_ACTIONS:
        if wanted == action.name or wanted in action.legacy:
            return action.name
    return ""


def binding_for_legacy(key: str, value: str) -> list[str]:
    """The selectors an old `[Input]` value means.

    `keyleft = ArrowLeft,ShiftLeft` was a comma-separated list of key names; `joyleft = 3`
    was one gamepad button index and nothing said which pad. Both become selectors.
    """
    name = str(key or "").strip().lower()
    raw = str(value or "").strip()
    if not raw:
        return []
    if name.startswith("joy"):
        index = raw.split(",")[0].strip()
        return [f"{PAD_PREFIX}0/button:{index}"] if index else []
    return [f"{KEY_PREFIX}{part.strip()}" for part in raw.split(",") if part.strip()]


def keys_in(bindings) -> list[str]:
    """The keyboard key names in a binding list - what the UI's keyboard field shows."""
    return [b[len(KEY_PREFIX):] for b in bindings or ()
            if str(b).startswith(KEY_PREFIX) and "+" not in b and "@" not in b]


def pad_buttons_in(bindings) -> list[str]:
    """The plain gamepad button indexes - what the UI's controller field shows."""
    out = []
    for b in bindings or ():
        text = str(b)
        if not text.startswith(PAD_PREFIX) or "@" not in text and "/button:" not in text:
            continue
        if "chord(" in text or "@" in text or "/axis:" in text:
            continue
        out.append(text.rsplit("/button:", 1)[-1])
    return out


# What no gesture can produce. A chord is pressing two things and a hold is keeping one
# down, so both came off this list when capture learned to watch until release; a
# modifier and an axis have no gesture yet - one because Shift is a flipper on a cabinet
# and must stay bindable on its own, the other because it is a tuned value rather than
# a press.
_UNCAPTURABLE = ("ctrl+", "shift+", "alt+", "meta+", "/axis:")


def capturable(binding: str) -> bool:
    """Whether pressing something could produce this binding again.

    Asked before offering to delete one: a surface that removes what nothing can rebuild
    is a door that only opens one way, which is what `unrenderable` was written to
    prevent back when the same bindings were merely invisible.
    """
    text = str(binding or "").lower()
    return not any(mark in text for mark in _UNCAPTURABLE)


def describe(binding: str) -> str:
    """One binding as a person reads it.

    A selector is written for a parser - `pad:0/button:3` - and reading ten of them off a
    settings page is the thing that made bindings feel like configuration rather than a
    choice. Anything this cannot name is returned as it came, because inventing a name
    for a chord would be worse than showing the one that is stored.
    """
    text = normalize(str(binding or "").strip())
    members = chord_members(text)
    if members:
        # Composed, not looked up. "Left Shift + Right Shift, held 1.5s" is built from
        # its parts, which is where the readable names stop being a table.
        said = " + ".join(describe(one) for one in members)
        return f"{said}{_held_for(text)}"
    if text.endswith(_hold_of(text)) and _hold_of(text):
        return f"{describe(text[:-len(_hold_of(text))])}{_held_for(text)}"
    if any(mark in text for mark in ("@", "+", "/axis:")):
        # Whatever is left after chords and holds have been named above: a modifier, an
        # axis, a selector this build has never seen. Returned whole, because inventing
        # a name would say something the binding does not do.
        return text
    if text.startswith(KEY_PREFIX):
        return _key_name(text[len(KEY_PREFIX):])
    if text.startswith(PAD_PREFIX):
        rest = text[len(PAD_PREFIX):]
        pad, _, what = rest.partition("/")
        # Pads are numbered from zero on the wire and from one on screen. A person with
        # one controller has "pad 1", not "pad 0".
        if not what.startswith("button:"):
            # An axis, or something this build has never seen. Half-naming it - "Pad 1"
            # followed by the raw rest - would read as a name while saying nothing.
            return text
        where = f"Pad {int(pad) + 1}" if pad.isdigit() else f"Pad {pad}"
        return f"{where} button {what[len('button:'):]}"
    return text


def hold_ms(binding: str) -> int:
    """How long this binding asks to be held, or 0 for one that does not."""
    suffix = _hold_of(binding)
    return int(suffix[len(HOLD_MARK):]) if suffix else 0


def with_hold(binding: str, ms: int) -> str:
    """The same binding, held for `ms` - or not held at all when `ms` is 0.

    A hold is a *modifier on* a binding rather than a different binding, so adding one
    after the fact is editing this suffix and nothing else. Which is the point: a
    duration nobody can perform exactly is the part of the grammar an editor exists for.
    """
    text = str(binding or "").strip()
    bare = text[:-len(_hold_of(text))] if _hold_of(text) else text
    wanted = max(0, int(ms or 0))
    return f"{bare}{HOLD_MARK}{wanted}" if wanted else bare


def _hold_of(binding: str) -> str:
    """The `@hold:<ms>` suffix, or "" - the whole suffix, so it can be taken off."""
    text = str(binding or "")
    at = text.rfind(HOLD_MARK)
    return text[at:] if at != -1 and text[at + len(HOLD_MARK):].isdigit() else ""


def _held_for(binding: str) -> str:
    """", held 1.5s" - said in seconds, because a hold is something a person counts."""
    suffix = _hold_of(binding)
    if not suffix:
        return ""
    ms = int(suffix[len(HOLD_MARK):])
    seconds = f"{ms / 1000:g}"
    return f", held {seconds}s"


# Key names as a keyboard has them printed. `event.code` is what a browser reports and
# what is stored; the rest is only ever shown.
_KEY_NAMES = {
    "ArrowLeft": "Left arrow", "ArrowRight": "Right arrow",
    "ArrowUp": "Up arrow", "ArrowDown": "Down arrow",
    "ShiftLeft": "Left Shift", "ShiftRight": "Right Shift",
    "ControlLeft": "Left Ctrl", "ControlRight": "Right Ctrl",
    "AltLeft": "Left Alt", "AltRight": "Right Alt",
    "MetaLeft": "Left Meta", "MetaRight": "Right Meta",
    "PageUp": "Page Up", "PageDown": "Page Down",
    "Escape": "Esc", "Enter": "Enter", "Space": "Space", "Tab": "Tab",
    "Backspace": "Backspace", "Delete": "Delete", "Home": "Home", "End": "End",
    # A code names the key; a chip shows what is printed on it.
    "Minus": "-", "Equal": "=", "BracketLeft": "[", "BracketRight": "]",
    "Backslash": "\\", "Semicolon": ";", "Quote": "'", "Comma": ",",
    "Period": ".", "Slash": "/", "Backquote": "`",
}


def key_names() -> dict[str, str]:
    """The printed names, for a surface that has to do this without Python.

    Handed over rather than reimplemented: a browser reading a gamepad cannot call
    `describe`, and a second copy of this table is a second thing to keep in step.
    """
    return dict(_KEY_NAMES)


def _key_name(code: str) -> str:
    if code in _KEY_NAMES:
        return _KEY_NAMES[code]
    if code.startswith("Key") and len(code) == 4:
        return code[3]
    if code.startswith("Digit") and len(code) == 6:
        return code[5]
    if code.startswith("Numpad"):
        return f"Numpad {code[len('Numpad'):]}"
    # A single character is already its own name, and an unknown code is more use shown
    # than replaced with a guess.
    return code


CHORD_PREFIX = "chord("
HOLD_MARK = "@hold:"


def chord_members(binding: str) -> tuple[str, ...]:
    """What a chord is made of, in a settled order, or () for anything else.

    Sorted and de-duplicated because a chord is a *set* of inputs held together -
    `chord(a+b)` and `chord(b+a)` are one binding written two ways, and comparing them as
    text would call them different.

    The members are not looked at. The grammar's own example writes action names where
    selectors would also read - see the note in 5.4a - and settling that is not this
    function's to do; whichever it turns out to be, a chord is still its members.
    """
    text = str(binding or "").strip()
    if not text.startswith(CHORD_PREFIX) or ")" not in text:
        return ()
    inside = text[len(CHORD_PREFIX):text.rindex(")")]
    return tuple(sorted({part.strip() for part in inside.split("+") if part.strip()}))


# A key selector has two spellings, because a browser reports two things: `event.key` is
# what the key produces - "c" - and `event.code` is which key it is - "KeyC". The defaults
# were written in the first and capture stores the second, and both dispatch, so a config
# can hold `key:c` and `key:KeyC` for one key and nothing notices.
#
# The code wins. It survives a layout where the same physical key produces something else,
# which is the whole reason the browser reports both.
_PUNCTUATION_CODES = {
    "-": "Minus", "=": "Equal", "[": "BracketLeft", "]": "BracketRight",
    "\\": "Backslash", ";": "Semicolon", "'": "Quote", ",": "Comma",
    ".": "Period", "/": "Slash", "`": "Backquote", " ": "Space",
}


def normalize(binding: str) -> str:
    """One spelling for a key selector: the code a browser reports.

    Only a selector naming a single character is rewritten - `key:c` becomes `key:KeyC`.
    Anything already spelled as a code is left as it is, and so is a binding this does not
    understand, because guessing at one would invent a key nobody pressed.
    """
    text = str(binding or "").strip()
    if not text.startswith(KEY_PREFIX):
        return text
    name = text[len(KEY_PREFIX):]
    if len(name) != 1:
        return text
    if name.isalpha():
        return f"{KEY_PREFIX}Key{name.upper()}"
    if name.isdigit():
        return f"{KEY_PREFIX}Digit{name}"
    found = _PUNCTUATION_CODES.get(name)
    return f"{KEY_PREFIX}{found}" if found else text


def identity(binding: str) -> str:
    """The form two bindings are compared in.

    A chord written in either order is one binding, so comparison happens on the settled
    order rather than on what somebody typed. Everything else is already its own
    identity.

    **A chord does not fold into its members, and that is the decision rather than an
    oversight** (Chris, 2026-09-06): both flippers fire their own actions *and* the
    chord, so a chord and a plain binding on one of its members are two bindings that
    both work. What repeat does while a chord is held is dispatch's to answer.
    """
    text = str(binding or "").strip()
    members = chord_members(text)
    if not members:
        return normalize(text)
    suffix = text[text.rindex(")") + 1:]
    return f"{CHORD_PREFIX}{'+'.join(normalize(one) for one in members)}){suffix}"


def holders(bound) -> dict[str, list[str]]:
    """Every binding, and which actions hold it.

    Compared by `identity`, so a chord written in either order is one binding and a key
    written either way - `key:c` or `key:KeyC` - is one key. Dispatch matches on both of
    an event's tokens, so those two really are the same binding, and reading them as
    different was how a clash could sit on the page unreported.
    """
    seen: dict[str, list[str]] = {}
    for name, bindings in dict(bound or {}).items():
        for binding in bindings or ():
            text = identity(binding)
            if not text:
                continue
            # An action listing the same binding twice holds it once.
            if name not in seen.setdefault(text, []):
                seen[text].append(name)
    return seen


def collisions(bound) -> dict[str, list[str]]:
    """Bindings more than one action holds.

    Nothing refused one before, anywhere. Dispatch resolves a key to the *first* action
    that lists it in declaration order, so the second binding is not a conflict a player
    is asked about - it is a binding that silently does nothing, and the settings page
    that let them make it showed no sign.
    """
    return {binding: names for binding, names in holders(bound).items()
            if len(names) > 1}


def unrenderable(bindings) -> list[str]:
    """Bindings neither UI field can show - chords, holds, axes, a second pad.

    Kept and written back untouched: dropping them would delete a cabinet's
    hold-both-flippers binding the first time anyone opened settings and pressed Save.
    """
    shown = set(f"{KEY_PREFIX}{k}" for k in keys_in(bindings))
    shown |= set(f"{PAD_PREFIX}0/button:{b}" for b in pad_buttons_in(bindings))
    return [str(b) for b in bindings or () if str(b) not in shown]
