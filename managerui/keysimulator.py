from pynput.keyboard import Key
import logging
import time
import re
import shutil
import subprocess
import os
from pathlib import Path
from common.iniconfig import IniConfig
from managerui.paths import VPINFE_INI_PATH
import sys


logger = logging.getLogger("vpinfe.manager.keysimulator")

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
        Key.ctrl_r: 62, Key.shift_r: 56, Key.alt_r: 58,
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


class PynputKeyboardBackend:
    def __init__(self, key_map):
        self.key_map = key_map
        self._keyboard = None

    @property
    def keyboard(self):
        if self._keyboard is None:
            self._keyboard = QuartzKeyboardController()
        return self._keyboard

    def _translate(self, key_id):
        return self.key_map.get(key_id)

    def press(self, key_id):
        key = self._translate(key_id)
        if key is None:
            return False
        self.keyboard.press(key)
        self.keyboard.release(key)
        return True

    def hold(self, key_id, seconds=1):
        key = self._translate(key_id)
        if key is None:
            return False
        self.keyboard.press(key)
        time.sleep(seconds)
        self.keyboard.release(key)
        return True

    def combo(self, *key_ids):
        translated = [self._translate(key_id) for key_id in key_ids]
        if any(key is None for key in translated):
            return False
        for key in translated:
            self.keyboard.press(key)
        for key in reversed(translated):
            self.keyboard.release(key)
        return True


class YdotoolKeyboardBackend:
    def __init__(self, key_map, debug=False):
        self.key_map = key_map
        self.debug = debug
        self.socket_path = self._resolve_socket_path()

    def _translate(self, key_id):
        return self.key_map.get(key_id)

    def _run_key_sequence(self, key_args):
        cmd = ["ydotool", "key", *key_args]
        env = os.environ.copy()
        if self.socket_path:
            env["YDOTOOL_SOCKET"] = self.socket_path
        if self.debug:
            logger.debug("Using ydotool socket: %s", self.socket_path or "<default>")
            logger.debug("Running ydotool command: %s", cmd)
        try:
            subprocess.run(cmd, check=True, capture_output=not self.debug, text=True, env=env)
            return True
        except FileNotFoundError:
            logger.warning("ydotool is not installed or not on PATH")
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            if stderr:
                logger.warning("ydotool failed: %s", stderr)
            else:
                logger.warning("ydotool failed with exit code %s", exc.returncode)
        return False

    def _resolve_socket_path(self):
        configured = os.environ.get("YDOTOOL_SOCKET", "").strip()
        if configured:
            return configured

        candidates = [
            f"/run/user/{os.getuid()}/.ydotool_socket",
            "/run/ydotool/socket",
            "/tmp/.ydotool_socket",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        return None

    def press(self, key_id):
        code = self._translate(key_id)
        if code is None:
            return False
        return self._run_key_sequence([f"{code}:1", f"{code}:0"])

    def hold(self, key_id, seconds=1):
        code = self._translate(key_id)
        if code is None:
            return False
        if not self._run_key_sequence([f"{code}:1"]):
            return False
        time.sleep(seconds)
        return self._run_key_sequence([f"{code}:0"])

    def combo(self, *key_ids):
        codes = [self._translate(key_id) for key_id in key_ids]
        if any(code is None for code in codes):
            return False
        key_args = [f"{code}:1" for code in codes]
        key_args.extend(f"{code}:0" for code in reversed(codes))
        return self._run_key_sequence(key_args)


class KeySimulator:

    # ------------------------------------------------------------------
    # SDL scancode -> internal key id mapping
    # ------------------------------------------------------------------

    SDL_TO_KEY_ID = {
        # Letters A–Z
        **{code: chr(ord('a') + code - 4) for code in range(4, 30)},

        # Numbers
        30: '1', 31: '2', 32: '3', 33: '4', 34: '5',
        35: '6', 36: '7', 37: '8', 38: '9', 39: '0',

        # Control
        40: "enter",
        41: "esc",
        42: "backspace",
        43: "tab",
        44: "space",

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
        58: "f1",
        59: "f2",
        60: "f3",
        61: "f4",
        62: "f5",
        63: "f6",
        64: "f7",
        65: "f8",
        66: "f9",
        67: "f10",
        68: "f11",
        69: "f12",

        # Navigation        
        74: "home",
        75: "page_up",
        76: "delete",
        77: "end",
        78: "page_down",
        79: "right",
        80: "left",
        81: "down",
        82: "up",

        # Modifiers
        224: "ctrl_l",
        225: "shift_l",
        226: "alt_l",
        227: "cmd",
        228: "ctrl_r",
        229: "shift_r",
        230: "alt_r",
        231: "cmd_r",
    }

    # navigation: not on mac,  but other platforms get these keys
    if sys.platform != "darwin":  # macOS
        SDL_TO_KEY_ID.update({
            70: "print_screen",
            72: "pause",
            73: "insert",
        })

    KEY_ID_TO_PYNPUT = {
        "enter": Key.enter,
        "esc": Key.esc,
        "backspace": Key.backspace,
        "tab": Key.tab,
        "space": Key.space,
        "f1": Key.f1,
        "f2": Key.f2,
        "f3": Key.f3,
        "f4": Key.f4,
        "f5": Key.f5,
        "f6": Key.f6,
        "f7": Key.f7,
        "f8": Key.f8,
        "f9": Key.f9,
        "f10": Key.f10,
        "f11": Key.f11,
        "f12": Key.f12,
        "home": Key.home,
        "page_up": Key.page_up,
        "delete": Key.delete,
        "end": Key.end,
        "page_down": Key.page_down,
        "right": Key.right,
        "left": Key.left,
        "down": Key.down,
        "up": Key.up,
        "ctrl_l": Key.ctrl_l,
        "shift_l": Key.shift_l,
        "alt_l": Key.alt_l,
        "cmd": Key.cmd,
        "ctrl_r": Key.ctrl_r,
        "shift_r": Key.shift_r,
        "alt_r": Key.alt_r,
        "cmd_r": Key.cmd,
    }

    if sys.platform != "darwin":
        KEY_ID_TO_PYNPUT.update({
            "print_screen": Key.print_screen,
            "pause": Key.pause,
            "insert": Key.insert,
        })

    KEY_ID_TO_YDOTOOL = {
        "1": 2,
        "2": 3,
        "3": 4,
        "4": 5,
        "5": 6,
        "6": 7,
        "7": 8,
        "8": 9,
        "9": 10,
        "0": 11,
        "-": 12,
        "=": 13,
        "backspace": 14,
        "tab": 15,
        "q": 16,
        "w": 17,
        "e": 18,
        "r": 19,
        "t": 20,
        "y": 21,
        "u": 22,
        "i": 23,
        "o": 24,
        "p": 25,
        "[": 26,
        "]": 27,
        "enter": 28,
        "ctrl_l": 29,
        "a": 30,
        "s": 31,
        "d": 32,
        "f": 33,
        "g": 34,
        "h": 35,
        "j": 36,
        "k": 37,
        "l": 38,
        ";": 39,
        "'": 40,
        "`": 41,
        "shift_l": 42,
        "\\": 43,
        "z": 44,
        "x": 45,
        "c": 46,
        "v": 47,
        "b": 48,
        "n": 49,
        "m": 50,
        ",": 51,
        ".": 52,
        "/": 53,
        "shift_r": 54,
        "alt_l": 56,
        "space": 57,
        "f1": 59,
        "f2": 60,
        "f3": 61,
        "f4": 62,
        "f5": 63,
        "f6": 64,
        "f7": 65,
        "f8": 66,
        "f9": 67,
        "f10": 68,
        "pause": 119,
        "print_screen": 99,
        "home": 102,
        "up": 103,
        "page_up": 104,
        "left": 105,
        "right": 106,
        "end": 107,
        "down": 108,
        "page_down": 109,
        "insert": 110,
        "delete": 111,
        "cmd": 125,
        "cmd_r": 126,
        "ctrl_r": 97,
        "alt_r": 100,
        "esc": 1,
        "f11": 87,
        "f12": 88,
    }

    # Pinmame
    PINMAME_OPEN_COIN_DOOR = "end"
    PINMAME_CANCEL = '7'
    PINMAME_DOWN = '8'
    PINMAME_UP = '9'
    PINMAME_ENTER = '0'

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self, debug=False):
        self.debug = debug

        config_path = VPINFE_INI_PATH

        if self.debug:
            logger.debug("Looking for vpinfe.ini at: %s", config_path)
            logger.debug("File exists: %s", config_path.exists())

        iniconfig = IniConfig(str(config_path))
        vpinball_ini_path = iniconfig.config["Settings"]["vpxinipath"]

        if self.debug:
            logger.debug("VPinballX.ini path from config: %s", vpinball_ini_path)
            logger.debug("VPinballX.ini exists: %s", Path(vpinball_ini_path).exists())

        self.raw_mappings = self.parse_vpinball_key_mappings(vpinball_ini_path)
        self.key_mappings = self.convert_to_key_ids(self.raw_mappings)
        self.backend_name = self.detect_backend()
        self.backend = self.create_backend()

        if self.debug:
            logger.debug("Raw SDL mappings found: %s", len(self.raw_mappings))
            for name, scancode in self.raw_mappings.items():
                logger.debug("  %s: SDL scancode %s", name, scancode)
            logger.debug("Input backend: %s", self.backend_name)
            logger.debug("Converted key mappings: %s", len(self.key_mappings))
            for name, key_id in self.key_mappings.items():
                logger.debug("  %s: %s", name, key_id)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def press_mapping(self, name, seconds=0):
        key = self.key_mappings.get(name)
        if self.debug:
            logger.debug("press_mapping('%s'): key=%s, found=%s", name, key, key is not None)
        time.sleep(seconds)
        if key is not None:
            self.press(key)
        elif self.debug:
            logger.warning("No mapping found for '%s'", name)

    def hold_mapping(self, name, seconds=0.1):
        """Hold a mapped key for the specified duration"""
        key = self.key_mappings.get(name)
        if self.debug:
            logger.debug("hold_mapping('%s'): key=%s, found=%s", name, key, key is not None)
        if key is not None:
            self.hold(key, seconds)
        elif self.debug:
            logger.warning("No mapping found for '%s'", name)

    def press(self, key_id):
        if not self.backend.press(key_id) and self.debug:
            logger.warning("Unable to press key '%s' using backend '%s'", key_id, self.backend_name)

    def hold(self, key_id, seconds=1):
        if not self.backend.hold(key_id, seconds) and self.debug:
            logger.warning("Unable to hold key '%s' using backend '%s'", key_id, self.backend_name)

    def combo(self, *key_ids):
        if not self.backend.combo(*key_ids) and self.debug:
            logger.warning("Unable to send combo %s using backend '%s'", key_ids, self.backend_name)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_vpinball_key_mappings(self, ini_path: str) -> dict:
        KEY_REGEX = re.compile(r"\bKey;(\d+)\b")
        mappings = {}
        in_input_section = False

        if self.debug:
            logger.debug("Parsing VPinballX.ini: %s", ini_path)

        with open(ini_path, "r", encoding="utf-8-sig") as f:
            for raw_line in f:
                line = raw_line.strip()

                if not line or line.startswith(";"):
                    continue

                if line.startswith("[") and line.endswith("]"):
                    in_input_section = (line == "[Input]")
                    if self.debug and in_input_section:
                        logger.debug("Found [Input] section")
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
                    logger.debug("  Parsed: %s = %s -> scancode %s", name, value, scancode)

        if self.debug:
            if not mappings:
                logger.warning("No mappings found! Check if [Input] section exists with Mapping.* entries")
            else:
                logger.debug("Total mappings parsed: %s", len(mappings))

        return mappings

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def convert_to_key_ids(self, sdl_mappings: dict) -> dict:
        result = {}

        for name, scancode in sdl_mappings.items():
            if scancode is None:
                continue

            key_id = self.SDL_TO_KEY_ID.get(scancode)
            if key_id is not None:
                result[name] = key_id

        return result

    def detect_backend(self) -> str:
        if sys.platform == "darwin":
            return "pynput"

        session_type = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
        wayland_display = os.environ.get("WAYLAND_DISPLAY")
        display = os.environ.get("DISPLAY")

        if wayland_display or session_type == "wayland":
            if shutil.which("ydotool"):
                return "ydotool"
            logger.warning("Wayland session detected but ydotool is not available; falling back to pynput")
            return "pynput"

        if display or session_type == "x11":
            return "pynput"

        return "pynput"

    def create_backend(self):
        if self.backend_name == "ydotool":
            return YdotoolKeyboardBackend(self.KEY_ID_TO_YDOTOOL, debug=self.debug)
        return PynputKeyboardBackend(self.KEY_ID_TO_PYNPUT)
