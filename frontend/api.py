import logging

from common import events
from common.deprecations import announce
from common.games.collections_service import (
    get_collection_image_url,
    get_collection_names,
    get_collections_metadata,
)
from common.games.game_metadata import normalize_meta
from common.games.game_repository import ensure_games_loaded
from common.host import launch, launch_state, system_actions
from common.host.display_service import monitors_as_dicts
from common.online.vpinplay_runtime import (
    activate_alternate_profile,
    clear_alternate_profile,
    get_alternate_profile_state,
)
from frontend import (
    config_api,
    game_state,
    input_api,
    last_game,
    metadata_build_service,
    theme_api,
)
from frontend.theme_contract import CURRENT_CONTRACT, declared_contract

logger = logging.getLogger("vpinfe.frontend.api")

_FILTER_OPTION_KEYS = {
    "letters": "letters",
    "themes": "themes",
    "types": "types",
    "manufacturers": "manufacturers",
    "years": "years",
}


API_ALLOWED_METHODS = {
    'get_my_window_name',
    'close_app',
    'shutdown_system',
    'get_monitors',
    'get_games',
    'get_initial_game_index',
    'get_collections',
    'get_collections_metadata',
    'get_collection_image_url',
    'set_games_by_collection',
    'save_filter_collection',
    'get_current_filter_state',
    'get_current_sort_state',
    'get_current_order_state',
    'get_current_collection',
    'get_filter_letters',
    'get_filter_themes',
    'get_filter_types',
    'get_filter_manufacturers',
    'get_filter_years',
    'apply_filters',
    'apply_sort',
    'get_page_index',
    'reset_filters',
    'console_out',
    'get_joymaping',
    'get_keymapping',
    'get_mainmenu_config',
    'set_button_mapping',
    'launch_game',
    'notify_game_selected',
    'get_game_rating',
    'set_game_rating',
    'build_metadata',
    'get_theme_config',
    'get_theme_name',
    'get_media_priorities',
    'get_vpinplay_endpoint',
    'get_temporary_vpinplay_profile',
    'set_temporary_vpinplay_profile',
    'clear_temporary_vpinplay_profile',
    'get_playfield_orientation',
    'get_playfield_rotation',
    'get_splashscreen_enabled',
    'get_audio_muted',
    'set_audio_muted',
    'get_cab_mode',
    'get_theme_assets_port',
    'get_managerui_remote_link',
    'get_managerui_vpinplay_multi_link',
    'get_theme_index_page',
    'send_event',
    'send_event_all_windows',
    'send_event_all_windows_incself',
}



# Themes written before the vocabulary rename call these names. The allowlist carries
# both spellings and __getattr__ forwards the old one, so an existing theme keeps working
# without a contract bump - the payload it gets back is identical either way.
_RENAMED_METHODS = {
    'get_tables': 'get_games',
    'get_initial_table_index': 'get_initial_game_index',
    'set_tables_by_collection': 'set_games_by_collection',
    'launch_table': 'launch_game',
    'notify_table_selected': 'notify_game_selected',
    'get_table_rating': 'get_game_rating',
    'set_table_rating': 'set_game_rating',
    'get_table_orientation': 'get_playfield_orientation',
    'get_table_rotation': 'get_playfield_rotation',
}

API_ALLOWED_METHODS |= set(_RENAMED_METHODS)


class API:

    def __getattr__(self, name):
        """Forward a pre-rename method name to its replacement.

        Only reached when normal lookup fails, so it costs nothing for current names.
        """
        renamed = _RENAMED_METHODS.get(name)
        if renamed is None:
            raise AttributeError(name)
        announce("ws-methods", name)
        return getattr(self, renamed)
    def __init__(self, iniConfig, window_name=None, ws_bridge=None, frontend_browser=None):
        self._iniConfig = iniConfig
        self.window_name = window_name          # 'bg', 'dmd', or 'table'
        self.ws_bridge = ws_bridge              # WebSocketBridge instance
        self.frontend_browser = frontend_browser  # ChromiumManager instance
        self.allGames = ensure_games_loaded()
        self.jsGameDictData = None
        # Track current filter state
        self.current_filters = game_state.default_filter_state()
        # Track current collection
        self.current_collection = None
        # Establish the default view: alphabetical by (article-reordered) title,
        # ascending. Also sets current_sort/current_order. Done here so the
        # initial wheel matches the displayed titles instead of on-disk folder
        # order (which ignores the "The"-moved-to-end renaming).
        self._reset_to_default_view()
        # Check for startup collection
        startup_collection = self._iniConfig.config['Settings'].get('startup_collection', '').strip()
        if startup_collection:
            try:
                self.set_games_by_collection(startup_collection)
            except Exception:
                logger.exception("Could not load startup collection '%s'", startup_collection)

    ####################
    ## Private Functions
    ####################

    def _finish_setup(self):
        pass

    def _normalize_game_meta(self, game):
        return normalize_meta(game.metaConfig)

    def _theme_contract(self) -> int:
        """Which shape the active theme asked for. Read per payload rather than cached,
        so switching themes does not need a restart to take effect."""
        theme_dir = theme_api.resolve_theme_dir(theme_api.get_theme_name(self._iniConfig.config))
        return declared_contract(theme_dir) if theme_dir else CURRENT_CONTRACT

    def _reset_to_default_view(self):
        """Reset the current view to the default order: alphabetical by the
        (article-reordered) title, ascending.

        filteredGames is a fresh shallow copy of allGames so later in-place
        sorts never disturb the master list (the Game objects stay shared, so
        rating/meta updates still propagate). Shared by startup and every reset
        path so they all agree on the default order.
        """
        self.filteredGames = list(self.allGames)
        self.current_sort = 'Alpha'
        self.current_order = 'Ascending'
        game_state.apply_sort(self.filteredGames, self.current_sort, self.current_order)


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

    def get_games(self, reset=False):
        if reset:
            self._reset_to_default_view()
        self.jsGameDictData = game_state.games_json(self.filteredGames,
                                                       self._theme_contract())
        return self.jsGameDictData

    def get_initial_game_index(self):
        # Position the wheel on the last-launched game at startup. Resolved
        # against the current (possibly filtered) view; 0 when disabled or unfound.
        return last_game.resolve_last_game_index(self._iniConfig, self.filteredGames)


    def get_collections(self):
        return get_collection_names()

    def get_collections_metadata(self):
        return get_collections_metadata()

    def get_collection_image_url(self, collection):
        return get_collection_image_url(collection)

    def set_games_by_collection(self, collection):
        """Set filtered games based on collection from collections.ini."""
        game_state.apply_collection(self, collection)

    def save_filter_collection(
        self,
        name,
        letter="All",
        theme="All",
        game_type="All",
        manufacturer="All",
        year="All",
        sort_by="Alpha",
        rating="All",
        rating_or_higher=False,
        order_by="Descending",
    ):
        """Save current filter settings as a named collection."""
        try:
            return game_state.save_current_filter_collection(
                self, name, letter, theme, game_type, manufacturer, year, sort_by, rating, rating_or_higher, order_by
            )
        except ValueError as e:
            return {"success": False, "message": str(e)}

    def get_current_filter_state(self):
        """Return current filter state for UI synchronization."""
        return self.current_filters

    def get_current_sort_state(self):
        """Return current sort state for UI synchronization."""
        return self.current_sort

    def get_current_order_state(self):
        """Return current sort order for UI synchronization."""
        return self.current_order

    def get_current_collection(self):
        """Return current collection name for UI synchronization."""
        return self.current_collection or 'None'

    def _filter_option(self, key: str):
        return game_state.filter_options(self.allGames)[key]

    def get_filter_letters(self):
        return self._filter_option(_FILTER_OPTION_KEYS["letters"])

    def get_filter_themes(self):
        return self._filter_option(_FILTER_OPTION_KEYS["themes"])

    def get_filter_types(self):
        return self._filter_option(_FILTER_OPTION_KEYS["types"])

    def get_filter_manufacturers(self):
        return self._filter_option(_FILTER_OPTION_KEYS["manufacturers"])

    def get_filter_years(self):
        return self._filter_option(_FILTER_OPTION_KEYS["years"])

    def apply_filters(self, letter=None, theme=None, game_type=None, manufacturer=None, year=None, rating=None, rating_or_higher=None):
        """
        Apply VPSdb filters to the full game list.
        These filters work independently of collections.
        Returns the count of filtered games.
        """
        logger.debug(
            "Applying filters: letter=%s, theme=%s, type=%s, manufacturer=%s, year=%s, rating=%s, rating_or_higher=%s",
            letter,
            theme,
            game_type,
            manufacturer,
            year,
            rating,
            rating_or_higher,
        )
        count = game_state.apply_filters(self, letter, theme, game_type, manufacturer, year, rating, rating_or_higher)
        logger.debug("Filtered games count: %s", count)
        return count

    def reset_filters(self):
        """Reset all VPSdb filters back to full game list."""
        self.current_filters = game_state.default_filter_state()
        self._reset_to_default_view()

    def apply_sort(self, sort_type, order_by=None):
        """
        Sort the current filtered games.
        sort_type: 'Alpha', 'Newest', 'LastRun', 'Highest StartCount', or 'RunTime'
        order_by: 'Ascending' or 'Descending'
        Returns the count of sorted games.
        """
        self.current_sort = sort_type
        self.current_order = game_state.normalize_sort_order(order_by, sort_type)
        logger.debug("Applying sort: %s %s", sort_type, self.current_order)

        count = game_state.apply_sort(self.filteredGames, sort_type, self.current_order)
        logger.debug("Sorted %s games by %s %s", count, sort_type, self.current_order)
        return count

    def get_page_index(self, index, direction):
        """
        Compute the target wheel index for a page next/prev request.
        Paging behavior comes from [Input] pagingtype/pagingsize and the
        current sort; see game_state.page_jump_index.
        """
        try:
            index = int(index)
        except (TypeError, ValueError):
            index = 0
        paging_type, page_size = input_api.get_paging_config(self._iniConfig.config)
        return game_state.page_jump_index(
            self.filteredGames, index, direction, self.current_sort, paging_type, page_size
        )

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

    def launch_game(self, index):
        """Launch what the wheel is sitting on.

        The windows hear about it through the bus like everyone else, so nothing
        here has to tell them.
        """
        try:
            game = self.filteredGames[int(index)]
        except Exception:
            logger.warning("Ignoring launch for invalid index: %s", index)
            return {"success": False, "reason": "invalid_index"}

        try:
            launch.launch_game(game, self._iniConfig,
                                source=launch_state.SOURCE_FRONTEND)
        except launch.LaunchUnavailableError as exc:
            logger.warning("Cannot launch %s: %s", game.gameDirName, exc)
            return {"success": False, "reason": str(exc)}
        return {"success": True}

    def notify_game_selected(self, index):
        """Announce that the player moved to this game.

        Whatever reacts - a DOF effect, the real DMD, something not written yet -
        subscribes to the event. Nothing is reported back, because none of it can
        fail in a way the wheel should care about.
        """
        try:
            game = self.filteredGames[int(index)]
        except Exception:
            logger.debug("Ignoring game selection for invalid index: %s", index)
            return {"success": False, "reason": "invalid_index"}

        events.emit(events.GAME_SELECTED, game=game, ini_config=self._iniConfig)
        return {"success": True}

    def get_game_rating(self, index):
        """Get User.Rating for a game index in the current filtered list."""
        return game_state.get_game_rating(self.filteredGames, index)

    def set_game_rating(self, index, rating):
        """Set User.Rating (0-5) for a game index in the current filtered list."""
        result = game_state.set_game_rating(self.filteredGames, index, rating)
        logger.info("Updated User.Rating for %s -> %s", self.filteredGames[index].gameDirName, result["rating"])
        return result

    def build_metadata(self, download_media=True, update_all=False):
        """
        Trigger buildMetaData from the frontend.
        This runs in a background thread and returns progress/log updates via window events.

        Args:
            download_media: Whether to download media files
            update_all: Whether to update all games (even if the .info exists)

        Returns:
            dict with success status and message
        """
        from common.games.metadata_service import build_metadata

        return metadata_build_service.start_build(
            self,
            build_metadata_func=lambda **kwargs: build_metadata(iniconfig=self._iniConfig, **kwargs),
            ensure_games_loaded_func=ensure_games_loaded,
            download_media=download_media,
            update_all=update_all,
        )

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

    def get_media_priorities(self):
        return config_api.get_media_priorities(self._iniConfig.config)

    def get_vpinplay_endpoint(self):
        return config_api.get_vpinplay_endpoint(self._iniConfig.config)

    def get_temporary_vpinplay_profile(self):
        return get_alternate_profile_state()

    def set_temporary_vpinplay_profile(self, payload, source_name=""):
        result = activate_alternate_profile(payload, source_name=source_name)
        self.send_event_all_windows_incself({
            "type": "VPinPlayAlternateProfileChanged",
            "profile": result,
        })
        return result

    def clear_temporary_vpinplay_profile(self):
        result = clear_alternate_profile()
        self.send_event_all_windows_incself({
            "type": "VPinPlayAlternateProfileChanged",
            "profile": result,
        })
        return result

    def get_playfield_orientation(self):
        return config_api.get_playfield_orientation(self._iniConfig.config)

    def get_playfield_rotation(self):
        return config_api.get_playfield_rotation(self._iniConfig.config)

    def get_cab_mode(self):
        return config_api.get_cab_mode(self._iniConfig.config)

    def get_theme_assets_port(self):
        return config_api.get_theme_assets_port(self._iniConfig.config)

    def get_managerui_remote_link(self):
        return config_api.get_managerui_remote_link(self._iniConfig.config)

    def get_managerui_vpinplay_multi_link(self):
        return config_api.get_managerui_vpinplay_multi_link(self._iniConfig.config)

    def get_theme_index_page(self):
        return theme_api.get_theme_index_page(self._iniConfig.config, self.get_my_window_name())
