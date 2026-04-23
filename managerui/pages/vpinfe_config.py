import os
import io
import contextlib
import html
import logging
import re
import runpy
import shlex
import sys
from urllib.parse import quote
from nicegui import ui, run
from common.iniconfig import IniConfig
from common.dof_service import clear_active_dof_event, find_dof_file, send_dof_event_token
from common.vpinplay_service import sync_installed_tables
from common.launcher import build_masked_tableini_path, build_vpx_launch_command
from common.vpxcollections import VPXCollections
from pathlib import Path
from platformdirs import user_config_dir
from screeninfo import get_monitors


logger = logging.getLogger("vpinfe.manager.vpinfe_config")

CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
INI_PATH = CONFIG_DIR / 'vpinfe.ini'
COLLECTIONS_PATH = CONFIG_DIR / 'collections.ini'
VPINPLAY_BASE_URL = 'https://www.vpinplay.com/'

# Sections to ignore
IGNORED_SECTIONS = {
    'VPSdb',
    'pinmame-score-parser',
}

# Icons for each section (fallback to 'settings' if not defined)
SECTION_ICONS = {
    'Settings': 'folder_open',
    'Input': 'sports_esports',
    'Logger': 'terminal',
    'Media': 'perm_media',
    'Displays': 'monitor',
    'DOF': 'key',
    'libdmdutil': 'developer_board',
    'vpinplay': 'science',
}

SECTION_DESCRIPTIONS = {
    'Settings': 'Core paths, startup behavior, and theme defaults.',
    'Displays': 'Monitor assignments and playfield orientation settings.',
    'Input': 'Controller and input-related preferences.',
    'Logger': 'Verbosity, console logging, and quick log access.',
    'Media': 'Default media handling and fallback asset preferences.',
    'Network': 'Ports and services used by the local frontend stack.',
    'Mobile': 'Connection details for external mobile devices.',
    'DOF': 'Direct Output Framework integration and sync tools.',
    'libdmdutil': 'libdmdutil integration settings for DMD device support.',
    'VPinPlay': 'VPinPlay Experimental',
}

# Dictionary for explicit user-friendly name mappings
FRIENDLY_NAMES = {
    # [Settings]
    'vpxbinpath': 'VPX Executable Path',
    'vpxlaunchenv': 'VPX Launch Environment',
    'globalinioverride': 'Global ini Override (/home/test/mysuper.ini)',
    'globaltableinioverrideenabled': 'Global tableini Override Enabled',
    'globaltableinioverridemask': 'Global tableini Override Mask',
    'vpxinipath' : 'VPX Ini Path',
    'tablerootdir': 'Tables Directory',
    'startup_collection': 'Startup Collection',
    'autoupdatemediaonstartup': 'Auto Update Media On Startup',
    'splashscreen': 'Enable splashscreen',
    'muteaudio': 'Mute Frontend Audio',
    'mmhidequitbutton': 'Hide Quit from MainMenu',
    'enabledof': 'Enable DOF',
    'dofconfigtoolapikey': 'DOF Config Tool API Key',
    'enabled': 'Enabled',
    'pin2dmdenabled': 'Enable',
    'pixelcadedevice': 'PixelcadeDevice',
    'zedmddevice': 'ZeDMDDevice',
    'zedmdwifiaddr': 'ZeDMDWiFiAddr',
    'theme': 'Active Theme',
    'level': 'Log Verbosity',
    'console': 'Console Logging',

    # [Displays]
    'tablescreenid': 'Playfield Monitor ID',
    'bgscreenid': 'Backglass Monitor ID',
    'dmdscreenid': 'DMD Monitor ID',
    'bgwindowoverride': 'Backglass Window Override (x,y,width,height)',
    'dmdwindowoverride': 'DMD Window Override (x,y,width,height)',
    'tablerotation': 'Playfield Rotation (0/90/270)',
    'tableorientation': 'Playfield Orientation (Landscape/Portrait)',
    'playfieldorientation': 'Playfield Orientation (Landscape/Portrait)',
    'cabmode': 'Cabinet Mode',

    # [Network]
    'http_port': 'Web Server Port',
    'themeassetsport': 'Theme Server Port',
    'manageruiport': 'Manager UI Port',
    'startup_collection': 'Default Startup Collection',
    # [Mobile]
    'deviceip': 'Mobile Device IP',
    'deviceport': 'Mobile Device Port',
    'chunksize': 'Mobile Chunk Size',
    'renamemasktodefaultini': 'Enable Rename Mask To Default INI',
    'renamemasktodefaultinimask': 'Rename Mask To Default INI Mask',
    # [Input]
    'keyleft': 'Keyboard Left',
    'keyright': 'Keyboard Right',
    'keyup': 'Keyboard Up',
    'keydown': 'Keyboard Down',
    'keyselect': 'Keyboard Select',
    'keymenu': 'Keyboard Menu',
    'keyback': 'Keyboard Back',
    'joyleft': 'Gamepad Left',
    'joyright': 'Gamepad Right',
    'joyup': 'Gamepad Up',
    'joydown': 'Gamepad Down',
    'joyselect': 'Gamepad Select',
    'joymenu': 'Gamepad Menu',
    'joyback': 'Gamepad Back',
    'joytutorial': 'Gamepad Tutorial',
    'keytutorial': 'Keyboard Tutorial',
    'joyexit': 'Gamepad Exit',
    'keyexit': 'Keyboard Exit',
    'joycollectionmenu': 'Gamepad Collection Menu',
    'keycollectionmenu': 'Keyboard Collection Menu',
    # [vpinplay]
    'synconexit': 'Sync on Exit',
    'apiendpoint': 'API Endpoint',
    'userid': 'User ID',
    'initials': 'Initials',
    'machineid': 'Machine ID',
    # [Media]
    'tabletype': 'Table Type',
    'tableresolution': 'Default Table Resolution',
    'tablevideoresolution': 'Default Table Video Resolution',
    'defaultmissingmediaimg': 'Default Missing Media Image',
    'thumbcachemaxmb': 'Thumbnail Cache Max (MB)',


}

def get_friendly_name(key: str) -> str:
    """Return an explicitly mapped friendly name, or cleanly format the raw key."""
    if key in FRIENDLY_NAMES:
        return FRIENDLY_NAMES[key]
    # Fallback: 'my_raw_key' becomes 'My Raw Key'
    return key.replace('_', ' ').title()


INPUT_MAPPING_ACTION_ORDER = [
    'left',
    'right',
    'up',
    'down',
    'select',
    'menu',
    'back',
    'exit',
    'collectionmenu',
    'tutorial',
]


def _sort_input_mapping_keys(keys: list[str], prefix: str) -> list[str]:
    ordered_keys: list[str] = []
    present_keys = set(keys)

    for action in INPUT_MAPPING_ACTION_ORDER:
        mapping_key = f'{prefix}{action}'
        if mapping_key in present_keys:
            ordered_keys.append(mapping_key)

    for key in keys:
        if key not in ordered_keys:
            ordered_keys.append(key)

    return ordered_keys

def _get_collection_names():
    """Get list of collection names for the dropdown."""
    try:
        collections = VPXCollections(str(COLLECTIONS_PATH))
        return [''] + collections.get_collections_name()  # Empty option + all collections
    except Exception:
        return ['']

def _get_installed_theme_names():
    """Get list of installed theme names."""
    themes = []
    themes_dir = CONFIG_DIR / 'themes'
    if themes_dir.is_dir():
        for entry in os.scandir(themes_dir):
            if entry.is_dir():
                themes.append(entry.name)
    return sorted(themes)

def _get_detected_displays():
    """Return monitor info in the same shape/IDs as the --listres CLI output."""
    detected = {
        'screeninfo': [],
        'nsscreen': [],
        'error': '',
    }

    try:
        monitors = get_monitors()
        detected['screeninfo'] = [{
            'id': f'Monitor {i}',
            'output': m.name,
            'x': m.x,
            'y': m.y,
            'width': m.width,
            'height': m.height,
        } for i, m in enumerate(monitors)]
    except Exception as e:
        detected['error'] = str(e)
        return detected

    if sys.platform == 'darwin':
        try:
            from frontend.chromium_manager import get_mac_screens
            detected['nsscreen'] = [{
                'id': f'Screen {i}',
                'x': s.x,
                'y': s.y,
                'width': s.width,
                'height': s.height,
            } for i, s in enumerate(get_mac_screens())]
        except Exception:
            pass

    return detected

def _get_display_id_options(detected_displays, current_value: str = ''):
    """Build dropdown options for monitor ID fields: empty + 0..(max detected-1)."""
    options = ['']
    count = len(detected_displays.get('screeninfo', []))
    options.extend(str(i) for i in range(count))

    current = (current_value or '').strip()
    if current and current not in options:
        options.append(current)
    return options


def _get_logger_level_options(current_value: str = ''):
    options = ['debug', 'info', 'warning', 'error', 'critical']
    current, _, _ = _split_logger_level_value(current_value)
    if current and current not in options:
        options.append(current)
    return options


def _get_uniform_field_width_ch(values: list[str], minimum: int = 30, padding: int = 2) -> int:
    longest = max((len(str(value or '').strip()) for value in values), default=0)
    return max(minimum, longest + padding)


def _split_logger_level_value(raw_value: str | None) -> tuple[str, bool, bool]:
    include_thirdparty = False
    include_windows = False
    level = 'info'
    tokens = [token.strip().lower() for token in re.split(r"[|,]", str(raw_value or '')) if token.strip()]
    for token in tokens:
        if token == 'thirdparty':
            include_thirdparty = True
            continue
        if token == 'windows':
            include_windows = True
            continue
        level = token
    return level, include_thirdparty, include_windows


def _get_ledcontrol_command(script_path: Path, api_key: str, force: bool) -> list[str]:
    """Build the displayed ledcontrol_pull command."""
    api_key = api_key.strip()
    if not api_key:
        raise ValueError('DOF Config Tool API Key is required.')

    command = [str(script_path), '--apikey', api_key]
    if force:
        command.append('--force')
    return command


def _run_ledcontrol_pull(script_path: Path, api_key: str, force: bool) -> tuple[int, str, list[str]]:
    command = _get_ledcontrol_command(script_path, api_key, force)
    old_env = os.environ.copy()
    env = old_env.copy()
    script_dir = str(script_path.parent)
    if sys.platform.startswith('linux'):
        env['LD_LIBRARY_PATH'] = script_dir + os.pathsep + env.get('LD_LIBRARY_PATH', '')
    elif sys.platform == 'darwin':
        env['DYLD_LIBRARY_PATH'] = script_dir + os.pathsep + env.get('DYLD_LIBRARY_PATH', '')
    elif sys.platform == 'win32':
        env['PATH'] = script_dir + os.pathsep + env.get('PATH', '')

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    old_cwd = os.getcwd()
    old_argv = sys.argv[:]
    old_sys_path = sys.path[:]

    os.environ.update(env)
    sys.path.insert(0, script_dir)
    sys.argv = command[:]

    exit_code = 0
    try:
        os.chdir(script_dir)
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            try:
                runpy.run_path(str(script_path), run_name='__main__')
            except SystemExit as e:
                if isinstance(e.code, int):
                    exit_code = e.code
                elif e.code is None:
                    exit_code = 0
                else:
                    exit_code = 1
                    logger.error("%s", e.code)
    finally:
        os.chdir(old_cwd)
        sys.argv = old_argv
        sys.path[:] = old_sys_path
        os.environ.clear()
        os.environ.update(old_env)

    output = stdout_buffer.getvalue()
    stderr_output = stderr_buffer.getvalue()
    if stderr_output:
        if output and not output.endswith('\n'):
            output += '\n'
        output += stderr_output
    return exit_code, output.strip() or '(no output)', command


def show_log_file_dialog() -> None:
    log_path = CONFIG_DIR / 'vpinfe.log'
    try:
        content = log_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        content = '(log file not found)'
    except Exception as exc:
        content = f'Failed to read log file: {exc}'
    escaped_content = html.escape(content)

    with ui.dialog().props('persistent max-width=1100px') as dlg, ui.card().classes('w-full').style(
        'background: var(--surface); border: 1px solid var(--line); min-width: min(92vw, 1000px); height: 82vh;'
    ):
        with ui.column().classes('w-full h-full gap-3'):
            ui.label('VPinFE Log').classes('text-xl font-bold').style('color: var(--ink) !important;')
            ui.label(str(log_path)).classes('text-xs break-all').style('color: var(--ink-muted) !important;')
            with ui.scroll_area().classes('w-full').style(
                'flex: 1 1 auto; min-height: 0; border: 1px solid var(--neon-purple); border-radius: 8px; background: var(--surface);'
            ):
                ui.html(
                    f'<pre style="margin:0; padding:12px; white-space:pre-wrap; word-break:break-word; '
                    f'font-family:monospace; font-size:12px; color:var(--ink);">{escaped_content}</pre>'
                ).classes('w-full')
        with ui.row().classes('w-full justify-end mt-2'):
            ui.button('Close', on_click=dlg.close).style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;')
    dlg.open()

def render_panel(tab=None):
    # Re-read config from disk each time the page is opened
    config = IniConfig(str(INI_PATH))
    detected_displays = _get_detected_displays()

    # Add custom styles for config page
    ui.add_head_html('''
    <style>
        .config-page-shell {
            gap: 1.25rem;
        }
        .config-hero {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: var(--radius);
            box-shadow: 0 18px 40px var(--shadow);
        }
        .config-hero-kicker {
            font-size: 0.7rem;
            text-transform: uppercase;
            color: var(--ink);
            font-weight: 700;
        }
        .config-uppercase-input input {
            text-transform: uppercase !important;
        }
        .config-tabs {
            gap: 0.6rem;
            padding: 0.3rem 0.2rem 0.2rem;
        }
        .config-tabs .q-tabs__content {
            gap: 0.6rem;
            flex-wrap: wrap;
        }
        .config-tabs .q-tab {
            min-height: 46px;
            border-radius: 999px;
            padding: 0 16px;
            background: var(--surface-soft);
            border: 1px solid var(--line);
            color: var(--ink);
            transition: all 0.2s ease;
        }
        .config-tabs .q-tab--active {
            background: var(--surface);
            border-color: var(--neon-purple);
            box-shadow: 0 8px 20px var(--shadow);
        }
        .config-tabs .q-tab__label {
            font-weight: 700;
        }
        .config-panel-shell {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: var(--radius);
            padding: 1.2rem;
        }
        .config-section-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 1rem;
            padding: 1rem 1.1rem;
            border-radius: 14px;
            background: var(--surface-2);
            border: 1px solid var(--line);
        }
        .config-section-title {
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--ink);
        }
        .config-section-description {
            font-size: 0.9rem;
            color: var(--ink-muted);
        }
        .config-card {
            background: var(--surface-2) !important;
            border: 1px solid var(--line) !important;
            border-radius: var(--radius) !important;
            box-shadow: 0 12px 30px var(--glow-purple) !important;
            transition: all 0.2s ease !important;
        }
        .config-card:hover {
            border-color: var(--neon-purple) !important;
            box-shadow: 0 8px 12px -2px var(--glow-purple) !important;
        }
        .config-form-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 1rem;
            align-items: start;
        }
        .config-display-form-grid {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 1rem;
            align-items: start;
        }
        .config-settings-form-grid {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 3fr);
            gap: 1rem;
            align-items: start;
        }
        .config-vpinplay-pair {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 1rem;
            align-items: start;
        }
        .config-vpinplay-links {
            display: flex;
            align-items: center;
            gap: 1.25rem;
            flex-wrap: wrap;
        }
        .config-vpinplay-links-copy {
            display: flex;
            flex-direction: column;
            gap: 0.45rem;
            min-width: 180px;
        }
        .config-three-column-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 1rem;
            align-items: start;
        }
        .config-input-panel-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 1rem;
            align-items: start;
        }
        .config-display-column {
            display: grid;
            gap: 1rem;
            align-content: start;
        }
        .config-paths-list {
            display: grid;
            gap: 1rem;
            align-content: start;
            width: 100%;
        }
        .config-path-field-shell {
            width: min(100%, var(--path-field-width, 30ch));
            max-width: 100%;
            display: block;
        }
        .config-paths-list .config-field-card,
        .config-paths-list .config-input,
        .config-paths-list .q-field,
        .config-paths-list .q-field__control {
            width: 100% !important;
            max-width: 100% !important;
        }
        .config-paths-list .q-field__native,
        .config-paths-list input,
        .config-paths-list textarea {
            min-width: 0 !important;
            width: 100% !important;
            max-width: 100% !important;
            font-family: monospace !important;
        }
        .config-main-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.9fr);
            gap: 1rem;
            align-items: start;
        }
        .config-inline-pair {
            display: grid;
            grid-template-columns: minmax(220px, 0.9fr) minmax(0, 1.6fr);
            gap: 0.75rem;
            align-items: start;
        }
        .config-launch-layout {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 1rem;
            align-items: start;
        }
        .config-launch-preview-box {
            display: grid;
            gap: 0.75rem;
            align-content: start;
        }
        .config-launch-preview-full {
            grid-column: 1 / -1;
        }
        .config-field-card {
            padding: 0.95rem 1rem;
            border-radius: 14px;
            background: var(--surface-soft);
            border: 1px solid var(--line);
        }
        .config-field-card.compact {
            display: flex;
            align-items: center;
            min-height: 76px;
        }
        .config-field-label {
            margin-bottom: 0.45rem;
            font-size: 0.82rem;
            font-weight: 700;
            letter-spacing: 0.01em;
            color: var(--ink);
        }
        .config-input {
            width: 100%;
        }
        .config-input .q-field__control {
            background: var(--surface) !important;
            border-radius: 8px !important;
        }
        .config-input .q-field__native,
        .config-input input,
        .config-input .q-field__input {
            color: var(--ink-muted) !important;
        }
        .config-input .q-field__label {
            color: var(--ink) !important;
        }
        .config-input-env {
            width: 100%;
        }
        .config-input-env .q-field__control,
        .config-input-env .q-field__native,
        .config-input-env textarea {
            min-height: 12rem !important;
        }
        .config-input .q-checkbox__label {
            color: var(--ink) !important;
            font-weight: 600;
        }
        .config-side-card {
            border-radius: 16px;
            background: var(--surface-2);
            border: 1px solid var(--line);
            box-shadow: inset 0 1px 0 var(--glow-purple), 0 10px 30px var(--shadow);
        }
        .config-display-item {
            padding: 0.75rem 0.85rem;
            border-radius: 12px;
            background: var(--surface-soft);
            border: 1px solid var(--neon-purple);
            color: var(--ink-muted);
        }
        .config-display-item strong {
            color: var(--ink);
        }
        .config-footer-bar {
            position: sticky;
            bottom: 0.75rem;
            z-index: 5;
            display: flex;
            justify-content: flex-end;
            padding-top: 0.25rem;
        }
        .q-tab-panels {
            background: transparent !important;
        }
        .q-tab-panel {
            background: transparent !important;
            padding: 0 !important;
        }
        @media (max-width: 960px) {
            .config-main-grid {
                grid-template-columns: 1fr;
            }
            .config-inline-pair {
                grid-template-columns: 1fr;
            }
            .config-launch-layout {
                grid-template-columns: 1fr;
            }
            .config-launch-preview-full {
                grid-column: auto;
            }
            .config-display-form-grid {
                grid-template-columns: 1fr;
            }
            .config-settings-form-grid {
                grid-template-columns: 1fr;
            }
            .config-three-column-grid {
                grid-template-columns: 1fr;
            }
            .config-input-panel-grid {
                grid-template-columns: 1fr;
            }
            .config-vpinplay-pair {
                grid-template-columns: 1fr;
            }
            .config-vpinplay-links {
                justify-content: center;
            }
            .config-vpinplay-links-copy {
                align-items: center;
                text-align: center;
            }
            .config-section-header {
                align-items: flex-start;
                flex-direction: column;
            }
        }
    </style>
    ''')

    # Dictionary to store all input references: {section: {key: input_element}}
    inputs = {}
    dof_force_checkbox = None
    update_dof_button = None
    dof_test_event_input = None
    sync_vpinplay_button = None
    launch_command_preview = None
    launch_env_preview = None
    vpinplay_user_link = None

    # Get all sections, filter out ignored ones
    sections = [s for s in config.config.sections() if s not in IGNORED_SECTIONS]
    launch_preview_keys = {
        ('Settings', 'vpxbinpath'),
        ('Settings', 'globalinioverride'),
        ('Settings', 'globaltableinioverrideenabled'),
        ('Settings', 'globaltableinioverridemask'),
        ('Settings', 'vpxlaunchenv'),
    }

    def _as_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')

    def _build_launch_preview_text() -> tuple[str, str]:
        sample_vpx = 'A-Go-Go (Williams 1966).vpx'
        settings_inputs = inputs.get('Settings', {})

        vpxbin = str(
            getattr(settings_inputs.get('vpxbinpath'), 'value', config.config.get('Settings', 'vpxbinpath', fallback=''))
            or ''
        ).strip()
        global_ini_override = str(
            getattr(settings_inputs.get('globalinioverride'), 'value', config.config.get('Settings', 'globalinioverride', fallback=''))
            or ''
        ).strip()
        tableini_enabled = _as_bool(
            getattr(
                settings_inputs.get('globaltableinioverrideenabled'),
                'value',
                config.config.get('Settings', 'globaltableinioverrideenabled', fallback='false'),
            )
        )
        tableini_mask = str(
            getattr(
                settings_inputs.get('globaltableinioverridemask'),
                'value',
                config.config.get('Settings', 'globaltableinioverridemask', fallback=''),
            )
            or ''
        ).strip()
        launch_env = str(
            getattr(settings_inputs.get('vpxlaunchenv'), 'value', config.config.get('Settings', 'vpxlaunchenv', fallback=''))
            or ''
        ).strip()

        tableini_override = build_masked_tableini_path(sample_vpx, tableini_enabled, tableini_mask)
        launcher = vpxbin or '<VPX Executable Path>'
        command = build_vpx_launch_command(
            launcher_path=launcher,
            vpx_table_path=sample_vpx,
            global_ini_override=global_ini_override,
            tableini_override=tableini_override,
        )
        env_line = launch_env if launch_env else '(none)'
        return shlex.join(command), env_line

    def update_launch_preview():
        if launch_command_preview is None or launch_env_preview is None:
            return
        command_text, env_text = _build_launch_preview_text()
        launch_command_preview.value = command_text
        launch_env_preview.value = env_text

    def build_config_input(section: str, key: str, value: str):
        friendly_label = get_friendly_name(key)
        special_label_above = (
            (section == 'libdmdutil' and key == 'enabled')
            or (section == 'libdmdutil' and key == 'pin2dmdenabled')
        )
        is_checkbox = (
            (section == 'Settings' and key == 'autoupdatemediaonstartup')
            or (section == 'Displays' and key == 'cabmode')
            or (section == 'Logger' and key == 'console')
            or (section == 'Settings' and key == 'splashscreen')
            or (section == 'Settings' and key == 'muteaudio')
            or (section == 'Settings' and key == 'mmhidequitbutton')
            or (section == 'DOF' and key == 'enabledof')
            or (section == 'libdmdutil' and key == 'enabled')
            or (section == 'libdmdutil' and key == 'pin2dmdenabled')
            or (section == 'Settings' and key == 'globaltableinioverrideenabled')
            or (section == 'Mobile' and key == 'renamemasktodefaultini')
            or (section == 'vpinplay' and key == 'synconexit')
        )

        with ui.element('div').classes(
            'config-field-card compact' if is_checkbox and not special_label_above else 'config-field-card'
        ):
            label_widget = None
            if not is_checkbox or special_label_above:
                if section == 'libdmdutil' and key == 'enabled':
                    label_text = 'libdmdutil Service'
                elif section == 'libdmdutil' and key == 'pin2dmdenabled':
                    label_text = 'PIN2DMD'
                else:
                    label_text = friendly_label
                if section == 'Settings' and key == 'globaltableinioverridemask':
                    mask_value = (value or '').strip()
                    if mask_value:
                        label_text = (
                            f'{friendly_label} (Example: A-Go-Go (Williams 1966).{mask_value}.ini)'
                        )
                label_widget = ui.label(label_text).classes('config-field-label')

            if section == 'Settings' and key == 'startup_collection':
                collection_options = _get_collection_names()
                if value and value not in collection_options:
                    collection_options.append(value)
                inp = ui.select(
                    options=collection_options,
                    value=value
                ).props('outlined dense options-dense').classes('config-input')
            elif section == 'Settings' and key == 'vpxlaunchenv':
                inp = ui.textarea(
                    value=value,
                    placeholder='KEY=value KEY2="value with spaces"'
                ).props('outlined autogrow').classes('config-input config-input-env')
            elif section == 'Settings' and key == 'theme':
                theme_options = _get_installed_theme_names()
                if value and value not in theme_options:
                    theme_options.append(value)
                inp = ui.select(
                    options=theme_options,
                    value=value
                ).props('outlined dense options-dense').classes('config-input')
            elif is_checkbox:
                inp = ui.checkbox(
                    text='Enable' if special_label_above else friendly_label,
                    value=(value == "true")
                ).classes('config-input')
            elif section == 'Displays' and key in ('tablescreenid', 'bgscreenid', 'dmdscreenid'):
                monitor_options = _get_display_id_options(detected_displays, value)
                inp = ui.select(
                    options=monitor_options,
                    value=(value or '').strip()
                ).props('outlined dense options-dense').classes('config-input')
            elif section == 'Logger' and key == 'level':
                level_options = _get_logger_level_options(value)
                normalized, include_thirdparty, include_windows = _split_logger_level_value(value)
                inp = ui.select(
                    options=level_options,
                    value=normalized
                ).props('outlined dense options-dense').classes('config-input')
                thirdparty_inp = ui.checkbox(
                    text='Include thirdparty logs',
                    value=include_thirdparty,
                ).classes('config-input')
                windows_inp = ui.checkbox(
                    text='Include Windows logs',
                    value=include_windows,
                ).classes('config-input')
                inputs[section]['__thirdparty_included'] = thirdparty_inp
                inputs[section]['__windows_included'] = windows_inp
            else:
                inp = ui.input(value=value).props('outlined dense').classes('config-input')
                if section == 'vpinplay' and key == 'machineid':
                    inp.props('readonly disable')
                if section == 'Displays' and key in ('bgwindowoverride', 'dmdwindowoverride'):
                    inp.props('hint="Format: x,y,width,height"')
                    inp.tooltip(
                        'Optional high-DPI override passed to themes instead of the detected window bounds.'
                    )
                if section == 'Settings' and key == 'globaltableinioverridemask' and label_widget is not None:
                    def on_mask_change(e):
                        mask_value = (e.value or '').strip()
                        if mask_value:
                            label_widget.text = (
                                f'{friendly_label} (Example: A-Go-Go (Williams 1966).{mask_value}.ini)'
                            )
                        else:
                            label_widget.text = friendly_label
                    inp.on_value_change(on_mask_change)
                if section == 'vpinplay' and key == 'initials':
                    inp.props('maxlength=3').classes('config-uppercase-input')

                    def on_initials_change(e):
                        normalized = str(e.value or '').upper()
                        if inp.value != normalized:
                            inp.value = normalized
                        update_vpinplay_sync_button_state()

                    inp.on('input', on_initials_change)
                    inp.on_value_change(on_initials_change)

            inputs[section][key] = inp
            if (section, key) in launch_preview_keys:
                inp.on_value_change(lambda _: update_launch_preview())
            if section == 'vpinplay' and key == 'userid':
                inp.on_value_change(lambda _: update_vpinplay_sync_button_state())

    def save_config():
        for section, keys in inputs.items():
            for key, inp in keys.items():
                if key == '__thirdparty_included' or key == '__windows_included':
                    continue
                if section == 'Logger' and key == 'level':
                    level_value = str(inp.value or 'info').strip().lower() or 'info'
                    include_thirdparty = bool(getattr(inputs.get('Logger', {}).get('__thirdparty_included'), 'value', False))
                    include_windows = bool(getattr(inputs.get('Logger', {}).get('__windows_included'), 'value', False))
                    flags = []
                    if include_thirdparty:
                        flags.append('thirdparty')
                    if include_windows:
                        flags.append('windows')
                    if flags:
                        level_value = f"{level_value} | {' | '.join(flags)}"
                    config.config.set(section, key, level_value)
                    continue
                if type(inp.value) is bool:
                    config.config.set(section, key, str(inp.value).lower())
                else:
                    value = inp.value
                    if section == 'vpinplay' and key == 'initials':
                        value = str(value or '').upper()
                        inp.value = value
                    config.config.set(section, key, value)
        with open(INI_PATH, 'w') as f:
            config.config.write(f)
        update_vpinplay_sync_button_state()
        ui.notify('Configuration Saved', type='positive')

    def split_evenly(items: list[str], columns: int) -> list[list[str]]:
        if columns <= 1:
            return [items]
        size = (len(items) + columns - 1) // columns
        return [items[i * size:(i + 1) * size] for i in range(columns)]

    def show_command_output_dialog(title: str, command: list[str], output: str, exit_code: int | None):
        with ui.dialog().props('persistent max-width=1000px') as dlg, ui.card().classes('w-full').style(
            'background: var(--surface); border: 1px solid var(--line); min-width: min(92vw, 900px);'
        ):
            ui.label(title).classes('text-xl font-bold').style('color: var(--ink) !important;')
            ui.label(shlex.join(command)).classes('text-xs break-all').style('color: var(--ink-muted) !important;')
            if exit_code is not None:
                status_color = 'text-green-400' if exit_code == 0 else 'text-red-400'
                ui.label(f'Exit code: {exit_code}').classes(f'text-sm {status_color}')
            ui.textarea(value=output).props('readonly outlined').classes('w-full').style(
                'height: 420px; font-family: monospace;'
            )
            with ui.row().classes('w-full justify-end mt-2'):
                ui.button('Close', on_click=dlg.close).style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;')
        dlg.open()

    def show_live_command_dialog(title: str, command: list[str]):
        with ui.dialog().props('persistent max-width=1000px') as dlg, ui.card().classes('w-full').style(
            'background: var(--surface); border: 1px solid var(--line); min-width: min(92vw, 900px);'
        ):
            ui.label(title).classes('text-xl font-bold').style('color: var(--ink) !important;')
            command_label = ui.label(shlex.join(command)).classes('text-xs break-all').style('color: var(--ink-muted) !important;')
            status_label = ui.label('Running...').classes('text-sm').style('color: var(--neon-yellow) !important;')
            output_area = ui.textarea(value='Starting sync...').props('readonly outlined').classes('w-full').style(
                'height: 420px; font-family: monospace;'
            )
            with ui.row().classes('w-full justify-end mt-2'):
                close_button = ui.button('Close', on_click=dlg.close).style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;')
                close_button.disable()
        dlg.open()
        return command_label, status_label, output_area, close_button

    async def run_dof_online_update():
        api_key = str(
            getattr(inputs.get('DOF', {}).get('dofconfigtoolapikey'), 'value', '') or ''
        ).strip()
        force = bool(getattr(dof_force_checkbox, 'value', False))
        script_path = find_dof_file('ledcontrol_pull.py')

        if not api_key:
            ui.notify('DOF Config Tool API Key is required.', type='warning')
            return

        if script_path is None:
            show_command_output_dialog(
                'DOF Online Config Update',
                ['ledcontrol_pull.py', '--apikey', api_key] + (['--force'] if force else []),
                'Unable to locate ledcontrol_pull.py in the bundled DOF files.',
                None,
            )
            return

        update_dof_button.disable()
        update_dof_button.text = 'Running...'
        try:
            exit_code, output, command = await run.io_bound(
                _run_ledcontrol_pull, script_path, api_key, force
            )
            show_command_output_dialog('DOF Online Config Update', command, output, exit_code)
            if exit_code == 0:
                ui.notify('DOF update completed.', type='positive')
            else:
                ui.notify('DOF update failed. See command output.', type='negative')
        except Exception as e:
            command = ['ledcontrol_pull.py', '--apikey', api_key] + (['--force'] if force else [])
            show_command_output_dialog(
                'DOF Online Config Update',
                command,
                str(e),
                None,
            )
            ui.notify('Failed to start DOF update.', type='negative')
        finally:
            update_dof_button.text = 'Update DOF via Online Config Tool'
            update_dof_button.enable()

    async def run_dof_test_event_start():
        event_token = str(getattr(dof_test_event_input, 'value', '') or '').strip()
        if not event_token:
            ui.notify('Enter a DOF event like E900.', type='warning')
            return

        try:
            started = await run.io_bound(send_dof_event_token, config, event_token)
            if started:
                ui.notify(f'Started DOF event {event_token.strip().upper()}.', type='positive')
            else:
                ui.notify('DOF is disabled or unavailable.', type='warning')
        except ValueError as e:
            ui.notify(str(e), type='warning')
        except Exception as e:
            logger.exception("Failed to start DOF test event")
            ui.notify(f'Failed to start DOF event: {e}', type='negative')

    async def run_dof_test_event_stop():
        try:
            cleared = await run.io_bound(clear_active_dof_event, config)
            if cleared:
                ui.notify('Stopped active DOF event.', type='positive')
            else:
                ui.notify('No active DOF event to stop.', type='warning')
        except Exception as e:
            logger.exception("Failed to stop DOF test event")
            ui.notify(f'Failed to stop DOF event: {e}', type='negative')

    async def run_vpinplay_sync():
        vpinplay_inputs = inputs.get('vpinplay', {})
        settings_inputs = inputs.get('Settings', {})

        service_ip = str(
            getattr(vpinplay_inputs.get('apiendpoint'), 'value', config.config.get('vpinplay', 'apiendpoint', fallback=''))
            or ''
        ).strip()
        user_id = str(
            getattr(vpinplay_inputs.get('userid'), 'value', config.config.get('vpinplay', 'userid', fallback=''))
            or ''
        ).strip()
        initials = str(
            getattr(vpinplay_inputs.get('initials'), 'value', config.config.get('vpinplay', 'initials', fallback=''))
            or ''
        ).strip()
        machine_id = str(
            getattr(vpinplay_inputs.get('machineid'), 'value', config.config.get('vpinplay', 'machineid', fallback=''))
            or ''
        ).strip()
        tables_dir = str(
            getattr(settings_inputs.get('tablerootdir'), 'value', config.config.get('Settings', 'tablerootdir', fallback=''))
            or ''
        ).strip()

        if not service_ip:
            ui.notify('API Endpoint is required.', type='warning')
            return
        if not user_id:
            ui.notify('User ID is required.', type='warning')
            return
        if not initials:
            ui.notify('Initials is required.', type='warning')
            return
        if not machine_id:
            ui.notify('Machine ID is required.', type='warning')
            return
        if not tables_dir:
            ui.notify('Tables Directory is required in Settings.', type='warning')
            return

        command_label, status_label, output_area, close_button = show_live_command_dialog(
            'VPinPlay Sync',
            ['POST', service_ip],
        )
        sync_vpinplay_button.disable()
        sync_vpinplay_button.text = 'Syncing...'
        try:
            result = await run.io_bound(
                sync_installed_tables,
                service_ip,
                user_id,
                initials,
                machine_id,
                tables_dir,
            )
            summary = (
                f"Scanned: {result['tables_scanned']}\n"
                f"Sent: {result['tables_sent']}\n"
                f"Skipped (missing VPSId): {result['tables_skipped']}\n\n"
                f"HTTP status: {result['status_code']}\n\n"
                f"{result['response_body']}"
            )
            command_label.text = shlex.join(['POST', result['endpoint']])
            status_label.text = f"Exit code: {0 if result['ok'] else 1}"
            output_area.value = summary
            if result['ok']:
                ui.notify('Sync completed.', type='positive')
            else:
                ui.notify('Sync failed. See output for details.', type='negative')
        except Exception as e:
            status_label.text = 'Failed to start sync.'
            output_area.value = str(e)
            ui.notify('Failed to start sync.', type='negative')
        finally:
            close_button.enable()
            sync_vpinplay_button.text = 'Sync Installed Tables'
            update_vpinplay_sync_button_state()

    def _get_vpinplay_user_id_value() -> str:
        vpinplay_inputs = inputs.get('vpinplay', {})
        return str(
            getattr(vpinplay_inputs.get('userid'), 'value', config.config.get('vpinplay', 'userid', fallback=''))
            or ''
        ).strip()

    def _build_vpinplay_user_url(user_id: str) -> str:
        uid = (user_id or '').strip()
        if not uid:
            return f'{VPINPLAY_BASE_URL}players.html'
        return f'{VPINPLAY_BASE_URL}players.html?userid={quote(uid)}'

    def update_vpinplay_user_link():
        if vpinplay_user_link is None:
            return
        user_id = _get_vpinplay_user_id_value()
        user_url = _build_vpinplay_user_url(user_id)
        vpinplay_user_link.text = 'Your Stats'
        vpinplay_user_link.props(f'href={user_url}')

    def update_vpinplay_sync_button_state():
        if sync_vpinplay_button is None:
            return
        vpinplay_inputs = inputs.get('vpinplay', {})
        user_id = str(
            getattr(vpinplay_inputs.get('userid'), 'value', config.config.get('vpinplay', 'userid', fallback=''))
            or ''
        ).strip()
        initials = str(
            getattr(vpinplay_inputs.get('initials'), 'value', config.config.get('vpinplay', 'initials', fallback=''))
            or ''
        ).strip()
        if user_id and initials:
            sync_vpinplay_button.enable()
        else:
            sync_vpinplay_button.disable()

    with ui.column().classes('w-full config-page-shell'):
        with ui.card().classes('w-full config-hero').style('overflow: hidden;'):
            with ui.row().classes('w-full items-center justify-between p-6 gap-6'):
                with ui.row().classes('items-center gap-4'):
                    ui.icon('tune', size='34px').style('color: var(--ink) !important;')
                    with ui.column().classes('gap-1'):
                        ui.label('System Setup').classes('config-hero-kicker')
                        ui.label('VPinFE Configuration').classes('text-2xl font-bold').style('color: var(--ink) !important;')
                        ui.label(
                            'Organize display mapping, startup behavior, media, and service settings from one place.'
                        ).classes('text-sm').style('color: var(--neon-cyan) !important;')

        with ui.tabs().classes('w-full config-tabs').props(
            'inline-label dense active-color=white indicator-color=transparent'
        ) as tabs:
            for section in sections:
                icon = SECTION_ICONS.get(section, 'settings')
                ui.tab(section, label=section, icon=icon)

        with ui.tab_panels(tabs, value=sections[0] if sections else None).classes('w-full'):
            for section in sections:
                with ui.tab_panel(section):
                    inputs[section] = {}
                    options = config.config.options(section)
                    if section == 'Logger':
                        options = [key for key in options if key != 'file']

                    with ui.element('div').classes('config-panel-shell w-full'):
                        with ui.element('div').classes('config-section-header'):
                            with ui.row().classes('items-center gap-3'):
                                ui.icon(SECTION_ICONS.get(section, 'settings'), size='24px').style('color: var(--neon-cyan) !important;')
                                with ui.column().classes('gap-0'):
                                    ui.label(section).classes('config-section-title')
                                    ui.label(
                                        SECTION_DESCRIPTIONS.get(section, 'Configuration values for this section.')
                                    ).classes('config-section-description')
                            ui.label(f'{len(options)} setting{"s" if len(options) != 1 else ""}').classes('text-xs font-semibold').style('color: var(--ink-muted) !important;')

                        content_classes = 'config-main-grid' if section == 'Displays' else 'w-full'
                        with ui.element('div').classes(content_classes):
                            if section == 'Settings':
                                path_keys = [
                                    key for key in ('vpxbinpath', 'tablerootdir', 'vpxinipath')
                                    if key in options
                                ]
                                launch_keys = [
                                    key for key in (
                                        'vpxlaunchenv',
                                        'globalinioverride',
                                        'globaltableinioverrideenabled',
                                        'globaltableinioverridemask',
                                    )
                                    if key in options
                                ]
                                general_keys = [
                                    key for key in options
                                    if key not in set(path_keys + launch_keys)
                                ]
                                frontend_toggle_keys = [
                                    key for key in general_keys
                                    if key in ('autoupdatemediaonstartup', 'splashscreen', 'muteaudio', 'mmhidequitbutton')
                                ]
                                frontend_primary_keys = [
                                    key for key in general_keys
                                    if key not in frontend_toggle_keys
                                ]
                                path_field_width_ch = _get_uniform_field_width_ch([
                                    config.config.get(section, key, fallback='')
                                    for key in path_keys
                                ])

                                with ui.column().classes('w-full gap-4'):
                                    if path_keys:
                                        with ui.card().classes('config-side-card w-full p-4'):
                                            ui.label('Paths').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                            ui.label(
                                                'Set the main Visual Pinball executable, table location, and ini file.'
                                            ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                            with ui.element('div').classes('config-paths-list mt-3').style(
                                                f'--path-field-width: {path_field_width_ch}ch;'
                                            ):
                                                for key in path_keys:
                                                    value = config.config.get(section, key, fallback='')
                                                    with ui.element('div').classes('config-path-field-shell'):
                                                        build_config_input(section, key, value)

                                    if general_keys:
                                        with ui.card().classes('config-side-card w-full p-4'):
                                            ui.label('Frontend').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                            ui.label(
                                                'Configure startup behavior and frontend defaults.'
                                            ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                            with ui.element('div').classes('config-display-form-grid mt-3'):
                                                with ui.element('div').classes('config-display-column'):
                                                    for key in frontend_primary_keys:
                                                        value = config.config.get(section, key, fallback='')
                                                        build_config_input(section, key, value)
                                                with ui.element('div').classes('config-display-column'):
                                                    for key in frontend_toggle_keys:
                                                        value = config.config.get(section, key, fallback='')
                                                        build_config_input(section, key, value)

                                    if launch_keys:
                                        with ui.card().classes('config-side-card w-full p-4'):
                                            ui.label('Launch Overrides').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                            ui.label(
                                                'Optional launch-time environment and ini overrides for VPX startup.'
                                            ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                            with ui.element('div').classes('config-launch-layout mt-3'):
                                                with ui.element('div').classes('config-display-column'):
                                                    if 'vpxlaunchenv' in launch_keys:
                                                        value = config.config.get(section, 'vpxlaunchenv', fallback='')
                                                        build_config_input(section, 'vpxlaunchenv', value)

                                                    if 'globalinioverride' in launch_keys:
                                                        value = config.config.get(section, 'globalinioverride', fallback='')
                                                        build_config_input(section, 'globalinioverride', value)

                                                    if (
                                                        'globaltableinioverrideenabled' in launch_keys
                                                        or 'globaltableinioverridemask' in launch_keys
                                                    ):
                                                        with ui.element('div').classes('w-full config-inline-pair'):
                                                            if 'globaltableinioverrideenabled' in launch_keys:
                                                                value = config.config.get(
                                                                    section,
                                                                    'globaltableinioverrideenabled',
                                                                    fallback='false',
                                                                )
                                                                with ui.element('div').classes('w-full'):
                                                                    build_config_input(
                                                                        section,
                                                                        'globaltableinioverrideenabled',
                                                                        value,
                                                                    )
                                                            if 'globaltableinioverridemask' in launch_keys:
                                                                value = config.config.get(
                                                                    section,
                                                                    'globaltableinioverridemask',
                                                                    fallback='',
                                                                )
                                                                with ui.element('div').classes('w-full'):
                                                                    build_config_input(
                                                                        section,
                                                                        'globaltableinioverridemask',
                                                                        value,
                                                                    )

                                                with ui.element('div').classes('config-launch-preview-box'):
                                                    ui.label('VPinball Launch Comand w/Options').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                    ui.label(
                                                        'Preview uses sample table: A-Go-Go (Williams 1966).vpx'
                                                    ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                                    launch_command_preview = ui.textarea(
                                                        value='',
                                                    ).props('readonly outlined autogrow').classes('w-full').style(
                                                        'font-family: monospace;'
                                                    )

                                                with ui.element('div').classes('config-launch-preview-box config-launch-preview-full'):
                                                    ui.label('Launch environment overrides').classes('text-sm font-semibold').style('color: var(--ink-muted) !important;')
                                                    launch_env_preview = ui.textarea(
                                                        value='',
                                                    ).props('readonly outlined autogrow').classes('w-full').style(
                                                        'font-family: monospace;'
                                                    )
                                                    update_launch_preview()
                            else:
                                with ui.card().classes('config-card w-full p-4'):
                                    if section == 'Displays':
                                        split_key = 'tableorientation' if section == 'Displays' else 'theme'
                                        split_index = options.index(split_key) if split_key in options else len(options)
                                        first_column_keys = options[:split_index]
                                        second_column_keys = options[split_index:]
                                        override_keys = ['bgwindowoverride', 'dmdwindowoverride']
                                        present_override_keys = []

                                        for override_key in override_keys:
                                            if override_key in first_column_keys:
                                                first_column_keys.remove(override_key)
                                                present_override_keys.append(override_key)
                                            elif override_key in second_column_keys:
                                                second_column_keys.remove(override_key)
                                                present_override_keys.append(override_key)

                                        monitor_anchor_keys = ['tablescreenid', 'bgscreenid', 'dmdscreenid']
                                        insert_after = max(
                                            (first_column_keys.index(key) for key in monitor_anchor_keys if key in first_column_keys),
                                            default=-1,
                                        )
                                        first_column_keys[insert_after + 1:insert_after + 1] = present_override_keys

                                        with ui.element('div').classes('config-display-form-grid'):
                                            with ui.element('div').classes('config-display-column'):
                                                for key in first_column_keys:
                                                    value = config.config.get(section, key, fallback='')
                                                    build_config_input(section, key, value)
                                            with ui.element('div').classes('config-display-column'):
                                                for key in second_column_keys:
                                                    value = config.config.get(section, key, fallback='')
                                                    build_config_input(section, key, value)
                                    elif section == 'Input':
                                        controller_keys = _sort_input_mapping_keys(
                                            [key for key in options if key.startswith('joy')],
                                            'joy',
                                        )
                                        keyboard_keys = _sort_input_mapping_keys(
                                            [key for key in options if key.startswith('key')],
                                            'key',
                                        )
                                        other_input_keys = [
                                            key for key in options
                                            if key not in set(controller_keys + keyboard_keys)
                                        ]

                                        with ui.column().classes('w-full gap-4'):
                                            with ui.card().classes('config-side-card w-full p-4'):
                                                ui.label('Controller Mappings').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                ui.label(
                                                    'Assign gamepad button indexes for each frontend action.'
                                                ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                                with ui.element('div').classes('config-input-panel-grid mt-3'):
                                                    for key in controller_keys:
                                                        value = config.config.get(section, key, fallback='')
                                                        build_config_input(section, key, value)

                                            with ui.card().classes('config-side-card w-full p-4'):
                                                ui.label('Keyboard Mappings').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                ui.label(
                                                    'Set comma-separated keyboard bindings used only by the VPinFE frontend.'
                                                ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                                with ui.element('div').classes('config-input-panel-grid mt-3'):
                                                    for key in keyboard_keys:
                                                        value = config.config.get(section, key, fallback='')
                                                        build_config_input(section, key, value)

                                        if other_input_keys:
                                            with ui.card().classes('config-side-card w-full mt-4 p-4'):
                                                ui.label('Additional Input Settings').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                with ui.element('div').classes('config-form-grid mt-3'):
                                                    for key in other_input_keys:
                                                        value = config.config.get(section, key, fallback='')
                                                        build_config_input(section, key, value)
                                    elif section == 'Mobile':
                                        rename_enabled_key = 'renamemasktodefaultini'
                                        rename_mask_key = 'renamemasktodefaultinimask'
                                        normal_mobile_options = [
                                            key for key in options
                                            if key not in (rename_enabled_key, rename_mask_key)
                                        ]
                                        with ui.element('div').classes('config-form-grid'):
                                            for key in normal_mobile_options:
                                                value = config.config.get(section, key, fallback='')
                                                build_config_input(section, key, value)
                                        if rename_enabled_key in options or rename_mask_key in options:
                                            with ui.element('div').classes('config-field-card mt-3'):
                                                with ui.column().classes('w-full gap-3'):
                                                    if rename_enabled_key in options:
                                                        value = config.config.get(section, rename_enabled_key, fallback='false')
                                                        inp = ui.checkbox(
                                                            text=get_friendly_name(rename_enabled_key),
                                                            value=(value == "true")
                                                        ).classes('config-input')
                                                        inputs[section][rename_enabled_key] = inp
                                                    if rename_mask_key in options:
                                                        value = config.config.get(section, rename_mask_key, fallback='')
                                                        ui.label(get_friendly_name(rename_mask_key)).classes('config-field-label')
                                                        inp = ui.input(value=value).props('outlined dense').classes('config-input')
                                                        inputs[section][rename_mask_key] = inp
                                    elif section == 'vpinplay':
                                        sync_key = 'synconexit'
                                        endpoint_key = 'apiendpoint'
                                        user_key = 'userid'
                                        initials_key = 'initials'
                                        machine_key = 'machineid'
                                        with ui.element('div').classes('config-vpinplay-pair'):
                                            with ui.column().classes('w-full gap-3'):
                                                with ui.element('div').classes('w-full config-field-card'):
                                                    with ui.element('div').classes('w-full config-vpinplay-links'):
                                                        ui.image('/static/img/VPinPlay_Logo_1.0.png').style(
                                                            'width: 200px; height: 200px; object-fit: contain;'
                                                        )
                                                        with ui.column().classes('config-vpinplay-links-copy'):
                                                            ui.link(
                                                                'VPinPlay Home',
                                                                VPINPLAY_BASE_URL,
                                                                new_tab=True,
                                                            ).style('color: var(--neon-cyan) !important;')
                                                            vpinplay_user_link = ui.link(
                                                                '',
                                                                _build_vpinplay_user_url(
                                                                    config.config.get(section, user_key, fallback='')
                                                                ),
                                                                new_tab=True,
                                                            ).style('color: var(--neon-cyan) !important;')
                                                        update_vpinplay_user_link()

                                                if endpoint_key in options:
                                                    with ui.element('div').classes('w-full'):
                                                        value = config.config.get(section, endpoint_key, fallback='')
                                                        build_config_input(section, endpoint_key, value)

                                                with ui.element('div').classes('config-vpinplay-pair'):
                                                    if user_key in options:
                                                        with ui.element('div').classes('w-full'):
                                                            value = config.config.get(section, user_key, fallback='')
                                                            build_config_input(section, user_key, value)
                                                            user_input = inputs.get(section, {}).get(user_key)
                                                            if user_input is not None:
                                                                user_input.on_value_change(lambda _: update_vpinplay_user_link())
                                                    if initials_key in options:
                                                        with ui.element('div').classes('w-full'):
                                                            value = config.config.get(section, initials_key, fallback='')
                                                            build_config_input(section, initials_key, value)

                                                with ui.element('div').classes('config-vpinplay-pair'):
                                                    if machine_key in options:
                                                        with ui.element('div').classes('w-full'):
                                                            value = config.config.get(section, machine_key, fallback='')
                                                            build_config_input(section, machine_key, value)

                                                for key in options:
                                                    if key in (sync_key, endpoint_key, user_key, initials_key, machine_key):
                                                        continue
                                                    value = config.config.get(section, key, fallback='')
                                                    build_config_input(section, key, value)

                                            with ui.column().classes('w-full gap-3'):
                                                with ui.card().classes('config-side-card w-full p-4'):
                                                    ui.label('Table Metadata Sync').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                    ui.label(
                                                        'Sends installed table metadata to the configured VPinPlay service endpoint.'
                                                    ).classes('text-sm text-slate-300')
                                                    sync_vpinplay_button = ui.button(
                                                        'Sync Installed Tables',
                                                        icon='sync',
                                                        on_click=run_vpinplay_sync,
                                                    ).classes('mt-3').style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;')
                                                    update_vpinplay_sync_button_state()
                                                if sync_key in options:
                                                    with ui.element('div').classes('w-full'):
                                                        value = config.config.get(section, sync_key, fallback='false')
                                                        build_config_input(section, sync_key, value)
                                    elif section == 'DOF':
                                        with ui.element('div').classes('config-vpinplay-pair'):
                                            with ui.column().classes('w-full gap-3'):
                                                with ui.card().classes('config-side-card w-full p-4'):
                                                    ui.label('DOF Settings').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                    ui.label(
                                                        'Configure frontend DOF support and the online config tool API key.'
                                                    ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                                    with ui.element('div').classes('config-form-grid mt-3'):
                                                        for key in options:
                                                            value = config.config.get(section, key, fallback='')
                                                            build_config_input(section, key, value)
                                            with ui.column().classes('w-full gap-3'):
                                                with ui.card().classes('config-side-card w-full p-4'):
                                                    ui.label('DOF Event Test').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                    ui.label(
                                                        'Enter an event token like E900 or S27, then start or stop it for testing.'
                                                    ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                                    dof_test_event_input = ui.input(
                                                        label='Test Event',
                                                        value='E900',
                                                        placeholder='E900',
                                                    ).props('outlined').classes('w-full mt-2')
                                                    with ui.row().classes('items-center gap-3 mt-3'):
                                                        ui.button(
                                                            'Start Event',
                                                            icon='play_arrow',
                                                            on_click=run_dof_test_event_start,
                                                        ).style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;')
                                                        ui.button(
                                                            'Stop Event',
                                                            icon='stop',
                                                            on_click=run_dof_test_event_stop,
                                                        ).style('color: var(--neon-pink) !important; background: var(--surface) !important; border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 10px;')
                                    elif section == 'libdmdutil':
                                        service_key = 'enabled'
                                        zedmd_keys = ['zedmddevice', 'zedmdwifiaddr']
                                        trailing_keys = [
                                            key for key in options
                                            if key not in ([service_key] + zedmd_keys)
                                        ]

                                        with ui.element('div').classes('config-form-grid'):
                                            if service_key in options:
                                                value = config.config.get(section, service_key, fallback='false')
                                                build_config_input(section, service_key, value)

                                        present_zedmd_keys = [key for key in zedmd_keys if key in options]
                                        if present_zedmd_keys:
                                            with ui.element('div').classes('config-field-card mt-3'):
                                                with ui.column().classes('w-full gap-3'):
                                                    ui.label('ZeDMD').classes('config-field-label')
                                                    for key in present_zedmd_keys:
                                                        value = config.config.get(section, key, fallback='')
                                                        build_config_input(section, key, value)

                                        with ui.element('div').classes('config-form-grid mt-3'):
                                            for key in trailing_keys:
                                                value = config.config.get(section, key, fallback='')
                                                build_config_input(section, key, value)
                                    else:
                                        with ui.element('div').classes('config-form-grid'):
                                            for key in options:
                                                value = config.config.get(section, key, fallback='')
                                                build_config_input(section, key, value)

                            if section == 'Displays':
                                with ui.card().classes('config-side-card w-full p-4 gap-3'):
                                    ui.label('Detected Displays').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                    ui.label(
                                        'Use these IDs when setting Playfield, Backglass, and DMD monitor assignments.'
                                    ).classes('text-sm').style('color: var(--ink-muted) !important;')

                                    if detected_displays['error']:
                                        ui.label(
                                            f"Unable to detect displays: {detected_displays['error']}"
                                        ).style('color: var(--bad) !important;')
                                    elif not detected_displays['screeninfo']:
                                        ui.label('No displays were detected.').style('color: var(--warn) !important;')
                                    else:
                                        for m in detected_displays['screeninfo']:
                                            ui.html(
                                                f"<div class='config-display-item'><strong>{m['id']}</strong><br>"
                                                f"output={m['output']}<br>{m['width']}x{m['height']} at x={m['x']}, y={m['y']}</div>"
                                            )

                                    if detected_displays['nsscreen']:
                                        ui.separator().classes('my-2')
                                        ui.label(
                                            'macOS NSScreen monitors used for window positioning:'
                                        ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                        for s in detected_displays['nsscreen']:
                                            ui.html(
                                                f"<div class='config-display-item'><strong>{s['id']}</strong><br>"
                                                f"{s['width']}x{s['height']} at x={s['x']}, y={s['y']}</div>"
                                            )

                        if section == 'DOF':
                            with ui.card().classes('config-side-card w-full mt-4 p-4'):
                                with ui.row().classes('items-center gap-3'):
                                    ui.label('Online Config Tool').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                    ui.link(
                                        '(DOF Config Online Tool)',
                                        'https://configtool.vpuniverse.com/app/home',
                                        new_tab=True,
                                    ).style('color: var(--neon-cyan) !important;')
                                ui.label(
                                    'Downloads updated DOF config using ledcontrol_pull.py and the API key above.'
                                ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                dof_force_checkbox = ui.checkbox('Force update').classes('mt-2').style('color: var(--ink) !important;')
                                update_dof_button = ui.button(
                                    'Update DOF via Online Config Tool',
                                    icon='cloud_download',
                                    on_click=run_dof_online_update,
                                ).classes('mt-3').style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;')

                        if section == 'Logger':
                            with ui.card().classes('config-side-card w-full mt-4 p-4'):
                                ui.label('Log File').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                ui.label(
                                    f'VPinFE always writes logs to {CONFIG_DIR / "vpinfe.log"}. '
                                    'Each app launch starts a fresh log file.'
                                ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                ui.button(
                                    'View Log',
                                    icon='article',
                                    on_click=show_log_file_dialog,
                                ).classes('mt-3').style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;')

        with ui.element('div').classes('w-full config-footer-bar'):
            ui.button('Save Changes', icon='save', on_click=save_config).classes('px-6 py-3').style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;')
