from __future__ import annotations

from datetime import datetime

from nicegui import events, run, ui

from managerui.services import vpinplay_runtime_service
from managerui.ui_helpers import load_page_style


def _format_timestamp(value) -> str:
    try:
        return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def render_panel():
    load_page_style("vpinfe_config.css")

    status_container = None
    current_profile_select = None

    def render_status():
        nonlocal status_container, current_profile_select
        if status_container is None:
            return
        status = vpinplay_runtime_service.get_profile_status()
        status_container.clear()
        with status_container:
            with ui.card().classes("config-side-card w-full p-4"):
                ui.label("Alternate Player Status").classes("text-lg font-semibold").style(
                    "color: var(--ink) !important;"
                )
                profiles = status.get("profiles") or []
                if current_profile_select is not None:
                    current_profile_select.options = {
                        profile.get("profileKey", ""): f"{profile.get('userId', '')} ({profile.get('initials', '')})"
                        for profile in profiles
                    }
                    current_profile_select.value = status.get("activeProfileKey", "")
                    current_profile_select.update()

                if not profiles:
                    ui.label("No alternate VPinPlay players are loaded for this session.").classes("text-sm").style(
                        "color: var(--ink-muted) !important;"
                    )
                    ui.label(
                        "Upload one or more VPinFE-generated QR SVG files to keep a session roster of alternate players until you clear them or VPinFE shuts down."
                    ).classes("text-sm").style("color: var(--ink-muted) !important;")
                    return

                profile = status.get("profile") or {}
                with ui.column().classes("w-full gap-2"):
                    ui.label(f"Loaded Players: {len(profiles)}").style("color: var(--ink-muted) !important;")
                    ui.label(f"User ID: {profile.get('userId', '')}").style("color: var(--ink) !important;")
                    ui.label(f"Initials: {profile.get('initials', '')}").style("color: var(--ink) !important;")
                    if profile.get("sourceName"):
                        ui.label(f"Source File: {profile.get('sourceName', '')}").style(
                            "color: var(--ink-muted) !important;"
                        )
                    if profile.get("activatedAt"):
                        ui.label(f"Activated: {_format_timestamp(profile.get('activatedAt'))}").style(
                            "color: var(--ink-muted) !important;"
                        )
                    ui.label(
                        f"Tracked Session Tables: {int(status.get('active_tables', 0) or 0)}"
                    ).style("color: var(--ink-muted) !important;")
                    ui.label(
                        "While this is active, VPinFE submits the alternate player's post-game VPinPlay data without modifying the machine's real table .info files."
                    ).classes("text-sm").style("color: var(--ink-muted) !important;")

    async def handle_upload(e: events.UploadEventArguments):
        try:
            content = await e.file.read()
            result = await run.io_bound(vpinplay_runtime_service.activate_profile_from_upload, e.file.name, content)
            render_status()
            profile = result.get("profile") or {}
            ui.notify(f"Alternate VPinPlay player activated: {profile.get('userId', '')}", type="positive")
        except Exception as ex:
            ui.notify(f"QR upload failed: {ex}", type="negative")

    def set_current_profile(e):
        try:
            vpinplay_runtime_service.set_current_profile(e.value)
            render_status()
        except Exception as ex:
            ui.notify(f"Could not switch alternate player: {ex}", type="negative")

    def clear_current_profile():
        status = vpinplay_runtime_service.get_profile_status()
        active_profile_key = str(status.get("activeProfileKey", "") or "").strip()
        if not active_profile_key:
            ui.notify("No alternate player is currently selected.", type="warning")
            return
        vpinplay_runtime_service.clear_profile_by_key(active_profile_key)
        render_status()
        ui.notify("Alternate VPinPlay player removed.", type="positive")

    def clear_all_profiles():
        vpinplay_runtime_service.clear_profile()
        render_status()
        ui.notify("All alternate VPinPlay players cleared.", type="positive")

    with ui.column().classes("w-full config-page-shell"):
        with ui.card().classes("w-full config-hero").style("overflow: hidden;"):
            with ui.column().classes("w-full p-6 gap-2"):
                ui.label("Alternate VPinPlay Player").classes("text-2xl font-bold").style(
                    "color: var(--ink) !important;"
                )
                ui.label(
                    "Upload your VPinFE QR code to submit VPinPlay results under an alternate player profile."
                ).classes("text-sm").style("color: var(--ink-muted) !important;")

        with ui.element("div").classes("config-panel-shell w-full"):
            with ui.card().classes("config-card w-full p-4"):
                with ui.element("div").classes("config-vpinplay-pair"):
                    with ui.column().classes("w-full gap-3"):
                        with ui.card().classes("config-side-card w-full p-4"):
                            ui.label("Upload QR Code").classes("text-lg font-semibold").style(
                                "color: var(--ink) !important;"
                            )
                            ui.label(
                                "Use the SVG downloaded from the VPinPlay page. Each upload is kept for this session so you can switch players from the dropdown."
                            ).classes("text-sm").style("color: var(--ink-muted) !important;")
                            ui.upload(
                                label="Upload VPinPlay QR SVG",
                                on_upload=handle_upload,
                                auto_upload=True,
                                max_files=1,
                            ).props('accept=".svg,image/svg+xml" flat bordered').classes("w-full mt-3").style(
                                "background: var(--bg); border: 1px dashed var(--line);"
                            )
                            current_profile_select = ui.select(
                                options={},
                                label="Current Alternate Player",
                                on_change=set_current_profile,
                            ).props("outlined dense").classes("w-full mt-3")
                            with ui.row().classes("w-full gap-3 mt-3"):
                                ui.button("Remove Current Player", icon="person_remove", on_click=clear_current_profile).style(
                                    "color: var(--neon-pink) !important; background: var(--surface) !important; "
                                    "border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 10px;"
                                )
                                ui.button("Clear All Players", icon="groups", on_click=clear_all_profiles).style(
                                    "color: var(--neon-yellow) !important; background: var(--surface) !important; "
                                    "border: 1px solid var(--neon-yellow); border-radius: 18px; padding: 4px 10px;"
                                )

                    with ui.column().classes("w-full gap-3") as status_container:
                        render_status()
