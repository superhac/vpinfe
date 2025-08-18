from nicegui import ui

AXIS_OPTIONS = [
    "(disabled)", "X Axis", "Y Axis", "Z Axis",
    "rX Axis", "rY Axis", "rZ Axis", "Slider 1", "Slider 2", "OpenPinDevice"
]
KEY_OPTIONS = ["(none)", "Key 1", "Key 2"]
INPUT_API_OPTIONS = ["Direct Input", "XInput"]
RUMBLE_MODE_OPTIONS = ["Off", "Low", "Medium", "High"]

widgets = {}

def build():
    ui.label("Nudge & DOF Settings").classes("text-2xl font-bold")

    with ui.row().classes("w-full q-gutter-md"):
        with ui.card().classes("flex-1"):
            with ui.card_section():
                ui.label("Nudge Settings").classes("text-lg font-semibold")
                with ui.column().classes("gap-2"):
                    with ui.row().classes("items-center gap-2"):
                        widgets["LRAxis"] = ui.select(AXIS_OPTIONS, label="X Axis (L/R)", value="(disabled)").style("min-width: 120px")
                        widgets["LRAxisFlip"] = ui.checkbox("Reverse")
                    with ui.row().classes("items-center gap-2"):
                        widgets["UDAxis"] = ui.select(AXIS_OPTIONS, label="Y Axis (U/D)", value="(disabled)").style("min-width: 120px")
                        widgets["UDAxisFlip"] = ui.checkbox("Reverse")
                    with ui.row().classes("items-center gap-2"):
                        widgets["PlungerAxis"] = ui.select(AXIS_OPTIONS, label="Plunger", value="(disabled)").style("min-width: 120px")
                        widgets["ReversePlungerAxis"] = ui.checkbox("Reverse")
                    with ui.row().classes("items-center gap-2"):
                        widgets["PlungerSpeedAxis"] = ui.select(AXIS_OPTIONS, label="Pl. Speed", value="(disabled)").style("min-width: 120px")
                        widgets["DeadZone"] = ui.number(label="Dead Zone %", value=0).props("dense").style("width: 80px")
                    widgets["PlungerSpeedScale"] = ui.number(label="Pl. Speed Scale", value=0).props("dense").style("min-width: 120px")
            with ui.card_section():
                ui.label("Input & Rumble").classes("text-lg font-semibold")
                with ui.row().classes("items-center gap-4"):
                    widgets["InputApi"] = ui.select(INPUT_API_OPTIONS, label="Input API", value="Direct Input").style("min-width: 120px")
                    widgets["RumbleMode"] = ui.select(RUMBLE_MODE_OPTIONS, label="Ctrl. Rumble Behavior", value="Off").style("min-width: 120px")


        with ui.card().classes("flex-1"):
            with ui.card_section():
                ui.label("Button Mappings").classes("text-lg font-semibold")
                ui.label("Service Buttons").classes("text-md font-semibold")
                with ui.row().classes("items-center gap-4"):
                    widgets["JoyPMCancel"] = ui.select(KEY_OPTIONS, label="Cancel (7)").style("min-width: 120px")
                    widgets["JoyPMDown"] = ui.select(KEY_OPTIONS, label="Down (8)").style("min-width: 120px")
                    widgets["JoyPMUp"] = ui.select(KEY_OPTIONS, label="UP (9)").style("min-width: 120px")
                    widgets["JoyPMEnter"] = ui.select(KEY_OPTIONS, label="Enter (0)").style("min-width: 120px")
                ui.label("PinMAME Buttons").classes("text-md font-semibold q-mt-md")
                with ui.row().classes("items-center gap-4"):
                    widgets["JoyPMBuyIn"] = ui.select(KEY_OPTIONS, label="EB BuyIn (2)").style("min-width: 120px")
                    widgets["JoyPMCoin3"] = ui.select(KEY_OPTIONS, label="Coin 3 (5)").style("min-width: 120px")
                    widgets["JoyPMCoin4"] = ui.select(KEY_OPTIONS, label="Coin 4 (6)").style("min-width: 120px")
                    widgets["JoyPMCoinDoor"] = ui.select(KEY_OPTIONS, label="Door (END)").style("min-width: 120px")


    def save_nudge_dof():
        ui.notify("Settings saved!", type="positive")

    with ui.row().classes("justify-end q-mt-lg"):
        ui.button("Save", on_click=save_nudge_dof).props("color=primary")
