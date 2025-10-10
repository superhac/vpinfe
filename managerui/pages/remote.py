from nicegui import ui
from managerui.keysimulator import KeySimulator

ks = KeySimulator()
content_area = None
category_select = None


def build(parent=None):
    global content_area, category_select

    target = parent or ui

    # --- custom CSS for exact vertical centering and dark theme ---
    ui.add_head_html("""
    <style>
    /* Fix text color and centering in select */
    .q-field__native, .q-field__control, .q-field__marginal {
        min-height: 26px !important;
        height: 26px !important;
    }
    .q-field__control {
        background-color: #374151 !important; /* bg-gray-700 */
        border-radius: 6px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        border: none !important;
        padding: 0 !important;
    }
    .q-field__native {
        color: white !important;
        text-align: center !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    .q-field__input {
        color: white !important;
        text-align: center !important;
    }
    .q-placeholder {
        color: white !important;
    }

    /* dark popup dropdown */
    .q-menu {
        background-color: #374151 !important;
        color: white !important;
        border-radius: 6px !important;
        box-shadow: 0 6px 18px rgba(0,0,0,0.4) !important;
    }
    .q-item__label {
        color: white !important;
    }
    .q-item:hover {
        background-color: #4b5563 !important; /* hover gray-600 */
    }

    /* remove blue focus glow */
    .q-field--focused .q-field__control:before,
    .q-field--focused .q-field__control:after {
        display: none !important;
        box-shadow: none !important;
    }
    </style>
    """)

    with target.column().classes("w-full h-full items-center justify-center p-4"):
        with ui.card().classes(
            "bg-gray-800 text-white w-[90vw] max-w-[400px] rounded-3xl shadow-xl p-4 flex flex-col items-center gap-4"
        ):
            with ui.row().classes("items-center justify-center w-full gap-2"):
                ui.label("Mode:").classes("text-sm text-gray-300")
                category_select = ui.select(
                    ["VPX", "PinMAME", "Other"],
                    value="VPX",
                    on_change=lambda e: show_buttons(e.value.lower()),
                ).props(
                    "dense outlined options-dense"
                ).classes(
                    "text-white text-sm w-[110px] h-[26px] rounded-md border-none"
                )

            with ui.column().classes("w-full items-center justify-center gap-3") as content_area:
                pass

    show_buttons("vpx")


def show_buttons(category: str):
    global content_area
    content_area.clear()

    if category == "vpx":
        buttons = [
            "Pause", "Quit", "Volume Up", "Volume Down",
            "Frame Count", "Menu", "Table Reset", "Add/Remove Ball"
        ]
    elif category == "pinmame":
        buttons = ["O/C Door", "Cancel", "Down", "Up", "Enter"]
    else:
        buttons = ["Power", "Settings", "Help", "Update", "Shutdown"]

    with content_area:
        with ui.grid(columns=3).classes("gap-3 w-full justify-center"):
            for label in buttons:
                ui.button(label, on_click=lambda l=label: handle_button(category, l)).classes(
                    "bg-blue-500 text-white rounded-full py-3 min-w-[80px] text-sm "
                    "shadow-lg hover:bg-blue-400 active:bg-blue-600 transition-all duration-150"
                )


def handle_button(category: str, button: str):
    print(f"[{category}] Button pressed: {button}")
    match category:
        case 'vpx':
            match button:
                case 'Frame Count': ks.press(KeySimulator.VPX_FRAME_COUNT)
                case 'Volume Up': ks.hold(KeySimulator.VPX_VOLUME_UP, seconds=0.1)
                case 'Volume Down': ks.hold(KeySimulator.VPX_VOLUME_DOWN, seconds=0.1)
                case 'Menu': ks.press(KeySimulator.VPX_IN_GAME_UI)
                case 'Table Reset': ks.press(KeySimulator.VPX_TABLE_RESET)
                case 'Quit': ks.press(KeySimulator.VPX_QUIT)
                case 'Pause': ks.press(KeySimulator.VPX_PAUSE)
                case 'Add/Remove Ball': ks.press(KeySimulator.VPX_ADD_BALL)
        case 'pinmame':
            match button:
                case 'Open/Close Door': ks.press(KeySimulator.PINMAME_OPEN_COIN_DOOR)
                case 'Cancel': ks.press(KeySimulator.PINMAME_CANCEL)
                case 'Down': ks.hold(KeySimulator.PINMAME_DOWN, seconds=0.1)
                case 'Up': ks.hold(KeySimulator.PINMAME_UP, seconds=0.1)
                case 'Enter': ks.press(KeySimulator.PINMAME_ENTER)
        case 'other':
            print(f"Other category pressed: {button}")

