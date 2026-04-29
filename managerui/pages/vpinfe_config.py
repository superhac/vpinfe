import os
import io
import contextlib
import html
import logging
import re
import runpy
import shlex
import sys
from nicegui import ui, run
from common.iniconfig import IniConfig
from common.dof_service import clear_active_dof_event, find_dof_file, send_dof_event_token
from common.launcher import build_masked_tableini_path, build_vpx_launch_command
from common.vpxcollections import VPXCollections
from pathlib import Path
from managerui.config_fields import is_checkbox_field, sort_input_mapping_keys
from managerui import config_support
from managerui.paths import COLLECTIONS_PATH, CONFIG_DIR, VPINFE_INI_PATH, THEMES_DIR
from managerui.ui_helpers import load_page_style


logger = logging.getLogger("vpinfe.manager.vpinfe_config")

INI_PATH = VPINFE_INI_PATH

# Sections to ignore
IGNORED_SECTIONS = {
    'VPSdb',
    'pinmame-score-parser',
    'vpinplay',
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
    themes_dir = THEMES_DIR
    if themes_dir.is_dir():
        for entry in os.scandir(themes_dir):
            if entry.is_dir():
                themes.append(entry.name)
    return sorted(themes)

def _get_detected_displays():
    """Return monitor info in the same shape/IDs as the --listres CLI output."""
    return config_support.get_detected_displays()

def _get_display_id_options(detected_displays, current_value: str = ''):
    """Build dropdown options for monitor ID fields: empty + 0..(max detected-1)."""
    return config_support.get_display_id_options(detected_displays, current_value)


def _get_logger_level_options(current_value: str = ''):
    return config_support.get_logger_level_options(current_value)


def _get_uniform_field_width_ch(values: list[str], minimum: int = 30, padding: int = 2) -> int:
    return config_support.get_uniform_field_width_ch(values, minimum, padding)


def _split_logger_level_value(raw_value: str | None) -> tuple[str, bool, bool]:
    return config_support.split_logger_level_value(raw_value)


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
    load_page_style("vpinfe_config.css")

    # Dictionary to store all input references: {section: {key: input_element}}
    inputs = {}
    dof_force_checkbox = None
    update_dof_button = None
    dof_test_event_input = None
    launch_command_preview = None
    launch_env_preview = None

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
        is_checkbox = is_checkbox_field(section, key)

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

            inputs[section][key] = inp
            if (section, key) in launch_preview_keys:
                inp.on_value_change(lambda _: update_launch_preview())

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
                    config.config.set(section, key, value)
        with open(INI_PATH, 'w') as f:
            config.config.write(f)
        ui.notify('Configuration Saved', type='positive')

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
                                    if path_keys or general_keys:
                                        with ui.element('div').classes('config-paths-panel-grid').style(
                                            'display: grid !important; '
                                            'grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) !important; '
                                            'gap: 1rem; '
                                            'align-items: stretch;'
                                        ):
                                            if path_keys:
                                                with ui.card().classes('config-side-card config-equal-height-card w-full p-4'):
                                                    with ui.element('div').classes('config-display-column'):
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
                                                with ui.card().classes('config-side-card config-equal-height-card w-full p-4'):
                                                    with ui.element('div').classes('config-display-column'):
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
                                                    ui.label('VPinball Launch Command w/Options').classes('text-lg font-semibold').style('color: var(--ink) !important;')
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
                                        controller_keys = sort_input_mapping_keys(
                                            [key for key in options if key.startswith('joy')],
                                            'joy',
                                        )
                                        keyboard_keys = sort_input_mapping_keys(
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
                                    elif section == 'libdmdutil':
                                        service_key = 'enabled'
                                        zedmd_keys = ['zedmddevice', 'zedmdwifiaddr']
                                        pin2dmd_keys = ['pin2dmdenabled']
                                        pixelcade_keys = ['pixelcadedevice']
                                        device_keys = zedmd_keys + pin2dmd_keys + pixelcade_keys
                                        trailing_keys = [
                                            key for key in options
                                            if key not in ([service_key] + device_keys)
                                        ]

                                        with ui.element('div').classes('config-form-grid'):
                                            if service_key in options:
                                                value = config.config.get(section, service_key, fallback='false')
                                                build_config_input(section, service_key, value)

                                        present_zedmd_keys = [key for key in zedmd_keys if key in options]
                                        present_pin2dmd_keys = [key for key in pin2dmd_keys if key in options]
                                        present_pixelcade_keys = [key for key in pixelcade_keys if key in options]
                                        if present_zedmd_keys or present_pin2dmd_keys or present_pixelcade_keys:
                                            with ui.element('div').classes('config-three-column-grid mt-3'):
                                                if present_zedmd_keys:
                                                    with ui.element('div').classes('config-field-card'):
                                                        with ui.column().classes('w-full gap-3'):
                                                            ui.label('ZeDMD').classes('config-field-label')
                                                            for key in present_zedmd_keys:
                                                                value = config.config.get(section, key, fallback='')
                                                                build_config_input(section, key, value)

                                                if present_pin2dmd_keys:
                                                    with ui.element('div').classes('config-field-card'):
                                                        with ui.column().classes('w-full gap-3'):
                                                            ui.label('PIN2DMD').classes('config-field-label')
                                                            for key in present_pin2dmd_keys:
                                                                value = config.config.get(section, key, fallback='')
                                                                build_config_input(section, key, value)

                                                if present_pixelcade_keys:
                                                    with ui.element('div').classes('config-field-card'):
                                                        with ui.column().classes('w-full gap-3'):
                                                            ui.label('PixelcadeDevice').classes('config-field-label')
                                                            for key in present_pixelcade_keys:
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
