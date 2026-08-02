# Frontend Runtime Architecture

The frontend starts at `main.py`, but most runtime responsibilities now live in focused modules under `frontend/` and `common/`.

## Startup Flow

1. `main.py` handles executable-only concerns such as platform console behavior, early config/logging setup, and command-line parsing.
2. `frontend.runtime` creates the websocket/API/browser runtime, starts optional startup media sync, builds static mount points, starts the theme asset server, runs the frontend blocking loop, and performs shutdown/restart handling.
3. `frontend.ws_bridge.WebSocketBridge` receives JavaScript calls from theme windows and dispatches only methods listed by `frontend.api.API_ALLOWED_METHODS`.
4. `frontend.api.API` remains the JS-facing facade for theme code. It should stay thin and delegate feature behavior to service modules.

## Core Modules

- `common/paths.py`: shared config paths, `vpinfe.ini`, `collections.ini`, themes directory, and table root lookup.
- `common/games/game.py`: dataclass representation of a parsed table folder.
- `common/games/game_metadata.py`: shared metadata normalization, section lookup, rating/truthy helpers, and metadata persistence.
- `common/games/game_repository.py`: table parser/cache ownership and table row shaping.
- `common/games/gamelistfilters.py`: instance-based table filtering with no hidden singleton state.
- `common/games/collections_service.py`: shared collection manager access and filter-collection helpers.
- `common/games/game_play_service.py`: Last Played tracking, start count, runtime, score update, and NVRAM cleanup.
- `common/host/display_service.py`: shared monitor discovery.
- `common/games/metadata_service.py`: build metadata and VPX patch orchestration shared by CLI, frontend, and Manager UI.
- `common/games/game_report_service.py`: CLI-oriented missing/unknown table reports backed by the shared parser and VPSdb lookup.
- `common/host/system_actions.py`: shared app restart sentinel/execution, clean OS command environment, shutdown, and reboot commands.
- `frontend/game_state.py`: table JSON serialization, filtering, sorting, collections, and rating mutations for the JS API.
- `common/host/launch.py`: VPX launch lifecycle, DOF/DMD stop-start, and frontend launch events.
- `frontend/input_api.py`: input mapping reads/writes.
- `frontend/theme_api.py`: theme name/config/index URL and audio-muted helpers.
- `frontend/metadata_build_service.py`: asynchronous build metadata orchestration and progress event forwarding.
- `frontend/config_api.py`: small config getters/setters exposed through the JS API.

## Adding API Methods

1. Put feature behavior in a focused service module first.
2. Add a thin method to `frontend.api.API`.
3. Add the public method name to `API_ALLOWED_METHODS`.
4. Keep websocket transport logic in `frontend.ws_bridge`; it should not grow feature-specific behavior.

## Guidelines

- Keep `main.py` focused on executable wiring.
- Keep `API` as a compatibility facade for JavaScript themes, not a home for business logic.
- Use `common/paths.py` instead of calling `user_config_dir("vpinfe", "vpinfe")` directly in new code.
- Use `common/games/game_metadata.py` for metadata reads/writes instead of repeating `Info`/`VPinFE`/`User` normalization.
- Use service modules for behavior shared by Manager UI and the frontend.
- Keep `clioptions.py` as CLI dispatch and compatibility wrappers; put reusable app behavior in `common/`.
