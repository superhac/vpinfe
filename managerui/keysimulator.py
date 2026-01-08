from pynput.keyboard import Key, Controller
import time
import re
from platformdirs import user_config_dir
from pathlib import Path
from common.iniconfig import IniConfig


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
        70: Key.print_screen,
        72: Key.pause,
        73: Key.insert,
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
    
    # Pinmame 
    PINMAME_OPEN_COIN_DOOR = Key.end
    PINMAME_CANCEL = '7'
    PINMAME_DOWN = '8'
    PINMAME_UP = '9'
    PINMAME_ENTER = '0'

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self):
        config_dir = Path(user_config_dir("vpinfe", "vpinfe"))
        config_path = config_dir / "vpinfe.ini"

        iniconfig = IniConfig(str(config_path))
        vpinball_ini_path = iniconfig.config["Settings"]["vpxinipath"]

        #print("Parsing:", vpinball_ini_path)

        self.raw_mappings = self.parse_vpinball_key_mappings(vpinball_ini_path)
        self.pynput_mappings = self.convert_to_pynput_keys(self.raw_mappings)

        #print("SDL mappings:", self.raw_mappings)
        #print("pynput mappings:", self.pynput_mappings)

        self.keyboard = Controller()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def press_mapping(self, name, seconds=0):
        key = self.pynput_mappings.get(name)
        time.sleep(seconds)
        if key is not None:
            self.press(key)

    def hold_mapping(self, name, seconds=0.1):
        """Hold a mapped key for the specified duration"""
        key = self.pynput_mappings.get(name)
        if key is not None:
            self.hold(key, seconds)

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

        with open(ini_path, "r", encoding="utf-8-sig") as f:
            for raw_line in f:
                line = raw_line.strip()

                if not line or line.startswith(";"):
                    continue

                if line.startswith("[") and line.endswith("]"):
                    in_input_section = (line == "[Input]")
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
