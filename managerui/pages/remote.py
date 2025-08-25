from nicegui import ui
from managerui.keysimulator import KeySimulator

ks = KeySimulator()
drawer = None
content_area = None
title_label = None

def build():
    global content_area, drawer, title_label

    with ui.header().classes('bg-gray-800 text-white items-center'):
        ui.button(icon='menu', on_click=lambda: drawer.toggle())

    with ui.left_drawer(value=False, bordered=True) as drawer:
        ui.label("Remote Control").classes("text-lg font-bold p-2")
        ui.separator()
        ui.button("VPX", on_click=lambda: show_buttons("vpx")).classes("w-full")
        ui.button("PinMAME", on_click=lambda: show_buttons("pinmame")).classes("w-full")
        ui.button("Other", on_click=lambda: show_buttons("other")).classes("w-full")

    # main content area
    with ui.column().classes("p-4 w-full h-full items-start content-start gap-2 flex-wrap") as content_area:
        title_label = ui.label("").classes("text-2xl font-bold mb-4")

    # show default buttons
    show_buttons("vpx")

def show_buttons(category: str):
    global content_area, drawer, title_label
    content_area.clear()

    # Title at the top
    with content_area:
        title_label = ui.label(category.upper()).classes("text-2xl font-bold mb-4")

    # Example button sets for each category
    if category == "vpx":
        buttons = ["Pause", "Quit", "Volume Up", "Volume Down", "Frame Count", "Menu", "Table Reset", "Add/Remove Ball"]
    elif category == "pinmame":
        buttons = ["Open/Close Door", "Cancel", "Down", "Up", "Enter"]
    else:
        buttons = ["Power", "Settings", "Help", "Update", "Shutdown"]

    # Flowing, wrapping button layout
    with content_area:
        with ui.row().classes("flex-wrap gap-2"):
            for label in buttons:
                ui.button(label, on_click=lambda l=label: handle_button(category, l)).classes("px-4 py-2 rounded-lg shadow")

    # collapse drawer after selection
    if drawer.value:
        drawer.toggle()

def handle_button(category: str, button: str):
    print(f"[{category}] Button pressed: {button}")
    match category:
        case 'vpx':
            match button:
                case 'Frame Count':
                    ks.press(KeySimulator.VPX_FRAME_COUNT)
                case 'Volume Up':
                    ks.press(KeySimulator.VPX_VOLUME_UP)
                case 'Volume Down':
                    ks.press(KeySimulator.VPX_VOLUME_DOWN)
                case 'Menu':
                    ks.press(KeySimulator.VPX_MENU)
                case 'Reset Table':
                    ks.press(KeySimulator.VPX_TABLE_RESET)
                case 'Quit':
                    ks.press(KeySimulator.VPX_QUIT)
                case 'Pause':
                    ks.press(KeySimulator.VPX_PAUSE)
                case 'Add/Remove Ball':
                    ks.press(KeySimulator.VPX_ADD_BALL)
        case 'pinmame':
            match button:
                case 'Open/Close Door':
                    ks.press(KeySimulator.PINMAME_OPEN_COIN_DOOR)
                case 'Cancel':
                    ks.press(KeySimulator.PINMAME_CANCEL)
                case 'Down':
                    ks.press(KeySimulator.PINMAME_DOWN)
                case 'Up':
                    ks.press(KeySimulator.PINMAME_UP)
                case 'Enter':
                    ks.press(KeySimulator.PINMAME_ENTER)
        case 'other':
            pass