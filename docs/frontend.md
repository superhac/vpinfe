# Frontend Runtime Architecture

The frontend starts at `main.py`, but most runtime responsibilities now live in focused modules under `frontend/` and `common/`.

## Startup Flow

1. `main.py` handles executable-only concerns such as platform console behavior, early config/logging setup, and command-line parsing.
2. `frontend.runtime` creates the websocket/API/browser runtime, starts optional startup media sync, builds static mount points, starts the theme asset server, runs the frontend blocking loop, and performs shutdown/restart handling.
3. `frontend.ws_bridge.WebSocketBridge` receives JavaScript calls from theme windows and dispatches only methods listed by `frontend.api.API_ALLOWED_METHODS`.
4. `frontend.api.API` remains the JS-facing facade for theme code. It should stay thin and delegate feature behavior to service modules.

## Core Modules

- `common/paths.py`: shared config paths, `vpinfe.ini`, `collections.ini`, themes directory, and table root lookup.
- `common/table.py`: dataclass representation of a parsed table folder.
- `common/table_metadata.py`: shared metadata normalization, section lookup, rating/truthy helpers, and metadata persistence.
- `common/table_repository.py`: table parser/cache ownership and table row shaping.
- `common/tablelistfilters.py`: instance-based table filtering with no hidden singleton state.
- `common/collections_service.py`: shared collection manager access and filter-collection helpers.
- `common/table_play_service.py`: Last Played tracking, start count, runtime, score update, and NVRAM cleanup.
- `common/display_service.py`: shared monitor discovery.
- `common/metadata_service.py`: build metadata, VPX patch orchestration, and user-media claiming shared by CLI, frontend, and Manager UI.
- `common/system_actions.py`: shared app restart sentinel, clean OS command environment, shutdown, and reboot commands.
- `frontend/table_state.py`: table JSON serialization, filtering, sorting, collections, and rating mutations for the JS API.
- `frontend/launch_service.py`: VPX launch lifecycle, DOF/DMD stop-start, and frontend launch events.
- `frontend/input_api.py`: input mapping reads/writes.
- `frontend/theme_api.py`: theme name/config/index URL and audio-muted helpers.
- `frontend/metadata_build_service.py`: asynchronous build metadata orchestration and progress event forwarding.

## Adding API Methods

1. Put feature behavior in a focused service module first.
2. Add a thin method to `frontend.api.API`.
3. Add the public method name to `API_ALLOWED_METHODS`.
4. Keep websocket transport logic in `frontend.ws_bridge`; it should not grow feature-specific behavior.

## Guidelines

- Keep `main.py` focused on executable wiring.
- Keep `API` as a compatibility facade for JavaScript themes, not a home for business logic.
- Use `common/paths.py` instead of calling `user_config_dir("vpinfe", "vpinfe")` directly in new code.
- Use `common/table_metadata.py` for metadata reads/writes instead of repeating `Info`/`VPinFE`/`User` normalization.
- Use service modules for behavior shared by Manager UI and the frontend.
- Keep `clioptions.py` as CLI dispatch and compatibility wrappers; put reusable app behavior in `common/`.
