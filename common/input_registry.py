"""Every input action VPinFE understands, declared once.

Ten actions, each with one ordered list of bindings. The names say what the player
*meant* rather than which way a stick moved: three surfaces - the wheel, a vertical menu
and a scrolling page - already disagreed about what "left" pointed at, and every overlay
carried a fall-through case as the evidence.

A binding names its own device - `key:<name>`, `pad:<index>/button:<n>` - so an action
needs one list rather than a key per device. Richer selectors - modifiers, axes, hold,
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
        bindings=("key:ArrowLeft", "key:ShiftLeft"),
        label="Previous",
        legacy=("joyleft", "keyleft"),
    ),
    InputAction(
        "next",
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
        bindings=("key:PageUp", "key:ArrowUp"),
        label="Page previous",
        legacy=("joypageup", "keypageup", "joyup", "keyup"),
    ),
    InputAction(
        "page_next",
        bindings=("key:PageDown", "key:ArrowDown"),
        label="Page next",
        legacy=("joypagedown", "keypagedown", "joydown", "keydown"),
    ),
    InputAction(
        "select",
        bindings=("key:Enter",),
        label="Select",
        legacy=("joyselect", "keyselect"),
    ),
    InputAction(
        "back",
        bindings=("key:b",),
        label="Back",
        legacy=("joyback", "keyback"),
    ),
    InputAction(
        "menu",
        bindings=("key:m",),
        label="Menu",
        legacy=("joymenu", "keymenu"),
    ),
    InputAction(
        "collection_menu",
        bindings=("key:c",),
        label="Collection menu",
        legacy=("joycollectionmenu", "keycollectionmenu"),
    ),
    InputAction(
        "tutorial",
        bindings=("key:t",),
        label="Tutorial",
        legacy=("joytutorial", "keytutorial"),
    ),
    InputAction(
        "exit",
        bindings=("key:Escape", "key:q"),
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


def unrenderable(bindings) -> list[str]:
    """Bindings neither UI field can show - chords, holds, axes, a second pad.

    Kept and written back untouched: dropping them would delete a cabinet's
    hold-both-flippers binding the first time anyone opened settings and pressed Save.
    """
    shown = set(f"{KEY_PREFIX}{k}" for k in keys_in(bindings))
    shown |= set(f"{PAD_PREFIX}0/button:{b}" for b in pad_buttons_in(bindings))
    return [str(b) for b in bindings or () if str(b) not in shown]
