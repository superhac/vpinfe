import subprocess
import os
import logging
from nicegui import ui, run
from managerui.paths import VPINFE_INI_PATH
from managerui.remote_actions import PINMAME_SERVICE_CONTROLS, SYSTEM_CONTROLS, RemoteAction
from managerui import remote_launch
from managerui.services import app_control

ks = None
content_area = None
category_select = None

# Config for launching tables
# Import config
from common.iniconfig import IniConfig
from common.config_access import SettingsConfig
from common.dof_service import start_dof_service_if_enabled, stop_dof_service
from common.vpx_log import delete_vpinball_log_on_start_if_configured
from common.libdmdutil_service import (
    stop_libdmdutil_service,
)
from managerui.ui_helpers import debounced_input, load_page_style
from common.launcher import (
    build_vpx_launch_command,
    get_effective_launcher,
    parse_launch_env_overrides,
    resolve_launch_tableini_override,
)
_INI_CFG = None
logger = logging.getLogger("vpinfe.manager.remote")


def _get_keysimulator_class():
    from managerui.keysimulator import KeySimulator
    return KeySimulator


def _get_key_class():
    from pynput.keyboard import Key
    return Key


def _get_keysimulator():
    global ks
    if ks is None:
        ks = _get_keysimulator_class()(debug=True)
    return ks


def _remote_section(title: str):
    card = ui.card().classes("w-full p-3 md:p-4").style(
        "background-color: var(--surface) !important; "
        "border: 1px solid var(--neon-purple); "
        "border-radius: 18px;"
    )
    with card:
        ui.label(title).classes("text-center text-xs md:text-sm font-semibold mb-2 md:mb-3").style(
            "color: var(--ink-muted) !important;"
        )
    return card


def _labeled_icon_action(category: str, action: RemoteAction):
    with ui.column().classes("items-center gap-2"):
        btn = ui.button(
            on_click=lambda a=action: handle_button(category, a.command) if a.enabled else None
        ).props("flat round").classes("icon-button")
        if not action.enabled:
            btn.props("disable")
            btn.style("opacity: 0.4; cursor: not-allowed;")
        with btn:
            ui.icon(action.icon or "radio_button_checked", size="md").classes(
                action.color_class if action.enabled else "text-gray-600"
            )
        ui.label(action.label).classes(
            f"text-xs font-medium {'text-gray-400' if action.enabled else 'text-gray-600'}"
        )


def _get_collections():
    """Get list of collection names."""
    return remote_launch.get_collections()


def _get_collection_vpsids(collection_name):
    """Get VPSIds for a specific collection (vpsid-based only)."""
    return remote_launch.get_collection_vpsids(collection_name)


def _is_filter_collection(collection_name):
    """Check if a collection is filter-based."""
    return remote_launch.is_filter_collection(collection_name)


def _get_collection_filters(collection_name):
    """Get filters for a filter-based collection."""
    return remote_launch.get_collection_filters(collection_name)


def _table_matches_filters(table, filters):
    """Check if a table matches the given filter criteria."""
    return remote_launch.table_matches_filters(table, filters)


def _get_ini_config():
    """Lazy load the INI config."""
    global _INI_CFG
    if _INI_CFG is None:
        _INI_CFG = IniConfig(str(VPINFE_INI_PATH))
    return _INI_CFG


def _get_tables_path() -> str:
    """Get the tables root directory from config."""
    from managerui.paths import get_tables_path
    return get_tables_path()


def _scan_tables_for_launch():
    """Scan for tables that can be launched (have .info and .vpx files)."""
    return remote_launch.scan_tables_for_launch()


def _launch_table(table: dict):
    """Launch a table using the VPX binary."""
    import threading
    from managerui.managerui import set_remote_launch_state

    try:
        vpx_path = table.get('vpx_path', '')
        table_name = table.get('name', 'table')
        table_meta = table.get('meta', {})

        cfg = _get_ini_config()
        vpxbin = cfg.config['Settings'].get('vpxbinpath', '')
        vpxbin_path, source_key, _ = get_effective_launcher(vpxbin, table_meta)
        if not vpxbin_path:
            ui.notify('No launcher configured (set Settings.vpxbinpath or VPinFE.altlauncher)', type='negative')
            return False

        if not vpxbin_path.exists():
            ui.notify(f'Launcher not found ({source_key}): {vpxbin_path}', type='negative')
            return False

        logger.info("Remote launching table: %s", vpx_path)
        ui.notify(f'Remote Launching {table_name}...', type='info')

        delete_vpinball_log_on_start_if_configured(SettingsConfig.from_config(cfg))
        stop_dof_service()
        stop_libdmdutil_service(clear=False)

        # Signal to frontend that we're launching
        set_remote_launch_state(True, table_name)

        # Run the launch in a background thread so UI stays responsive
        global_ini_override = cfg.config['Settings'].get('globalinioverride', '').strip()
        tableini_override = resolve_launch_tableini_override(
            vpx_path,
            cfg.config['Settings'].get('globaltableinioverrideenabled', 'false'),
            cfg.config['Settings'].get('globaltableinioverridemask', ''),
        )
        cmd = build_vpx_launch_command(
            launcher_path=str(vpxbin_path),
            vpx_table_path=vpx_path,
            global_ini_override=global_ini_override,
            tableini_override=tableini_override,
        )
        launch_env = os.environ.copy()
        launch_env.update(
            parse_launch_env_overrides(cfg.config['Settings'].get('vpxlaunchenv', ''))
        )

        def run_and_wait():
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    env=launch_env,
                )
                process.wait()
            finally:
                # Clear the launch state when done
                set_remote_launch_state(False, None)
                start_dof_service_if_enabled(cfg)

        # Run in background thread
        thread = threading.Thread(target=run_and_wait, daemon=True)
        thread.start()
        return True
    except Exception as e:
        set_remote_launch_state(False, None)
        try:
            start_dof_service_if_enabled(_get_ini_config())
        except Exception:
            pass
        ui.notify(f'Failed to launch: {e}', type='negative')
        return False


def _restart_app():
    app_control.restart_app()


def _quit_app():
    app_control.quit_app()


def _shutdown_system():
    app_control.shutdown_system()


def _reboot_system():
    app_control.reboot_system()


def _show_reboot_confirmation():
    """Show a confirmation dialog before rebooting."""
    with ui.dialog() as dialog, ui.card().classes('bg-gray-800 p-6'):
        with ui.column().classes('items-center gap-4'):
            ui.icon('warning', size='48px').classes('text-orange-400')
            ui.label('Reboot System?').classes('text-xl font-bold text-white')
            ui.label('This will reboot the entire system.').classes('text-gray-400')

            with ui.row().classes('gap-4 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes(
                    'bg-gray-600 text-white px-6 py-2 rounded hover:bg-gray-500'
                )
                ui.button('Reboot', on_click=lambda: (dialog.close(), _reboot_system())).props('flat').classes(
                    'bg-orange-600 text-white px-6 py-2 rounded hover:bg-orange-500'
                )

    dialog.open()


def _show_shutdown_confirmation():
    """Show a confirmation dialog before shutting down."""
    with ui.dialog() as dialog, ui.card().classes('bg-gray-800 p-6'):
        with ui.column().classes('items-center gap-4'):
            ui.icon('warning', size='48px').classes('text-red-400')
            ui.label('Shutdown System?').classes('text-xl font-bold text-white')
            ui.label('This will shutdown the entire system.').classes('text-gray-400')

            with ui.row().classes('gap-4 mt-4'):
                ui.button('Cancel', on_click=dialog.close).props('flat').classes(
                    'bg-gray-600 text-white px-6 py-2 rounded hover:bg-gray-500'
                )
                ui.button('Shutdown', on_click=lambda: (dialog.close(), _shutdown_system())).props('flat').classes(
                    'bg-red-600 text-white px-6 py-2 rounded hover:bg-red-500'
                )

    dialog.open()


def build(parent=None):
    global content_area, category_select, ks
    _get_keysimulator()

    target = parent or ui

    # Custom CSS for remote control styling
    load_page_style("remote.css")

    with target.column().classes("w-full min-h-screen items-center justify-start p-0 md:p-4 md:justify-center"):
        with ui.card().classes(
            "remote-body text-white w-full md:w-[95vw] md:max-w-[420px] rounded-none md:rounded-3xl p-4 md:p-6 flex flex-col items-center gap-3 md:gap-5"
        ):
            # Header with mode selector
            ui.label("VPinFE Remote").classes("text-xl md:text-2xl font-bold text-gray-100 tracking-wide")

            with ui.row().classes("items-center justify-center w-full gap-2 mb-1 md:mb-2"):
                ui.label("Mode:").classes("text-xs md:text-sm text-gray-400 font-medium")
                category_select = ui.select(
                    ["VPX Maintenance", "VPX Game", "PinMAME", "VPinFE"],
                    value="VPX Maintenance",
                    on_change=lambda e: show_buttons(e.value.lower()),
                ).props(
                    "dense outlined options-dense dropdown-icon='expand_more' behavior='menu'"
                ).classes(
                    "text-white text-xs md:text-sm w-[150px] md:w-[180px]"
                ).style("min-width: 150px;")

            # Main content area
            with ui.column().classes("w-full items-center justify-center gap-1 mt-1") as content_area:
                pass

    show_buttons("vpx maintenance")


def show_buttons(category: str):
    global content_area
    content_area.clear()

    with content_area:
        if category == "vpx maintenance":
            show_vpx_controls()
        elif category == "vpx game":
            show_vpx_game_controls()
        elif category == "pinmame":
            show_pinmame_controls()
        else:
            show_other_controls()


def show_vpx_controls():
    """VPX remote control layout"""

    # Main Section (moved to top)
    with ui.card().classes("w-full p-3 md:p-4").style("background-color: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px;"):
        ui.label("Main").classes("text-center text-xs md:text-sm font-semibold mb-2 md:mb-3").style("color: var(--ink-muted) !important;")
        with ui.row().classes("items-center justify-center gap-3 md:gap-4 w-full"):
            # Reset
            with ui.column().classes("items-center gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Table Reset")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("refresh", size="sm").classes("text-orange-400")
                ui.label("Reset").classes("text-[10px] md:text-xs").style("color: var(--ink-muted) !important;")

            # Quit
            with ui.column().classes("items-center gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Quit")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("power_settings_new", size="sm").classes("text-red-400")
                ui.label("Quit").classes("text-[10px] md:text-xs").style("color: var(--ink-muted) !important;")

    # Volume Section
    with ui.card().classes("w-full p-3 md:p-4").style("background-color: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px;"):
        ui.label("Volume").classes("text-center text-xs md:text-sm font-semibold mb-2 md:mb-3").style("color: var(--ink-muted) !important;")
        with ui.column().classes("items-center justify-center gap-2 md:gap-3 w-full"):
            # Volume buttons row
            with ui.row().classes("items-center justify-center gap-4 md:gap-6 w-full"):
                # Volume Down
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Volume Down")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("remove", size="sm").classes("text-red-400")

                # Volume Up
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Volume Up")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("add", size="sm").classes("text-green-400")

            # Stereo Toggle (centered below)
            ui.button(
                "Toggle Stereo",
                on_click=lambda: handle_button("vpx", "Toggle Stereo")
            ).classes("remote-button px-4 md:px-6 py-1.5 md:py-2 text-xs md:text-sm font-medium").style('color: var(--neon-cyan) !important; background: var(--surface) !important; border: 1px solid var(--neon-cyan); border-radius: 18px;')

    # In-Game UI Section
    with ui.card().classes("w-full p-3 md:p-4").style("background-color: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px;"):
        # Title row with menu button
        with ui.row().classes("items-start justify-between w-full"):
            # Title (left aligned)
            ui.label("In Game UI").classes("text-xs md:text-sm font-semibold").style("color: var(--ink-muted) !important;")

            # Menu button (right aligned with circle)
            with ui.button(
                on_click=lambda: handle_button("vpx", "Menu")
            ).props("flat round").classes("icon-button").style("background-color: var(--surface) !important; border: 1px solid var(--neon-cyan); border-radius: 18px;"):
                ui.icon("menu", size="sm").style('color: var(--neon-cyan) !important;')

        # D-pad navigation (all centered vertically)
        with ui.column().classes("items-center gap-1 w-full"):
            # Up arrow
            with ui.button(
                on_click=lambda: handle_button("vpx", "Navigate Up")
            ).props("flat").classes("dpad-button rounded-t-xl"):
                ui.icon("keyboard_arrow_up", size="sm").style('color: var(--neon-cyan) !important; background: var(--surface-soft) !important;')

            # Left, Enter, Right row
            with ui.row().classes("gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Navigate Left")
                ).props("flat").classes("dpad-button rounded-l-xl"):
                    ui.icon("chevron_left", size="sm").style('color: var(--neon-cyan) !important; background: var(--surface-soft) !important;')

                ui.button(
                    "Enter",
                    on_click=lambda: handle_button("vpx", "Enter")
                ).classes("dpad-button text-white font-medium text-[10px] md:text-xs").style('color: var(--neon-cyan) !important; background: var(--surface-soft) !important; border: 1px solid var(--neon-purple);')

                with ui.button(
                    on_click=lambda: handle_button("vpx", "Navigate Right")
                ).props("flat").classes("dpad-button rounded-r-xl"):
                    ui.icon("chevron_right", size="sm").style('color: var(--neon-cyan) !important; background: var(--surface-soft) !important;')

            # Down arrow
            with ui.button(
                on_click=lambda: handle_button("vpx", "Navigate Down")
            ).props("flat").classes("dpad-button rounded-b-xl"):
                ui.icon("keyboard_arrow_down", size="sm").style('color: var(--neon-cyan) !important; background: var(--surface-soft) !important;')

            # Keyboard button (below D-pad)
            ui.button(
                "Keyboard",
                on_click=lambda: show_virtual_keyboard()
            ).classes("remote-button px-6 md:px-8 py-1.5 md:py-2 rounded-lg text-[10px] md:text-xs font-medium mt-2").style("color: var(--ink) !important; background: var(--surface-soft) !important; border: 1px solid var(--neon-purple);")

    # Debug Section
    with ui.card().classes("w-full p-3 md:p-4").style("background-color: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px;"):
        ui.label("Debug").classes("text-center text-xs md:text-sm font-semibold mb-2 md:mb-3").style("color: var(--ink-muted) !important;")
        with ui.row().classes("items-center justify-center gap-3 md:gap-4 w-full"):
            # Debugger
            with ui.column().classes("items-center gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Debugger")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("bug_report", size="sm").style("color: var(--neon-yellow) !important;")
                ui.label("Debugger").classes("text-[10px] md:text-xs").style("color: var(--ink-muted) !important;")

            # Debug Balls
            with ui.column().classes("items-center gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Debug Balls")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("circle", size="sm").style("color: var(--ink-muted) !important;")
                ui.label("Debug Balls").classes("text-[10px] md:text-xs").style("color: var(--ink-muted) !important;")

            # Performance Overlay
            with ui.column().classes("items-center gap-1"):
                with ui.button(
                    on_click=lambda: handle_button("vpx", "Performance Overlay")
                ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                    ui.icon("speed", size="sm").style("color: var(--neon-purple) !important;")
                ui.label("Perf Overlay").classes("text-[10px] md:text-xs text-gray-400").style("color: var(--ink-muted) !important;")


def show_vpx_game_controls():
    """VPX Game control layout"""

    # Main Section
    with ui.card().classes("w-full p-3 md:p-4").style("background-color: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px;"):
        ui.label("Main").classes("text-center text-xs md:text-sm font-semibold mb-2 md:mb-3").style("color: var(--ink-muted) !important;")
        with ui.column().classes("items-center gap-2 w-full"):
            # Icon buttons row: Start, Pause, and Quit
            with ui.row().classes("items-center justify-center gap-3 md:gap-4 w-full"):
                # Start
                with ui.column().classes("items-center gap-1"):
                    with ui.button(
                        on_click=lambda: handle_button("vpx game", "Start")
                    ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                        ui.icon("play_arrow", size="sm").style("color: var(--ok) !important;")
                    ui.label("Start").classes("text-[10px] md:text-xs").style("color: var(--ink-muted) !important;")

                # Pause
                with ui.column().classes("items-center gap-1"):
                    with ui.button(
                        on_click=lambda: handle_button("vpx game", "Pause")
                    ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                        ui.icon("pause", size="sm").style("color: var(--neon-cyan) !important;")
                    ui.label("Pause").classes("text-[10px] md:text-xs").style("color: var(--ink-muted) !important;")

                # Quit
                with ui.column().classes("items-center gap-1"):
                    with ui.button(
                        on_click=lambda: handle_button("vpx game", "Quit")
                    ).props("flat round").classes("icon-button").style("font-size: 18px;"):
                        ui.icon("power_settings_new", size="sm").style("color: var(--bad) !important;")
                    ui.label("Quit").classes("text-[10px] md:text-xs").style("color: var(--ink-muted) !important;")

            # Row with ShowRules, ExtraBall, Lockbar
            with ui.row().classes("items-center justify-center gap-2 w-full"):
                with ui.button(
                    on_click=lambda: handle_button("vpx game", "ShowRules")
                ).classes("remote-button px-3 md:px-4 py-1.5 md:py-2 rounded-lg text-[10px] md:text-xs font-medium flex items-center gap-1").style("color: var(--ink) !important; background: var(--surface-soft) !important; border: 1px solid var(--neon-purple);"):
                    ui.icon("description", size="xs").style("color: var(--neon-cyan) !important;")
                    ui.label("Show Rules").classes("text-[10px] md:text-xs")

                with ui.button(
                    on_click=lambda: handle_button("vpx game", "ExtraBall")
                ).classes("remote-button px-3 md:px-4 py-1.5 md:py-2 rounded-lg text-[10px] md:text-xs font-medium flex items-center gap-1").style("color: var(--ink) !important; background: var(--surface-soft) !important; border: 1px solid var(--neon-purple);"):
                    ui.icon("sports_baseball", size="xs").style("color: var(--neon-yellow) !important;")
                    ui.label("Extra Ball").classes("text-[10px] md:text-xs")

                with ui.button(
                    on_click=lambda: handle_button("vpx game", "Lockbar")
                ).classes("remote-button px-3 md:px-4 py-1.5 md:py-2 rounded-lg text-[10px] md:text-xs font-medium flex items-center gap-1").style("color: var(--ink) !important; background: var(--surface-soft) !important; border: 1px solid var(--neon-purple);"):
                     ui.icon("fiber_manual_record", size="xs").style("color: var(--bad) !important;")
                     ui.label("Fire!").classes("text-[10px] md:text-xs")

    # Coins Section
    with ui.card().classes("w-full p-3 md:p-4").style("background-color: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px;"):
        ui.label("Coins").classes("text-center text-xs md:text-sm font-semibold mb-2 md:mb-3").style("color: var(--ink-muted) !important;")

        with ui.grid(columns=2).classes("gap-2 w-full justify-items-center"):
            for i in range(1, 5):
                with ui.button(
                    on_click=lambda num=i: handle_button("vpx game", f"Credit{num}")
                ).classes("remote-button px-4 md:px-6 py-2 rounded-lg text-xs md:text-sm font-medium flex items-center gap-1").style("color: var(--ink) !important; background: var(--surface-soft) !important; border: 1px solid var(--neon-purple);"):
                    ui.icon("paid", size="xs").style("color: var(--neon-yellow) !important;")
                    ui.label(f"Credit {i}").classes("text-xs md:text-sm")

    # Launch Table Section
    with ui.card().classes("w-full p-3 md:p-4").style("background-color: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px;"):
        ui.label("Launch Table").classes("text-center text-xs md:text-sm font-semibold mb-2 md:mb-3").style("color: var(--ink-muted) !important;")

        # State for the selection - also store UI element references
        launch_state = {'tables': [], 'all_options': {}, 'filtered_options': {}, 'collection': 'All', 'last_term': ''}
        ui_refs = {}

        # Dropdown and launch button row (first)
        with ui.row().classes("w-full items-center gap-2 mb-2"):
            # Dropdown select for tables
            table_select = ui.select(
                options=[],
                on_change=lambda e: None
            ).props(
                "outlined dense options-dense dark behavior='menu' menu-anchor='top left' menu-self='bottom left'"
            ).classes("flex-grow").style(
                "min-width: 0; background: var(--surface) !important; border-radius: 8px;"
            )
            ui_refs['table_select'] = table_select

            # Launch button
            def do_launch():
                selected = ui_refs['table_select'].value
                if selected:
                    # Find the table by vpx_path (which is the value)
                    table = next((t for t in launch_state['tables'] if t['vpx_path'] == selected), None)
                    if table:
                        _launch_table(table)
                    else:
                        ui.notify('Please select a table first', type='warning')
                else:
                    ui.notify('Please select a table first', type='warning')

            with ui.button(on_click=do_launch).props("flat round dense").classes("icon-button").style(
                "width: 40px !important; height: 40px !important; background: var(--surface-soft) !important;"
            ):
                ui.icon("play_arrow", size="sm").style("color: var(--ok) !important;")

        def apply_collection_filter():
            """Apply collection filter to get base options."""
            collection = launch_state.get('collection', 'All')
            if collection == 'All':
                # Use all tables
                launch_state['filtered_options'] = {
                    t['vpx_path']: t['display_name'] for t in launch_state['tables']
                }
            elif _is_filter_collection(collection):
                # Filter-based collection
                filters = _get_collection_filters(collection)
                launch_state['filtered_options'] = {
                    t['vpx_path']: t['display_name']
                    for t in launch_state['tables']
                    if _table_matches_filters(t, filters)
                }
            else:
                # VPSId-based collection
                vpsids = _get_collection_vpsids(collection)
                launch_state['filtered_options'] = {
                    t['vpx_path']: t['display_name']
                    for t in launch_state['tables']
                    if t.get('vpsid') in vpsids
                }

        def on_collection_change(e):
            launch_state['collection'] = e.value
            apply_collection_filter()
            # Clear search and update table list
            ui_refs['filter_input'].value = ''
            launch_state['last_term'] = ''
            ui_refs['table_select'].options = launch_state['filtered_options']
            if launch_state['filtered_options']:
                first_key = next(iter(launch_state['filtered_options']))
                ui_refs['table_select'].value = first_key
            else:
                ui_refs['table_select'].value = None
            ui_refs['table_select'].update()

        # Collections dropdown (with label above)
        ui.label("Collection").classes("text-xs mb-1").style("color: var(--ink-muted) !important;")
        collection_select = ui.select(
            options=['All'],
            value='All',
            on_change=on_collection_change
        ).props(
            "outlined dense options-dense dark behavior='menu'"
        ).classes("w-full mb-2").style(
            "background: var(--surface) !important; border-radius: 8px;"
        )
        ui_refs['collection_select'] = collection_select

        # Search/filter input (below collections dropdown)
        filter_input = debounced_input(ui.input(
            placeholder="Search/Filter..."
        )).props("outlined dense clearable dark").classes("w-full").style(
            "background: var(--surface) !important; border-radius: 8px;"
        )
        ui_refs['filter_input'] = filter_input

        async def on_filter(e):
            term = (e.value or '').lower().strip()
            last_term = launch_state.get('last_term', '')
            launch_state['last_term'] = term

            # Use filtered_options (collection-filtered) as base
            base_options = launch_state.get('filtered_options', launch_state['all_options'])

            if not term:
                # Show all options from collection and select first
                table_select.options = base_options
                if base_options:
                    first_key = next(iter(base_options))
                    table_select.value = first_key
                else:
                    table_select.value = None
            else:
                # Filter options by search term - limit to first 10 matches
                filtered = {k: v for k, v in base_options.items()
                           if term in v.lower()}
                filtered_limited = dict(list(filtered.items())[:10])
                table_select.options = filtered_limited
                # Auto-select first match
                if filtered_limited:
                    first_key = next(iter(filtered_limited))
                    table_select.value = first_key
                    # Only open dropdown when adding characters (not deleting)
                    if len(term) > len(last_term):
                        table_select.run_method('showPopup')
                        await ui.run_javascript('''
                            setTimeout(() => {
                                document.querySelector('[placeholder="Search/Filter..."]').focus();
                            }, 100);
                        ''')
                else:
                    table_select.value = None
            table_select.update()

        filter_input.on_value_change(on_filter)

        # Launch on Enter key
        def on_enter():
            if table_select.value:
                table = next((t for t in launch_state['tables'] if t['vpx_path'] == table_select.value), None)
                if table:
                    _launch_table(table)

        filter_input.on('keydown.enter', on_enter)

        # Load tables and collections on first render
        async def load_tables():
            # Load collections
            collections = await run.io_bound(_get_collections)
            collection_options = ['All'] + list(collections)
            logger.debug("Setting collection options: %s", collection_options)
            collection_select.options = collection_options
            collection_select.update()

            # Load tables
            tables = await run.io_bound(_scan_tables_for_launch)
            launch_state['tables'] = tables
            # Build options as dict: {vpx_path: display_name}
            options = {t['vpx_path']: t['display_name'] for t in tables}
            launch_state['all_options'] = options
            launch_state['filtered_options'] = options
            table_select.options = options
            # Select first table by default
            if options:
                first_key = next(iter(options))
                table_select.value = first_key
            table_select.update()

        # Trigger initial load
        ui.timer(0.1, load_tables, once=True)


def show_pinmame_controls():
    """PinMAME remote control layout"""

    with ui.card().classes("w-full p-3 md:p-4").style("background-color: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px;"):
        ui.label("Service Menu Navigation").classes("text-center text-xs md:text-sm font-semibold mb-2 md:mb-3").style("color: var(--ink-muted) !important;")

        # Three column layout: Coin Door | Up/Down | Enter/Cancel
        with ui.row().classes("items-center justify-center gap-4 w-full flex-nowrap"):
            # Left column: Coin Door (centered vertically)
            with ui.column().classes("items-center justify-center flex-shrink-0"):
                with ui.button(
                    on_click=lambda: handle_button("pinmame", "Coin Door")
                ).props("flat").classes("dpad-button").style("background-color: var(--surface-soft) !important; border: 1px solid var(--line) !important;"):
                    ui.icon("meeting_room", size="sm").style("color: var(--neon-cyan) !important;")

            # Middle column: Up/Down
            with ui.column().classes("items-center justify-center gap-2 flex-shrink-0"):
                # Up
                with ui.button(
                    on_click=lambda: handle_button("pinmame", "Up")
                ).props("flat").classes("dpad-button rounded-t-xl").style("background-color: var(--surface-soft) !important; border: 1px solid var(--line) !important;"):
                    ui.icon("keyboard_arrow_up", size="sm").style("color: var(--ok) !important;")

                # Down
                with ui.button(
                    on_click=lambda: handle_button("pinmame", "Down")
                ).props("flat").classes("dpad-button rounded-b-xl").style("background-color: var(--surface-soft) !important; border: 1px solid var(--line) !important;"):
                    ui.icon("keyboard_arrow_down", size="sm").style("color: var(--ok) !important;")

            # Right column: Enter/Cancel (side by side)
            with ui.column().classes("items-center justify-center gap-2 flex-shrink-0"):
                with ui.row().classes("gap-2 flex-nowrap"):
                    # Enter
                    ui.button(
                        "Enter",
                        on_click=lambda: handle_button("pinmame", "Enter")
                    ).classes("dpad-button font-bold text-[10px] md:text-xs px-3").style("color: var(--ok) !important; background: var(--surface-soft) !important; border: 1px solid var(--line) !important;")

                    # Cancel
                    with ui.button(
                        on_click=lambda: handle_button("pinmame", "Cancel")
                    ).props("flat").classes("dpad-button").style("color: var(--bad) !important; background: var(--surface-soft) !important; border: 1px solid var(--line) !important;"):
                        ui.icon("close", size="sm").style("color: var(--bad) !important;")

    # Services Section
    with _remote_section("Service Buttons"):
        with ui.grid(columns=4).classes("gap-2 w-full justify-items-center"):
            for action in PINMAME_SERVICE_CONTROLS:
                ui.button(
                    action.label,
                    on_click=lambda a=action: handle_button("pinmame", a.command)
                ).classes("remote-button px-3 py-2 rounded-lg text-[10px] md:text-xs font-medium").style("color: var(--ink) !important; background: var(--surface-soft) !important; border: 1px solid var(--line) !important;")


def show_other_controls():
    """Other controls layout"""

    with _remote_section("System Controls"):
        with ui.grid(columns=3).classes("gap-4 w-full justify-items-center"):
            for action in SYSTEM_CONTROLS:
                _labeled_icon_action("other", action)


def show_virtual_keyboard():
    """Show a virtual keyboard dialog"""
    Key = _get_key_class()
    with ui.dialog() as keyboard_dialog, ui.card().classes("p-4 w-[90vw] max-w-[500px]").style("background: var(--surface) !important;"):
        ui.label("Virtual Keyboard").classes("text-xl font-bold mb-4").style("color: var(--ink) !important;")

        # Common keys layout
        keyboard_layout = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
            ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
            ['Z', 'X', 'C', 'V', 'B', 'N', 'M'],
        ]

        for row in keyboard_layout:
            with ui.row().classes("gap-1 justify-center w-full"):
                for key in row:
                    ui.button(
                        key,
                        on_click=lambda k=key, d=keyboard_dialog: send_keyboard_key(k, d)
                    ).classes("px-3 py-2 rounded text-sm min-w-[40px]").style("color: var(--ink) !important; background: var(--surface-soft) !important;")

        # Special keys row
        with ui.row().classes("gap-2 justify-center w-full mt-2"):
            ui.button(
                "Space",
                on_click=lambda d=keyboard_dialog: send_keyboard_key(Key.space, d)
            ).classes("px-6 py-2 rounded text-sm").style("color: var(--ink) !important; background: var(--surface-soft) !important;")

            ui.button(
                "Enter",
                on_click=lambda d=keyboard_dialog: send_keyboard_key(Key.enter, d)
            ).classes("px-6 py-2 rounded text-sm").style("color: var(--ink) !important; background: var(--surface-soft) !important;")

            ui.button(
                "Backspace",
                on_click=lambda d=keyboard_dialog: send_keyboard_key(Key.backspace, d)
            ).classes("px-4 py-2 rounded text-sm").style("color: var(--ink) !important; background: var(--surface-soft) !important;")

        # Close button
        with ui.row().classes("justify-center w-full mt-4"):
            ui.button(
                "Close",
                on_click=keyboard_dialog.close
            ).classes("px-8 py-2 rounded").style('color: var(--neon-purple) !important; background: var(--surface) !important; border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;')

    keyboard_dialog.open()


def send_keyboard_key(key, dialog):
    """Send a keyboard key press through KeySimulator"""
    Key = _get_key_class()
    # Handle Key objects vs strings
    if isinstance(key, Key):
        key_name = key.name
    else:
        key_name = key

    logger.info("Virtual keyboard: Pressing key '%s'", key_name)
    _get_keysimulator().press(key)
    # Keep dialog open for multiple key presses
    # If you want to close after each key, uncomment the next line:
    # dialog.close()


def handle_button(category: str, button: str):
    logger.info("[%s] Button pressed: %s", category, button)
    sim = _get_keysimulator()
    Key = _get_key_class()
    KeySimulator = _get_keysimulator_class()
    match category:
        case 'vpx maintenance' | 'vpx':
            match button:
                case 'Performance Overlay': sim.press_mapping("PerfOverlay")
                case 'Volume Up': sim.press_mapping("VolumeUp", seconds=0.1)
                case 'Volume Down': sim.press_mapping("VolumeDown", seconds=0.1)
                case 'Toggle Stereo': sim.press_mapping("ToggleStereo")
                case 'Menu': sim.press_mapping("InGameUI")
                case 'Table Reset': sim.press_mapping("Reset")
                case 'Quit': sim.press_mapping("ExitGame")
                case 'Pause': sim.press_mapping("Pause")
                case 'Extra Ball': sim.press_mapping("ExtraBall")
                case 'Debugger': sim.press_mapping("Debugger")
                case 'Debug Balls': sim.press_mapping("DebugBalls")
                case 'Navigate Up': sim.hold_mapping("LeftMagna", seconds=0.1)
                case 'Navigate Down': sim.hold_mapping("RightMagna", seconds=0.1)
                case 'Navigate Left': sim.hold_mapping("LeftFlipper", seconds=0.1)
                case 'Navigate Right': sim.hold_mapping("RightFlipper", seconds=0.1)
                case 'Enter': sim.hold(Key.enter, seconds=0.1)
        case 'vpx game':
            match button:
                case 'Start': sim.hold_mapping("Start")
                case 'Pause': sim.press_mapping("Pause")
                case 'Quit': sim.press_mapping("ExitGame")
                case 'ShowRules': sim.press_mapping("ShowRules")
                case 'ExtraBall': sim.press_mapping("ExtraBall")
                case 'Lockbar': sim.press_mapping("Lockbar")
                case 'Credit1': sim.press_mapping("Credit1")
                case 'Credit2': sim.press_mapping("Credit2")
                case 'Credit3': sim.press_mapping("Credit3")
                case 'Credit4': sim.press_mapping("Credit4")
        case 'pinmame':
            match button:
                case 'Coin Door': sim.press(KeySimulator.PINMAME_OPEN_COIN_DOOR)
                case 'Cancel': sim.hold(KeySimulator.PINMAME_CANCEL)
                case 'Down': sim.hold(KeySimulator.PINMAME_DOWN, seconds=0.1)
                case 'Up': sim.hold(KeySimulator.PINMAME_UP, seconds=0.1)
                case 'Enter': sim.hold(KeySimulator.PINMAME_ENTER, seconds=0.1)
                case 'Service 1': sim.press_mapping("Service1")
                case 'Service 2': sim.press_mapping("Service2")
                case 'Service 3': sim.press_mapping("Service3")
                case 'Service 4': sim.press_mapping("Service4")
                case 'Service 5': sim.press_mapping("Service5")
                case 'Service 6': sim.press_mapping("Service6")
                case 'Service 7': sim.press_mapping("Service7")
                case 'Service 8': sim.press_mapping("Service8")
        case 'other':
            match button:
                case 'Restart VPinFE': _restart_app()
                case 'Reboot': _show_reboot_confirmation()
                case 'Shutdown': _show_shutdown_confirmation()
                case _:
                    logger.info("Other category pressed: %s", button)
