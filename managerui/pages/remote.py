from nicegui import ui
from managerui.keysimulator import KeySimulator
from pynput.keyboard import Key

ks = None
content_area = None
category_select = None


def build(parent=None):
    global content_area, category_select, ks
    if ks is None:
        ks = KeySimulator(debug=True)

    target = parent or ui

    # Custom CSS for remote control styling
    ui.add_head_html("""
    <style>
    /* Remove default body margins and set background */
    body {
        margin: 0 !important;
        padding: 0 !important;
        background-color: #111827 !important;
        overflow-x: hidden !important;
    }

    /* Remote control button styling */
    .remote-button {
        background: linear-gradient(145deg, #4a5568, #2d3748) !important;
        border: 2px solid #1a202c !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.1) !important;
        transition: all 0.15s ease !important;
    }
    .remote-button:hover {
        background: linear-gradient(145deg, #5a6678, #3d4758) !important;
        box-shadow: 0 6px 8px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.15) !important;
    }
    .remote-button:active {
        background: linear-gradient(145deg, #2d3748, #1a202c) !important;
        box-shadow: 0 2px 3px rgba(0,0,0,0.3), inset 0 2px 4px rgba(0,0,0,0.4) !important;
        transform: translateY(2px) !important;
    }

    /* Icon button styling - 25% smaller */
    .icon-button {
        background: linear-gradient(145deg, #374151, #1f2937) !important;
        border: 2px solid #111827 !important;
        width: 52px !important;
        height: 52px !important;
        border-radius: 50% !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 4px 8px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.1) !important;
        transition: all 0.15s ease !important;
    }
    .icon-button:hover {
        background: linear-gradient(145deg, #4b5563, #374151) !important;
        box-shadow: 0 6px 10px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.15) !important;
    }
    .icon-button:active {
        background: linear-gradient(145deg, #1f2937, #111827) !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.4), inset 0 3px 6px rgba(0,0,0,0.5) !important;
        transform: translateY(2px) !important;
    }

    /* D-pad button styling - 25% smaller */
    .dpad-button {
        background: linear-gradient(145deg, #374151, #1f2937) !important;
        border: 2px solid #111827 !important;
        width: 45px !important;
        height: 45px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 3px 6px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.1) !important;
        transition: all 0.15s ease !important;
    }
    .dpad-button:hover {
        background: linear-gradient(145deg, #4b5563, #374151) !important;
    }
    .dpad-button:active {
        background: linear-gradient(145deg, #1f2937, #111827) !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.4), inset 0 2px 4px rgba(0,0,0,0.5) !important;
        transform: translateY(1px) !important;
    }

    /* Select dropdown styling */
    .q-field__native, .q-field__control, .q-field__marginal {
        min-height: 32px !important;
        height: 32px !important;
    }
    .q-field__control {
        background-color: #1f2937 !important;
        border: 2px solid #111827 !important;
        border-radius: 8px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 8px !important;
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
    .q-field__append {
        color: white !important;
    }
    .q-select__dropdown-icon {
        color: white !important;
    }
    .q-menu {
        background-color: #1f2937 !important;
        color: white !important;
        border-radius: 8px !important;
        box-shadow: 0 6px 18px rgba(0,0,0,0.4) !important;
    }
    .q-item {
        color: white !important;
        min-height: 40px !important;
        padding: 8px 16px !important;
    }
    .q-item__label {
        color: white !important;
        font-size: 14px !important;
    }
    .q-item:hover, .q-item--active {
        background-color: #374151 !important;
    }
    .q-field--focused .q-field__control:before,
    .q-field--focused .q-field__control:after {
        display: none !important;
        box-shadow: none !important;
    }

    /* Mobile optimizations */
    @media (max-width: 640px) {
        .remote-body {
            max-width: 100vw !important;
            width: 100vw !important;
            margin: 0 !important;
            border-radius: 0 !important;
            border: none !important;
            min-height: 100vh !important;
        }
        .q-menu {
            max-height: 60vh !important;
        }
        /* Scale down fonts by 25% on mobile */
        .remote-body {
            font-size: 0.75em !important;
        }
    }

    /* Remote control body */
    .remote-body {
        background: linear-gradient(145deg, #1f2937, #111827) !important;
        border: 3px solid #0f1419 !important;
        box-shadow: 0 10px 30px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.05) !important;
    }

    /* Section dividers */
    .section-divider {
        height: 2px;
        background: linear-gradient(90deg, transparent, #374151, transparent);
        margin: 8px 0;
    }
    </style>
    """)

    with target.column().classes("w-full min-h-screen items-center justify-start p-0 md:p-4 md:justify-center"):
        with ui.card().classes(
            "remote-body text-white w-full md:w-[95vw] md:max-w-[420px] rounded-none md:rounded-3xl p-4 md:p-6 flex flex-col items-center gap-3 md:gap-5"
        ):
            # Header with mode selector
            ui.label("VPinFE Remote").classes("text-xl md:text-2xl font-bold text-gray-100 tracking-wide")

            with ui.row().classes("items-center justify-center w-full gap-2 mb-1 md:mb-2"):
                ui.label("Mode:").classes("text-xs md:text-sm text-gray-400 font-medium")
                category_select = ui.select(
                    ["VPX Maintenance", "VPX Game", "PinMAME", "VPinFE"],
                    value="VPX Maintenance",
                    on_change=lambda e: show_buttons(e.value.lower()),
                ).props(
                    "dense outlined options-dense dropdown-icon='expand_more' behavior='menu'"
                ).classes(
                    "text-white text-xs md:text-sm w-[150px] md:w-[180px]"
                ).style("min-width: 150px;")

            # Main content area
            with ui.column().classes("w-full items-center justify-center gap-1 mt-1") as content_area:
                pass

    show_buttons("vpx maintenance")


def show_buttons(category: str):
    global content_area
    content_area.clear()

    with content_area:
        if category == "vpx maintenance":
            show_vpx_controls()
        elif category == "vpx game":
            show_vpx_game_controls()
        elif category == "pinmame":
            show_pinmame_controls()
        else:
            show_other_controls()


def show_vpx_controls():
    """VPX remote control layout"""

    # Main Section (moved to top)
    with ui.card().classes("bg-gray-900/50 w-full p-3 md:p-4 rounded-xl border border-gray-700"):
        ui.label("Main").classes("text-center text-xs md:text-sm font-semibold text-gray-300 mb-2 md:mb-3")
        with ui.row().classes("items-center justify-center gap-3 md:gap-4 w-full"):
            # Reset
            with ui.column().classes("items-center gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Table Reset")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("refresh", size="sm").classes("text-orange-400")
                ui.label("Reset").classes("text-[10px] md:text-xs text-gray-400")

            # Quit
            with ui.column().classes("items-center gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Quit")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("power_settings_new", size="sm").classes("text-red-400")
                ui.label("Quit").classes("text-[10px] md:text-xs text-gray-400")

    # Volume Section
    with ui.card().classes("bg-gray-900/50 w-full p-3 md:p-4 rounded-xl border border-gray-700"):
        ui.label("Volume").classes("text-center text-xs md:text-sm font-semibold text-gray-300 mb-2 md:mb-3")
        with ui.column().classes("items-center justify-center gap-2 md:gap-3 w-full"):
            # Volume buttons row
            with ui.row().classes("items-center justify-center gap-4 md:gap-6 w-full"):
                # Volume Down
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Volume Down")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("remove", size="sm").classes("text-red-400")

                # Volume Up
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Volume Up")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("add", size="sm").classes("text-green-400")

            # Stereo Toggle (centered below)
            ui.button(
                "Toggle Stereo",
                on_click=lambda: handle_button("vpx", "Toggle Stereo")
            ).classes("remote-button text-white px-4 md:px-6 py-1.5 md:py-2 rounded-lg text-xs md:text-sm font-medium")

    # In-Game UI Section
    with ui.card().classes("bg-gray-900/50 w-full p-3 md:p-4 rounded-xl border border-gray-700"):
        # Title row with menu button
        with ui.row().classes("items-start justify-between w-full"):
            # Title (left aligned)
            ui.label("In Game UI").classes("text-xs md:text-sm font-semibold text-gray-300")

            # Menu button (right aligned with circle)
            with ui.button(
                on_click=lambda: handle_button("vpx", "Menu")
            ).props("flat round").classes("icon-button bg-gray-800 border-2 border-blue-300"):
                ui.icon("menu", size="sm").classes("text-blue-300")

        # D-pad navigation (all centered vertically)
        with ui.column().classes("items-center gap-1 w-full"):
            # Up arrow
            with ui.button(
                on_click=lambda: handle_button("vpx", "Navigate Up")
            ).props("flat").classes("dpad-button rounded-t-xl"):
                ui.icon("keyboard_arrow_up", size="sm").classes("text-blue-300")

            # Left, Enter, Right row
            with ui.row().classes("gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Navigate Left")
                ).props("flat").classes("dpad-button rounded-l-xl"):
                    ui.icon("chevron_left", size="sm").classes("text-blue-300")

                ui.button(
                    "Enter",
                    on_click=lambda: handle_button("vpx", "Enter")
                ).classes("dpad-button text-white font-medium text-[10px] md:text-xs")

                with ui.button(
                    on_click=lambda: handle_button("vpx", "Navigate Right")
                ).props("flat").classes("dpad-button rounded-r-xl"):
                    ui.icon("chevron_right", size="sm").classes("text-blue-300")

            # Down arrow
            with ui.button(
                on_click=lambda: handle_button("vpx", "Navigate Down")
            ).props("flat").classes("dpad-button rounded-b-xl"):
                ui.icon("keyboard_arrow_down", size="sm").classes("text-blue-300")

            # Keyboard button (below D-pad)
            ui.button(
                "Keyboard",
                on_click=lambda: show_virtual_keyboard()
            ).classes("remote-button text-white px-6 md:px-8 py-1.5 md:py-2 rounded-lg text-[10px] md:text-xs font-medium mt-2")

    # Debug Section
    with ui.card().classes("bg-gray-900/50 w-full p-3 md:p-4 rounded-xl border border-gray-700"):
        ui.label("Debug").classes("text-center text-xs md:text-sm font-semibold text-gray-300 mb-2 md:mb-3")
        with ui.row().classes("items-center justify-center gap-3 md:gap-4 w-full"):
            # Debugger
            with ui.column().classes("items-center gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Debugger")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("bug_report", size="sm").classes("text-yellow-400")
                ui.label("Debugger").classes("text-[10px] md:text-xs text-gray-400")

            # Debug Balls
            with ui.column().classes("items-center gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Debug Balls")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("circle", size="sm").classes("text-gray-300")
                ui.label("Debug Balls").classes("text-[10px] md:text-xs text-gray-400")

            # Performance Overlay
            with ui.column().classes("items-center gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Performance Overlay")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("speed", size="sm").classes("text-purple-400")
                ui.label("Perf Overlay").classes("text-[10px] md:text-xs text-gray-400")


def show_vpx_game_controls():
    """VPX Game control layout"""

    # Main Section
    with ui.card().classes("bg-gray-900/50 w-full p-3 md:p-4 rounded-xl border border-gray-700"):
        ui.label("Main").classes("text-center text-xs md:text-sm font-semibold text-gray-300 mb-2 md:mb-3")
        with ui.column().classes("items-center gap-2 w-full"):
            # Icon buttons row: Start and Pause
            with ui.row().classes("items-center justify-center gap-3 md:gap-4 w-full"):
                # Start
                with ui.column().classes("items-center gap-1"):
                    with ui.button(
                        on_click=lambda: handle_button("vpx game", "Start")
                    ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                        ui.icon("play_arrow", size="sm").classes("text-green-400")
                    ui.label("Start").classes("text-[10px] md:text-xs text-gray-400")

                # Pause
                with ui.column().classes("items-center gap-1"):
                    with ui.button(
                        on_click=lambda: handle_button("vpx game", "Pause")
                    ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                        ui.icon("pause", size="sm").classes("text-blue-400")
                    ui.label("Pause").classes("text-[10px] md:text-xs text-gray-400")

            # Row with ShowRules, ExtraBall, Lockbar
            with ui.row().classes("items-center justify-center gap-2 w-full"):
                with ui.button(
                    on_click=lambda: handle_button("vpx game", "ShowRules")
                ).classes("remote-button text-white px-3 md:px-4 py-1.5 md:py-2 rounded-lg text-[10px] md:text-xs font-medium flex items-center gap-1"):
                    ui.icon("description", size="xs").classes("text-cyan-400")
                    ui.label("Show Rules").classes("text-[10px] md:text-xs")

                with ui.button(
                    on_click=lambda: handle_button("vpx game", "ExtraBall")
                ).classes("remote-button text-white px-3 md:px-4 py-1.5 md:py-2 rounded-lg text-[10px] md:text-xs font-medium flex items-center gap-1"):
                    ui.icon("sports_baseball", size="xs").classes("text-yellow-400")
                    ui.label("Extra Ball").classes("text-[10px] md:text-xs")

                with ui.button(
                    on_click=lambda: handle_button("vpx game", "Lockbar")
                ).classes("remote-button text-white px-3 md:px-4 py-1.5 md:py-2 rounded-lg text-[10px] md:text-xs font-medium flex items-center gap-1"):
                    ui.icon("lock", size="xs").classes("text-orange-400")
                    ui.label("Lockbar").classes("text-[10px] md:text-xs")

    # Coins Section
    with ui.card().classes("bg-gray-900/50 w-full p-3 md:p-4 rounded-xl border border-gray-700"):
        ui.label("Coins").classes("text-center text-xs md:text-sm font-semibold text-gray-300 mb-2 md:mb-3")

        with ui.grid(columns=2).classes("gap-2 w-full justify-items-center"):
            for i in range(1, 5):
                with ui.button(
                    on_click=lambda num=i: handle_button("vpx game", f"Credit{num}")
                ).classes("remote-button text-white px-4 md:px-6 py-2 rounded-lg text-xs md:text-sm font-medium flex items-center gap-1"):
                    ui.icon("paid", size="xs").classes("text-yellow-400")
                    ui.label(f"Credit {i}").classes("text-xs md:text-sm")


def show_pinmame_controls():
    """PinMAME remote control layout"""

    with ui.card().classes("bg-gray-900/50 w-full p-3 md:p-4 rounded-xl border border-gray-700"):
        ui.label("Service Menu Navigation").classes("text-center text-xs md:text-sm font-semibold text-gray-300 mb-2 md:mb-3")

        # Three column layout: Coin Door | Up/Down | Enter/Cancel
        with ui.row().classes("items-center justify-center gap-4 w-full flex-nowrap"):
            # Left column: Coin Door (centered vertically)
            with ui.column().classes("items-center justify-center flex-shrink-0"):
                with ui.button(
                    on_click=lambda: handle_button("pinmame", "Coin Door")
                ).props("flat").classes("dpad-button"):
                    ui.icon("meeting_room", size="sm").classes("text-blue-400")

            # Middle column: Up/Down
            with ui.column().classes("items-center justify-center gap-2 flex-shrink-0"):
                # Up
                with ui.button(
                    on_click=lambda: handle_button("pinmame", "Up")
                ).props("flat").classes("dpad-button rounded-t-xl"):
                    ui.icon("keyboard_arrow_up", size="sm").classes("text-green-400")

                # Down
                with ui.button(
                    on_click=lambda: handle_button("pinmame", "Down")
                ).props("flat").classes("dpad-button rounded-b-xl"):
                    ui.icon("keyboard_arrow_down", size="sm").classes("text-green-400")

            # Right column: Enter/Cancel (side by side)
            with ui.column().classes("items-center justify-center gap-2 flex-shrink-0"):
                with ui.row().classes("gap-2 flex-nowrap"):
                    # Enter
                    ui.button(
                        "Enter",
                        on_click=lambda: handle_button("pinmame", "Enter")
                    ).classes("dpad-button text-white font-bold text-[10px] md:text-xs px-3").style("background: linear-gradient(145deg, #10b981, #059669) !important;")

                    # Cancel
                    with ui.button(
                        on_click=lambda: handle_button("pinmame", "Cancel")
                    ).props("flat").classes("dpad-button"):
                        ui.icon("close", size="sm").classes("text-red-400")

    # Services Section
    with ui.card().classes("bg-gray-900/50 w-full p-3 md:p-4 rounded-xl border border-gray-700"):
        ui.label("Service Buttons").classes("text-center text-xs md:text-sm font-semibold text-gray-300 mb-2 md:mb-3")

        with ui.grid(columns=4).classes("gap-2 w-full justify-items-center"):
            for i in range(1, 9):
                ui.button(
                    f"S{i}",
                    on_click=lambda num=i: handle_button("pinmame", f"Service {num}")
                ).classes("remote-button text-white px-3 py-2 rounded-lg text-[10px] md:text-xs font-medium")


def show_other_controls():
    """Other controls layout"""

    with ui.card().classes("bg-gray-900/50 w-full p-4 rounded-xl border border-gray-700"):
        ui.label("System Controls").classes("text-center text-sm font-semibold text-gray-300 mb-4")

        with ui.grid(columns=3).classes("gap-4 w-full justify-items-center"):
            controls = [
                ("Power", "power_settings_new", "text-green-400"),
                ("Settings", "settings", "text-blue-400"),
                ("Help", "help", "text-purple-400"),
                ("Update", "system_update", "text-yellow-400"),
                ("Shutdown", "power_off", "text-red-400"),
                ("Info", "info", "text-cyan-400"),
            ]

            for label, icon, color in controls:
                with ui.column().classes("items-center gap-2"):
                    with ui.button(
                        on_click=lambda l=label: handle_button("other", l)
                    ).props("flat round").classes("icon-button"):
                        ui.icon(icon, size="md").classes(color)
                    ui.label(label).classes("text-xs text-gray-400 font-medium")


def show_virtual_keyboard():
    """Show a virtual keyboard dialog"""
    with ui.dialog() as keyboard_dialog, ui.card().classes("bg-gray-800 p-4 w-[90vw] max-w-[500px]"):
        ui.label("Virtual Keyboard").classes("text-xl font-bold text-white mb-4")

        # Common keys layout
        keyboard_layout = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
            ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
            ['Z', 'X', 'C', 'V', 'B', 'N', 'M'],
        ]

        for row in keyboard_layout:
            with ui.row().classes("gap-1 justify-center w-full"):
                for key in row:
                    ui.button(
                        key,
                        on_click=lambda k=key, d=keyboard_dialog: send_keyboard_key(k, d)
                    ).classes("bg-gray-700 text-white px-3 py-2 rounded text-sm min-w-[40px] hover:bg-gray-600")

        # Special keys row
        with ui.row().classes("gap-2 justify-center w-full mt-2"):
            ui.button(
                "Space",
                on_click=lambda d=keyboard_dialog: send_keyboard_key(Key.space, d)
            ).classes("bg-gray-700 text-white px-6 py-2 rounded text-sm hover:bg-gray-600")

            ui.button(
                "Enter",
                on_click=lambda d=keyboard_dialog: send_keyboard_key(Key.enter, d)
            ).classes("bg-blue-600 text-white px-6 py-2 rounded text-sm hover:bg-blue-500")

            ui.button(
                "Backspace",
                on_click=lambda d=keyboard_dialog: send_keyboard_key(Key.backspace, d)
            ).classes("bg-red-600 text-white px-4 py-2 rounded text-sm hover:bg-red-500")

        # Close button
        with ui.row().classes("justify-center w-full mt-4"):
            ui.button(
                "Close",
                on_click=keyboard_dialog.close
            ).classes("bg-gray-600 text-white px-8 py-2 rounded hover:bg-gray-500")

    keyboard_dialog.open()


def send_keyboard_key(key, dialog):
    """Send a keyboard key press through KeySimulator"""
    # Handle Key objects vs strings
    if isinstance(key, Key):
        key_name = key.name
    else:
        key_name = key

    print(f"Virtual keyboard: Pressing key '{key_name}'")
    ks.press(key)
    # Keep dialog open for multiple key presses
    # If you want to close after each key, uncomment the next line:
    # dialog.close()


def handle_button(category: str, button: str):
    print(f"[{category}] Button pressed: {button}")
    match category:
        case 'vpx maintenance' | 'vpx':
            match button:
                case 'Performance Overlay': ks.press_mapping("PerfOverlay")
                case 'Volume Up': ks.press_mapping("VolumeUp", seconds=0.1)
                case 'Volume Down': ks.press_mapping("VolumeDown", seconds=0.1)
                case 'Toggle Stereo': ks.press_mapping("ToggleStereo")
                case 'Menu': ks.press_mapping("InGameUI")
                case 'Table Reset': ks.press_mapping("Reset")
                case 'Quit': ks.press_mapping("ExitGame")
                case 'Pause': ks.press_mapping("Pause")
                case 'Extra Ball': ks.press_mapping("ExtraBall")
                case 'Debugger': ks.press_mapping("Debugger")
                case 'Debug Balls': ks.press_mapping("DebugBalls")
                case 'Navigate Up': ks.hold_mapping("LeftMagna", seconds=0.1)
                case 'Navigate Down': ks.hold_mapping("RightMagna", seconds=0.1)
                case 'Navigate Left': ks.hold_mapping("LeftFlipper", seconds=0.1)
                case 'Navigate Right': ks.hold_mapping("RightFlipper", seconds=0.1)
                case 'Enter': ks.hold(Key.enter, seconds=0.1)
        case 'vpx game':
            match button:
                case 'Start': ks.hold_mapping("Start")
                case 'Pause': ks.press_mapping("Pause")
                case 'ShowRules': ks.press_mapping("ShowRules")
                case 'ExtraBall': ks.press_mapping("ExtraBall")
                case 'Lockbar': ks.press_mapping("Lockbar")
                case 'Credit1': ks.press_mapping("Credit1")
                case 'Credit2': ks.press_mapping("Credit2")
                case 'Credit3': ks.press_mapping("Credit3")
                case 'Credit4': ks.press_mapping("Credit4")
        case 'pinmame':
            match button:
                case 'Coin Door': ks.press(KeySimulator.PINMAME_OPEN_COIN_DOOR)
                case 'Cancel': ks.press(KeySimulator.PINMAME_CANCEL)
                case 'Down': ks.hold(KeySimulator.PINMAME_DOWN, seconds=0.1)
                case 'Up': ks.hold(KeySimulator.PINMAME_UP, seconds=0.1)
                case 'Enter': ks.press(KeySimulator.PINMAME_ENTER)
                case 'Service 1': ks.press_mapping("Service1")
                case 'Service 2': ks.press_mapping("Service2")
                case 'Service 3': ks.press_mapping("Service3")
                case 'Service 4': ks.press_mapping("Service4")
                case 'Service 5': ks.press_mapping("Service5")
                case 'Service 6': ks.press_mapping("Service6")
                case 'Service 7': ks.press_mapping("Service7")
                case 'Service 8': ks.press_mapping("Service8")
        case 'other':
            print(f"Other category pressed: {button}")
