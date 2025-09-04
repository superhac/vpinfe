from __future__ import annotations
from typing import Tuple, List, Optional, Callable
from nicegui import ui
from ..ini_store import IniStore
from ..schema import (
    PLUGIN_ENABLE_FIELDS,
    PLUGIN_OPTIONS,
    SCOREVIEW_FIELDS,
    DOF_CONTROLLER_FIELDS,     
    DOF_ROUTING_OPTIONS,
)
from ..binders import _bind_input, _bind_indexed_select, _bind_switch

# 0/1 fields that should appear as switches (currently hardcoded)
SWITCH10_FIELDS = {
    # [Plugin.B2S]
    ('Plugin.B2S', 'ScoreviewDMDOverlay'),
    ('Plugin.B2S', 'ScoreviewDMDAutoPos'),
    ('Plugin.B2S', 'BackglassDMDOverlay'),
    ('Plugin.B2S', 'BackglassDMDAutoPos'),

    # [Plugin.B2SLegacy]
    ('Plugin.B2SLegacy', 'B2SHideGrill'),
    ('Plugin.B2SLegacy', 'B2SHideB2SDMD'),
    ('Plugin.B2SLegacy', 'B2SHideB2SBackglass'),
    ('Plugin.B2SLegacy', 'B2SHideDMD'),
    ('Plugin.B2SLegacy', 'B2SDualMode'),
    ('Plugin.B2SLegacy', 'B2SDMDFlipY'),
    ('Plugin.B2SLegacy', 'BackglassDMDOverlay'),
    ('Plugin.B2SLegacy', 'BackglassDMDAutoPos'),
    ('Plugin.B2SLegacy', 'ScoreviewDMDOverlay'),
    ('Plugin.B2SLegacy', 'ScoreviewDMDAutoPos'),

    # [Plugin.DMDUtil]
    ('Plugin.DMDUtil', 'ZeDMD'),
    ('Plugin.DMDUtil', 'DMDServer'),
    ('Plugin.DMDUtil', 'ZeDMDDebug'),
    ('Plugin.DMDUtil', 'ZeDMDWiFi'),
    ('Plugin.DMDUtil', 'Pixelcade'),
    ('Plugin.DMDUtil', 'DumpDMDTxt'),
    ('Plugin.DMDUtil', 'DumpDMDRaw'),
    ('Plugin.DMDUtil', 'FindDisplays'),

    # [Plugin.PinMAME]
    ('Plugin.PinMAME', 'Cheat'),
    ('Plugin.PinMAME', 'Sound'),
}



def _bind_switch_enable(store: IniStore, sw, sec_opt: Tuple[str, str], on_toggle: Optional[Callable[[bool], None]] = None):
    """'Enable' switch that stores '1'/'0' (string)."""
    sec, opt = sec_opt
    def push(val: str):
        on = str(val).strip().lower() in ('1', 'true', 'on', 'yes')
        sw.value = on
        if on_toggle:
            on_toggle(on)
    push(store.get(sec, opt))
    store.on_change(sec, opt, push)
    sw.on('update:model-value',
          lambda e: (store.set(sec, opt, '1' if bool(sw.value) else '0'),
                     on_toggle and on_toggle(bool(sw.value))))
    
def _field_switch(label_text: str):
    r = ui.row().classes('w-full items-center gap-3')
    with r:
        ui.label(label_text).classes('w-72')
        comp = ui.switch().classes('flex-none')
    return comp

    

def _set_visible(el, yes: bool):
    try:
        el.visible = yes
    except Exception:
        if yes:
            el.classes(remove='hidden')
        else:
            el.classes('hidden')

# ---------------- UI Helpers ----------------

def _chunk(lst: List, size: int) -> List[List]:
    return [lst[i:i+size] for i in range(0, len(lst), size)]

def _field_row(label_text: str):
    r = ui.row().classes('w-full items-center gap-3')
    with r:
        ui.label(label_text).classes('w-72')
        comp = ui.input().props('clearable dense').classes('flex-1')
    return comp

def _field_card(title: str, fields: List[Tuple[str, Tuple[str, str]]], store: IniStore):
    """Card with multiple rows (label + input)"""
    with ui.card().classes('p-3'):
        if title:
            ui.label(title).classes('text-sm font-medium mb-1')
        for label_text, sec_opt in fields:
            comp = _field_row(label_text)
            _bind_input(store, comp, sec_opt)

def _options_block(store: IniStore, option_pairs: List[Tuple[str, str]]):
    """
    Render plugin options.
    - option_pairs: list of (section, option) in order.
    - If len > 3: split into cards (up to ~6 fields per card), and display cards in 3xN grids.
    - If len <= 3: simple rows only.
    - Each field is rendered as input or switch according to SWITCH10_FIELDS.
    """
    if not option_pairs:
        return

    labeled = [(opt, (sec, opt)) for (sec, opt) in option_pairs]

    def _render_one(label_text: str, sec_opt: Tuple[str, str]):
        sec, opt = sec_opt
        if (sec, opt) in SWITCH10_FIELDS:
            comp = _field_switch(label_text)
            _bind_switch(store, comp, sec_opt)
        else:
            comp = _field_row(label_text)
            _bind_input(store, comp, sec_opt)

    if len(labeled) <= 3:
        for label_text, sec_opt in labeled:
            _render_one(label_text, sec_opt)
        return

    # More than 3: 3xN cards, ~6 fields per card
    per_card = 6
    cards_data = _chunk(labeled, per_card)
    for trio in _chunk(cards_data, 3):  # up to 3 cards per grid
        with ui.grid(columns=3).classes('w-full gap-0'):
            for card_fields in trio:
                with ui.card().classes('p-3'):
                    for label_text, sec_opt in card_fields:
                        _render_one(label_text, sec_opt)


# ---------------- Generic plugin row ----------------

def _plugin_line(store: IniStore, plugin_name: str, enable_field: Tuple[str, str], option_pairs: List[Tuple[str, str]]):
    """One row per plugin: Label + Enable + Expansion showing options."""
    with ui.row().classes('w-full items-start justify-between gap-3'):
        # Header and switch
        with ui.row().classes('items-center gap-3'):
            ui.icon('extension')
            ui.label(plugin_name).classes('text-base font-medium')
        sw = ui.switch('Enable').classes('ml-auto')

    # expandable block; visibility is tied to Enable
    options_holder = ui.column().classes('w-full')
    if option_pairs:
        with options_holder:
            exp = ui.expansion('Options', icon='tune', value=False).classes('w-full')
            with exp:
                _options_block(store, option_pairs)

    def _toggle(on: bool):
        _set_visible(options_holder, on)

    _bind_switch_enable(store, sw, enable_field, on_toggle=_toggle)
    _toggle(sw.value if hasattr(sw, 'value') else False)

# ---------------- Special case: ScoreView ----------------

def _scoreview_block(store: IniStore):
    """Render the ScoreView section (outside Plugin.ScoreView), visible only when enabled."""
    # Header + switch of the ScoreView plugin
    with ui.row().classes('w-full items-start justify-between gap-3'):
        with ui.row().classes('items-center gap-3'):
            ui.icon('score')
            ui.label('ScoreView').classes('text-base font-medium')
        sw = ui.switch('Enable').classes('ml-auto')

    options_holder = ui.column().classes('w-full')
    with options_holder:
        exp = ui.expansion('Options', icon='tune', value=False).classes('w-full')
        with exp:
            # There is a lot, so use two grids (cards) to organize
            # Grid 1: three cards
            with ui.grid(columns=3).classes('w-full gap-0'):
                # Card 1: Display & Mode
                with ui.card().classes('p-3'):
                    ui.label('Display & Mode').classes('text-sm font-medium mb-1')
                    comp = _field_row('ScoreViewDisplay')
                    _bind_input(store, comp, SCOREVIEW_FIELDS['ScoreViewDisplay'])
                    comp = _field_row('ScoreViewFullScreen')
                    _bind_input(store, comp, SCOREVIEW_FIELDS['ScoreViewFullScreen'])
                    # ScoreViewOutput combobox (indices 0..2)
                    ui.label('ScoreViewOutput').classes('text-xs text-gray-600 mt-1')
                    sel = ui.select(options=[]).props('dense').classes('w-full')
                    _bind_indexed_select(store, sel, SCOREVIEW_FIELDS['ScoreViewOutput'], [
                        'Disabled',                       # 0
                        'Embedded in playfield output',   # 1
                        'Native system window',           # 2
                    ])

                # Card 2: Window Position
                with ui.card().classes('p-3'):
                    ui.label('Window Position').classes('text-sm font-medium mb-1')
                    comp = _field_row('ScoreViewWndX')
                    _bind_input(store, comp, SCOREVIEW_FIELDS['ScoreViewWndX'])
                    comp = _field_row('ScoreViewWndY')
                    _bind_input(store, comp, SCOREVIEW_FIELDS['ScoreViewWndY'])

                # Card 3: Window Size
                with ui.card().classes('p-3'):
                    ui.label('Window Size').classes('text-sm font-medium mb-1')
                    comp = _field_row('ScoreViewWidth')
                    _bind_input(store, comp, SCOREVIEW_FIELDS['ScoreViewWidth'])
                    comp = _field_row('ScoreViewHeight')
                    _bind_input(store, comp, SCOREVIEW_FIELDS['ScoreViewHeight'])

            # Grid 2: Priorities
            with ui.grid(columns=3).classes('w-full gap-0 mt-2'):
                with ui.card().classes('p-3'):
                    ui.label('Priorities').classes('text-sm font-medium mb-1')
                    comp = _field_row('Priority.B2SLegacyDMD')
                    _bind_input(store, comp, SCOREVIEW_FIELDS['Priority.B2SLegacyDMD'])
                    comp = _field_row('Priority.ScoreView')
                    _bind_input(store, comp, SCOREVIEW_FIELDS['Priority.ScoreView'])

    # Bind of Enable from ScoreView plugin
    enable_field = PLUGIN_ENABLE_FIELDS['ScoreView']
    def _toggle(on: bool):
        _set_visible(options_holder, on)
    _bind_switch_enable(store, sw, enable_field, on_toggle=_toggle)
    _toggle(sw.value if hasattr(sw, 'value') else False)

def _dof_controller_block(store: IniStore):
    """Extra block: routing options in [Controller], visible only when Plugin.DOF.Enable = 1."""
    holder = ui.column().classes('w-full')

    # content (expansion with a 3-column grid, options per card)
    with holder:
        exp = ui.expansion('Controller routing (DOF)', icon='tune', value=False).classes('w-full')
        with exp:
            with ui.grid(columns=3).classes('w-full gap-0'):
                for label, sec_opt in DOF_CONTROLLER_FIELDS.items():
                    with ui.card().classes('p-3'):
                        ui.label(label).classes('text-sm font-medium mb-1')
                        sel = ui.select(options=[]).props('dense').classes('w-full')
                        _bind_indexed_select(store, sel, sec_opt, DOF_ROUTING_OPTIONS)

    # Visibility tied to DOF Enable (no new switch; subscribed via store)
    sec, opt = PLUGIN_ENABLE_FIELDS['DOF']
    def _apply_visibility(val: str):
        on = str(val).strip().lower() in ('1', 'true', 'on', 'yes')
        _set_visible(holder, on)

    # Initial state + subscribe for reloads and changes
    _apply_visibility(store.get(sec, opt))
    store.on_change(sec, opt, _apply_visibility)


# ---------------- Tab API ----------------

def create_tab():
    return ui.tab('Plugins', icon='extension')

def render_panel(tab, store: IniStore):
    with ui.tab_panel(tab):
        ui.label('Plugins').classes('text-xl font-semibold')

        # Render order based on schema keys (or define a fixed list)
        order = [
            'AlphaDMD', 'B2S', 'B2SLegacy', 'DMDUtil', 'DOF', 'FlexDMD',
            'PinMAME', 'PUP', 'RemoteControl', 'Serum', 'ScoreView', 'WMP',
        ]

        for name in order:
            if name == 'ScoreView':
                # special case: options in [ScoreView]
                _scoreview_block(store)
            elif name == 'DOF':                     # << add extra block here
                enable_field = PLUGIN_ENABLE_FIELDS.get(name)
                option_pairs = PLUGIN_OPTIONS.get(name, [])
                _plugin_line(store, name, enable_field, option_pairs)
                _dof_controller_block(store)        # << add the extra block
            else:
                enable_field = PLUGIN_ENABLE_FIELDS.get(name)
                option_pairs = PLUGIN_OPTIONS.get(name, [])
                # option_pairs is a list of (section, option); pass through
                _plugin_line(store, name, enable_field, option_pairs)

            ui.separator().classes('my-2')
