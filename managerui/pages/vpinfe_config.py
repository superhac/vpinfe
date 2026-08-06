import contextlib
import io
import logging
import os
import runpy
import shlex
import sys
from pathlib import Path

from nicegui import run, ui

from common import config_schema, input_actions
from frontend import input_api
from common.config_access import cfg_get
from common.config_store import ConfigStore
from common.games.collection_store import CollectionStore
from common.host.dof_service import clear_active_dof_event, find_dof_file, send_dof_event_token
from common.host.launch import build_masked_tableini_path, build_vpx_launch_command
from frontend.chromium_manager import (
    get_builtin_chromium_options,
    parse_additional_chromium_options,
)
from managerui import config_support
from managerui.config_fields import is_checkbox_field
from managerui.paths import COLLECTIONS_PATH, THEMES_DIR, VPINFE_INI_PATH
from managerui.ui_helpers import attach_shell_save_bar, load_page_style

logger = logging.getLogger("vpinfe.manager.vpinfe_config")

INI_PATH = VPINFE_INI_PATH

# Sections to ignore
IGNORED_SECTIONS = {
    'vpsdb',
    'pinmame_score_parser',
    'vpinplay',
    'state',
    # Theme sources are urls VPinFE fetches and installs code from. Editing them stays a
    # deliberate act in the config file rather than a text box beside the log level.
    'themes',
}

# Icons for each section (fallback to 'settings' if not defined)
SECTION_ICONS = {
    'general': 'folder_open',
    'Input': 'sports_esports',
    'logger': 'terminal',
    'media': 'perm_media',
    'displays': 'monitor',
    'dof': 'key',
    'libdmdutil': 'developer_board',
}

SECTION_DESCRIPTIONS = {
    'general': 'Core paths, startup behavior, and theme defaults.',
    'displays': 'Monitor assignments and playfield orientation settings.',
    'Input': 'Controller and input-related preferences.',
    'logger': 'Verbosity, console logging, and quick log access.',
    'media': 'Default media handling and fallback asset preferences.',
    'network': 'Ports and services used by the local frontend stack.',
    'mobile': 'Connection details for external mobile devices.',
    'dof': 'Direct Output Framework integration and sync tools.',
    'libdmdutil': 'libdmdutil integration settings for DMD device support.',
}


MEDIA_PRIORITY_KEYS = (
    'playfieldmediapriority',
    'bgmediapriority',
    'dmdmediapriority',
    'realdmdmediapriority',
)

def get_friendly_name(key: str, section: str = "") -> str:
    """What to call a setting on screen, from the schema that declares it.

    Section is optional only because two callers do not have one; pass it where you do,
    since `screen_id` means a different monitor in each window's section.
    """
    return config_schema.label_for(key, section)


def _get_collection_names():
    """Get list of collection names for the dropdown."""
    try:
        collections = CollectionStore(str(COLLECTIONS_PATH))
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


def render_panel(tab=None):
    # Re-read config from disk each time the page is opened
    config = ConfigStore(str(INI_PATH))
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
    chrome_options_preview = None

    # Get all sections, filter out ignored ones
    sections = [s for s in config.config.sections() if s not in IGNORED_SECTIONS]
    launch_preview_keys = {
        ('general', 'vpxbinpath'),
        ('general', 'globalinioverride'),
        ('general', 'globaltableinioverrideenabled'),
        ('general', 'globaltableinioverridemask'),
        ('general', 'vpxlaunchenv'),
    }

    def _as_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')

    def _build_launch_preview_text() -> tuple[str, str]:
        sample_vpx = 'A-Go-Go (Williams 1966).vpx'
        settings_inputs = inputs.get('general', {})

        vpxbin = str(
            getattr(settings_inputs.get('vpxbinpath'), 'value', cfg_get(config, 'general', 'vpx_bin_path', ''))
            or ''
        ).strip()
        global_ini_override = str(
            getattr(settings_inputs.get('globalinioverride'), 'value', cfg_get(config, 'general', 'global_ini_override', ''))
            or ''
        ).strip()
        tableini_enabled = _as_bool(
            getattr(
                settings_inputs.get('globaltableinioverrideenabled'),
                'value',
                cfg_get(config, 'general', 'global_game_ini_override_enabled', 'false'),
            )
        )
        tableini_mask = str(
            getattr(
                settings_inputs.get('globaltableinioverridemask'),
                'value',
                cfg_get(config, 'general', 'global_game_ini_override_mask', ''),
            )
            or ''
        ).strip()
        launch_env = str(
            getattr(settings_inputs.get('vpxlaunchenv'), 'value', cfg_get(config, 'general', 'vpx_launch_env', ''))
            or ''
        ).strip()

        tableini_override = build_masked_tableini_path(sample_vpx, tableini_enabled, tableini_mask)
        launcher = vpxbin or '<VPX Executable Path>'
        command = build_vpx_launch_command(
            launcher_path=launcher,
            vpx_game_path=sample_vpx,
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

    def update_chrome_options_preview():
        if chrome_options_preview is None:
            return
        settings_inputs = inputs.get('general', {})
        disable_defaults = _as_bool(
            getattr(
                settings_inputs.get('disabledefaultchromeoptions'),
                'value',
                cfg_get(config, 'general', 'disable_default_chrome_options', 'false'),
            )
        )
        exclude_raw = str(
            getattr(
                settings_inputs.get('chromeoptionsexclude'),
                'value',
                cfg_get(config, 'general', 'chrome_options_exclude', ''),
            )
            or ''
        ).strip()
        additional_raw = str(
            getattr(
                settings_inputs.get('chromeoptions'),
                'value',
                cfg_get(config, 'general', 'chrome_options', ''),
            )
            or ''
        ).strip()
        try:
            additional_opts = parse_additional_chromium_options(additional_raw)
        except ValueError:
            additional_opts = []
        chrome_options_preview.value = '\n'.join(
            get_builtin_chromium_options(
                include_default_options=not disable_defaults,
                exclude_options=parse_additional_chromium_options(exclude_raw),
            )
            + additional_opts
        )

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
                if section == 'general' and key == 'globaltableinioverridemask':
                    mask_value = (value or '').strip()
                    if mask_value:
                        label_text = (
                            f'{friendly_label} (Example: A-Go-Go (Williams 1966).{mask_value}.ini)'
                        )
                label_widget = ui.label(label_text).classes('config-field-label')

            if section == 'general' and key == 'startup_collection':
                collection_options = _get_collection_names()
                if value and value not in collection_options:
                    collection_options.append(value)
                inp = ui.select(
                    options=collection_options,
                    value=value
                ).props('outlined dense options-dense').classes('config-input')
            elif section == 'general' and key == 'vpxlaunchenv':
                inp = ui.textarea(
                    value=value,
                    placeholder='KEY=value KEY2="value with spaces"'
                ).props('outlined autogrow').classes('config-input config-input-env')
            elif section == 'general' and key == 'chromeoptions':
                inp = ui.textarea(
                    value=value,
                    placeholder='--disable-accelerated-video-decode\n--ozone-platform=x11'
                ).props('outlined autogrow').classes('config-input config-input-env')
            elif section == 'general' and key == 'theme':
                theme_options = _get_installed_theme_names()
                if value and value not in theme_options:
                    theme_options.append(value)
                inp = ui.select(
                    options=theme_options,
                    value=value
                ).props('outlined dense options-dense').classes('config-input')
            elif section == 'media' and key in MEDIA_PRIORITY_KEYS:
                normalized_priority = str(value or '').strip().lower()
                if key == 'realdmdmediapriority':
                    priority_options = {'color': 'Colorized frame', 'standard': 'Standard frame'}
                    priority_value = normalized_priority if normalized_priority in priority_options else 'color'
                else:
                    priority_options = {'video': 'Video', 'image': 'Image'}
                    priority_value = normalized_priority if normalized_priority in priority_options else 'video'
                inp = ui.select(
                    options=priority_options,
                    value=priority_value
                ).props('outlined dense options-dense emit-value map-options').classes('config-input')
            elif section == 'Input' and key == 'pagingtype':
                normalized_paging = str(value or '').strip().lower()
                paging_options = {'alpha': 'Alphabetic (jump by letter)', 'numeric': 'Numeric (jump by page size)'}
                paging_value = normalized_paging if normalized_paging in paging_options else 'alpha'
                inp = ui.select(
                    options=paging_options,
                    value=paging_value
                ).props('outlined dense options-dense emit-value map-options').classes('config-input')
            elif is_checkbox:
                inp = ui.checkbox(
                    text='Enable' if special_label_above else friendly_label,
                    value=(value == "true")
                ).classes('config-input')
                if section == 'displays' and key == 'cabmode':
                    inp.tooltip(
                        'Presents VPinFE for playing standing at a cabinet: larger text and '
                        'targets, and no controls that need a mouse. It does not rotate '
                        'anything - use Playfield Monitor Mounting and Rotate VPinFE '
                        'Display for that.'
                    )
            elif section == 'displays' and key == 'playfieldorientation':
                inp = ui.select(
                    options={'landscape': 'Landscape', 'portrait': 'Portrait'},
                    value=(value or 'landscape').strip().lower()
                ).props('outlined dense options-dense emit-value map-options').classes('config-input')
                inp.tooltip(
                    'How the playfield screen is physically mounted. Portrait means it is '
                    'turned on its side in the cabinet. This does not rotate anything by '
                    'itself - it tells themes what shape to lay out for.'
                )
            elif section == 'displays' and key == 'playfieldrotation':
                inp = ui.select(
                    options={
                        '0': '0\u00b0 - the screen is already the right way up',
                        '90': '90\u00b0 clockwise',
                        '180': '180\u00b0 - upside down',
                        '270': '270\u00b0 clockwise',
                    },
                    value=(value or '0').strip() if (value or '0').strip() in
                          ('0', '90', '180', '270') else '0'
                ).props('outlined dense options-dense emit-value map-options').classes('config-input')
                inp.tooltip(
                    'How far VPinFE turns its own display so it faces the player. Leave at '
                    '0 if your operating system already rotates this screen - the desktop '
                    'appears upright on it. If the desktop appears sideways, or the taskbar '
                    'runs up the side of the screen, set 90 or 270 here instead.'
                )
            elif section == 'displays' and key in (
                    'playfieldscreenid', 'bgscreenid', 'dmdscreenid'):
                monitor_options = _get_display_id_options(detected_displays, value)
                inp = ui.select(
                    options=monitor_options,
                    value=(value or '').strip()
                ).props('outlined dense options-dense').classes('config-input')
            elif section == 'logger' and key == 'level':
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
                if section == 'displays' and key in ('bgwindowoverride', 'dmdwindowoverride'):
                    inp.props('hint="Format: x,y,width,height"')
                    inp.tooltip(
                        'Optional high-DPI override passed to themes instead of the detected window bounds.'
                    )
                if section == 'general' and key == 'globaltableinioverridemask' and label_widget is not None:
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
            if section == 'general' and key == 'chromeoptions':
                inp.on_value_change(lambda _: update_chrome_options_preview())

    binding_inputs: dict[str, dict[str, object]] = {}

    def build_binding_input(action, device: str, value: str):
        """One field of the two an action is shown through.

        The pair is a view over the action's single binding list - `device` says which
        half this field owns, and save_config recombines them.
        """
        with ui.element('div').classes('config-field'):
            ui.label(action.label).classes('config-field-label')
            widget = ui.input(value=value).props('outlined dense').classes('config-input')
        binding_inputs.setdefault(action.name, {})[device] = widget
        return widget

    def save_config():
        try:
            for action in input_actions.actions():
                fields = binding_inputs.get(action.name)
                if not fields:
                    continue
                keys = [k.strip() for k in
                        str(getattr(fields.get('key'), 'value', '') or '').split(',') if k.strip()]
                pads = [b.strip() for b in
                        str(getattr(fields.get('pad'), 'value', '') or '').split(',') if b.strip()]
                rebuilt = [f'{input_actions.KEY_PREFIX}{k}' for k in keys]
                rebuilt += [f'{input_actions.PAD_PREFIX}0/button:{b}' for b in pads]
                # Anything neither field can show - a chord, a hold, an axis, a second
                # pad - is carried through untouched. Rebuilding from the two fields
                # alone would delete it the first time anyone pressed Save.
                current = input_api.get_bindings(config)[action.name]
                rebuilt += input_actions.unrenderable(current)
                if not config.config.has_section(input_actions.SECTION):
                    config.config.add_section(input_actions.SECTION)
                config.config.set(input_actions.SECTION, action.name, ','.join(rebuilt))

            for section, keys in inputs.items():
                for key, inp in keys.items():
                    if key == '__thirdparty_included' or key == '__windows_included':
                        continue
                    if section == 'logger' and key == 'level':
                        level_value = str(inp.value or 'info').strip().lower() or 'info'
                        include_thirdparty = bool(getattr(inputs.get('logger', {}).get('__thirdparty_included'), 'value', False))
                        include_windows = bool(getattr(inputs.get('logger', {}).get('__windows_included'), 'value', False))
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
                        value = '' if inp.value is None else str(inp.value)
                        config.config.set(section, key, value)
            # Through the store, never straight to the file - it owns the format, the
            # schema version and the typing, and writing past it would leave a stale copy.
            config.save()
            logger.info(
                "Saved configuration to %s: vpxbinpath=%r gamerootdir=%r vpxinipath=%r",
                config.configfilepath,
                cfg_get(config, 'general', 'vpx_bin_path', ''),
                cfg_get(config, 'general', 'game_root_dir', ''),
                cfg_get(config, 'general', 'vpx_ini_path', ''),
            )
            try:
                from managerui.services import game_index_service
                game_index_service.invalidate()
            except Exception:
                logger.exception("Failed to invalidate game index after saving configuration")
            ui.notify('Configuration Saved', type='positive')
        except Exception as e:
            logger.exception("Failed to save configuration to %s", config.configfilepath)
            ui.notify(f'Failed to save configuration: {e}', type='negative')

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
            getattr(inputs.get('dof', {}).get('dof_config_tool_api_key'), 'value', '') or ''
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
                    if section == 'logger':
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

                        content_classes = 'config-main-grid' if section == 'displays' else 'w-full'
                        with ui.element('div').classes(content_classes):
                            if section == 'general':
                                path_keys = [
                                    key for key in ('vpxbinpath', 'gamerootdir', 'vpxinipath')
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
                                chrome_option_keys = [
                                    key for key in ('disabledefaultchromeoptions', 'chromeoptions', 'chromeoptionsexclude')
                                    if key in options
                                ]
                                general_keys = [
                                    key for key in options
                                    if key not in set(path_keys + launch_keys + chrome_option_keys)
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
                                    if chrome_option_keys:
                                        with ui.card().classes('config-side-card w-full p-4'):
                                            ui.label('Chrome Options').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                            ui.label(
                                                'Modify the default flags applied to each Chromium or Chrome frontend window.'
                                            ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                            with ui.element('div').classes('config-launch-layout mt-3'):
                                                with ui.element('div').classes('config-display-column'):
                                                    value = config.config.get(section, 'chromeoptions', fallback='')
                                                    build_config_input(section, 'chromeoptions', value)
                                                    if 'disabledefaultchromeoptions' in chrome_option_keys:
                                                        with ui.element('div').classes('config-field-card'):
                                                            ui.label('Disabled Default Options').classes('config-field-label')
                                                            disable_all_inp = ui.checkbox(
                                                                text='Disable All',
                                                                value=(config.config.get(section, 'disabledefaultchromeoptions', fallback='false') == 'true'),
                                                            ).classes('config-input')
                                                            exclude_inp = ui.textarea(
                                                                value=config.config.get(section, 'chromeoptionsexclude', fallback=''),
                                                                placeholder='--kiosk\n--start-maximized'
                                                            ).props('outlined autogrow').classes('config-input config-input-env')
                                                            inputs.setdefault(section, {})['disabledefaultchromeoptions'] = disable_all_inp
                                                            inputs[section]['chromeoptionsexclude'] = exclude_inp

                                                            def _sync_exclude_enabled():
                                                                (exclude_inp.disable if bool(disable_all_inp.value) else exclude_inp.enable)()

                                                            _sync_exclude_enabled()
                                                            disable_all_inp.on_value_change(lambda _: (_sync_exclude_enabled(), update_chrome_options_preview()))
                                                            exclude_inp.on_value_change(lambda _: update_chrome_options_preview())
                                                with ui.element('div').classes('config-launch-preview-box'):
                                                    ui.label('Effective Chrome Options').classes('text-sm font-semibold').style('color: var(--ink-muted) !important;')
                                                    chrome_options_preview = ui.textarea(
                                                        value='',
                                                    ).props('readonly outlined autogrow').classes('w-full').style(
                                                        'font-family: monospace;'
                                                    )
                                                    update_chrome_options_preview()
                            else:
                                with ui.card().classes('config-card w-full p-4'):
                                    if section == 'displays':
                                        split_key = 'playfieldorientation' if section == 'displays' else 'theme'
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

                                        monitor_anchor_keys = ['playfieldscreenid', 'bgscreenid', 'dmdscreenid']
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
                                    elif section == input_actions.SECTION:
                                        # Two cards over one list. Each action stores its
                                        # bindings together; the page shows the keyboard
                                        # ones and the gamepad one in the places they have
                                        # always been, and save_config puts them back.
                                        bindings = input_api.get_bindings(config)
                                        other_input_keys = [
                                            key for key in options
                                            if not input_actions.action_for_legacy_key(key)
                                        ]

                                        with ui.column().classes('w-full gap-4'):
                                            with ui.card().classes('config-side-card w-full p-4'):
                                                ui.label('Controller Mappings').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                ui.label(
                                                    'Assign gamepad button indexes for each frontend action.'
                                                ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                                with ui.element('div').classes('config-input-panel-grid mt-3'):
                                                    for action in input_actions.actions():
                                                        build_binding_input(
                                                            action, 'pad',
                                                            ','.join(input_actions.pad_buttons_in(
                                                                bindings[action.name])))

                                            with ui.card().classes('config-side-card w-full p-4'):
                                                ui.label('Keyboard Mappings').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                ui.label(
                                                    'Set comma-separated keyboard bindings used only by the VPinFE frontend.'
                                                ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                                with ui.element('div').classes('config-input-panel-grid mt-3'):
                                                    for action in input_actions.actions():
                                                        build_binding_input(
                                                            action, 'key',
                                                            ','.join(input_actions.keys_in(
                                                                bindings[action.name])))

                                        if other_input_keys:
                                            with ui.card().classes('config-side-card w-full mt-4 p-4'):
                                                ui.label('Additional Input Settings').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                with ui.element('div').classes('config-form-grid mt-3'):
                                                    for key in other_input_keys:
                                                        value = config.config.get(section, key, fallback='')
                                                        build_config_input(section, key, value)
                                    elif section == 'media':
                                        priority_keys = [key for key in MEDIA_PRIORITY_KEYS if key in options]
                                        default_keys = [key for key in options if key not in set(priority_keys)]

                                        with ui.column().classes('w-full gap-4'):
                                            if default_keys:
                                                with ui.card().classes('config-side-card w-full p-4'):
                                                    ui.label('Media Defaults').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                    ui.label(
                                                        'Set default download preferences and Manager UI media cache limits.'
                                                    ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                                    with ui.element('div').classes('config-form-grid mt-3'):
                                                        for key in default_keys:
                                                            value = config.config.get(section, key, fallback='')
                                                            build_config_input(section, key, value)

                                            if priority_keys:
                                                with ui.card().classes('config-side-card w-full p-4'):
                                                    ui.label('Media Priorities').classes('text-lg font-semibold').style('color: var(--ink) !important;')
                                                    ui.label(
                                                        'Choose the preferred asset when both matching image and video media exist. Missing preferred assets automatically fall back to the available alternate.'
                                                    ).classes('text-sm').style('color: var(--ink-muted) !important;')
                                                    with ui.element('div').classes('config-form-grid mt-3'):
                                                        for key in priority_keys:
                                                            value = config.config.get(section, key, fallback='')
                                                            build_config_input(section, key, value)
                                    elif section == 'mobile':
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
                                    elif section == 'dof':
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

                            if section == 'displays':
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

                        if section == 'dof':
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
        # --- Save bar with unsaved-change tracking --------------------------
        # Snapshot the loaded values so we can tell when the user has edits.
        # save_config() is left as-is; the shared footer drives the UI.
        def _norm(value):
            return '' if value is None else str(value)

        initial_raw = {
            (section, key): inp.value
            for section, keys in inputs.items()
            for key, inp in keys.items()
        }

        def changed_count():
            return sum(
                1
                for section, keys in inputs.items()
                for key, inp in keys.items()
                if _norm(inp.value) != _norm(initial_raw.get((section, key)))
            )

        def on_save():
            save_config()
            for section, keys in inputs.items():
                for key, inp in keys.items():
                    initial_raw[(section, key)] = inp.value

        def on_discard():
            for (section, key), value in initial_raw.items():
                inp = inputs.get(section, {}).get(key)
                if inp is not None:
                    inp.value = value

        update_save_bar = attach_shell_save_bar(
            count=changed_count, on_save=on_save, on_discard=on_discard
        )

        for section, keys in inputs.items():
            for key, inp in keys.items():
                inp.on_value_change(lambda _: update_save_bar())

        update_save_bar()
