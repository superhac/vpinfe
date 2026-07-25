# Common Architecture

The `common/` package is the shared application layer used by the frontend,
manager UI, CLI, startup/shutdown flow, and table metadata jobs. Code in this
folder should stay UI-independent and should expose stable service functions or
small facade classes for older call sites.

## Layout

Three domain packages over an infrastructure layer, grouped by what a module knows
about. The boundaries were drawn from the import graph rather than by hand: 92% of
the domain-to-domain edges stay inside one package.

**`common/` itself is the infrastructure layer.** Nothing here knows about tables,
hardware or any outside service, so anything may depend on it - and nothing in it may
import from a domain package. That rule is the point of the layer; breaking it is how
`config_access` ended up importing `table_metadata` to read a boolean.

- `paths.py`: canonical user config, themes, collections, and table-root paths. `CONFIG_DIR` is resolved once at import time; set `VPINFE_CONFIG_DIR` before import (main.py maps the `--configdir` flag onto it) to relocate the whole config directory. `APP_ROOT` is where the app itself lives - use it for bundled assets instead of counting directory levels from `__file__`.
- `config_access.py`: typed, UI-independent accessors for common INI sections.
- `values.py`: value coercion (`is_truthy`) shared by config, metadata and filters.
- `iniconfig.py`, `config_bootstrap.py`: ini reading and first-run config creation.
- `events.py`: the in-process event bus. Hooks are part of an operation; subscribers are told about it.
- `media_paths.py`: canonical media keys, filenames, table attributes, and path resolution.
- `jobs.py`: callback-friendly progress/log reporting for long-running workflows.
- `http_client.py`: shared request/download helpers.
- `third_party.py`: finding and loading the third-party libraries the build bundles.
- `logging_config.py`, `app_version.py`.

**`common/tables/`** - tables, their metadata, and the collections built from them.

- `table.py`, `tableparser.py`, `table_repository.py`: table discovery and cached table rows.
- `table_metadata.py`, `metaconfig.py`: `.info` file schema, defaults, display helpers, and persistence. `metaconfig` also versions the `VPinFE` section and migrates it forward on read.
- `table_identity.py`: the stable per-install table id that addresses a table everywhere.
- `game_files.py`: which .vpx in a table folder is the table. Every caller resolves through it.
- `metadata_service.py`, `table_report_service.py`, `table_play_service.py`: workflows over tables and metadata.
- `collections_service.py`, `vpxcollections.py`, `tablelistfilters.py`: collection and filter logic. `collections.ini` carries its own schema version in a reserved `[VPinFE]` section.
- `vpxparser.py`, `standalonescripts.py`: reading and patching the .vpx itself.
- `score_parser.py`: PinMAME NVRAM score extraction.

**`common/online/`** - services reached over the internet.

- `vpsdb.py`: compatibility facade for VPS database lookup and media download.
- `vpsdb_cache.py`, `vpsdb_media.py`: VPS database cache/update and VPinMediaDB download helpers.
- `themes.py`: compatibility facade for manager UI theme registry operations.
- `theme_registry_client.py`, `theme_installer.py`: theme registry network and local install helpers.
- `app_updater.py`, `pinmame_score_parser_updater.py`: update checks and downloads.
- `vpinplay_service.py`, `vpinplay_runtime.py`: the VPinPlay client.

**`common/host/`** - this machine: attached hardware, the launcher, the running session.

- `dof_service.py`, `dof_service_worker.py`, `libdmdutil_service.py`: hardware service facades.
- `peripherals.py`: DOF and real-DMD, driven by table lifecycle events. Each device is its own handler, so a new one is a new subscriber rather than an edit.
- `realdmd.py`: which image a table shows on a real DMD panel, sent on a worker thread.
- `launcher.py`, `launch_state.py`: starting a table, and whether a launch was requested from outside the frontend.
- `display_service.py`, `system_actions.py`, `vpx_log.py`.

Three cross-package edges are deliberate: `tables` reads VPSdb through `online`
when building metadata, and `online`'s VPinPlay client reaches into `tables` to
enumerate the library. That last one is the wrong direction; VPinPlay predates the
extension model and is expected to become a plugin.

## Design Rules

Naming, comment density and lint rules live in `docs/conventions.md`.

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

Know which table id you want. A table row carries several, and they are not
interchangeable:

- `vpinfe_id` is this install's stable local id from `table_identity.py`. It
  identifies the table - in the HTTP API, in events, in jobs, in collection
  membership, and as the row key in the manager UI tables grid.
- `vpsid` and `altvpsid` are VPS-derived (`Info.VPSId` and `VPinFE.altvpsid`).
  They correlate with VPSdb, VPinPlay and other services keyed by them. Read the
  one you mean; there is deliberately no combined `id` field to reach for by
  accident.

Use `table_identity.table_id()` to read one, `ensure_id()` when you need a table
to have one. Reading never mints, so table scans stay a read path.
`table_repository.get_table_rows()` is the exception and calls `ensure_unique_ids`:
a row is addressed by its id, so a table imported since startup has to be given one
rather than appear with an empty key that collides with every other such table.

Collection membership is keyed by `vpinfe_id`. A VPS id could not do the job: it is
empty for a table VPSdb never matched, it is not unique, and it is cleared when the
.vpx changes - so membership recorded under one was orphaned by an ordinary table
update.

Both membership paths tolerate VPS-keyed entries, and both have to. The migration
leaves an entry alone when no table matched it - the table may simply not be
installed yet - and it runs only once, so such an entry can stay VPS-keyed
indefinitely. `VPXCollections.is_member` covers the frontend;
`table_repository._collections_for` covers the manager UI row. If only one of them
did, a table would show its collections in one place and not the other.

Announce table lifecycle through `events.py` rather than calling the affected
services directly. Both launch paths - the frontend wheel and the Remote Control
page - emit the same events, so behavior that has to happen around a launch is
written once.

Choose the right kind of handler. A **hook** is part of the operation: it runs in
priority order, the publisher waits, and raising stops the operation. A
**subscriber** is only told what happened; order is not promised and a failure is
logged and contained. Releasing the peripherals is a hook because launching with
them still held would be wrong; anything that merely wants to know about a launch
is a subscriber and must not be able to prevent one.

`table.selected` is deliberately subscribers-only. It fires once per wheel stop and
drives decoration - a DOF effect, the art on a DMD panel - so a handler that raises
has failed to decorate a selection, not failed to select. Registering a hook on it
would let a dead device stop the wheel.

Never pick a table's `.vpx` yourself. A folder can hold several, and picking
differently from everyone else means the metadata a user sees describes a different
file than the one that launches. Use `game_files.default_game_file()`.

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

Use `third_party.py` to locate and load a bundled third-party library. Where one
lives depends on whether this is a source checkout or a frozen build, and DOF and
libdmdutil should not each carry their own copy of that reasoning.

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
