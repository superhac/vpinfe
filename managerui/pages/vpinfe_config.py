from nicegui import ui
from common.iniconfig import IniConfig
from common.vpxcollections import VPXCollections
from pathlib import Path
from platformdirs import user_config_dir

CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
INI_PATH = CONFIG_DIR / 'vpinfe.ini'
COLLECTIONS_PATH = CONFIG_DIR / 'collections.ini'
config = IniConfig(str(INI_PATH))


def _get_collection_names():
    """Get list of collection names for the dropdown."""
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        return [''] + collections.get_collections_name()  # Empty option + all collections
    except Exception:
        return ['']

# Sections to ignore
IGNORED_SECTIONS = {'VPSdb'}

# Icons for each section (fallback to 'settings' if not defined)
SECTION_ICONS = {
    'Settings': 'folder_open',
    'Input': 'sports_esports',
    'Logger': 'terminal',
    'Media': 'perm_media',
    'Displays': 'monitor',
}

def render_panel(tab=None):
    # Add custom styles for config page
    ui.add_head_html('''
    <style>
        .config-card {
            background: linear-gradient(145deg, #1e293b 0%, #152238 100%) !important;
            border: 1px solid #334155 !important;
            border-radius: 12px !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2) !important;
            transition: all 0.2s ease !important;
        }
        .config-card:hover {
            border-color: #3b82f6 !important;
            box-shadow: 0 8px 12px -2px rgba(59, 130, 246, 0.15) !important;
        }
        .config-card-header {
            background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
            margin: -16px -16px 16px -16px;
            padding: 12px 16px;
            border-radius: 12px 12px 0 0;
        }
        .config-input .q-field__control {
            background: #1a2744 !important;
            border-radius: 8px !important;
        }
        .config-input .q-field__label {
            color: #94a3b8 !important;
        }
        .q-tab-panels {
            background: #0d1a2d !important;
        }
        .q-tab-panel {
            background: #0d1a2d !important;
        }
    </style>
    ''')

    # Dictionary to store all input references: {section: {key: input_element}}
    inputs = {}

    # Get all sections, filter out ignored ones
    sections = [s for s in config.config.sections() if s not in IGNORED_SECTIONS]

    def save_config():
        for section, keys in inputs.items():
            for key, inp in keys.items():
                config.config.set(section, key, inp.value)
        with open(INI_PATH, 'w') as f:
            config.config.write(f)
        ui.notify('Configuration Saved', type='positive')

    with ui.column().classes('w-full'):
        # Header card
        with ui.card().classes('w-full mb-6').style(
            'background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); '
            'border-radius: 12px;'
        ):
            with ui.row().classes('w-full items-center p-4 gap-3'):
                ui.icon('tune', size='32px').classes('text-white')
                ui.label('VPinFE Configuration').classes('text-2xl font-bold text-white')

        # Tabs for each section - all on one row
        with ui.tabs().classes('w-full').props('inline-label dense') as tabs:
            for section in sections:
                icon = SECTION_ICONS.get(section, 'settings')
                ui.tab(section, label=section, icon=icon)

        # Tab panels with content
        with ui.tab_panels(tabs, value=sections[0] if sections else None).classes('w-full'):
            for section in sections:
                with ui.tab_panel(section):
                    inputs[section] = {}

                    with ui.card().classes('config-card p-4 w-full'):
                        options = config.config.options(section)

                        with ui.column().classes('gap-3'):
                            for key in options:
                                value = config.config.get(section, key, fallback='')

                                # Special handling for startup_collection in Settings
                                if section == 'Settings' and key == 'startup_collection':
                                    collection_options = _get_collection_names()
                                    # Ensure current value is in options
                                    if value and value not in collection_options:
                                        collection_options.append(value)
                                    inp = ui.select(
                                        label=key,
                                        options=collection_options,
                                        value=value
                                    ).classes('config-input').style('min-width: 200px;')
                                else:
                                    # Calculate width: 10% bigger than content, minimum 100px
                                    char_width = max(len(value), len(key), 5)  # at least 5 chars
                                    width_px = int(char_width * 10 * 1.1)  # ~10px per char, +10%
                                    width_px = max(width_px, 100)  # minimum 100px
                                    inp = ui.input(key, value=value).classes('config-input').style(f'width: {width_px}px;')
                                inputs[section][key] = inp

        # Save button
        with ui.row().classes('w-full justify-end mt-4'):
            ui.button('Save Changes', icon='save', on_click=save_config).props('color=primary rounded').classes('px-6')
