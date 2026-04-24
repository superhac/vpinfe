import logging
import subprocess
from common import system_actions
from common.table_repository import ensure_tables_loaded
from common.collections_service import get_collection_names
from common.display_service import monitors_as_dicts
from common.dof_service import (
    send_frontend_dof_event,
    start_dof_service_if_enabled,
    stop_dof_service,
)
from common.libdmdutil_service import (
    show_image as show_libdmdutil_image,
    stop_libdmdutil_service,
)
from common.launcher import (
    build_vpx_launch_command,
    get_effective_launcher,
    parse_launch_env_overrides,
    resolve_launch_tableini_override,
)
from common.table_metadata import (
    get_or_create_user_meta,
    meta_file_path,
    normalize_meta,
    persist_table_meta,
)
from common import table_play_service
from frontend import config_api, input_api, launch_service, metadata_build_service, realdmd_service, table_state, theme_api


logger = logging.getLogger("vpinfe.frontend.api")


API_ALLOWED_METHODS = {
    'get_my_window_name',
    'close_app',
    'shutdown_system',
    'get_monitors',
    'get_tables',
    'get_collections',
    'set_tables_by_collection',
    'save_filter_collection',
    'get_current_filter_state',
    'get_current_sort_state',
    'get_current_collection',
    'get_filter_letters',
    'get_filter_themes',
    'get_filter_types',
    'get_filter_manufacturers',
    'get_filter_years',
    'apply_filters',
    'apply_sort',
    'reset_filters',
    'console_out',
    'get_joymaping',
    'get_keymapping',
    'get_mainmenu_config',
    'set_button_mapping',
    'launch_table',
    'update_frontend_dof_for_table',
    'get_table_rating',
    'set_table_rating',
    'build_metadata',
    'get_theme_config',
    'get_theme_name',
    'get_vpinplay_endpoint',
    'get_table_orientation',
    'get_table_rotation',
    'get_splashscreen_enabled',
    'get_audio_muted',
    'set_audio_muted',
    'get_cab_mode',
    'get_theme_assets_port',
    'get_theme_index_page',
    'send_event',
    'send_event_all_windows',
    'send_event_all_windows_incself',
}


class API:
    def __init__(self, iniConfig, window_name=None, ws_bridge=None, frontend_browser=None):
        self._iniConfig = iniConfig
        self.window_name = window_name          # 'bg', 'dmd', or 'table'
        self.ws_bridge = ws_bridge              # WebSocketBridge instance
        self.frontend_browser = frontend_browser  # ChromiumManager instance
        self.allTables = ensure_tables_loaded()
        self.filteredTables = self.allTables
        self.jsTableDictData = None
        # Track current filter state
        self.current_filters = table_state.default_filter_state()
        # Track current sort state
        self.current_sort = 'Alpha'
        # Track current collection
        self.current_collection = None
        # Check for startup collection
        startup_collection = self._iniConfig.config['Settings'].get('startup_collection', '').strip()
        if startup_collection:
            try:
                self.set_tables_by_collection(startup_collection)
            except Exception:
                logger.exception("Could not load startup collection '%s'", startup_collection)

        self._realdmd_updater = realdmd_service.RealDmdUpdater(
            self._iniConfig,
            self.window_name,
            show_libdmdutil_image,
        )

    ####################
    ## Private Functions
    ####################

    def _finish_setup(self):
        pass

    def _normalize_table_meta(self, table):
        return normalize_meta(table.metaConfig)

    def _get_frontend_dof_event_for_table(self, table) -> str:
        return realdmd_service.get_frontend_dof_event_for_table(table)

    def _get_realdmd_image_for_table(self, table):
        return realdmd_service.get_realdmd_image_for_table(table)

    def _queue_realdmd_image_update(self, table_name: str, image_path) -> None:
        self._realdmd_updater.queue_image_update(table_name, image_path)


    ###################
    ## Public Functions
    ###################

    def get_my_window_name(self):
        return self.window_name or "unknown"

    def close_app(self):
        logger.info("close_app called from window '%s'", self.window_name)
        if self.frontend_browser:
            self.frontend_browser.terminate_all()

    def shutdown_system(self):
        """Shutdown the host system (cross-platform) and close frontend windows."""
        logger.info("shutdown_system called from window '%s'", self.window_name)
        system_actions.shutdown_system()
        if self.frontend_browser:
            self.frontend_browser.terminate_all()

    def get_monitors(self):
        return monitors_as_dicts()

    def send_event_all_windows(self, message):
        if self.ws_bridge:
            self.ws_bridge.send_event_all(message, exclude=self.window_name)

    def send_event(self, window_name, message):
        if self.ws_bridge:
            self.ws_bridge.send_event(window_name, message)

    def send_event_all_windows_incself(self, message):
        if self.ws_bridge:
            self.ws_bridge.send_event_all_with_iframe(message)

    def get_tables(self, reset=False):
        if reset:
            self.filteredTables = self.allTables
        self.jsTableDictData = table_state.tables_json(self.filteredTables)
        return self.jsTableDictData


    def get_collections(self):
        return get_collection_names()

    def set_tables_by_collection(self, collection):
        """Set filtered tables based on collection from collections.ini."""
        table_state.apply_collection(self, collection)

    def save_filter_collection(
        self,
        name,
        letter="All",
        theme="All",
        table_type="All",
        manufacturer="All",
        year="All",
        sort_by="Alpha",
        rating="All",
        rating_or_higher=False,
    ):
        """Save current filter settings as a named collection."""
        try:
            return table_state.save_current_filter_collection(
                self, name, letter, theme, table_type, manufacturer, year, sort_by, rating, rating_or_higher
            )
        except ValueError as e:
            return {"success": False, "message": str(e)}

    def get_current_filter_state(self):
        """Return current filter state for UI synchronization."""
        return self.current_filters

    def get_current_sort_state(self):
        """Return current sort state for UI synchronization."""
        return self.current_sort

    def get_current_collection(self):
        """Return current collection name for UI synchronization."""
        return self.current_collection or 'None'

    def get_filter_letters(self):
        """Get available starting letters from ALL tables."""
        return table_state.filter_options(self.allTables)["letters"]

    def get_filter_themes(self):
        """Get available themes from ALL tables."""
        return table_state.filter_options(self.allTables)["themes"]

    def get_filter_types(self):
        """Get available table types from ALL tables."""
        return table_state.filter_options(self.allTables)["types"]

    def get_filter_manufacturers(self):
        """Get available manufacturers from ALL tables."""
        return table_state.filter_options(self.allTables)["manufacturers"]

    def get_filter_years(self):
        """Get available years from ALL tables."""
        return table_state.filter_options(self.allTables)["years"]

    def apply_filters(self, letter=None, theme=None, table_type=None, manufacturer=None, year=None, rating=None, rating_or_higher=None):
        """
        Apply VPSdb filters to the full table list.
        These filters work independently of collections.
        Returns the count of filtered tables.
        """
        logger.debug(
            "Applying filters: letter=%s, theme=%s, type=%s, manufacturer=%s, year=%s, rating=%s, rating_or_higher=%s",
            letter,
            theme,
            table_type,
            manufacturer,
            year,
            rating,
            rating_or_higher,
        )
        count = table_state.apply_filters(self, letter, theme, table_type, manufacturer, year, rating, rating_or_higher)
        logger.debug("Filtered tables count: %s", count)
        return count

    def reset_filters(self):
        """Reset all VPSdb filters back to full table list."""
        self.filteredTables = self.allTables
        self.current_filters = table_state.default_filter_state()

    def apply_sort(self, sort_type):
        """
        Sort the current filtered tables.
        sort_type: 'Alpha', 'Newest', 'LastRun', or 'Highest StartCount'
        Returns the count of sorted tables.
        """
        self.current_sort = sort_type
        logger.debug("Applying sort: %s", sort_type)

        count = table_state.apply_sort(self.filteredTables, sort_type)
        logger.debug("Sorted %s tables by %s", count, sort_type)
        return count

    def console_out(self, output):
        logger.info("Win: %s - %s", self.window_name, output)
        return output

    def get_joymaping(self):
        return input_api.get_joymapping(self._iniConfig.config)

    def get_keymapping(self):
        return input_api.get_keymapping(self._iniConfig.config)

    def get_mainmenu_config(self):
        try:
            return config_api.get_mainmenu_config(self._iniConfig)
        except Exception:
            logger.exception("Failed to reload ini before get_mainmenu_config")
            return {"hideQuitButton": False}

    def set_button_mapping(self, button_name, button_index):
        """Set a gamepad button mapping and save to config."""
        return input_api.set_button_mapping(self._iniConfig, button_name, button_index)

    def launch_table(self, index):
        return launch_service.launch_table(
            self,
            index,
            get_effective_launcher=get_effective_launcher,
            build_vpx_launch_command=build_vpx_launch_command,
            parse_launch_env_overrides=parse_launch_env_overrides,
            resolve_launch_tableini_override=resolve_launch_tableini_override,
            stop_dof_service=stop_dof_service,
            stop_libdmdutil_service=stop_libdmdutil_service,
            start_dof_service_if_enabled=start_dof_service_if_enabled,
            popen=subprocess.Popen,
        )

    def update_frontend_dof_for_table(self, index):
        """Send the configured frontend DOF event for the selected table."""
        try:
            table = self.filteredTables[int(index)]
        except Exception:
            logger.debug("Skipping frontend DOF update for invalid table index: %s", index)
            return {"success": False, "reason": "invalid_index"}

        event_token = self._get_frontend_dof_event_for_table(table)
        event_sent = send_frontend_dof_event(self._iniConfig, event_token)
        realdmd_path = self._get_realdmd_image_for_table(table)
        self._queue_realdmd_image_update(table.tableDirName, realdmd_path)
        resolved_event = event_token if event_token else "random:E900-E990"
        logger.debug(
            "Frontend media update for %s -> event=%s (dof_sent=%s, dmd_queued=%s, image=%s)",
            table.tableDirName,
            resolved_event,
            event_sent,
            True,
            realdmd_path,
        )
        return {
            "success": True,
            "event": resolved_event,
            "sent": event_sent,
            "realdmd_image": str(realdmd_path) if realdmd_path else "",
            "realdmd_sent": False,
            "realdmd_queued": True,
        }

    def get_table_rating(self, index):
        """Get User.Rating for a table index in the current filtered list."""
        return table_state.get_table_rating(self.filteredTables, index)

    def set_table_rating(self, index, rating):
        """Set User.Rating (0-5) for a table index in the current filtered list."""
        result = table_state.set_table_rating(self.filteredTables, index, rating)
        logger.info("Updated User.Rating for %s -> %s", self.filteredTables[index].tableDirName, result["rating"])
        return result

    def _track_table_play(self, table):
        """Track a table play by adding it to the Last Played collection."""
        table_play_service.track_table_play(table)

    def _get_meta_file_path(self, table):
        return meta_file_path(table)

    def _persist_table_meta(self, table, config):
        persist_table_meta(table, config)

    def _get_or_create_user_meta(self, config):
        return get_or_create_user_meta(config)

    def _update_user_score_from_nvram(self, table):
        table_play_service.update_score_from_nvram(table)

    def _increment_user_start_count(self, table):
        table_play_service.increment_start_count(table)

    def _add_user_runtime_minutes(self, table, elapsed_seconds):
        table_play_service.add_runtime_minutes(table, elapsed_seconds)

    def _delete_nvram_if_configured(self, table):
        """Delete the NVRAM .nv file if deletedNVRamOnClose is enabled for this table."""
        table_play_service.delete_nvram_if_configured(table)

    def build_metadata(self, download_media=True, update_all=False):
        """
        Trigger buildMetaData from the frontend.
        This runs in a background thread and returns progress/log updates via window events.

        Args:
            download_media: Whether to download media files
            update_all: Whether to update all tables (even if meta.ini exists)

        Returns:
            dict with success status and message
        """
        from common.metadata_service import build_metadata

        return metadata_build_service.start_build(
            self,
            build_metadata_func=lambda **kwargs: build_metadata(iniconfig=self._iniConfig, **kwargs),
            ensure_tables_loaded_func=ensure_tables_loaded,
            download_media=download_media,
            update_all=update_all,
        )

    def _resolve_theme_dir(self, theme_name):
        """Returns the filesystem path to the theme directory."""
        return theme_api.resolve_theme_dir(theme_name)

    def get_theme_config(self):
        return theme_api.get_theme_config(self._iniConfig.config)

    ###################
    ### For splash page
    ###################

    def get_splashscreen_enabled(self):
        return config_api.get_splashscreen_enabled(self._iniConfig.config)

    def get_audio_muted(self):
        return theme_api.get_audio_muted(self._iniConfig.config)

    def set_audio_muted(self, muted):
        return config_api.set_audio_muted(self, muted)

    def get_theme_name(self):
        return theme_api.get_theme_name(self._iniConfig.config)

    def get_vpinplay_endpoint(self):
        return config_api.get_vpinplay_endpoint(self._iniConfig.config)

    def get_table_orientation(self):
        return config_api.get_table_orientation(self._iniConfig.config)

    def get_table_rotation(self):
        return config_api.get_table_rotation(self._iniConfig.config)

    def get_cab_mode(self):
        return config_api.get_cab_mode(self._iniConfig.config)

    def get_theme_assets_port(self):
        return config_api.get_theme_assets_port(self._iniConfig.config)

    def get_theme_index_page(self):
        return theme_api.get_theme_index_page(self._iniConfig.config, self.get_my_window_name())
