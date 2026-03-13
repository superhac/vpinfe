import os
import io
import contextlib
import html
import logging
import runpy
import shlex
import sys
from nicegui import ui, run
from common.iniconfig import IniConfig
from common.dof_service import find_dof_file
from common.vpxcollections import VPXCollections
from pathlib import Path
from platformdirs import user_config_dir
from screeninfo import get_monitors


logger = logging.getLogger("vpinfe.manager.vpinfe_config")

CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
INI_PATH = CONFIG_DIR / 'vpinfe.ini'
COLLECTIONS_PATH = CONFIG_DIR / 'collections.ini'

# Sections to ignore
IGNORED_SECTIONS = {'VPSdb'}

# Icons for each section (fallback to 'settings' if not defined)
SECTION_ICONS = {
    'Settings': 'folder_open',
    'Input': 'sports_esports',
    'Logger': 'terminal',
    'Media': 'perm_media',
    'Displays': 'monitor',
    'DOF': 'key',
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
}

# Dictionary for explicit user-friendly name mappings
FRIENDLY_NAMES = {
    # [Settings]
    'vpxbinpath': 'VPX Executable Path',
    'vpxinipath' : 'VPX Ini Path',
    'tablerootdir': 'Tables Directory',
    'startup_collection': 'Startup Collection',
    'autoupdatemediaonstartup': 'Auto Update Media On Startup',
    'splashscreen': 'Enable splashscreen',
    'enabledof': 'Enable DOF',
    'dofconfigtoolapikey': 'DOF Config Tool API Key',
    'theme': 'Active Theme',
    'level': 'Log Verbosity',
    'console': 'Console Logging',
    
    # [Displays]
    'tablescreenid': 'Playfield Monitor ID',
    'bgscreenid': 'Backglass Monitor ID',
    'dmdscreenid': 'DMD Monitor ID',
    'tablerotation': 'Playfield Rotation (0/90/270)',
    'tableorientation': 'Playfield Orientation (Landscape/Portrait)',
    'playfieldorientation': 'Playfield Orientation (Landscape/Portrait)',
    'cabmode': 'Cabinet Mode',
    
    # [Network]
    'http_port': 'Web Server Port',
    'themeassetsport': 'Theme Server Port',
    'manageruiport': 'Manager UI Port',
    'manageruipublic': 'Manager UI is accessible on other computers (Restart required)',
    'startup_collection': 'Default Startup Collection',
    # [Mobile]
    'deviceip': 'Mobile Device IP',
    'deviceport': 'Mobile Device Port',
    'chunksize': 'Mobile Chunk Size',
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
    current = (current_value or '').strip().lower()
    if current and current not in options:
        options.append(current)
    return options


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
        'background: #0f172a; border: 1px solid #334155; min-width: min(92vw, 1000px); height: 82vh;'
    ):
        with ui.column().classes('w-full h-full gap-3'):
            ui.label('VPinFE Log').classes('text-xl font-bold text-white')
            ui.label(str(log_path)).classes('text-xs text-slate-400 break-all')
            with ui.scroll_area().classes('w-full').style(
                'flex: 1 1 auto; min-height: 0; border: 1px solid #475569; border-radius: 8px; background: #020617;'
            ):
                ui.html(
                    f'<pre style="margin:0; padding:12px; white-space:pre-wrap; word-break:break-word; '
                    f'font-family:monospace; font-size:12px; color:#e2e8f0;">{escaped_content}</pre>'
                ).classes('w-full')
        with ui.row().classes('w-full justify-end mt-2'):
            ui.button('Close', on_click=dlg.close).props('color=primary rounded')
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
            background:
                radial-gradient(circle at top right, rgba(125, 211, 252, 0.16), transparent 34%),
                linear-gradient(135deg, #203a5e 0%, #305887 55%, #26466c 100%);
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 18px;
            box-shadow: 0 18px 40px rgba(2, 6, 23, 0.28);
        }
        .config-hero-kicker {
            font-size: 0.72rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #bfdbfe;
            font-weight: 700;
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
            background: rgba(30, 41, 59, 0.72);
            border: 1px solid rgba(71, 85, 105, 0.9);
            color: #dbeafe;
            transition: all 0.2s ease;
        }
        .config-tabs .q-tab--active {
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.22), rgba(14, 165, 233, 0.18));
            border-color: rgba(96, 165, 250, 0.95);
            box-shadow: 0 8px 20px rgba(14, 165, 233, 0.12);
        }
        .config-tabs .q-tab__label {
            font-weight: 700;
        }
        .config-panel-shell {
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.78), rgba(13, 26, 45, 0.92));
            border: 1px solid #24344b;
            border-radius: 18px;
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
            background: linear-gradient(135deg, rgba(37, 99, 235, 0.14), rgba(15, 23, 42, 0.52));
            border: 1px solid rgba(59, 130, 246, 0.25);
        }
        .config-section-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: #f8fafc;
        }
        .config-section-description {
            font-size: 0.92rem;
            color: #93c5fd;
        }
        .config-card {
            background: linear-gradient(145deg, #1c2a40 0%, #152238 100%) !important;
            border: 1px solid #334155 !important;
            border-radius: 16px !important;
            box-shadow: 0 12px 30px rgba(2, 6, 23, 0.18) !important;
            transition: all 0.2s ease !important;
        }
        .config-card:hover {
            border-color: #3b82f6 !important;
            box-shadow: 0 8px 12px -2px rgba(59, 130, 246, 0.15) !important;
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
        .config-three-column-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 1rem;
            align-items: start;
        }
        .config-display-column {
            display: grid;
            gap: 1rem;
            align-content: start;
        }
        .config-main-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.9fr);
            gap: 1rem;
            align-items: start;
        }
        .config-field-card {
            padding: 0.95rem 1rem;
            border-radius: 14px;
            background: linear-gradient(180deg, rgba(20, 32, 56, 0.96), rgba(17, 27, 46, 0.96));
            border: 1px solid rgba(71, 85, 105, 0.72);
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
            color: #93c5fd;
        }
        .config-input {
            width: 100%;
        }
        .config-input .q-field__control {
            background: #1a2744 !important;
            border-radius: 8px !important;
        }
        .config-input .q-field__native,
        .config-input input,
        .config-input .q-field__input {
            color: #f8fafc !important;
        }
        .config-input .q-field__label {
            color: #94a3b8 !important;
        }
        .config-input .q-checkbox__label {
            color: #f8fafc !important;
            font-weight: 600;
        }
        .config-side-card {
            border-radius: 16px;
            background: linear-gradient(180deg, rgba(17, 24, 39, 0.94), rgba(15, 23, 42, 0.98));
            border: 1px solid rgba(71, 85, 105, 0.8);
            box-shadow: inset 0 1px 0 rgba(148, 163, 184, 0.08), 0 10px 30px rgba(2, 6, 23, 0.18);
        }
        .config-display-item {
            padding: 0.75rem 0.85rem;
            border-radius: 12px;
            background: rgba(30, 41, 59, 0.55);
            border: 1px solid rgba(71, 85, 105, 0.58);
            color: #e2e8f0;
        }
        .config-display-item strong {
            color: #f8fafc;
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
            .config-display-form-grid {
                grid-template-columns: 1fr;
            }
            .config-three-column-grid {
                grid-template-columns: 1fr;
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

    # Get all sections, filter out ignored ones
    sections = [s for s in config.config.sections() if s not in IGNORED_SECTIONS]

    def build_config_input(section: str, key: str, value: str):
        friendly_label = get_friendly_name(key)
        is_checkbox = (
            (section == 'Settings' and key == 'autoupdatemediaonstartup')
            or (section == 'Displays' and key == 'cabmode')
            or (section == 'Logger' and key == 'console')
            or (section == 'Settings' and key == 'splashscreen')
            or (section == 'DOF' and key == 'enabledof')
            or (section == 'Network' and key == 'manageruipublic')
        )

        with ui.element('div').classes(
            'config-field-card compact' if is_checkbox else 'config-field-card'
        ):
            if not is_checkbox:
                ui.label(friendly_label).classes('config-field-label')

            if section == 'Settings' and key == 'startup_collection':
                collection_options = _get_collection_names()
                if value and value not in collection_options:
                    collection_options.append(value)
                inp = ui.select(
                    options=collection_options,
                    value=value
                ).props('outlined dense options-dense').classes('config-input')
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
                    text=friendly_label,
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
                normalized = (value or 'info').strip().lower()
                inp = ui.select(
                    options=level_options,
                    value=normalized
                ).props('outlined dense options-dense').classes('config-input')
            else:
                inp = ui.input(value=value).props('outlined dense').classes('config-input')

            inputs[section][key] = inp

    def save_config():
        for section, keys in inputs.items():
            for key, inp in keys.items():
                if type(inp.value) is bool:
                    config.config.set(section, key, str(inp.value).lower())
                else:
                    config.config.set(section, key, inp.value)
        with open(INI_PATH, 'w') as f:
            config.config.write(f)
        ui.notify('Configuration Saved', type='positive')

    def split_evenly(items: list[str], columns: int) -> list[list[str]]:
        if columns <= 1:
            return [items]
        size = (len(items) + columns - 1) // columns
        return [items[i * size:(i + 1) * size] for i in range(columns)]

    def show_command_output_dialog(title: str, command: list[str], output: str, exit_code: int | None):
        with ui.dialog().props('persistent max-width=1000px') as dlg, ui.card().classes('w-full').style(
            'background: #0f172a; border: 1px solid #334155; min-width: min(92vw, 900px);'
        ):
            ui.label(title).classes('text-xl font-bold text-white')
            ui.label(shlex.join(command)).classes('text-xs text-slate-400 break-all')
            if exit_code is not None:
                status_color = 'text-green-400' if exit_code == 0 else 'text-red-400'
                ui.label(f'Exit code: {exit_code}').classes(f'text-sm {status_color}')
            ui.textarea(value=output).props('readonly outlined').classes('w-full').style(
                'height: 420px; font-family: monospace;'
            )
            with ui.row().classes('w-full justify-end mt-2'):
                ui.button('Close', on_click=dlg.close).props('color=primary rounded')
        dlg.open()

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

    with ui.column().classes('w-full config-page-shell'):
        with ui.card().classes('w-full config-hero').style('overflow: hidden;'):
            with ui.row().classes('w-full items-center justify-between p-6 gap-6'):
                with ui.row().classes('items-center gap-4'):
                    ui.icon('tune', size='34px').classes('text-white')
                    with ui.column().classes('gap-1'):
                        ui.label('System Setup').classes('config-hero-kicker')
                        ui.label('VPinFE Configuration').classes('text-2xl font-bold text-white')
                        ui.label(
                            'Organize display mapping, startup behavior, media, and service settings from one place.'
                        ).classes('text-sm text-blue-100')
                with ui.column().classes('items-start gap-1'):
                    ui.label(f'{len(sections)} sections').classes('text-sm font-semibold text-white')
                    ui.label('Changes are saved directly to your active vpinfe.ini.').classes('text-xs text-blue-100')

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
                                ui.icon(SECTION_ICONS.get(section, 'settings'), size='24px').classes('text-blue-200')
                                with ui.column().classes('gap-0'):
                                    ui.label(section).classes('config-section-title')
                                    ui.label(
                                        SECTION_DESCRIPTIONS.get(section, 'Configuration values for this section.')
                                    ).classes('config-section-description')
                            ui.label(f'{len(options)} setting{"s" if len(options) != 1 else ""}').classes(
                                'text-xs font-semibold text-slate-300'
                            )

                        content_classes = 'config-main-grid' if section == 'Displays' else 'w-full'
                        with ui.element('div').classes(content_classes):
                            with ui.card().classes('config-card w-full p-4'):
                                if section in ('Displays', 'Settings'):
                                    split_key = 'tableorientation' if section == 'Displays' else 'theme'
                                    split_index = options.index(split_key) if split_key in options else len(options)
                                    first_column_keys = options[:split_index]
                                    second_column_keys = options[split_index:]

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
                                    with ui.element('div').classes('config-three-column-grid'):
                                        for column_keys in split_evenly(options, 3):
                                            with ui.element('div').classes('config-display-column'):
                                                for key in column_keys:
                                                    value = config.config.get(section, key, fallback='')
                                                    build_config_input(section, key, value)
                                else:
                                    with ui.element('div').classes('config-form-grid'):
                                        for key in options:
                                            value = config.config.get(section, key, fallback='')
                                            build_config_input(section, key, value)

                            if section == 'Network':
                                with ui.card().classes('config-side-card w-full mt-4 p-4'):
                                    ui.label('Warning about publicly accessible management UI').classes('text-lg font-semibold text-white')
                                    ui.label(
                                        'Anyone on your local network can connect and access the management UI when the Manager UI is set to be accessible on other computers. This can be a security risk and should be enabled with care.'
                                    ).classes('text-sm text-slate-300')
                                    ui.label(
                                        'The terminal will be disabled when the Manager UI is accessible by other computers.'
                                    ).classes('text-sm text-slate-300')
                                    
                            if section == 'Displays':
                                with ui.card().classes('config-side-card w-full p-4 gap-3'):
                                    ui.label('Detected Displays').classes('text-lg font-semibold text-white')
                                    ui.label(
                                        'Use these IDs when setting Playfield, Backglass, and DMD monitor assignments.'
                                    ).classes('text-sm text-slate-300')

                                    if detected_displays['error']:
                                        ui.label(
                                            f"Unable to detect displays: {detected_displays['error']}"
                                        ).classes('text-red-300')
                                    elif not detected_displays['screeninfo']:
                                        ui.label('No displays were detected.').classes('text-amber-300')
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
                                        ).classes('text-sm text-slate-300')
                                        for s in detected_displays['nsscreen']:
                                            ui.html(
                                                f"<div class='config-display-item'><strong>{s['id']}</strong><br>"
                                                f"{s['width']}x{s['height']} at x={s['x']}, y={s['y']}</div>"
                                            )

                        if section == 'DOF':
                            with ui.card().classes('config-side-card w-full mt-4 p-4'):
                                ui.label('Online Config Tool').classes('text-lg font-semibold text-white')
                                ui.label(
                                    'Downloads updated DOF config using ledcontrol_pull.py and the API key above.'
                                ).classes('text-sm text-slate-300')
                                dof_force_checkbox = ui.checkbox('Force update').classes('mt-2 text-white')
                                update_dof_button = ui.button(
                                    'Update DOF via Online Config Tool',
                                    icon='cloud_download',
                                    on_click=run_dof_online_update,
                                ).props('color=primary rounded').classes('mt-3')

                        if section == 'Logger':
                            with ui.card().classes('config-side-card w-full mt-4 p-4'):
                                ui.label('Log File').classes('text-lg font-semibold text-white')
                                ui.label(
                                    f'VPinFE always writes logs to {CONFIG_DIR / "vpinfe.log"}. '
                                    'Each app launch starts a fresh log file.'
                                ).classes('text-sm text-slate-300')
                                ui.button(
                                    'View Log',
                                    icon='article',
                                    on_click=show_log_file_dialog,
                                ).props('color=primary rounded').classes('mt-3')

        with ui.element('div').classes('w-full config-footer-bar'):
            ui.button('Save Changes', icon='save', on_click=save_config).props('color=primary rounded').classes('px-6 py-3')
