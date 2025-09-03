# app/tabs/nudge.py
from __future__ import annotations
from typing import Tuple, List
from nicegui import ui
from ..ini_store import IniStore
from ..schema import NUDGE_FIELDS
from ..binders import _bind_indexed_select, _bind_switch, _bind_input

AXIS_OPTIONS: List[str] = [
    'disabled', 'X Axis', 'Y Axis', 'Z Axis', 'rX Axis', 'rY Axis', 'rZ Axis', 'Slider 1', 'Slider 2'
]

# Common binders are imported from managerui.binders

def create_tab():
    return ui.tab('Nudge', icon='vibration')  

def render_panel(tab, store: IniStore):
    def row(label_text: str):
                        r = ui.row().classes('w-full items-center gap-6')
                        with r:
                            ui.label(label_text).classes('w-72')
                            field = ui.input().props('clearable').classes('flex-1')
                        return field
    
    with ui.tab_panel(tab):
        ui.label('Nudge Settings').classes('text-xl font-semibold')

        with ui.grid(columns=2).classes('w-full gap-0'):

            with ui.card():#.classes('max-w-5xl w-full'):
                with ui.column().classes('w-full gap-4'):

                    # --- Nudge ---
                    ui.label('Nudge').classes('text-base font-medium')
                    with ui.row().classes('w-full items-center gap-6'):
                        ui.label('LRAxis').classes('w-48')
                        LRAxis = ui.select(options=AXIS_OPTIONS, with_input=False).classes('flex-1')
                        LRAxisFlip           = ui.switch("Reverse LRAxis")
                        PBWAccelGainX        = ui.input('PBWAccelGainX')
                        PBWAccelMaxX         = ui.input('PBWAccelMaxX')
                    with ui.row().classes('w-full items-center gap-6'):
                        ui.label('UDAxis').classes('w-48')
                        UDAxis = ui.select(options=AXIS_OPTIONS, with_input=False).classes('flex-1')
                        UDAxisFlip           = ui.switch("Reverse UDAxis")
                        PBWAccelGainY        = ui.input('PBWAccelGainY')
                        PBWAccelMaxY         = ui.input('PBWAccelMaxY')
                    with ui.row().classes('w-full items-center gap-6'):
                        ui.label('PlungerAxis').classes('w-48')
                        PlungerAxis = ui.select(options=AXIS_OPTIONS, with_input=False).classes('flex-1')
                        ReversePlungerAxis = ui.switch("Reverse PlungerAxis").classes('flex-1')
                    PBWEnabled           = ui.switch('PBWEnabled')
                    EnableMouseInPlayer       = ui.switch('EnableMouseInPlayer')
                    EnableCameraModeFlyAround = ui.switch('EnableCameraModeFlyAround')
                    PlungerRetract     = ui.switch('PlungerRetract')
                    DeadZone           = ui.input('DeadZone').classes('w-48')


            with ui.card():#.classes('max-w-5xl w-full'):
                with ui.column().classes('w-full gap-4'):
                    #LRAxisFlip           = row('LRAxisFlip')
                    #UDAxisFlip           = row('LRAxisFlip')
                    #ReversePlungerAxis = row('ReversePlungerAxis')
                    PBWNormalMount       = row('PBWNormalMount')
                    PBWDefaultLayout     = row('PBWDefaultLayout')
                    PBWRotationCB        = row('PBWRotationCB')
                    PBWRotationvalue     = row('PBWRotationvalue')
                    ui.separator()
                    ui.label('Tilt plumb').classes('text-base font-medium')
                    TiltSensCB    = ui.switch('TiltSensCB')
                    TiltSensValue = row('TiltSensValue')
                    TiltInertia   = row('TiltInertia')

        ui.separator()
        with ui.grid(columns=2).classes('w-full gap-0'):

            with ui.card():#.classes('max-w-5xl w-full'):
                with ui.column().classes('w-full gap-4'):
                    
                    EnableNudgeFilter    = ui.switch('EnableNudgeFilter')

                    # AccelVelocityInput (indexed combobox)
                    with ui.row().classes('w-full items-center gap-6'):
                        ui.label('AccelVelocityInput').classes('w-72')
                        AccelVelocityInput = ui.select(options=AXIS_OPTIONS, with_input=False).classes('flex-1')

            # --- Bindings ---
            _bind_indexed_select(store, LRAxis,             NUDGE_FIELDS['LRAxis'], AXIS_OPTIONS)
            _bind_indexed_select(store, UDAxis,             NUDGE_FIELDS['UDAxis'], AXIS_OPTIONS)
            _bind_indexed_select(store, PlungerAxis,        NUDGE_FIELDS['PlungerAxis'], AXIS_OPTIONS)
            _bind_indexed_select(store, AccelVelocityInput, NUDGE_FIELDS['AccelVelocityInput'], AXIS_OPTIONS)

            # SWITCHES (only _bind_switch_10 — no _bind_generic)
            _bind_switch(store, LRAxisFlip,                  NUDGE_FIELDS['LRAxisFlip'])
            _bind_switch(store, UDAxisFlip,                  NUDGE_FIELDS['UDAxisFlip'])
            _bind_switch(store, PBWEnabled,                  NUDGE_FIELDS['PBWEnabled'])
            _bind_switch(store, ReversePlungerAxis,          NUDGE_FIELDS['ReversePlungerAxis'])
            _bind_switch(store, PlungerRetract,              NUDGE_FIELDS['PlungerRetract'])
            _bind_switch(store, EnableMouseInPlayer,         NUDGE_FIELDS['EnableMouseInPlayer'])
            _bind_switch(store, EnableCameraModeFlyAround,   NUDGE_FIELDS['EnableCameraModeFlyAround'])
            _bind_switch(store, EnableNudgeFilter,  NUDGE_FIELDS['EnableNudgeFilter'])
            _bind_switch(store, TiltSensCB,       NUDGE_FIELDS['TiltSensCB'])

            # INPUTS
            _bind_input(store, PBWNormalMount,     NUDGE_FIELDS['PBWNormalMount'])
            _bind_input(store, PBWDefaultLayout,   NUDGE_FIELDS['PBWDefaultLayout'])
            _bind_input(store, PBWRotationCB,      NUDGE_FIELDS['PBWRotationCB'])
            _bind_input(store, PBWRotationvalue,   NUDGE_FIELDS['PBWRotationvalue'])
            _bind_input(store, PBWAccelGainX,      NUDGE_FIELDS['PBWAccelGainX'])
            _bind_input(store, PBWAccelGainY,      NUDGE_FIELDS['PBWAccelGainY'])
            _bind_input(store, PBWAccelMaxX,       NUDGE_FIELDS['PBWAccelMaxX'])
            _bind_input(store, PBWAccelMaxY,       NUDGE_FIELDS['PBWAccelMaxY'])
            _bind_input(store, TiltSensValue,      NUDGE_FIELDS['TiltSensValue'])
            _bind_input(store, TiltInertia,        NUDGE_FIELDS['TiltInertia'])
            _bind_input(store, DeadZone,           NUDGE_FIELDS['DeadZone'])
