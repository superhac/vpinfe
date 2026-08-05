"""Every input action VPinFE understands, declared once.

The twelve names were written out in seven places - the Python mapping keys, the config
defaults, the Manager UI's labels, the JavaScript defaults, the JavaScript key-to-action
table, the gamepad binding page and two docs tables - so adding an action meant editing
all seven, and they had already drifted: the JavaScript said `back` was unbound while
Python shipped `b`.

Two of those copies are gone already, into `config_schema`. This is the rest: the config
keys, the shipped keyboard binding and the label all come from here, and the copies that
cannot import Python are checked against it by `tests/test_input_actions.py`.

The names are 2.x's and are deliberately unchanged - `joy*` describes the transport rather
than the intent, which is a real problem and the vocabulary work's to fix, not this file's.
"""

from __future__ import annotations

from dataclasses import dataclass

SECTION = "Input"


@dataclass(frozen=True)
class InputAction:
    """One thing a player can ask for, and the two config keys that bind it.

    There are two keys per action because a stored value cannot say which device it came
    from: `keyleft` holds keyboard bindings and `joyleft` a gamepad button.
    """

    name: str
    keyboard: str
    label: str

    @property
    def key_config(self) -> str:
        return f"key{self.name}"

    @property
    def joy_config(self) -> str:
        return f"joy{self.name}"


INPUT_ACTIONS: tuple[InputAction, ...] = (
    InputAction("left", "ArrowLeft,ShiftLeft", "Keyboard Left"),
    InputAction("right", "ArrowRight,ShiftRight", "Keyboard Right"),
    InputAction("up", "ArrowUp", "Keyboard Up"),
    InputAction("down", "ArrowDown", "Keyboard Down"),
    InputAction("pageup", "PageUp", "Keyboard Page Up"),
    InputAction("pagedown", "PageDown", "Keyboard Page Down"),
    InputAction("select", "Enter", "Keyboard Select"),
    InputAction("menu", "m", "Keyboard Menu"),
    InputAction("back", "b", "Keyboard Back"),
    InputAction("tutorial", "t", "Keyboard Tutorial"),
    InputAction("exit", "Escape,q", "Keyboard Exit"),
    InputAction("collectionmenu", "c", "Keyboard Collection Menu"),
)


def actions() -> tuple[InputAction, ...]:
    return INPUT_ACTIONS


def joy_config_keys() -> list[str]:
    """The `[Input]` keys holding a gamepad button, in declaration order."""
    return [action.joy_config for action in INPUT_ACTIONS]


def keyboard_defaults() -> dict[str, str]:
    """The `[Input]` keyboard bindings a fresh install ships."""
    return {action.key_config: action.keyboard for action in INPUT_ACTIONS}


def action_for_config_key(key: str) -> str:
    """The action a `key*` or `joy*` config key binds, or "" when it binds none."""
    wanted = str(key or "").strip().lower()
    for action in INPUT_ACTIONS:
        if wanted in (action.key_config, action.joy_config):
            return action.name
    return ""
