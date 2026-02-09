from nicegui import ui, run, context
from common.themes import ThemeRegistry, ThemeRegistryError
from common.iniconfig import IniConfig
from pathlib import Path
from platformdirs import user_config_dir
from managerui.pages.remote import _restart_app

CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
INI_PATH = CONFIG_DIR / 'vpinfe.ini'

# Module-level registry cache
_registry: ThemeRegistry | None = None


def _get_active_theme() -> str:
    """Get the currently active theme name from config."""
    try:
        config = IniConfig(str(INI_PATH))
        return config.config.get('Settings', 'theme', fallback='default')
    except Exception:
        return 'default'


def _set_active_theme(theme_key: str):
    """Set the active theme in config (blocking)."""
    config = IniConfig(str(INI_PATH))
    config.config.set('Settings', 'theme', theme_key)
    with open(INI_PATH, 'w') as f:
        config.config.write(f)


def _load_registry() -> ThemeRegistry:
    """Load or reload the theme registry (blocking)."""
    reg = ThemeRegistry()
    reg.load_registry()
    reg.load_theme_manifests()
    return reg


def _install_theme(registry: ThemeRegistry, theme_key: str):
    """Install a theme (blocking)."""
    registry.install_theme(theme_key, force=True)


def _delete_theme(registry: ThemeRegistry, theme_key: str):
    """Delete a theme (blocking)."""
    registry.delete_theme(theme_key)


def render_panel(tab=None):
    global _registry

    ui.add_head_html('''
    <style>
        .theme-card {
            background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%) !important;
            border: 1px solid #334155 !important;
            border-radius: 12px !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2) !important;
            transition: all 0.2s ease !important;
        }
        .theme-card:hover {
            border-color: #3b82f6 !important;
            box-shadow: 0 8px 12px -2px rgba(59, 130, 246, 0.15) !important;
        }
        .theme-card-active {
            border: 2px solid #22c55e !important;
            box-shadow: 0 0 16px rgba(34, 197, 94, 0.25) !important;
        }
        .theme-card-active:hover {
            border-color: #4ade80 !important;
            box-shadow: 0 0 20px rgba(34, 197, 94, 0.35) !important;
        }
        .theme-preview-wrap {
            position: relative;
            overflow: visible;
            z-index: 1;
        }
        .theme-preview-wrap:hover {
            z-index: 100;
        }
        .theme-preview {
            width: 100%;
            max-height: 180px;
            object-fit: cover;
            border-radius: 8px;
            border: 1px solid #334155;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            transform-origin: left center;
        }
        .theme-preview:hover {
            transform: scale(2);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.5);
            z-index: 100;
        }
        .theme-badge {
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-installed {
            background: #065f46;
            color: #6ee7b7;
        }
        .badge-update {
            background: #78350f;
            color: #fcd34d;
        }
        .badge-available {
            background: #1e3a5f;
            color: #93c5fd;
        }
        .badge-active {
            background: #4c1d95;
            color: #c4b5fd;
        }
        .badge-type {
            background: #374151;
            color: #d1d5db;
        }
    </style>
    ''')

    # Container references
    cards_container = None
    loading_container = None
    active_theme = _get_active_theme()

    with ui.column().classes('w-full'):
        # Header card
        with ui.card().classes('w-full mb-4').style(
            'background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); '
            'border-radius: 12px;'
        ):
            with ui.row().classes('w-full justify-between items-center p-4 gap-4'):
                with ui.row().classes('items-center gap-3'):
                    ui.icon('palette', size='32px').classes('text-white')
                    ui.label('Themes').classes('text-2xl font-bold text-white')

                refresh_btn = ui.button('Refresh Registry', icon='refresh',
                                        on_click=lambda: do_refresh()).props('color=primary rounded')

        # Loading spinner area
        loading_container = ui.column().classes('w-full items-center justify-center').style('min-height: 200px;')
        loading_container.visible = False

        with loading_container:
            ui.spinner('dots', size='48px', color='blue')
            ui.label('Loading theme registry...').classes('text-slate-400 mt-2')

        # Cards container
        cards_container = ui.column().classes('w-full gap-4')

    def _build_theme_cards():
        """Rebuild the theme cards from current registry data."""
        nonlocal active_theme
        active_theme = _get_active_theme()

        with cards_container:
            cards_container.clear()

            if not _registry or not _registry.get_themes():
                with ui.card().classes('theme-card w-full p-6'):
                    ui.label('No themes found in registry.').classes('text-slate-400')
                return

            updates = {}
            try:
                updates = _registry.check_for_updates()
            except Exception:
                pass

            # Sort themes: active first, then installed, then the rest
            sorted_themes = sorted(
                _registry.get_themes().items(),
                key=lambda item: (
                    0 if item[0] == active_theme else 1,
                    0 if _registry.is_installed(item[0]) else 1,
                    item[0],
                )
            )

            for theme_key, theme_data in sorted_themes:
                manifest = theme_data.get('manifest', {})
                registry_info = theme_data.get('registry_info', {})
                is_installed = _registry.is_installed(theme_key)
                is_default = registry_info.get('default_install', False)
                update_info = updates.get(theme_key, {})
                has_update = update_info.get('update_available', False) and is_installed
                installed_version = update_info.get('installed_version', None)
                remote_version = update_info.get('remote_version', manifest.get('version', '?'))
                is_active = (theme_key == active_theme)

                card_classes = 'theme-card w-full'
                if is_active:
                    card_classes += ' theme-card-active'
                with ui.card().classes(card_classes):
                    with ui.row().classes('w-full gap-8 p-4'):
                        # Left: Preview image
                        # preview_image is a filename (e.g. "preview.png") relative to the theme root
                        preview_filename = manifest.get('preview_image', '')
                        preview_url = ''
                        if preview_filename:
                            if preview_filename.startswith('http'):
                                preview_url = preview_filename
                            elif is_installed:
                                # Serve from local /themes/ mount
                                preview_url = f'/themes/{theme_key}/{preview_filename}'
                            else:
                                # Build raw GitHub URL from manifest_url
                                manifest_url = registry_info.get('theme_manifest_url', '')
                                if manifest_url:
                                    raw_base = manifest_url.rsplit('/', 1)[0]
                                    preview_url = f'{raw_base}/{preview_filename}'
                        if preview_url:
                            with ui.element('div').classes('theme-preview-wrap').style(
                                'width: 280px; min-width: 280px; max-width: 280px;'
                            ):
                                ui.image(preview_url).classes('theme-preview')
                        else:
                            with ui.column().classes('items-center justify-center').style(
                                'width: 280px; min-width: 280px; height: 180px; '
                                'background: #1a2744; border-radius: 8px; border: 1px solid #334155;'
                            ):
                                ui.icon('image_not_supported', size='48px').classes('text-slate-600')

                        # Right: Info + optional Change log side by side
                        with ui.row().classes('flex-grow gap-6'):
                            # Meta data column
                            with ui.column().classes('gap-2'):
                                # Name + badges row
                                with ui.row().classes('items-center gap-2 flex-wrap'):
                                    ui.label(manifest.get('name', theme_key)).classes(
                                        'text-xl font-bold text-white'
                                    )

                                    # GitHub repo link
                                    repo_url = registry_info.get('theme_base_url', '')
                                    if repo_url:
                                        ui.html(
                                            f'<a href="{repo_url}" target="_blank" rel="noopener" '
                                            f'title="View on GitHub" '
                                            f'style="color: #94a3b8; text-decoration: none; display: inline-flex; align-items: center; padding: 2px;" '
                                            f'onmouseover="this.style.color=\'#60a5fa\'" onmouseout="this.style.color=\'#94a3b8\'">'
                                            f'<span class="material-icons" style="font-size: 20px;">open_in_new</span></a>'
                                        )

                                    # Status badge
                                    if is_active:
                                        ui.html('<span class="theme-badge badge-active">Active</span>')
                                    if is_installed and has_update:
                                        ui.html('<span class="theme-badge badge-update">Update Available</span>')
                                    elif is_installed:
                                        ui.html('<span class="theme-badge badge-installed">Installed</span>')
                                    else:
                                        ui.html('<span class="theme-badge badge-available">Not Installed</span>')

                                    # Type badge
                                    theme_type = manifest.get('type', '')
                                    if theme_type:
                                        ui.html(f'<span class="theme-badge badge-type">{theme_type}</span>')

                                    # Built-in badge
                                    if is_default:
                                        ui.html('<span class="theme-badge badge-type">Built-in</span>')

                                # Author
                                with ui.row().classes('items-center gap-2'):
                                    ui.icon('person', size='16px').classes('text-slate-400')
                                    ui.label(manifest.get('author', 'Unknown')).classes('text-sm text-slate-300')

                                # Description
                                desc = manifest.get('description', '')
                                if desc:
                                    ui.label(desc).classes('text-sm text-slate-400')

                                # Version info
                                with ui.row().classes('items-center gap-2'):
                                    ui.icon('label', size='16px').classes('text-slate-400')
                                    if is_installed and installed_version:
                                        version_text = f'v{installed_version}'
                                        if has_update:
                                            version_text += f'  ->  v{remote_version}'
                                        ui.label(version_text).classes('text-sm text-slate-300')
                                    else:
                                        ui.label(f'v{remote_version}').classes('text-sm text-slate-300')

                                # Supported screens
                                screens = manifest.get('supported_screens')
                                if screens is not None:
                                    with ui.row().classes('items-center gap-2'):
                                        ui.icon('monitor', size='16px').classes('text-slate-400')
                                        if isinstance(screens, list):
                                            screen_count = len(screens)
                                            screen_names = ', '.join(str(s) for s in screens)
                                            ui.label(f'{screen_count} screen{"s" if screen_count != 1 else ""}: {screen_names}').classes('text-sm text-slate-300')
                                        else:
                                            screen_count = int(screens)
                                            ui.label(f'{screen_count} screen{"s" if screen_count != 1 else ""}').classes('text-sm text-slate-300')

                                # Action buttons
                                with ui.row().classes('gap-2 mt-2 items-center'):
                                    if not is_installed:
                                        _make_install_btn(theme_key, 'Install', 'download')
                                    elif has_update:
                                        _make_install_btn(theme_key, 'Update', 'system_update_alt')
                                    if is_installed and not is_active:
                                        _make_activate_btn(theme_key)
                                    if is_installed and not is_default:
                                        _make_delete_btn(theme_key)

                            # Change log column (sits right next to meta, expands as needed)
                            change_log = manifest.get('change_log', '')
                            if change_log and (not is_installed or has_update):
                                with ui.column().classes('gap-2 self-start').style(
                                    'background: rgba(120, 53, 15, 0.2); '
                                    'border: 1px solid #78350f; border-radius: 8px; '
                                    'padding: 12px;'
                                ):
                                    with ui.row().classes('items-center gap-2'):
                                        ui.icon('new_releases', size='16px').classes('text-yellow-400')
                                        ui.label('What\'s new:').classes('text-sm font-semibold text-yellow-300')
                                    ui.label(change_log).classes('text-sm text-slate-300')

    def _make_install_btn(theme_key: str, label: str, icon: str):
        """Create an install/update button for a theme."""
        async def do_install():
            btn.disable()
            btn.text = 'Installing...'
            try:
                await run.io_bound(_install_theme, _registry, theme_key)
                ui.notify(f'Theme "{theme_key}" installed successfully', type='positive')
                _build_theme_cards()
            except Exception as e:
                ui.notify(f'Failed to install: {e}', type='negative')
            finally:
                btn.enable()

        btn = ui.button(label, icon=icon, on_click=do_install).props('color=primary rounded no-wrap').style('padding: 6px 20px;')

    def _make_activate_btn(theme_key: str):
        """Create a 'Set as Active' button for a theme."""
        async def do_activate():
            confirm_dlg.close()
            btn.disable()
            try:
                await run.io_bound(_set_active_theme, theme_key)
                ui.notify(f'Theme "{theme_key}" set as active — restarting...', type='positive')
                _restart_app()
            except Exception as e:
                ui.notify(f'Failed to set theme: {e}', type='negative')
                btn.enable()

        with ui.dialog() as confirm_dlg, ui.card().style(
            'background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%); '
            'border: 1px solid #334155; min-width: 350px;'
        ):
            ui.label(f'Set "{theme_key}" as active theme?').classes('text-lg font-bold text-white')
            ui.label('VPinFE will restart to apply the new theme.').classes('text-sm text-slate-400 mt-1')
            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=confirm_dlg.close).props('flat')
                ui.button('Set & Restart', icon='restart_alt', on_click=do_activate).props(
                    'color=purple rounded'
                )

        btn = ui.button('Set as Active', icon='check_circle', on_click=confirm_dlg.open).props(
            'color=purple rounded no-wrap'
        ).style('padding: 6px 20px;')

    def _make_delete_btn(theme_key: str):
        """Create a delete button with confirmation for a theme."""
        async def do_delete():
            btn.disable()
            try:
                await run.io_bound(_delete_theme, _registry, theme_key)
                ui.notify(f'Theme "{theme_key}" deleted', type='positive')
                _build_theme_cards()
            except ThemeRegistryError as e:
                ui.notify(str(e), type='warning')
            except Exception as e:
                ui.notify(f'Failed to delete: {e}', type='negative')
            finally:
                btn.enable()

        async def confirm_and_delete():
            confirm_dlg.close()
            await do_delete()

        with ui.dialog() as confirm_dlg, ui.card().style(
            'background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%); '
            'border: 1px solid #334155; min-width: 350px;'
        ):
            ui.label(f'Delete "{theme_key}"?').classes('text-lg font-bold text-white')
            ui.label('This will remove the theme files from your system.').classes('text-sm text-slate-400 mt-1')
            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('Cancel', on_click=confirm_dlg.close).props('flat')
                ui.button('Delete', icon='delete', on_click=confirm_and_delete).props(
                    'color=negative rounded'
                )

        btn = ui.button('Delete', icon='delete', on_click=confirm_dlg.open).props(
            'color=negative rounded outline no-wrap'
        ).style('padding: 6px 20px;')

    async def do_refresh():
        """Refresh the theme registry from remote."""
        global _registry
        refresh_btn.disable()
        loading_container.visible = True
        cards_container.visible = False

        try:
            _registry = await run.io_bound(_load_registry)
            _build_theme_cards()
            ui.notify('Theme registry refreshed', type='positive')
        except Exception as e:
            ui.notify(f'Failed to load registry: {e}', type='negative')
            with cards_container:
                cards_container.clear()
                with ui.card().classes('theme-card w-full p-6'):
                    with ui.row().classes('items-center gap-3'):
                        ui.icon('cloud_off', size='24px').classes('text-red-400')
                        ui.label(f'Could not load theme registry: {e}').classes('text-slate-400')
        finally:
            loading_container.visible = False
            cards_container.visible = True
            refresh_btn.enable()

    # Initial load — use ui.timer so NiceGUI slot context is preserved
    if _registry:
        _build_theme_cards()
    else:
        ui.timer(0.1, do_refresh, once=True)
