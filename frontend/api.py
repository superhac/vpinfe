"""Everything a theme is allowed to ask for.

The WebSocket bridge dispatches to these methods by name, and only the names in
`API_ALLOWED_METHODS` are reachable - so adding a method here is adding to the theme
contract, and the parity gate holds it to that. Renamed methods keep their old
spelling as an alias rather than breaking a published theme.
"""

import logging

from common import events, lifecycle
from common.config_access import cfg_get
from common.deprecations import announce
from common.games import collection_resolver
from common.games.collections_service import (
    get_collection_image_url,
    get_collection_names,
    get_collections_metadata,
)
from common.games.game_metadata import normalize_meta
from common.games.game_repository import ensure_games_loaded
from common.host import launch, launch_state
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
    lifecycle_host,
    metadata_build_service,
    theme_api,
    theme_windows,
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
    'lifecycle_request',
    'lifecycle_needs_confirmation',
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
    'get_bindings',
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
    'get_playfield_media_rotation',
    'get_theme_assets_port',
    'get_manager_ui_port',
    'get_managerui_remote_link',
    'get_managerui_vpinplay_multi_link',
    'get_theme_index_page',
    # Additive: the contract a theme declared, so vpinfe-core.js can serve the surface
    # that theme asked for rather than every surface at once.
    'get_theme_contract',
    # The windows the theme declared, controller first, so the browser knows which
    # window it is without a hardcoded name.
    'get_theme_windows',
    'send_event',
    'send_event_all_windows',
    'send_event_all_windows_incself',
    # Additive, so no contract bump: a theme that never calls it is unaffected.
    'report_deprecated_use',
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

    """One instance per frontend window. Only methods in API_ALLOWED_METHODS are reachable."""

    def __getattr__(self, name):
        """Forward a pre-rename method name to its replacement.

        Only reached when normal lookup fails, so it costs nothing for current names.
        """
        renamed = _RENAMED_METHODS.get(name)
        if renamed is None:
            raise AttributeError(name)
        announce("ws-methods", name)
        return getattr(self, renamed)

    def report_deprecated_use(self, key, name):
        """Let the browser tell the log it used a legacy name.

        A theme runs in Chromium, so its use of a vpin.* alias is only visible in a
        console nobody reads on a cabinet. The WebSocket methods announce themselves
        here already; without this the eleven JS aliases are the one surface that
        cannot be judged from the machine, which is where they would be retired from.

        vpinfe-core.js calls this once per name. Untrusted input, so it only ever
        reaches announce(), which looks both up in the registry and logs.
        """
        announce(str(key), str(name))
    def __init__(self, iniConfig, window_name=None, ws_bridge=None, frontend_browser=None):
        self._iniConfig = iniConfig
        self.window_name = window_name          # whatever the theme declared
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
        startup_collection = cfg_get(self._iniConfig, 'general', 'startup_collection').strip()
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
        return normalize_meta(game.meta_config)

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
        self._rebuild_entries()

    @property
    def _expanded(self) -> bool:
        """Whether the wheel shows every table of a game or just one.

        Off by default, which is what every theme written so far assumes and what the
        list looked like before a game could offer more than one.
        """
        try:
            return str(self._iniConfig.config["Settings"].get(
                "expandtables", "false")).strip().lower() in ("1", "true", "yes", "on")
        except Exception:
            return False

    def _rebuild_entries(self) -> None:
        """Recompute the view. Called whenever the list or its order changes."""
        games = getattr(self, "filteredGames", []) or []
        self._entries = collection_resolver.entries_for(games, expanded=self._expanded)
        self._entries_source = games

    @property
    def entries(self):
        """What the wheel steps through, and what an index from a theme addresses.

        filteredGames stays the games the filters and sorts work on - those are
        game-level questions. Cached rather than derived per access: notify_game_selected
        fires on every wheel step, and rebuilding a large library there costs milliseconds
        a step.

        Rebuilt automatically when the source list is replaced, so a caller that swaps
        filteredGames cannot leave a stale view behind. An in-place re-sort keeps the
        same object, which is why apply_sort rebuilds explicitly.
        """
        games = getattr(self, "filteredGames", []) or []
        if getattr(self, "_entries", None) is None or self._entries_source is not games:
            self._rebuild_entries()
        return self._entries


    ###################
    ## Public Functions
    ###################

    def get_my_window_name(self):
        return self.window_name or "unknown"

    def _origin(self):
        """This window is the address a confirmation goes back to."""
        return lifecycle.Origin(lifecycle.SURFACE_FRONTEND, self.window_name or "")

    def close_app(self):
        """Quit VPinFE. The 2.x spelling of `lifecycle_request('app', 'stop')`."""
        return self.lifecycle_request(lifecycle.APP, lifecycle.STOP)

    def shutdown_system(self):
        """Power off the host. The 2.x spelling of `lifecycle_request('system', 'stop')`."""
        return self.lifecycle_request(lifecycle.SYSTEM, lifecycle.STOP)

    def lifecycle_needs_confirmation(self, scope, action):
        """Whether to ask the user first, and what to ask - the browser draws the dialog.

        The question is put where the request came from, and the bridge to a window only
        goes one way, so the confirmation happens in the browser and calls back with the
        answer. The wording comes from here so every surface asks the same thing.
        """
        return {
            "confirm": lifecycle_host.wants_confirmation(str(scope)),
            "description": lifecycle.Request(
                str(scope), str(action), self._origin()).describe().capitalize(),
        }

    def lifecycle_request(self, scope, action, reason="", confirmed=False):
        """Start, stop or restart the frontend, VPinFE or the machine.

        `confirmed` is the theme reporting that it already asked. A theme that never
        asks - every 2.x theme - is answered by the core's own fallback, so turning the
        setting on is never defeated by an old theme.

        Returns whether it is going ahead, so a theme can leave its own menu open when
        the user says no.
        """
        try:
            return lifecycle_host.request(
                scope, action, origin=self._origin(), reason=reason,
                already_confirmed=bool(confirmed))
        except ValueError:
            logger.warning("Window '%s' asked to %s the %s, which is not a thing",
                           self.window_name, action, scope)
            return False

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
        else:
            # This is the only place a refresh lands, so it re-derives the view rather
            # than assuming only the payload went stale.
            game_state.refresh_view(self)
        self.jsGameDictData = game_state.games_json(
            self.entries, self._theme_contract(),
            collection=self.current_collection or "", expanded=self._expanded)
        return self.jsGameDictData

    def get_initial_game_index(self):
        # Position the wheel on the last-launched game at startup. Resolved
        # against the current (possibly filtered) view; 0 when disabled or unfound.
        return last_game.resolve_last_game_index(
            self._iniConfig, [e.game for e in self.entries])


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
        self._rebuild_entries()
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
            [e.game for e in self.entries], index, direction, self.current_sort,
            paging_type, page_size
        )

    def console_out(self, output):
        logger.info("Win: %s - %s", self.window_name, output)
        return output

    def get_bindings(self):
        return input_api.get_bindings(self._iniConfig.config)

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
            entry = self.entries[int(index)]
        except Exception:
            logger.warning("Ignoring launch for invalid index: %s", index)
            return {"success": False, "reason": "invalid_index"}

        game = entry.game
        try:
            # The entry names the table, so an expanded list launches the build the
            # player is looking at rather than whatever the game defaults to.
            launch.launch_game(game, self._iniConfig,
                                source=launch_state.SOURCE_FRONTEND,
                                table=entry.filename)
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
            game = self.entries[int(index)].game
        except Exception:
            logger.debug("Ignoring game selection for invalid index: %s", index)
            return {"success": False, "reason": "invalid_index"}

        events.emit(events.GAME_SELECTED, game=game, ini_config=self._iniConfig)
        return {"success": True}

    def get_game_rating(self, index):
        """Get User.Rating for a game index in the current filtered list."""
        return game_state.get_game_rating([e.game for e in self.entries], index)

    def set_game_rating(self, index, rating):
        """Set User.Rating (0-5) for a game index in the current filtered list."""
        games = [e.game for e in self.entries]
        result = game_state.set_game_rating(games, index, rating)
        logger.info("Updated User.Rating for %s -> %s",
                    games[index].gameDirName, result["rating"])
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

    def get_playfield_media_rotation(self):
        return config_api.get_playfield_media_rotation(self._iniConfig.config)

    def get_cab_mode(self):
        return config_api.get_cab_mode(self._iniConfig.config)

    def get_theme_assets_port(self):
        return config_api.get_theme_assets_port(self._iniConfig.config)

    def get_manager_ui_port(self):
        return config_api.get_manager_ui_port(self._iniConfig.config)

    def get_managerui_remote_link(self):
        return config_api.get_managerui_remote_link(self._iniConfig.config)

    def get_managerui_vpinplay_multi_link(self):
        return config_api.get_managerui_vpinplay_multi_link(self._iniConfig.config)

    def get_theme_contract(self):
        return self._theme_contract()

    def get_theme_windows(self):
        theme_dir = theme_api.resolve_theme_dir(theme_api.get_theme_name(self._iniConfig.config))
        return list(theme_windows.declared_windows(theme_dir, self._theme_contract()))

    def get_theme_index_page(self):
        return theme_api.get_theme_index_page(self._iniConfig.config, self.get_my_window_name())
