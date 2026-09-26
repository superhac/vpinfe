"""The readout that answers "what is this button".

Capture answers what you just pressed. This answers the other direction, which is the one
that defeats somebody with an unlabelled encoder board - and it is drawn in the browser,
because a gamepad is only readable there.

What is worth pinning is the seam: the printed names come from Python so there is one
table, but the *rules* for a name Python has no entry for live in the JS as well. Those
two can drift, so they are checked against each other here.
"""

from __future__ import annotations

import json
import re
import unittest

from common import i18n, input_registry
from console import input_watch, settings


class TheNamesComeFromPython(unittest.TestCase):
    def test_the_table_is_handed_over_rather_than_rewritten(self) -> None:
        """A second copy of 22 key names is a second thing to keep in step."""
        names = input_registry.key_names()

        self.assertIn("ShiftLeft", names)
        self.assertEqual(names["ShiftLeft"], "Left Shift")
        # Whatever the script is handed, it is this - serialized, not retyped.
        self.assertEqual(json.loads(json.dumps(names)), names)

    def test_the_script_does_not_carry_its_own_copy_of_the_table(self) -> None:
        printed = set(input_registry.key_names().values())
        quoted = set(re.findall(r"'([^']*)'", input_watch._WATCH_JS))

        self.assertEqual(printed & quoted, set(),
                         "a printed name is written into the script as well as served "
                         "to it - one of the two will go stale")

    def test_the_fallback_rules_agree_with_python(self) -> None:
        """`KeyM` is not in the table and is still called M. That rule is in both, so it
        is checked in both."""
        for code, expected in (("KeyM", "M"), ("KeyZ", "Z"),
                               ("Digit4", "4"), ("Digit0", "0"),
                               ("Numpad7", "Numpad 7"),
                               ("F9", "F9"), ("Unlabelled", "Unlabelled")):
            with self.subTest(code=code):
                self.assertEqual(input_registry.describe(f"key:{code}"), expected)
                self.assertEqual(_as_the_script_would(code), expected)


# The standard `KeyboardEvent.code` values, from the UI Events code tables: the writing
# system, functional, control pad, arrow pad, numpad, function and media sections.
STANDARD_CODES = (
    "Backquote Backslash BracketLeft BracketRight Comma Equal IntlBackslash IntlRo IntlYen "
    "Minus Period Quote Semicolon Slash "
    "AltLeft AltRight Backspace CapsLock ContextMenu ControlLeft ControlRight Enter "
    "MetaLeft MetaRight ShiftLeft ShiftRight Space Tab "
    "Convert KanaMode Lang1 Lang2 Lang3 Lang4 Lang5 NonConvert "
    "Delete End Help Home Insert PageDown PageUp "
    "ArrowDown ArrowLeft ArrowRight ArrowUp "
    "NumLock NumpadAdd NumpadBackspace NumpadClear NumpadClearEntry NumpadComma "
    "NumpadDecimal NumpadDivide NumpadEnter NumpadEqual NumpadHash NumpadMemoryAdd "
    "NumpadMemoryClear NumpadMemoryRecall NumpadMemoryStore NumpadMemorySubtract "
    "NumpadMultiply NumpadParenLeft NumpadParenRight NumpadStar NumpadSubtract "
    "Escape Fn FnLock PrintScreen ScrollLock Pause "
    "BrowserBack BrowserFavorites BrowserForward BrowserHome BrowserRefresh BrowserSearch "
    "BrowserStop Eject LaunchApp1 LaunchApp2 LaunchMail MediaPlayPause MediaSelect "
    "MediaStop MediaTrackNext MediaTrackPrevious Power Sleep AudioVolumeDown "
    "AudioVolumeMute AudioVolumeUp WakeUp"
).split() + [f"Key{letter}" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] \
    + [f"Digit{n}" for n in range(10)] + [f"Numpad{n}" for n in range(10)]


class EveryKeyHasAName(unittest.TestCase):
    def test_no_standard_code_is_shown_as_it_was_stored(self) -> None:
        """In the pseudo-locale, where an English name that happens to match its code
        (Enter, Tab) still reads differently when it came from the catalog."""
        self.addCleanup(i18n.set_language, i18n.language())
        i18n.set_language("qps")
        raw = [code for code in STANDARD_CODES
               if input_registry.describe(f"key:{code}") == code]
        self.assertEqual([], raw)

    def test_the_script_names_each_one_as_python_does(self) -> None:
        for code in STANDARD_CODES:
            with self.subTest(code=code):
                self.assertEqual(input_registry.describe(f"key:{code}"),
                                 _as_the_script_would(code))

    def test_a_numpad_key_is_said_by_what_is_printed_on_it(self) -> None:
        for code, expected in (("NumpadAdd", "Numpad +"), ("NumpadDecimal", "Numpad ."),
                               ("NumpadEnter", "Numpad Enter")):
            with self.subTest(code=code):
                self.assertEqual(expected, input_registry.describe(f"key:{code}"))


def _as_the_script_would(code: str) -> str:
    """The script's `keyName`, in Python, so the two can be compared.

    Written out rather than executed: running the real thing needs a browser, and the
    thing worth catching is one side gaining a rule the other did not.
    """
    names = input_registry.key_names()
    if code in names:
        return names[code]
    if re.fullmatch(r"Key.", code):
        return code[3:]
    if re.fullmatch(r"Digit.", code):
        return code[5:]
    return code


class ItSitsUnderTheBindings(unittest.TestCase):
    def test_the_input_page_carries_it(self) -> None:
        """The same question the rows above ask, backwards - a binding says this key does
        that, and this says which key is which."""
        self.assertIn("input", settings.FOOTERS)

    def test_it_binds_nothing(self) -> None:
        """Said on screen, because a strip of inputs on a settings page would otherwise
        read as something that is about to take one."""
        self.assertNotIn("emit(", input_watch._WATCH_JS)


if __name__ == "__main__":
    unittest.main()
