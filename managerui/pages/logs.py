from __future__ import annotations

import html
from pathlib import Path

from nicegui import ui

from common.config_access import SettingsConfig
from common.iniconfig import IniConfig
from common.vpx_log import resolve_vpinball_log_path
from managerui.paths import CONFIG_DIR, VPINFE_INI_PATH
from managerui.ui_helpers import load_page_style


def _read_log_file(log_path: Path) -> tuple[str, str]:
    try:
        content = log_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = "(log file not found)"
    except Exception as exc:
        content = f"Failed to read log file: {exc}"
    return str(log_path), content


def _get_vpinfe_log_path() -> Path:
    return CONFIG_DIR / "vpinfe.log"


def _get_vpinball_log_path() -> Path | None:
    try:
        config = IniConfig(str(VPINFE_INI_PATH))
        settings = SettingsConfig.from_config(config)
    except Exception:
        return None

    return resolve_vpinball_log_path(settings.vpx_ini_path)


def _get_delete_on_start_enabled() -> bool:
    try:
        config = IniConfig(str(VPINFE_INI_PATH))
        return SettingsConfig.from_config(config).vpx_log_delete_on_start
    except Exception:
        return False


def _set_delete_on_start_enabled(value: bool) -> None:
    config = IniConfig(str(VPINFE_INI_PATH))
    config.config.set("Settings", "vpxlogdeleteonstart", "true" if value else "false")
    config.save()


def render_panel():
    load_page_style("vpinfe_config.css")

    def set_log_content(path_label, log_body, log_path: Path | None):
        if log_path is None:
            path_label.set_text("Settings.vpxinipath is not set in vpinfe.ini")
            log_body.set_content(
                '<pre style="margin:0; padding:12px; white-space:pre-wrap; word-break:break-word; '
                'font-family:monospace; font-size:12px; color:var(--ink);">(log path unavailable)</pre>'
            )
            return

        log_path_text, content = _read_log_file(log_path)
        path_label.set_text(log_path_text)
        log_body.set_content(
            f'<pre style="margin:0; padding:12px; white-space:pre-wrap; word-break:break-word; '
            f'font-family:monospace; font-size:12px; color:var(--ink);">{html.escape(content)}</pre>'
        )

    def show_log_dialog(title: str, log_path: Path | None):
        with ui.dialog().props("persistent max-width=1100px") as dlg, ui.card().classes("w-full").style(
            "background: var(--surface); border: 1px solid var(--line); min-width: min(92vw, 1000px); height: 82vh;"
        ):
            with ui.column().classes("w-full h-full gap-3"):
                ui.label(title).classes("text-xl font-bold").style("color: var(--ink) !important;")
                path_label = ui.label("").classes("text-xs break-all").style("color: var(--ink-muted) !important;")
                with ui.scroll_area().classes("w-full").style(
                    "flex: 1 1 auto; min-height: 0; border: 1px solid var(--neon-purple); "
                    "border-radius: 8px; background: var(--surface);"
                ):
                    log_body = ui.html("").classes("w-full")
                with ui.row().classes("w-full justify-end gap-3"):
                    ui.button("Refresh", icon="refresh", on_click=lambda: set_log_content(path_label, log_body, log_path)).style(
                        "color: var(--neon-cyan) !important; background: var(--surface) !important; "
                        "border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;"
                    )
                    ui.button("Close", on_click=dlg.close).style(
                        "color: var(--neon-purple) !important; background: var(--surface) !important; "
                        "border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;"
                    )
            set_log_content(path_label, log_body, log_path)
        dlg.open()

    def show_vpinfe_log():
        show_log_dialog("VPinFE Log", _get_vpinfe_log_path())

    def show_vpinball_log():
        show_log_dialog("VPinball Log", _get_vpinball_log_path())

    def delete_vpinball_log():
        log_path = _get_vpinball_log_path()
        if log_path is None:
            ui.notify("Settings.vpxinipath is not set in vpinfe.ini.", type="warning")
            return

        with ui.dialog() as dlg, ui.card().classes("w-full").style(
            "background: var(--surface); border: 1px solid var(--line); min-width: min(92vw, 520px);"
        ):
            ui.label("Delete VPinball Log?").classes("text-xl font-bold").style("color: var(--ink) !important;")
            ui.label(str(log_path)).classes("text-xs break-all").style("color: var(--ink-muted) !important;")
            ui.label(
                "This removes the current vpinball.log file. VPinball may recreate it the next time it writes logs."
            ).classes("text-sm").style("color: var(--ink-muted) !important;")

            def confirm_delete():
                try:
                    log_path.unlink()
                except FileNotFoundError:
                    ui.notify("vpinball.log was already missing.", type="warning")
                except Exception as exc:
                    ui.notify(f"Failed to delete vpinball.log: {exc}", type="negative")
                else:
                    ui.notify("vpinball.log deleted.", type="positive")
                dlg.close()

            with ui.row().classes("w-full justify-end gap-3 mt-3"):
                ui.button("Cancel", on_click=dlg.close).style(
                    "color: var(--neon-cyan) !important; background: var(--surface) !important; "
                    "border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;"
                )
                ui.button("Delete", icon="delete", on_click=confirm_delete).style(
                    "color: var(--bad) !important; background: var(--surface) !important; "
                    "border: 1px solid var(--bad); border-radius: 18px; padding: 4px 10px;"
                )
        dlg.open()

    vpinball_log_path = _get_vpinball_log_path()
    vpinball_log_description = (
        f"VPinball writes logs to {vpinball_log_path}."
        if vpinball_log_path is not None
        else "Set Settings.vpxinipath in vpinfe.ini so VPinball log location can be found."
    )
    delete_on_start_enabled = _get_delete_on_start_enabled()

    def update_delete_on_start(event):
        try:
            _set_delete_on_start_enabled(bool(event.value))
        except Exception as exc:
            ui.notify(f"Failed to save vpxlogdeleteonstart: {exc}", type="negative")
        else:
            state = "enabled" if event.value else "disabled"
            ui.notify(f"Delete VPinball Log on table start {state}.", type="positive")

    with ui.column().classes("w-full config-page-shell"):
        with ui.card().classes("w-full config-hero").style("overflow: hidden;"):
            with ui.row().classes("w-full items-center justify-between p-6 gap-6"):
                with ui.row().classes("items-center gap-4"):
                    ui.icon("article", size="34px").style("color: var(--ink) !important;")
                    with ui.column().classes("gap-1"):
                        ui.label("Logs").classes("text-2xl font-bold").style("color: var(--ink) !important;")
                        ui.label(
                            "Open application and Visual Pinball log files when you need them."
                        ).classes("text-sm").style("color: var(--neon-cyan) !important;")

        with ui.element("div").classes("config-panel-shell w-full"):
            with ui.element("div").classes("config-display-form-grid"):
                with ui.card().classes("config-side-card w-full p-4"):
                    ui.label("VPinFE Log").classes("text-lg font-semibold").style("color: var(--ink) !important;")
                    ui.label(
                        f"VPinFE writes the current session log to {_get_vpinfe_log_path()}."
                    ).classes("text-sm").style("color: var(--ink-muted) !important;")
                    ui.button("View VPinFE Log", icon="article", on_click=show_vpinfe_log).classes("mt-3").style(
                        "color: var(--neon-purple) !important; background: var(--surface) !important; "
                        "border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;"
                    )

                with ui.card().classes("config-side-card w-full p-4"):
                    ui.label("VPinball Log").classes("text-lg font-semibold").style("color: var(--ink) !important;")
                    ui.label(vpinball_log_description).classes("text-sm").style("color: var(--ink-muted) !important;")
                    ui.switch(
                        "Delete VPinball Log before each table start",
                        value=delete_on_start_enabled,
                        on_change=update_delete_on_start,
                    ).props("color=cyan").classes("mt-3").style("color: var(--ink) !important;")
                    with ui.row().classes("items-center gap-3 mt-3"):
                        ui.button("View VPinball Log", icon="sports_esports", on_click=show_vpinball_log).style(
                            "color: var(--neon-purple) !important; background: var(--surface) !important; "
                            "border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 10px;"
                        )
                        ui.button("Delete VPinball Log", icon="delete", on_click=delete_vpinball_log).style(
                            "color: var(--bad) !important; background: var(--surface) !important; "
                            "border: 1px solid var(--bad); border-radius: 18px; padding: 4px 10px;"
                        )
