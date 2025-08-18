from nicegui import ui, events, app


DIK_MAP = {
    'a': 'DIK_A', 'b': 'DIK_B', 'c': 'DIK_C', 'd': 'DIK_D',
    'enter': 'DIK_RETURN', 'space': 'DIK_SPACE', 'shift': 'DIK_LSHIFT',
    'control': 'DIK_LCONTROL', 'escape': 'DIK_ESCAPE',
    'left': 'DIK_LEFT', 'right': 'DIK_RIGHT', 'up': 'DIK_UP', 'down': 'DIK_DOWN',
    '-': 'DIK_MINUS', '=': 'DIK_EQUALS', ';': 'DIK_SEMICOLON', 'q': 'DIK_Q',
    'z': 'DIK_Z', '1': 'DIK_1', '5': 'DIK_5', '4': 'DIK_4', 'f11': 'DIK_F11',
    't': 'DIK_T', 'o': 'DIK_O', 'd': 'DIK_D', 'p': 'DIK_P', 'menu': 'DIK_MENU'
}

def build():
    button_config = {
        "Left Flipper": {"key": "L Shift", "button": "Button10"},
        "Right Flipper": {"key": "R Shift", "button": "Button11"},
        "LMagnaSave": {"key": "L Ctrl", "button": "Button8"},
        "RMagnaSave": {"key": "R Ctrl", "button": "Button9"},
        "Start Game": {"key": "1", "button": "Button2"},
        "Add Credit": {"key": "5", "button": "Button1"},
        "Add Credit 2": {"key": "4", "button": None},
        "Plunger": {"key": "Enter", "button": "Button13"},
        "Exit Game": {"key": "Q", "button": None},
        "Volume -": {"key": "-", "button": None},
        "Volume +": {"key": "=", "button": None},
        "Debug/Info": {"key": "F11", "button": None},
        "Left Nudge": {"key": "Z", "button": "Button14"},
        "Fwd Nudge": {"key": "Space", "button": "Button12"},
        "Right Nudge": {"key": ";", "button": "Button15"},
        "Mech Tilt": {"key": "T", "button": None},
        "Custom 1": {"key": "Up", "button": None},
        "Custom 2": {"key": "Down", "button": None},
        "Custom 3": {"key": "Left", "button": None},
        "Custom 4": {"key": "Right", "button": None},
        "Debug Balls": {"key": "O", "button": None},
        "Debugger/Editor": {"key": "D", "button": None},
        "Lockbar/Fire": {"key": "Menu", "button": "Button6"},
        "Pause": {"key": "P", "button": None},
    }

    available_buttons = [f"Button{i}" for i in range(1, 16)] + ["(none)"]

    ui.label("🎮 Button Configuration").classes("text-2xl font-bold mb-4")

    input_refs = {}
    current_action = {"name": None}

    dialog = ui.dialog().classes('bg-white')
    with dialog:
        ui.label('Press any key...').classes('text-lg font-bold')

    keyboard = ui.keyboard(on_key=lambda e: handle_key(e))

    def handle_key(e: events.KeyEventArguments):
        if not current_action["name"]:
            return

        key_str = str(e.key).lower()   

        dik = DIK_MAP.get(key_str, f'DIK_UNKNOWN({key_str})')
        button_config[current_action["name"]]["key"] = key_str
        button_config[current_action["name"]]["dik"] = dik
        input_refs[current_action["name"]].value = key_str

        ui.notify(f"{current_action['name']} set to {key_str} → {dik}")
        current_action["name"] = None
        dialog.close()

    with ui.grid(columns=4).classes("gap-4"):
        for action, data in button_config.items():
            with ui.card().style(
                    """
                    border-radius: 90%;
                    text-align: center;
                    width: 150px;
                    height: 150px;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                    background-image: url('/static/img/button.png');
                    background-size: cover;
                    background-position: center;
                    """
                ):
                ui.label(action).classes("text-sm font-bold")
                key_input = ui.input(value=data['key'], label='Default Key').props('dense readonly').style('width: 80px')
                input_refs[action] = key_input
                key_input.on("click", lambda e, a=action: open_key_dialog(a))
                ui.select(available_buttons, value=data['button'] or "(none)", label='Button').props('dense').style('width: 80px')

    def open_key_dialog(action: str):
        current_action["name"] = action
        dialog.open()

    def save_config():
        for action, config in button_config.items():
            dik = config.get('dik', 'N/A')
            button = config.get('button', '(none)')
            print(f"{action}: KEY={dik}, BUTTON={button}")
        ui.notify("Configuration saved!")

    ui.button("💾 Save Config", on_click=save_config).classes("mt-4")
