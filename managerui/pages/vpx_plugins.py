from __future__ import annotations

import logging
from pathlib import Path

from nicegui import ui

from managerui.services import plugin_profile_service, vpx_config_service
from managerui.services.plugin_profile_service import (
    DEFAULT_PROFILE_NAME,
    PLUGIN_PROFILES_DIR,
)
from managerui.ui_helpers import load_page_style, attach_shell_save_bar


logger = logging.getLogger("vpinfe.manager.vpx_plugins")


def _plugin_store_dialog() -> None:
    with ui.dialog() as dialog, ui.card().classes("w-full").style(
        "background: var(--surface); border: 1px solid var(--line); min-width: min(92vw, 460px);"
    ):
        with ui.column().classes("w-full items-center gap-4 p-2"):
            ui.icon("storefront", size="46px").style("color: var(--neon-pink) !important;")
            ui.label("Plugin Store").classes("text-xl font-bold").style(
                "color: var(--ink) !important;"
            )
            ui.label("Coming Soon....").classes("text-base").style(
                "color: var(--ink-muted) !important;"
            )

        with ui.row().classes("w-full justify-end"):
            ui.button("Close", on_click=dialog.close).style(
                "color: var(--ink-muted) !important; background: var(--surface) !important; "
                "border: 1px solid var(--line); border-radius: 18px; padding: 4px 10px;"
            )

    dialog.open()


def _error_card(title: str, detail: str) -> None:
    with ui.card().classes("w-full p-5").style(
        "background: var(--surface); border: 1px solid var(--line);"
    ):
        ui.label(title).classes("text-lg font-semibold").style("color: var(--bad) !important;")
        ui.label(detail).classes("text-sm").style("color: var(--ink-muted) !important;")


def render_panel() -> None:
    # Reuse the VPX Config stylesheet so both pages share one visual language;
    # vpx_plugins.css only adds the profile bar and per-plugin frame on top.
    load_page_style("vpx_config.css")
    load_page_style("vpx_plugins.css")

    try:
        vpx_ini_path = vpx_config_service.load_vpx_ini_path()
    except Exception:
        logger.exception("Failed to read vpxinipath from vpinfe.ini")
        vpx_ini_path = None

    with ui.column().classes("w-full vpx-config-shell"):
        with ui.card().classes("w-full vpx-config-hero").style("overflow: hidden;"):
            with ui.row().classes("w-full items-center justify-between p-6 gap-6"):
                with ui.row().classes("items-center gap-4"):
                    ui.icon("extension", size="34px").style("color: var(--ink) !important;")
                    with ui.column().classes("gap-1"):
                        ui.label("Plugin Profiles").classes("vpx-config-kicker")
                        ui.label("VPX-Plugins").classes("text-2xl font-bold").style(
                            "color: var(--ink) !important;"
                        )
                        ui.label(
                            "Edit the Plugin.* settings for a profile. Saving writes to the selected profile only."
                        ).classes("text-sm").style("color: var(--ink-muted) !important;")
                with ui.column().classes("items-end gap-1"):
                    ui.label("Profile File").classes("text-xs font-semibold").style(
                        "color: var(--ink-muted) !important;"
                    )
                    target_label = ui.label("").classes("text-sm text-right break-all").style(
                        "color: var(--ink) !important;"
                    )
                    ui.button(
                        "Plugin Store", icon="storefront", on_click=_plugin_store_dialog
                    ).classes("mt-2").style(
                        "color: var(--neon-pink) !important; background: var(--surface) !important; "
                        "border: 1px solid var(--neon-pink); border-radius: 18px; padding: 4px 14px;"
                    )

        if vpx_ini_path is None:
            _error_card(
                "`vpxinipath` is not set in vpinfe.ini.",
                "Set `Settings.vpxinipath` on the Configuration page first, then reopen VPX-Plugins.",
            )
            return

        if not vpx_ini_path.exists():
            _error_card("Configured VPinballX.ini file was not found.", str(vpx_ini_path))
            return

        state: dict = {
            "profile": DEFAULT_PROFILE_NAME,
            "path": vpx_ini_path,
            "sections": [],
        }
        inputs: dict[str, dict[str, ui.input]] = {}

        def collect_values() -> dict[str, dict[str, str]]:
            return {
                section: {key: getattr(inp, "value", "") for key, inp in section_inputs.items()}
                for section, section_inputs in inputs.items()
            }

        def load_profile(name: str) -> bool:
            path = plugin_profile_service.profile_path(name)
            if path is None or not path.exists():
                ui.notify(f'Profile "{name}" could not be found on disk.', type="negative")
                return False
            try:
                sections = plugin_profile_service.load_plugin_sections(path)
            except Exception as exc:
                logger.exception("Failed to parse profile %s", path)
                ui.notify(f"Failed to read profile: {exc}", type="negative")
                return False

            state["profile"] = name
            state["path"] = path
            state["sections"] = sections
            inputs.clear()
            target_label.set_text(str(path))
            render_plugins.refresh()
            update_save_bar()
            return True

        def on_profile_change(event) -> None:
            name = str(event.value or "")
            if not name or name == state["profile"]:
                return
            previous = state["profile"]
            if not load_profile(name):
                # Snap the dropdown back so it can't display a profile we failed to load.
                profile_select.set_value(previous)

        def save_profile() -> None:
            path: Path = state["path"]
            try:
                vpx_config_service.write_updated_ini(path, state["sections"], collect_values())
                # Re-parse so line indices stay accurate for the next save; any
                # keys we just inserted shift everything below them.
                state["sections"] = plugin_profile_service.load_plugin_sections(path)
                ui.notify(f'Saved profile "{state["profile"]}" to {path.name}', type="positive")
            except Exception as exc:
                logger.exception("Failed to save profile %s", path)
                ui.notify(f"Failed to save profile: {exc}", type="negative")

        def new_profile_dialog() -> None:
            with ui.dialog() as dialog, ui.card().classes("w-full").style(
                "background: var(--surface); border: 1px solid var(--line); min-width: min(92vw, 520px);"
            ):
                with ui.column().classes("w-full gap-4"):
                    ui.label("New Plugin Profile").classes("text-xl font-bold").style(
                        "color: var(--ink) !important;"
                    )
                    ui.label(
                        "The new profile starts as a full copy of VPinballX.ini and is saved as "
                        "{name}.ini in your plugin_profiles folder."
                    ).classes("text-sm").style("color: var(--ink-muted) !important;")
                    ui.label(str(PLUGIN_PROFILES_DIR)).classes("text-xs break-all").style(
                        "color: var(--ink-muted) !important;"
                    )
                    name_input = ui.input(
                        label="Profile Name",
                        placeholder="Example: no-dmd",
                    ).props("outlined clearable autofocus").classes("w-full")

                def _create() -> None:
                    try:
                        created = plugin_profile_service.create_profile(str(name_input.value or ""))
                    except ValueError as exc:
                        ui.notify(str(exc), type="negative")
                        return
                    except Exception as exc:
                        logger.exception("Failed to create plugin profile")
                        ui.notify(f"Failed to create profile: {exc}", type="negative")
                        return

                    dialog.close()
                    profile_select.set_options(
                        plugin_profile_service.list_profiles(),
                        value=state["profile"],
                    )
                    # set_value fires on_profile_change, which loads the new copy.
                    profile_select.set_value(created.stem)
                    ui.notify(f'Created profile "{created.stem}"', type="positive")

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=dialog.close).style(
                        "color: var(--ink-muted) !important; background: var(--surface) !important; "
                        "border: 1px solid var(--line); border-radius: 18px; padding: 4px 10px;"
                    )
                    ui.button("Create", icon="add", on_click=_create).style(
                        "color: var(--neon-cyan) !important; background: var(--surface) !important; "
                        "border: 1px solid var(--neon-cyan); border-radius: 18px; padding: 4px 10px;"
                    )

            name_input.on("keydown.enter", _create)
            dialog.open()

        with ui.card().classes("w-full p-4").style(
            "background: var(--surface); border: 1px solid var(--line);"
        ):
            with ui.row().classes("w-full items-center gap-4"):
                ui.label("Profile:").classes("text-sm font-semibold shrink-0").style(
                    "color: var(--ink) !important;"
                )
                profile_select = (
                    ui.select(
                        plugin_profile_service.list_profiles(),
                        value=DEFAULT_PROFILE_NAME,
                        on_change=on_profile_change,
                    )
                    .props("outlined dense options-dense")
                    .classes("vpx-plugins-profile-select")
                )
                ui.space()
                ui.button("New", icon="add", on_click=new_profile_dialog).style(
                    "color: var(--neon-purple) !important; background: var(--surface) !important; "
                    "border: 1px solid var(--neon-purple); border-radius: 18px; padding: 4px 14px;"
                )
            ui.label(
                f'"{DEFAULT_PROFILE_NAME}" edits VPinballX.ini directly and applies to all tables. '
                f"Custom profiles are stored in {PLUGIN_PROFILES_DIR}."
            ).classes("text-sm").style("color: var(--ink-muted) !important;")

        @ui.refreshable
        def render_plugins() -> None:
            if not state["sections"]:
                with ui.card().classes("w-full p-5").style(
                    "background: var(--surface); border: 1px solid var(--line);"
                ):
                    ui.label("No Plugin.* sections were found in this profile.").classes(
                        "text-lg font-semibold"
                    ).style("color: var(--warn) !important;")
                    ui.label(str(state["path"])).classes("text-sm break-all").style(
                        "color: var(--ink-muted) !important;"
                    )
                return

            for section in state["sections"]:
                name = section["name"]
                inputs.setdefault(name, {})
                with ui.element("div").classes("w-full vpx-plugins-group"):
                    with ui.row().classes("items-center gap-2 vpx-plugins-group-header"):
                        ui.icon("extension", size="20px").style("color: var(--neon-cyan) !important;")
                        ui.label(name).classes("vpx-plugins-group-title")
                        ui.label(
                            f'{len(section["fields"])} setting{"s" if len(section["fields"]) != 1 else ""}'
                        ).classes("vpx-plugins-group-count")

                    with ui.element("div").classes("vpx-config-panel vpx-plugins-frame w-full"):
                        if not section["fields"]:
                            ui.label("This plugin has no settings in the profile.").classes(
                                "text-sm"
                            ).style("color: var(--ink-muted) !important;")
                            continue
                        with ui.element("div").classes("vpx-config-grid"):
                            for plugin_field in section["fields"]:
                                with ui.element("div").classes("vpx-config-field"):
                                    ui.label(plugin_field.key).classes("vpx-config-key")
                                    ui.label(plugin_field.label or plugin_field.key).classes(
                                        "vpx-config-label"
                                    )
                                    ui.label(
                                        plugin_field.description
                                        or "Blank value lets VPX fall back to its default."
                                    ).classes("vpx-config-help")
                                    if plugin_field.default_text:
                                        ui.label(plugin_field.default_text).classes("vpx-config-default")
                                    inp = ui.input(
                                        value=plugin_field.value,
                                        placeholder="Blank = VPX default",
                                    ).props("outlined dense").classes("w-full vpx-config-input")
                                    inputs[name][plugin_field.key] = inp
                                    inp.on_value_change(lambda _: update_save_bar())

        # --- Save bar (shared shell footer) --------------------------------
        # Baseline is each field's loaded value; the status names the profile so
        # it's clear which profile a save writes to.
        def _norm(value):
            return "" if value is None else str(value)

        def changed_count():
            count = 0
            for section in state["sections"]:
                name = section["name"]
                for field in section["fields"]:
                    inp = inputs.get(name, {}).get(field.key)
                    if inp is None:
                        continue
                    if _norm(inp.value).strip() != _norm(field.value).strip():
                        count += 1
            return count

        def on_discard():
            for section in state["sections"]:
                name = section["name"]
                for field in section["fields"]:
                    inp = inputs.get(name, {}).get(field.key)
                    if inp is not None:
                        inp.value = field.value

        update_save_bar = attach_shell_save_bar(
            count=changed_count,
            on_save=save_profile,
            on_discard=on_discard,
            target_label=lambda: state["profile"],
        )

        load_profile(DEFAULT_PROFILE_NAME)
        render_plugins()
        update_save_bar()
