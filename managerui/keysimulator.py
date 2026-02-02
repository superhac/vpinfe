from pynput.keyboard import Key
import time
import re
from platformdirs import user_config_dir
from pathlib import Path
from common.iniconfig import IniConfig
import sys

if sys.platform == "darwin":
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventPost,
        kCGHIDEventTap,
    )

    PYNPUT_TO_MACOS_KEYCODE = {
        Key.enter: 36, Key.esc: 53, Key.backspace: 51, Key.tab: 48, Key.space: 49,
        Key.f1: 122, Key.f2: 120, Key.f3: 99, Key.f4: 118, Key.f5: 96, Key.f6: 97,
        Key.f7: 98, Key.f8: 100, Key.f9: 101, Key.f10: 109, Key.f11: 103, Key.f12: 111,
        Key.home: 115, Key.page_up: 116, Key.delete: 117, Key.end: 119, Key.page_down: 121,
        Key.right: 124, Key.left: 123, Key.down: 125, Key.up: 126,
        Key.ctrl_l: 59, Key.shift_l: 56, Key.alt_l: 58, Key.cmd: 55,
        Key.ctrl_r: 59, Key.shift_r: 56, Key.alt_r: 58,
        'a': 0, 'b': 11, 'c': 8, 'd': 2, 'e': 14, 'f': 3, 'g': 5, 'h': 4,
        'i': 34, 'j': 38, 'k': 40, 'l': 37, 'm': 46, 'n': 45, 'o': 31, 'p': 35,
        'q': 12, 'r': 15, 's': 1, 't': 17, 'u': 32, 'v': 9, 'w': 13, 'x': 7,
        'y': 16, 'z': 6,
        '1': 18, '2': 19, '3': 20, '4': 21, '5': 23, '6': 22, '7': 26, '8': 28,
        '9': 25, '0': 29,
        '-': 27, '=': 24, '[': 33, ']': 30, '\\': 42, ';': 41, "'": 39,
        '`': 50, ',': 43, '.': 47, '/': 44,
    }

    class QuartzKeyboardController:
        def press(self, key):
            keycode = PYNPUT_TO_MACOS_KEYCODE.get(key)
            if keycode is not None:
                event = CGEventCreateKeyboardEvent(None, keycode, True)
                CGEventPost(kCGHIDEventTap, event)

        def release(self, key):
            keycode = PYNPUT_TO_MACOS_KEYCODE.get(key)
            if keycode is not None:
                event = CGEventCreateKeyboardEvent(None, keycode, False)
                CGEventPost(kCGHIDEventTap, event)
else:
    from pynput.keyboard import Controller as QuartzKeyboardController


class KeySimulator:

    # ------------------------------------------------------------------
    # SDL scancode → pynput mapping table
    # ------------------------------------------------------------------

    SDL_TO_PYNPUT = {
        # Letters A–Z
        **{code: chr(ord('a') + code - 4) for code in range(4, 30)},

        # Numbers
        30: '1', 31: '2', 32: '3', 33: '4', 34: '5',
        35: '6', 36: '7', 37: '8', 38: '9', 39: '0',

        # Control
        40: Key.enter,
        41: Key.esc,
        42: Key.backspace,
        43: Key.tab,
        44: Key.space,

        # Symbols
        45: '-',
        46: '=',
        47: '[',
        48: ']',
        49: '\\',
        51: ';',
        52: "'",
        53: '`',
        54: ',',
        55: '.',
        56: '/',

        # Function keys
        58: Key.f1,
        59: Key.f2,
        60: Key.f3,
        61: Key.f4,
        62: Key.f5,
        63: Key.f6,
        64: Key.f7,
        65: Key.f8,
        66: Key.f9,
        67: Key.f10,
        68: Key.f11,
        69: Key.f12,

        # Navigation        
        74: Key.home,
        75: Key.page_up,
        76: Key.delete,
        77: Key.end,
        78: Key.page_down,
        79: Key.right,
        80: Key.left,
        81: Key.down,
        82: Key.up,

        # Modifiers
        224: Key.ctrl_l,
        225: Key.shift_l,
        226: Key.alt_l,
        227: Key.cmd,
        228: Key.ctrl_r,
        229: Key.shift_r,
        230: Key.alt_r,
        231: Key.cmd,
    }
    
    # navigation: not on mac,  but other platforms get these keys
    if sys.platform != "darwin":  # macOS
            SDL_TO_PYNPUT.update({
                70: Key.print_screen,
                72: Key.pause,
                73: Key.insert,
        })
    
    # Pinmame 
    PINMAME_OPEN_COIN_DOOR = Key.end
    PINMAME_CANCEL = '7'
    PINMAME_DOWN = '8'
    PINMAME_UP = '9'
    PINMAME_ENTER = '0'

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self, debug=False):
        self.debug = debug
        self._keyboard = None

        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        config_path = config_dir / "vpinfe.ini"

        if self.debug:
            print(f"[KeySimulator] Looking for vpinfe.ini at: {config_path}")
            print(f"[KeySimulator] File exists: {config_path.exists()}")

        iniconfig = IniConfig(str(config_path))
        vpinball_ini_path = iniconfig.config["Settings"]["vpxinipath"]

        if self.debug:
            print(f"[KeySimulator] VPinballX.ini path from config: {vpinball_ini_path}")
            print(f"[KeySimulator] VPinballX.ini exists: {Path(vpinball_ini_path).exists()}")

        self.raw_mappings = self.parse_vpinball_key_mappings(vpinball_ini_path)
        self.pynput_mappings = self.convert_to_pynput_keys(self.raw_mappings)

        if self.debug:
            print(f"[KeySimulator] Raw SDL mappings found: {len(self.raw_mappings)}")
            for name, scancode in self.raw_mappings.items():
                print(f"  {name}: SDL scancode {scancode}")
            print(f"[KeySimulator] Converted pynput mappings: {len(self.pynput_mappings)}")
            for name, key in self.pynput_mappings.items():
                print(f"  {name}: {key}")

    @property
    def keyboard(self):
        if self._keyboard is None:
            self._keyboard = QuartzKeyboardController()
        return self._keyboard

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def press_mapping(self, name, seconds=0):
        key = self.pynput_mappings.get(name)
        if self.debug:
            print(f"[KeySimulator] press_mapping('{name}'): key={key}, found={key is not None}")
        time.sleep(seconds)
        if key is not None:
            self.press(key)
        elif self.debug:
            print(f"[KeySimulator] WARNING: No mapping found for '{name}'")

    def hold_mapping(self, name, seconds=0.1):
        """Hold a mapped key for the specified duration"""
        key = self.pynput_mappings.get(name)
        if self.debug:
            print(f"[KeySimulator] hold_mapping('{name}'): key={key}, found={key is not None}")
        if key is not None:
            self.hold(key, seconds)
        elif self.debug:
            print(f"[KeySimulator] WARNING: No mapping found for '{name}'")

    def press(self, key):
        self.keyboard.press(key)
        self.keyboard.release(key)

    def hold(self, key, seconds=1):
        self.keyboard.press(key)
        time.sleep(seconds)
        self.keyboard.release(key)

    def combo(self, *keys):
        for key in keys:
            self.keyboard.press(key)
        for key in reversed(keys):
            self.keyboard.release(key)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_vpinball_key_mappings(self, ini_path: str) -> dict:
        KEY_REGEX = re.compile(r"\bKey;(\d+)\b")
        mappings = {}
        in_input_section = False

        if self.debug:
            print(f"[KeySimulator] Parsing VPinballX.ini: {ini_path}")

        with open(ini_path, "r", encoding="utf-8-sig") as f:
            for raw_line in f:
                line = raw_line.strip()

                if not line or line.startswith(";"):
                    continue

                if line.startswith("[") and line.endswith("]"):
                    in_input_section = (line == "[Input]")
                    if self.debug and in_input_section:
                        print(f"[KeySimulator] Found [Input] section")
                    continue

                if not in_input_section:
                    continue

                if not line.startswith("Mapping."):
                    continue

                key, _, value = line.partition("=")
                name = key[len("Mapping."):].strip()
                value = value.strip()

                match = KEY_REGEX.search(value)
                mappings[name] = int(match.group(1)) if match else None

                if self.debug:
                    scancode = mappings[name]
                    print(f"[KeySimulator]   Parsed: {name} = {value} -> scancode {scancode}")

        if self.debug:
            if not mappings:
                print(f"[KeySimulator] WARNING: No mappings found! Check if [Input] section exists with Mapping.* entries")
            else:
                print(f"[KeySimulator] Total mappings parsed: {len(mappings)}")

        return mappings

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def convert_to_pynput_keys(self, sdl_mappings: dict) -> dict:
        result = {}

        for name, scancode in sdl_mappings.items():
            if scancode is None:
                continue

            pynput_key = self.SDL_TO_PYNPUT.get(scancode)
            if pynput_key is not None:
                result[name] = pynput_key

        return result
