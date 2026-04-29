from __future__ import annotations

import logging
import shlex
from urllib.parse import quote

from nicegui import run, ui

from common.iniconfig import IniConfig
from common.vpinplay_service import sync_installed_tables
from managerui.config_fields import is_checkbox_field
from managerui.pages.vpinfe_config import get_friendly_name
from managerui.paths import VPINFE_INI_PATH
from managerui.ui_helpers import load_page_style


logger = logging.getLogger("vpinfe.manager.vpinplay")

INI_PATH = VPINFE_INI_PATH
VPINPLAY_BASE_URL = "https://www.vpinplay.com/"
SECTION = "vpinplay"


def _build_vpinplay_user_url(user_id: str) -> str:
    uid = (user_id or "").strip()
    if not uid:
        return f"{VPINPLAY_BASE_URL}players.html"
    return f"{VPINPLAY_BASE_URL}players.html?userid={quote(uid)}"


def render_panel():
    config = IniConfig(str(INI_PATH))
    load_page_style("vpinfe_config.css")

    if not config.config.has_section(SECTION):
        config.config.add_section(SECTION)

    inputs = {SECTION: {}}
    sync_vpinplay_button = None
    vpinplay_user_link = None

    def _input_value(key: str, fallback: str = "") -> str:
        return str(
            getattr(inputs[SECTION].get(key), "value", config.config.get(SECTION, key, fallback=fallback))
            or ""
        ).strip()

    def update_vpinplay_user_link():
        if vpinplay_user_link is None:
            return
        vpinplay_user_link.text = "Your Stats"
        vpinplay_user_link.props(f"href={_build_vpinplay_user_url(_input_value('userid'))}")

    def update_vpinplay_sync_button_state():
        if sync_vpinplay_button is None:
            return
        if _input_value("userid") and _input_value("initials"):
            sync_vpinplay_button.enable()
        else:
            sync_vpinplay_button.disable()

    def build_config_input(key: str, value: str):
        friendly_label = get_friendly_name(key)
        is_checkbox = is_checkbox_field(SECTION, key)

        with ui.element("div").classes("config-field-card compact" if is_checkbox else "config-field-card"):
            if not is_checkbox:
                ui.label(friendly_label).classes("config-field-label")

            if is_checkbox:
                inp = ui.checkbox(text=friendly_label, value=(value == "true")).classes("config-input")
            else:
                inp = ui.input(value=value).props("outlined dense").classes("config-input")
                if key == "machineid":
                    inp.props("readonly disable")
                if key == "initials":
                    inp.props("maxlength=3").classes("config-uppercase-input")

                    def on_initials_change(e):
                        normalized = str(e.value or "").upper()
                        if inp.value != normalized:
                            inp.value = normalized
                        update_vpinplay_sync_button_state()

                    inp.on("input", on_initials_change)
                    inp.on_value_change(on_initials_change)

            inputs[SECTION][key] = inp
            if key == "userid":
                inp.on_value_change(lambda _: (update_vpinplay_user_link(), update_vpinplay_sync_button_state()))

    def save_config():
        for key, inp in inputs[SECTION].items():
            if type(inp.value) is bool:
                config.config.set(SECTION, key, str(inp.value).lower())
            else:
                value = inp.value
                if key == "initials":
                    value = str(value or "").upper()
                    inp.value = value
                config.config.set(SECTION, key, value)
        with open(INI_PATH, "w") as f:
            config.config.write(f)
        update_vpinplay_sync_button_state()
        ui.notify("VPinPlay settings saved", type="positive")

    def show_live_command_dialog(title: str, command: list[str]):
        with ui.dialog().props("persistent max-width=1000px") as dlg, ui.card().classes("w-full").style(
            "background: var(--surface); border: 1px solid var(--line); min-width: min(92vw, 900px);"
        ):
            ui.label(title).classes("text-xl font-bold").style("color: var(--ink) !important;")
            command_label = ui.label(shlex.join(command)).classes("text-xs break-all").style(
                "color: var(--ink-muted) !important;"
            )
            status_label = ui.label("Running...").classes("text-sm").style("color: var(--neon-yellow) !important;")
            output_area = ui.textarea(value="Starting sync...").props("readonly outlined").classes("w-full").style(
                "height: 420px; font-family: monospace;"
            )
            with ui.row().classes("w-full justify-end mt-2"):
                close_button = ui.button("Close", on_click=dlg.close).style(
                    "color: var(--neon-purple) !important; background: var(--surface) !important; "
                    "border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;"
                )
                close_button.disable()
        dlg.open()
        return command_label, status_label, output_area, close_button

    async def run_vpinplay_sync():
        service_ip = _input_value("apiendpoint")
        user_id = _input_value("userid")
        initials = _input_value("initials")
        machine_id = _input_value("machineid")
        tables_dir = config.config.get("Settings", "tablerootdir", fallback="").strip()

        if not service_ip:
            ui.notify("API Endpoint is required.", type="warning")
            return
        if not user_id:
            ui.notify("User ID is required.", type="warning")
            return
        if not initials:
            ui.notify("Initials is required.", type="warning")
            return
        if not machine_id:
            ui.notify("Machine ID is required.", type="warning")
            return
        if not tables_dir:
            ui.notify("Tables Directory is required in Configuration > Settings.", type="warning")
            return

        command_label, status_label, output_area, close_button = show_live_command_dialog(
            "VPinPlay Sync",
            ["POST", service_ip],
        )
        sync_vpinplay_button.disable()
        sync_vpinplay_button.text = "Syncing..."
        try:
            result = await run.io_bound(
                sync_installed_tables,
                service_ip,
                user_id,
                initials,
                machine_id,
                tables_dir,
            )
            output_area.value = (
                f"Scanned: {result['tables_scanned']}\n"
                f"Sent: {result['tables_sent']}\n"
                f"Skipped (missing VPSId): {result['tables_skipped']}\n\n"
                f"HTTP status: {result['status_code']}\n\n"
                f"{result['response_body']}"
            )
            command_label.text = shlex.join(["POST", result["endpoint"]])
            status_label.text = f"Exit code: {0 if result['ok'] else 1}"
            ui.notify("Sync completed." if result["ok"] else "Sync failed. See output for details.", type="positive" if result["ok"] else "negative")
        except Exception as e:
            logger.exception("Failed to run VPinPlay sync")
            status_label.text = "Failed to start sync."
            output_area.value = str(e)
            ui.notify("Failed to start sync.", type="negative")
        finally:
            close_button.enable()
            sync_vpinplay_button.text = "Sync Installed Tables"
            update_vpinplay_sync_button_state()

    options = config.config.options(SECTION)
    sync_key = "synconexit"
    endpoint_key = "apiendpoint"
    user_key = "userid"
    initials_key = "initials"
    machine_key = "machineid"

    with ui.column().classes("w-full config-page-shell"):
        with ui.card().classes("w-full config-hero").style("overflow: hidden;"):
            with ui.element("div").classes("w-full config-vpinplay-links p-6"):
                ui.image("/static/img/VPinPlay_Logo_1.0.png").style(
                    "width: 200px; height: 200px; object-fit: contain;"
                )
                with ui.column().classes("config-vpinplay-links-copy"):
                    ui.link("VPinPlay Home", VPINPLAY_BASE_URL, new_tab=True).style(
                        "color: var(--neon-cyan) !important;"
                    )
                    vpinplay_user_link = ui.link(
                        "",
                        _build_vpinplay_user_url(config.config.get(SECTION, user_key, fallback="")),
                        new_tab=True,
                    ).style("color: var(--neon-cyan) !important;")
                update_vpinplay_user_link()

        with ui.element("div").classes("config-panel-shell w-full"):
            with ui.card().classes("config-card w-full p-4"):
                with ui.element("div").classes("config-vpinplay-pair"):
                    with ui.column().classes("w-full gap-3"):
                        with ui.card().classes("config-side-card w-full p-4"):
                            ui.label("VPinPlay Settings").classes("text-lg font-semibold").style(
                                "color: var(--ink) !important;"
                            )
                            ui.label(
                                "Configure the VPinPlay service endpoint and cabinet identity."
                            ).classes("text-sm").style("color: var(--ink-muted) !important;")
                            with ui.element("div").classes("config-form-grid mt-3"):
                                if endpoint_key in options:
                                    build_config_input(endpoint_key, config.config.get(SECTION, endpoint_key, fallback=""))
                                if user_key in options:
                                    build_config_input(user_key, config.config.get(SECTION, user_key, fallback=""))
                                if initials_key in options:
                                    build_config_input(initials_key, config.config.get(SECTION, initials_key, fallback=""))
                                if machine_key in options:
                                    build_config_input(machine_key, config.config.get(SECTION, machine_key, fallback=""))
                                if sync_key in options:
                                    build_config_input(sync_key, config.config.get(SECTION, sync_key, fallback="false"))

                        for key in options:
                            if key in (sync_key, endpoint_key, user_key, initials_key, machine_key):
                                continue
                            build_config_input(key, config.config.get(SECTION, key, fallback=""))

                    with ui.column().classes("w-full gap-3"):
                        with ui.card().classes("config-side-card w-full p-4"):
                            ui.label("Table Metadata Sync").classes("text-lg font-semibold").style(
                                "color: var(--ink) !important;"
                            )
                            ui.label(
                                "Sends installed table metadata to the configured VPinPlay service endpoint."
                            ).classes("text-sm text-slate-300")
                            sync_vpinplay_button = ui.button(
                                "Sync Installed Tables",
                                icon="sync",
                                on_click=run_vpinplay_sync,
                            ).classes("mt-3").style(
                                "color: var(--neon-purple) !important; background: var(--surface) !important; "
                                "border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;"
                            )
                            update_vpinplay_sync_button_state()

        with ui.element("div").classes("w-full config-footer-bar"):
            ui.button("Save Changes", icon="save", on_click=save_config).classes("px-6 py-3").style(
                "color: var(--neon-purple) !important; background: var(--surface) !important; "
                "border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;"
            )
