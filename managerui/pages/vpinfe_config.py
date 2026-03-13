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
    dof_force_checkbox = None
    update_dof_button = None

    # Get all sections, filter out ignored ones
    sections = [s for s in config.config.sections() if s not in IGNORED_SECTIONS]

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
                        if section == 'Logger':
                            options = [key for key in options if key != 'file']

                        with ui.column().classes('gap-3'):
                            for key in options:
                                value = config.config.get(section, key, fallback='')
                                friendly_label = get_friendly_name(key)

                                # Special handling for startup_collection in Settings
                                if section == 'Settings' and key == 'startup_collection':
                                    collection_options = _get_collection_names()
                                    # Ensure current value is in options
                                    if value and value not in collection_options:
                                        collection_options.append(value)
                                    inp = ui.select(
                                        label=friendly_label,
                                        options=collection_options,
                                        value=value
                                    ).classes('config-input').style('min-width: 200px;')
                                # Special handling for theme in Settings
                                elif section == 'Settings' and key == 'theme':
                                    theme_options = _get_installed_theme_names()
                                    if value and value not in theme_options:
                                        theme_options.append(value)
                                    inp = ui.select(
                                        label=friendly_label,
                                        options=theme_options,
                                        value=value
                                    ).classes('config-input').style('min-width: 200px;')
                                # Special handling for startup media auto-update in Settings
                                elif (section == 'Settings' and key == 'autoupdatemediaonstartup') or (section == 'Displays' and key == 'cabmode') or (section == 'Logger' and key == 'console') or (section == 'Settings' and key == 'splashscreen') or (section == 'DOF' and key == 'enabledof'):
                                    inp = ui.checkbox(
                                        text=friendly_label,
                                        value=(value == "true")
                                    ).classes('config-input').style('min-width: 200px;')
                                # Special handling for monitor IDs in Displays
                                elif section == 'Displays' and key in ('tablescreenid', 'bgscreenid', 'dmdscreenid'):
                                    monitor_options = _get_display_id_options(detected_displays, value)
                                    inp = ui.select(
                                        label=friendly_label,
                                        options=monitor_options,
                                        value=(value or '').strip()
                                    ).classes('config-input').style('min-width: 200px;')
                                elif section == 'Logger' and key == 'level':
                                    level_options = _get_logger_level_options(value)
                                    normalized = (value or 'info').strip().lower()
                                    inp = ui.select(
                                        label=friendly_label,
                                        options=level_options,
                                        value=normalized
                                    ).classes('config-input').style('min-width: 200px;')
                                else:
                                    # Calculate width based on the longer string (value or friendly label)
                                    char_width = max(len(value), len(friendly_label), 5)  
                                    width_px = int(char_width * 10 * 1.1)  
                                    width_px = max(width_px, 100)  
                                    inp = ui.input(
                                        label=friendly_label, 
                                        value=value
                                    ).classes('config-input').style(f'width: {width_px}px;')
                                
                                # Store the original INI key so saving works correctly
                                inputs[section][key] = inp

                            if section == 'DOF':
                                with ui.card().classes('w-full mt-3 p-3').style(
                                    'background: #122038; border: 1px solid #334155; border-radius: 10px;'
                                ):
                                    ui.label('Online Config Tool').classes('text-lg font-semibold')
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
                                with ui.card().classes('w-full mt-3 p-3').style(
                                    'background: #122038; border: 1px solid #334155; border-radius: 10px;'
                                ):
                                    ui.label('Log File').classes('text-lg font-semibold')
                                    ui.label(
                                        f'VPinFE always writes logs to {CONFIG_DIR / "vpinfe.log"}. '
                                        'Each app launch starts a fresh log file.'
                                    ).classes('text-sm text-slate-300')
                                    ui.button(
                                        'View Log',
                                        icon='article',
                                        on_click=show_log_file_dialog,
                                    ).props('color=primary rounded').classes('mt-3')

                            if section == 'Displays':
                                with ui.card().classes('w-full mt-3 p-3').style(
                                    'background: #122038; border: 1px solid #334155; border-radius: 10px;'
                                ):
                                    ui.label('Detected Displays').classes('text-lg font-semibold')
                                    ui.label('Use these IDs when setting Playfield/Backglass/DMD monitor IDs above.').classes('text-sm text-slate-300')

                                    if detected_displays['error']:
                                        ui.label(f"Unable to detect displays: {detected_displays['error']}").classes('text-red-3')
                                    elif not detected_displays['screeninfo']:
                                        ui.label('No displays were detected.').classes('text-amber-3')
                                    else:
                                        for m in detected_displays['screeninfo']:
                                            ui.label(
                                                f"{m['id']}: output={m['output']} "
                                                f"({m['width']}x{m['height']} at x={m['x']}, y={m['y']})"
                                            ).classes('text-sm')

                                    if detected_displays['nsscreen']:
                                        ui.separator().classes('my-2')
                                        ui.label('macOS NSScreen monitors (used for window positioning):').classes('text-sm text-slate-300')
                                        for s in detected_displays['nsscreen']:
                                            ui.label(
                                                f"{s['id']}: ({s['width']}x{s['height']} at x={s['x']}, y={s['y']})"
                                            ).classes('text-sm')

        # Save button
        with ui.row().classes('w-full justify-end mt-4'):
            ui.button('Save Changes', icon='save', on_click=save_config).props('color=primary rounded').classes('px-6')
