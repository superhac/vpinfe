from __future__ import annotations
from typing import Tuple, Dict, List, Optional
from nicegui import ui, events
import asyncio
import time

from ..ini_store import IniStore
from ..schema import BUTTONS_JOYSTICK_FIELDS, BUTTONS_KEYBOARD_FIELDS

# =================== Custom Mapping for Joystick ===================
JOYSTICK_TO_KEYBOARD_NAME_MAPPING: Dict[str, str] = {
    'LFlipKey': 'JoyLFlipKey',
    'RFlipKey': 'JoyRFlipKey',
    'StagedLFlipKey': 'JoyStagedLFlipKey',
    'StagedRFlipKey': 'JoyStagedRFlipKey',
    'PlungerKey': 'JoyPlungerKey',
    'AddCreditKey': 'JoyAddCreditKey',
    'AddCredit2Key': 'JoyAddCredit2Key',
    'LMagnaSave': 'JoyLMagnaSave',
    'RMagnaSave': 'JoyRMagnaSave',
    'StartGameKey': 'JoyStartGameKey',
    'ExitGameKey': 'JoyExitGameKey',
    'FrameCount': 'JoyFrameCount',
    'VolumeUp': 'JoyVolumeUp',
    'VolumeDown': 'JoyVolumeDown',
    'LTiltKey': 'JoyLTiltKey',
    'CTiltKey': 'JoyCTiltKey',
    'RTiltKey': 'JoyRTiltKey',
    'MechTiltKey': 'JoyMechTiltKey',
    'DebugKey': 'JoyDebugKey',
    'DebuggerKey': 'JoyDebuggerKey',
    'Custom1': 'JoyCustom1',
    'Custom2': 'JoyCustom2',
    'Custom3': 'JoyCustom3',
    'Custom4': 'JoyCustom4',
    'PMBuyIn': 'JoyPMBuyIn',
    'PMCoin3': 'JoyPMCoin3',
    'PMCoin4': 'JoyPMCoin4',
    'PMCoinDoor': 'JoyPMCoinDoor',
    'PMCancel': 'JoyPMCancel',
    'PMDown': 'JoyPMDown',
    'PMUp': 'JoyPMUp',
    'PMEnter': 'JoyPMEnter',
    'LockbarKey': 'JoyLockbarKey',
    'TableRecenterKey': 'JoyTableRecenterKey',
    'TableUpKey': 'JoyTableUpKey',
    'TableDownKey': 'JoyTableDownKey',
    'PauseKey': 'JoyPauseKey',
    'TweakKey': 'JoyTweakKey',
}
# =================== Styling ===================
COMMON_CSS = """
<style>
    .root-container {
        font-family: 'Inter', system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Arial, sans-serif;
        min-height: 100vh;
        background-color: #fff);
        padding: 20px;
    }
    .layout-grid {
        display: grid;
        grid-template-columns: minmax(480px, 1fr) 360px;
        gap: 20px;
        width: 100%;
        max-width: 1200px;
        margin: auto;
    }
    @media (max-width: 1100px) {
        .layout-grid {
            grid-template-columns: 1fr;
        }
    }
    .actions-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 20px;
    }
    .action-row {
        display: flex;
        flex-direction: row;
        align-items: center;
        justify-content: flex-start;
        flex-wrap: nowrap;
        padding: 10px 12px;
        gap: 10px;
        border-radius: 12px;
        background-color: #1f2937; /* fallback */
        box-shadow: 0 3px 5px rgba(0, 0, 0, 0.25);
    }
    /* Theme-aware backgrounds and borders for rows */
    .q-dark .action-row { background-color: #111827; border: 1px solid #1f2a44; }
    .q-light .action-row { background-color: #f9fafb; border: 1px solid #e5e7eb; }
    .action-circle-style {
        width: 110px;
        height: 110px;
        border-radius: 50%;
        border: 2px solid #3b4a60;
        display: flex;
        align-items: center;
        justify-content: center;
        background: radial-gradient(ellipse at center, rgba(255,255,255,0.08) 0%, rgba(0,0,0,0) 65%);
    }
    /* Pinball-style glossy red circle; applied via extra class */
    .pinball-circle {
        border-color: #7f1d1d;
        background:
          radial-gradient(circle at 30% 25%, rgba(255,255,255,0.45) 0%, rgba(255,255,255,0.18) 28%, rgba(255,255,255,0.06) 42%, rgba(255,255,255,0.0) 60%),
          linear-gradient(180deg, #ff5151 0%, #e11d1d 55%, #991b1b 100%);
        box-shadow:
          0 8px 14px rgba(0,0,0,0.35),
          inset 0 4px 8px rgba(255,255,255,0.28),
          inset 0 -6px 14px rgba(0,0,0,0.38);
    }
    .pinball-circle .action-label { color: #ffffff; text-shadow: 0 1px 2px rgba(0,0,0,0.6); }
    /* Fix inner widths for alignment */
    .action-row .action-circle-style { flex: 0 0 110px; }
    .action-row .joy-wrap  { flex: 0 0 90px; }
    .action-row .key-wrap  { flex: 0 0 90px; }
    .action-label {
        font-size: 0.75rem;
        line-height: 1.1;
        text-align: center;
        font-weight: 600;
    }
    .q-dark .action-label { color: #E5E7EB; }
    .q-light .action-label { color: #111827; }
    .button-label {
        font-size: 0.65rem;
    }
    .gamepad-button-style {
        width: 44px;
        height: 44px;
        border-radius: 50%;
        background-color: #3B82F6; /* primary */
        border: 3px solid rgba(59,130,246,0.6);
        box-shadow: 0 0 6px rgba(59,130,246,0.7), inset 0 0 4px rgba(59,130,246,0.6);
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.2s ease-in-out;
    }
    .gamepad-button-style:hover { background-color: #2563EB; box-shadow: 0 0 10px rgba(59,130,246,0.9), inset 0 0 6px rgba(59,130,246,0.8); }
    .keyboard-key-style {
        min-width: 56px;
        min-height: 32px;
        border-radius: 8px;
        background-color: #6b7280;
        box-shadow: 0 3px 0 #4b5563;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #111827;
        cursor: pointer;
        transition: all 0.1s ease-in-out;
    }
    .keyboard-key-style:active {
        transform: translateY(1px);
        box-shadow: 0 1px 0 #4b5563;
    }
    .keyboard-key-style:hover {
        background-color: #64748b;
    }
    .q-dark .keyboard-key-style { color: #111827; }
    .q-light .keyboard-key-style { color: #111827; }

    /* Make outer action cards transparent so only the inner row provides background */
    .action-card { background: transparent; box-shadow: none; border: none; }
    .mapping-overlay {
        position: fixed;
        inset: 0;
        background-color: rgba(0, 0, 0, 0.7);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
    }
    .mapping-card {
        background-color: #111827;
        color: #eee;
        padding: 22px;
        border-radius: 14px;
        text-align: center;
        box-shadow: 0 10px 24px rgba(0, 0, 0, 0.6);
        width: 360px;
        max-width: 90%;
        border: 1px solid #374151;
    }
    /* joystick map (visualizer) */
    .joy-map-card { 
        background: #0b1220; 
        color: #e5e7eb; 
        border-radius: 16px; 
        padding: 14px; 
        box-shadow: 0 10px 20px rgba(0,0,0,0.35); 
        border: 1px solid #1f2a44; 
    }
    .joy-map-title { font-weight: 700; margin-bottom: 10px; }
    .joy-grid { display: grid; grid-template-columns: repeat(8, 1fr); gap: 6px; }
    .joy-dot { 
        width: 32px; 
        height: 32px; 
        border-radius: 50%; 
        border: 2px solid #9CA3AF; 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        font-size: .8rem; 
        background: #111827; 
        color: #E5E7EB; 
        user-select: none; 
    }
    .joy-dot.active { border-color: #10B981; background: #065F46; }
    .joy-last { font-size: .85rem; opacity: .85; margin-top: 6px; }
    .joy-help { font-size: .75rem; opacity: .7; margin-top: 6px; }
</style>
"""

# =================== Keyboard map ===================
KEY_VALUE_MAP = {
    'escape': 1, 'digit1': 2, 'digit2': 3, 'digit3': 4, 'digit4': 5, 'digit5': 6, 'digit6': 7, 'digit7': 8, 'digit8': 9, 'digit9': 10, 'digit0': 11,
    'minus': 12, 'equal': 13, 'backspace': 14, 'tab': 15, 'keyq': 16, 'keyw': 17, 'keye': 18, 'keyr': 19, 'keyt': 20, 'keyy': 21,
    'keyu': 22, 'keyi': 23, 'keyo': 24, 'keyp': 25, 'bracketleft': 26, 'bracketright': 27, 'enter': 28,
    'controlleft': 29, 'keya': 30, 'keys': 31, 'keyd': 32, 'keyf': 33, 'keyg': 34, 'keyh': 35, 'keyj': 36, 'keyk': 37, 'keyl': 38,
    'semicolon': 39, 'quote': 40, 'grave': 41, 'shiftleft': 42, 'backslash': 43, 'keyz': 44, 'keyx': 45, 'keyc': 46, 'keyv': 47, 'keyb': 48, 'keyn': 49, 'keym': 50,
    'comma': 51, 'period': 52, 'slash': 53, 'shiftright': 54, 'numpadmultiply': 55, 'altleft': 56, 'space': 57, 'capslock': 58, 'f1': 59, 'f2': 60, 'f3': 61, 'f4': 62, 'f5': 63, 'f6': 64, 'f7': 65, 'f8': 66, 'f9': 67, 'f10': 68,
    'numlock': 69, 'scrolllock': 70, 'numpad7': 71, 'numpad8': 72, 'numpad9': 73, 'numpadsubtract': 74, 'numpad4': 75, 'numpad5': 76, 'numpad6': 77, 'numpadadd': 78,
    'numpad1': 79, 'numpad2': 80, 'numpad3': 81, 'numpad0': 82, 'numpaddecimal': 83, 'f11': 87, 'f12': 88, 'f13': 100, 'f14': 101, 'f15': 102, 'numpadequals': 141,
    'at': 145, 'colon': 146, 'underline': 147, 'stop': 149, 'numpadenter': 156, 'controlright': 157, 'numpadcomma': 179, 'numpaddivide': 181, 'altright': 184,
    'pause': 197, 'home': 199, 'arrowup': 200, 'pageup': 201, 'arrowleft': 203, 'arrowright': 205, 'end': 207, 'arrowdown': 208, 'pagedown': 209, 'insert': 210, 'delete': 211, 'metaleft': 219, 'metaright': 220
}
VALUE_TO_KEY_MAP = {v: k for k, v in KEY_VALUE_MAP.items()}

# Pretty names for displaying current mapping
PRETTY_KEY_NAMES: Dict[str, str] = {
    'shiftleft': 'L Shift', 'shiftright': 'R Shift',
    'controlleft': 'Left Ctrl', 'controlright': 'Right Ctrl',
    'altleft': 'Alt', 'altright': 'AltGr',
    'space': 'Space', 'enter': 'Enter', 'tab': 'Tab', 'escape': 'Esc',
    'arrowup': '↑', 'arrowdown': '↓', 'arrowleft': '←', 'arrowright': '→',
    'minus': '-', 'equal': '=', 'backslash': '\\\\', 'slash': '/', 'comma': ',', 
    'period': '.', 'semicolon': ';', 'quote': "'", 'grave': '`',
    'digit0': '0', 'digit1': '1', 'digit2': '2', 'digit3': '3', 'digit4': '4',
    'digit5': '5', 'digit6': '6', 'digit7': '7', 'digit8': '8', 'digit9': '9',
}

# =================== Defaults (friendly labels) ===================
DEFAULT_KEY_LABELS: Dict[str, str] = {
    # Flippers & MagnaSave
    'LFlipKey': 'L Shift',
    'RFlipKey': 'R Shift',
    'LMagnaSave': 'Z',
    'RMagnaSave': 'X',
    # Core actions
    'StartGameKey': '1',
    'AddCreditKey': '5',
    'PlungerKey': 'Space',
    'Launch Ball': 'Enter',
    # Nudge
    'LTiltKey': 'Left Ctrl',
    'RTiltKey': 'Right Ctrl',
    'CTiltKey': '↑',
    # Utility / service
    'ExitGameKey': 'Esc',
    'Service': 'F1',
    'VolumeUp': '=',
    'VolumeDown': '-',
    'PauseKey': 'P',
    'TweakKey': 'T',
    'Extra Ball': 'B',
    'Menu': 'Tab',
}
# For robust defaults on the blue pill, map action -> keyboard event code
DEFAULT_KEY_CODES: Dict[str, str] = {
    'LFlipKey': 'shiftleft',
    'RFlipKey': 'shiftright',
    'LMagnaSave': 'keyz',
    'RMagnaSave': 'keyx',
    'StartGameKey': 'digit1',
    'AddCreditKey': 'digit5',
    'PlungerKey': 'space',
    'Launch Ball': 'enter',
    'LTiltKey': 'controlleft',
    'RTiltKey': 'controlright',
    'CTiltKey': 'arrowup',
    'ExitGameKey': 'escape',
    'Service': 'f1',
    'VolumeUp': 'equal',
    'VolumeDown': 'minus',
    'PauseKey': 'keyp',
    'TweakKey': 'keyt',
    'Extra Ball': 'keyb',
    'Menu': 'tab',
}
_DEFAULT_CODES_LOWER = {k.lower(): v for k, v in DEFAULT_KEY_CODES.items()}

def get_default_label(action_key: str) -> str:
    """Friendly name for the action's default key (always)."""
    code = _DEFAULT_CODES_LOWER.get((action_key or '').lower())
    if code:
        return _pretty_key(code)
    # fallback: friendly label dictionary
    return DEFAULT_KEY_LABELS.get(action_key, 'Set key')

def compute_label_from_ini_or_default(action_key: str, saved: str) -> str:
    """If a value is saved in INI, show the mapped key; otherwise, show the default."""
    if saved and saved.isdigit():
        code = VALUE_TO_KEY_MAP.get(int(saved))
        if code:
            return _pretty_key(code)
    return get_default_label(action_key)

# =================== Local state for keyboard overlay and gamepad ===================
_keyboard_overlay_visible = False
_keyboard_active_field: Optional[str] = None
_esc_hold_start: Optional[float] = None
_last_gamepad_button: Optional[int] = None

# =================== Gamepad detection using the Browser Gamepad API ===================
JS_FIRST_PRESSED = """
(() => {
  const gps = (navigator.getGamepads ? navigator.getGamepads() : []);
  for (const g of gps) {
    if (!g) continue;
    const n = Math.min(24, g.buttons?.length || 0);
    for (let i = 0; i < n; i++) {
      if (g.buttons[i] && g.buttons[i].pressed) return i + 1; // 1-based
    }
  }
  return null;
})()
"""

JS_ALL_PRESSED = """
(() => {
  const result = [];
  const gps = (navigator.getGamepads ? navigator.getGamepads() : []);
  for (const g of gps) {
    if (!g) continue;
    const n = Math.min(24, g.buttons?.length || 0);
    for (let i = 0; i < n; i++) {
      if (g.buttons[i] && g.buttons[i].pressed) result.push(i + 1);
    }
  }
  return result;
})()
"""

async def _detect_gamepad_button(timeout_s: float = 10.0) -> Optional[int]:
    """Poll the browser Gamepad API and return the first pressed button index (1..24)."""
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            idx = await ui.run_javascript(JS_FIRST_PRESSED, timeout=0.5)
            if isinstance(idx, (int, float)):
                return int(idx)
        except TimeoutError:
            return None
        await asyncio.sleep(0.05)
    return None

# =================== Helpers ===================
def _open_keyboard_overlay(field_name: str):
    global _keyboard_overlay_visible, _keyboard_active_field, _esc_hold_start
    _keyboard_active_field = field_name
    _keyboard_overlay_visible = True
    _esc_hold_start = None

def _close_keyboard_overlay():
    global _keyboard_overlay_visible, _keyboard_active_field, _esc_hold_start
    _keyboard_overlay_visible = False
    _keyboard_active_field = None
    _esc_hold_start = None

def _pretty_key(code: str) -> str:
    if not code:
        return ''
    code = code.lower()
    if code in PRETTY_KEY_NAMES:
        return PRETTY_KEY_NAMES[code]
    if code.startswith('key') and len(code) == 4:
        return code[-1].upper()
    if code.startswith('digit') and len(code) == 6 and code[-1].isdigit():
        return code[-1]
    return code.upper()

def _handle_keyboard_key(
    store: IniStore,
    labels: Dict[str, ui.label],
    e: events.KeyEventArguments,
    sec_opt_map: Dict[str, Tuple[str, str]],
):
    global _esc_hold_start
    if not _keyboard_overlay_visible or not _keyboard_active_field:
        return

    code = (e.key.code or '').lower()

    if code == 'escape':
        if e.action.keydown and _esc_hold_start is None:
            _esc_hold_start = time.time()
        elif e.action.keyup:
            if _esc_hold_start and (time.time() - _esc_hold_start) >= 3:
                ui.notify('Mapping cancelled.', type='warning')
                _close_keyboard_overlay()
            _esc_hold_start = None
        return

    if e.action.keydown:
        save_val = KEY_VALUE_MAP.get(code)
        if save_val is not None:
            sec, opt = sec_opt_map[_keyboard_active_field]
            store.set(sec, opt, str(save_val))
            if _keyboard_active_field in labels:
                labels[_keyboard_active_field].set_text(_pretty_key(code))
            ui.notify(f'{_keyboard_active_field} = {_pretty_key(code)} ({save_val})', type='positive')
        else:
            ui.notify(f'Unknown code: {code}', type='warning')
        _close_keyboard_overlay()

def _bind_live_label(store: IniStore, label_widget: ui.label, sec_opt: Tuple[str, str], action_key: str):
    sec, opt = sec_opt
    def push(val: str):
        label_widget.set_text(compute_label_from_ini_or_default(action_key, val))
    push(store.get(sec, opt))
    store.on_change(sec, opt, push)

def _render_joystick_map_panel():
    global _last_gamepad_button
    
    with ui.card().classes('joy-map-card'):
        ui.label('Joystick Map').classes('joy-map-title')
        dots: List[ui.element] = []
        with ui.element('div').classes('joy-grid'):
            for i in range(1, 25):
                with ui.element('div').classes('joy-dot') as dot:
                    ui.label(str(i))
                dots.append(dot)
        last_label = ui.label('Last: —').classes('joy-last')
        ui.label('Press any gamepad button to see which index lights up.').classes('joy-help')
    
    async def refresh():
        global _last_gamepad_button
        try:
            pressed = await ui.run_javascript(JS_ALL_PRESSED, timeout=0.5) or []
        except TimeoutError:
            pressed = []
        
        if not isinstance(pressed, list):
            pressed = []
        
        for idx, dot in enumerate(dots, start=1):
            if idx in pressed:
                dot.classes(add='active')
            else:
                dot.classes(remove='active')
        
        if pressed:
            _last_gamepad_button = int(pressed[0])
            last_label.set_text(f'Last: Button {_last_gamepad_button}')

    ui.timer(0.10, refresh)

# =================== The ActionConfigRow Class ===================
class ActionConfigRow(ui.row):
    """A reusable component for a single action mapping row."""
    def __init__(self, store: IniStore, action_key: str, kbd_sec_opt: Tuple[str, str], keyboard_labels: Dict[str, ui.label]):
        super().__init__()
        self.store = store
        self.action_key = action_key
        self.kbd_sec_opt = kbd_sec_opt
        self.keyboard_labels = keyboard_labels
        self.classes('action-row')

        # Determine the joystick key name, if it exists in our mapping
        self.joy_field_name = JOYSTICK_TO_KEYBOARD_NAME_MAPPING.get(self.action_key)
        self.joy_sec_opt = ('Player', self.joy_field_name) if self.joy_field_name else None

        with self:
            # Action Circle and Label (add pinball glossy style)
            with ui.column().classes('items-center justify-center action-circle-style pinball-circle'):
                ui.label(self.action_key).classes('action-label')
            
            # Buttons Container
            with ui.row().classes('items-center gap-4'):
                # Gamepad block
                with ui.column().classes('items-center joy-wrap'):
                    with ui.button(on_click=self.handle_joystick_map).classes('gamepad-button-style'):
                        self.joy_label = ui.label('?').classes('text-2xl font-extrabold text-white')
                    ui.label('Joy Button').classes('button-label text-gray-400 mt-1')
                
                # Bind joy label to INI store value, using a mapping dictionary
                    def update_joy_label(val: str):
                        self.joy_label.set_text(f'{val}' if val else '?')
                    
                    if self.joy_sec_opt:
                        update_joy_label(self.store.get(*self.joy_sec_opt))
                        self.store.on_change(*self.joy_sec_opt, update_joy_label)
                    else:
                        self.joy_label.set_text('?')

                # Keyboard key block
                with ui.column().classes('items-center key-wrap'):
                    with ui.button(on_click=lambda name=self.action_key: _open_keyboard_overlay(name)).classes('keyboard-key-style'):
                        self.kbd_label = ui.label('?').classes('text-xl font-bold text-gray-900')
                    ui.label('Key').classes('button-label text-gray-400 mt-1')
        
        self.keyboard_labels[self.action_key] = self.kbd_label
        _bind_live_label(self.store, self.kbd_label, self.kbd_sec_opt, self.action_key)

    async def handle_joystick_map(self):
        with ui.dialog() as dialog, ui.card():
            ui.label('Press a button on your gamepad…')
            ui.spinner(size='lg')
            ui.button('Cancel', on_click=dialog.close)
        dialog.open()
        
        try:
            mapped = await _detect_gamepad_button()
            if mapped is not None:
                if self.joy_sec_opt:
                    self.store.set(*self.joy_sec_opt, str(mapped))
                    self.joy_label.set_text(str(mapped))
                    ui.notify(f'Joystick mapped to Button {mapped}', type='positive')
                else:
                    ui.notify('Action has no predefined joystick field, but a button was detected.', type='warning')
            else:
                ui.notify('No gamepad button pressed or mapping cancelled.', type='warning')
        except Exception as e:
            ui.notify(f'An error occurred: {e}', type='negative')
        finally:
            dialog.close()

# =================== Public API ===================
def create_tab():
    return ui.tab('Buttons', icon='sports_esports')

def render_panel(tab, store: IniStore):
    ui.add_head_html(COMMON_CSS)
    ui.add_head_html('<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">')

    with ui.tab_panel(tab):
        ui.label('Keys/Buttons Mapping').classes('text-xl font-semibold mt-4 mb-4 w-full')
        
        # Keyboard capture overlay
        overlay_col = ui.column().classes('mapping-overlay').bind_visibility_from(globals(), '_keyboard_overlay_visible')
        with overlay_col:
            with ui.card().classes('mapping-card'):
                ui.label().bind_text_from(globals(), '_keyboard_active_field', lambda k: f'Mapping: {k}…' if k else '').classes('text-lg font-bold')
                ui.label('(Hold ESC for 3s to cancel)').classes('text-xs text-red-300 mb-2')
                ui.spinner(size='lg')
                ui.button('Cancel', on_click=_close_keyboard_overlay)

        # Keyboard listener
        keyboard_labels: Dict[str, ui.label] = {}
        ui.keyboard(on_key=lambda e: _handle_keyboard_key(store, keyboard_labels, e, BUTTONS_KEYBOARD_FIELDS), active=True)

        friendly_order: List[str] = [
            'LFlipKey', 'RFlipKey', 'StagedLFlipKey', 'StagedRFlipKey',
            'LMagnaSave', 'RMagnaSave', 'PlungerKey', 'AddCreditKey',
            'AddCredit2Key', 'StartGameKey', 'ExitGameKey', 'FrameCount',
            'VolumeUp', 'VolumeDown', 'LTiltKey', 'RTiltKey', 'CTiltKey',
            'MechTiltKey', 'DebugKey', 'DebuggerKey', 'Custom1', 'Custom2',
            'Custom3', 'Custom4', 'PMBuyIn', 'PMCoin3', 'PMCoin4', 'PMCoinDoor',
            'PMCancel', 'PMDown', 'PMUp', 'PMEnter', 'LockbarKey', 'Enable3DKey',
            'TableRecenterKey', 'TableUpKey', 'TableDownKey', 'EscapeKey',
            'PauseKey', 'TweakKey',
        ]
        
        # RIGHT FIXED: joystick visualizer (does not scroll with list)
        with ui.column().classes('fixed right-6 top-24 w-[360px] z-50'):
            _render_joystick_map_panel()

        # LEFT: actions grid (4 columns) using NiceGUI grid + cards
        with ui.element('div').classes('root-container'):
            with ui.grid(columns=4).classes('w-full').style('gap: 16px; margin-right: 380px;'):
                for action_key in friendly_order:
                    sec_opt_kbd = BUTTONS_KEYBOARD_FIELDS.get(action_key)
                    if sec_opt_kbd:  # Only render if a keyboard mapping exists
                        with ui.card().classes('p-2 action-card'):
                            ActionConfigRow(store, action_key, sec_opt_kbd, keyboard_labels)
