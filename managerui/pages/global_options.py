# pages/physics.py
from nicegui import ui

def build():
    widgets = {}

    flipper_fields = [
        "Mass", "Strength", "Elasticity", "Elasticity Falloff", "Friction",
        "Return Strength Ratio", "Coil Ramp Up", "Scatter Angle",
        "EOS Torque", "EOS Torque Angle"
    ]

    playfield_fields = [
        "Gravity Constant", "Friction", "Elasticity", "Elasticity Falloff",
        "Playfield Scatter", "Default Ele. Scatter Angle",
        "Min Slope", "Max Slope", "Set Name"
    ]

    with ui.row().classes('w-full justify-center items-start'):
        with ui.card().classes("p-4 w-1/3"):
            ui.label("Flipper Settings").classes("text-lg font-bold mb-2")
            for field in flipper_fields:
                key = field.replace(" ", "").replace(".", "").replace("(", "").replace(")", "")
                widgets[key] = ui.input(label=field).props("type=number").classes("w-full")

        with ui.card().classes("p-4 w-1/3"):
            ui.label("Playfield Settings").classes("text-lg font-bold mb-2")
            for field in playfield_fields:
                key = field.replace(" ", "").replace(".", "").replace("(", "").replace(")", "")
                widgets[key] = ui.input(label=field).props("type=number").classes("w-full")

    ui.button("💾 Save Changes", on_click=lambda: ui.notify("Save logic goes here")).classes("mt-4")

    return widgets
