# Common Architecture

The `common/` package is the shared application layer used by the frontend,
manager UI, CLI, startup/shutdown flow, and table metadata jobs. Code in this
folder should stay UI-independent and should expose stable service functions or
small facade classes for older call sites.

## Layout

- `paths.py`: canonical user config, themes, collections, and table-root paths.
- `config_access.py`: typed, UI-independent accessors for common INI sections.
- `table.py`, `tableparser.py`, `table_repository.py`: table discovery and cached table rows.
- `table_metadata.py`, `metaconfig.py`: `.info` file schema, defaults, display helpers, and persistence.
- `media_paths.py`: canonical media keys, filenames, table attributes, and path resolution.
- `jobs.py`: callback-friendly progress/log reporting for long-running workflows.
- `metadata_service.py`, `table_report_service.py`, `table_play_service.py`: workflows that operate on tables and metadata.
- `collections_service.py`, `vpxcollections.py`, `tablelistfilters.py`: collection and filter logic.
- `vpsdb.py`: compatibility facade for VPS database lookup and media download.
- `vpsdb_cache.py`, `vpsdb_media.py`: VPS database cache/update and VPinMediaDB download helpers.
- `themes.py`: compatibility facade for manager UI theme registry operations.
- `theme_registry_client.py`, `theme_installer.py`: theme registry network and local install helpers.
- `dof_service.py`, `libdmdutil_service.py`: hardware service facades.
- `external_service.py`: shared third-party path discovery and dynamic import helpers.
- `http_client.py`: shared request/download helpers for common services.
- `system_actions.py`: OS shutdown/reboot and app restart helpers.

`score_parser.py` is intentionally left as its own compatibility module for now.

## Design Rules

Keep constructors cheap when adding new shared classes. If a class needs network,
filesystem mutation, or long-running scans, expose explicit methods such as
`ensure_current()`, `load_registry()`, or `apply_patches()`.

Prefer facade compatibility over broad caller churn. Existing imports like
`from common.vpsdb import VPSdb` and `from common.themes import ThemeRegistry`
remain valid, while new behavior can live in smaller modules behind them.

Use `table_metadata.py` for display and fallback accessors. New table filtering,
sorting, or row-building code should use helpers like `table_title`,
`table_themes`, `table_type`, `table_manufacturer`, `table_year`, and
`table_rating` instead of repeating `Info`/legacy `VPSdb` fallback logic.

Use `config_access.py` when reading common INI values from code outside the
configuration editor itself. This keeps defaults and bool/int coercion in one
place while preserving `IniConfig.config` for compatibility.

Use `media_paths.py` for media keys, filenames, and table path attributes.
Frontend payloads, parser discovery, media claiming, and VPS media downloads
should not each carry their own filename table.

Use `jobs.JobReporter` for long-running workflows that need both logs and UI
progress callbacks.

Use `http_client.py` for common network GET/download behavior unless a service
needs a special request shape such as POST.

Use `external_service.py` for third-party service path discovery and dynamic
module loading. DOF and libdmdutil should not grow separate copies of that logic.

## Adding A Shared Workflow

1. Put UI-free business logic in `common/`.
2. If callers already depend on an older class or function, keep that public API
   as a facade and delegate into the new module.
3. Use `common.paths` for user paths and config locations.
4. Add focused tests for the helper or service boundary.
5. Update frontend or manager UI docs only when their caller contract changes.

## Adding Metadata Fields

1. Add the default or normalization rule in `metaconfig.py` or
   `table_metadata.py`.
2. Add display/read helpers in `table_metadata.py` when multiple callers need the
   value.
3. Update row builders or filters to consume the helper rather than reading raw
   JSON directly.
4. Add a test covering both current `Info` fields and any legacy fallback.

## Adding Media Types

1. Add the media key, table attribute, and filename template to
   `common.media_paths.MEDIA_SPECS`.
2. Use the shared filename/key maps in manager UI, parser, and download code.
3. Update theme documentation if the media becomes part of the frontend API.

## Adding Networked Services

1. Keep the network client small and injectable where practical.
2. Avoid network work in constructors.
3. Store downloaded cache files under `common.paths.CONFIG_DIR`.
4. Catch request failures at the service boundary and return a clear empty or
   error result for UI callers.
