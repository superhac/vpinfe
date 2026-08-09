# Common Architecture

The `common/` package is the shared application layer used by the frontend,
manager UI, CLI, startup/shutdown flow, and game metadata jobs. Code in this
folder should stay UI-independent and should expose stable service functions or
small facade classes for older call sites.

## Layout

Three domain packages over an infrastructure layer, grouped by what a module knows
about. The boundaries were drawn from the import graph rather than by hand: 92% of
the domain-to-domain edges stay inside one package.

**`common/` itself is the infrastructure layer.** Nothing here knows about games,
hardware or any outside service, so anything may depend on it - and nothing in it may
import from a domain package. That rule is the point of the layer; breaking it is how
`config_access` ended up importing `game_metadata` to read a boolean.

- `paths.py`: canonical user config, themes, collections, and game-root paths. `CONFIG_DIR` is resolved once at import time; set `VPINFE_CONFIG_DIR` before import (main.py maps the `--configdir` flag onto it) to relocate the whole config directory. `APP_ROOT` is where the app itself lives; reach a file the build ships through `bundled()`, which answers for a source checkout and for both kinds of frozen build.
- `config_access.py`: typed, UI-independent accessors for common INI sections.
- `values.py`: value coercion (`is_truthy`) shared by config, metadata and filters.
- `config_store.py`, `config_bootstrap.py`: ini reading and first-run config creation.
- `events.py`: the in-process event bus. Hooks are part of an operation; subscribers are told about it.
- `media_specs.py`: canonical media keys, filenames, playfield attributes, and path resolution.
- `input_registry.py`: every input action, its default bindings and the names it used to have. `[input]` in the config is generated from it, so the two cannot disagree.
- `lifecycle.py`: starting, stopping and restarting the frontend, VPinFE or the machine, whichever surface asked.
- `jobs.py`: slow work as a job — one at a time per kind, progress published on the bus, answerable by id after it finishes.
- `http_client.py`: shared request/download helpers.
- `third_party.py`: finding and loading the third_party libraries the build bundles.
- `shutdown.py`: what a kill signal does. Startup notes it and stops at the next step boundary; once the frontend is up it takes the same route as a user's own quit.
- `log_setup.py`, `app_version.py`.

**`common/games/`** - games, their metadata, and the collections built from them.

- `game.py`, `game_parser.py`, `game_repository.py`: game discovery and cached game rows.
- `game_metadata.py`, `info_file.py`: `.info` file schema, defaults, display helpers, and persistence. `metaconfig` also versions the `VPinFE` section and migrates it forward on read.
- `game_identity.py`: the stable per-install game id that addresses a game everywhere.
- `tables.py`: which .vpx in a game folder is the default table. Every caller resolves through it.
- `metadata_service.py`, `game_report_service.py`, `game_play_service.py`: workflows over games and metadata.
- `collections_service.py`, `collection_store.py`, `collection_filters.py`: collection and filter logic. `collections.ini` carries its own schema version in a reserved `[VPinFE]` section.
- `vpx_parser.py`, `standalone_scripts.py`: reading and patching the .vpx itself.
- `score_parser.py`: PinMAME NVRAM score extraction.
- `game_service.py`, `game_index_service.py`, `media_service.py`, `asset_registry.py`, `archive_service.py`, `export_bundle.py`: workflows over a game and its media - rating, re-matching, the cached row index, media lookup and invalidation, and packing a game for export.

**`common/uploads/`** - getting files into the library.

- `upload_session_service.py`: an upload in progress. Files arrive in chunks into a session directory and every path is checked against it, so an upload naming `../` is refused rather than resolved.
- `asset_analyzer_service.py`: what a zip, folder or loose file holds, worked out without extracting it.
- `asset_import_service.py`: an analyzed drop becomes a plan, and only then files on disk - so an import that would overwrite something is declined rather than undone.

Depends on `common/games/`, never the reverse: importing assets needs to know the library it is importing into.

**`common/online/`** - services reached over the internet.

- `vpsdb.py`: compatibility facade for VPS database lookup and media download.
- `vpsdb_cache.py`, `vpsdb_media.py`: VPS database cache/update and VPinMediaDB download helpers.
- `themes.py`: compatibility facade for manager UI theme registry operations.
- `theme_registry_client.py`, `theme_installer.py`: theme registry network and local install helpers.
- `app_updater.py`, `pinmame_score_parser_updater.py`: update checks and downloads.
- `vpinplay_service.py`, `vpinplay_runtime.py`: the VPinPlay client.

**`common/host/`** - this machine: attached hardware, the launcher, the running session.

- `dof_service.py`, `dof_service_worker.py`, `libdmdutil_service.py`: hardware service facades.
- `peripherals.py`: DOF and real-DMD, driven by game lifecycle events. Each device is its own handler, so a new one is a new subscriber rather than an edit.
- `real_dmd.py`: which image a game shows on a real DMD panel, sent on a worker thread.
- `launch.py`, `launch_state.py`: starting a game - resolving what to launch it with, building the command, running it and recording the play - and whether a launch was requested from outside the frontend.
- `display_service.py`, `system_actions.py`, `vpx_log.py`.

Three cross-package edges are deliberate: `games` reads VPSdb through `online`
when building metadata, and `online`'s VPinPlay client reaches into `games` to
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

Use `game_metadata.py` for display and fallback accessors. New game filtering,
sorting, or row-building code should use helpers like `table_title`,
`table_themes`, `table_type`, `table_manufacturer`, `table_year`, and
`table_rating` instead of repeating `Info`/legacy `VPSdb` fallback logic.

Know which game id you want. A game row carries several, and they are not
interchangeable:

- `vpinfe_id` is this install's stable local id from `game_identity.py`. It
  identifies the game - in the HTTP API, in events, in jobs, in collection
  membership, and as the row key in the manager UI games grid.
- `vpsid` and `altvpsid` are VPS-derived (`Info.VPSId` and `VPinFE.altvpsid`).
  They correlate with VPSdb, VPinPlay and other services keyed by them. Read the
  one you mean; there is deliberately no combined `id` field to reach for by
  accident.

Use `game_identity.game_id()` to read one, `ensure_id()` when you need a game
to have one. Reading never mints, so game scans stay a read path.
`game_repository.get_game_rows()` is the exception and calls `ensure_unique_ids`:
a row is addressed by its id, so a game imported since startup has to be given one
rather than appear with an empty key that collides with every other such game.

Collection membership is keyed by `vpinfe_id`. A VPS id could not do the job: it is
empty for a game VPSdb never matched, it is not unique, and it is cleared when the
.vpx changes - so membership recorded under one was orphaned by an ordinary game
update.

Both membership paths tolerate VPS-keyed entries, and both have to. The migration
leaves an entry alone when no game matched it - the game may simply not be
installed yet - and it runs only once, so such an entry can stay VPS-keyed
indefinitely. `CollectionStore.is_member` covers the frontend;
`game_repository._collections_for` covers the manager UI row. If only one of them
did, a game would show its collections in one place and not the other.

Launch games through `host/launch.py`. It is the only place that starts a game
file, and it is what makes a launch mean the same thing wherever it came from -
the wheel, the Remote Control page and the HTTP API all call it. When there were
two implementations they drifted, and only one of them recorded that a game had
been played.

Anything a particular caller needs around a launch is a subscriber, not an
argument. The frontend's window messages and its last-game record live in
`frontend/play_events.py`; the peripherals live in `host/peripherals.py`. Nothing
about a specific caller belongs inside the launch itself, which is how the window
messages ended up firing only for launches the wheel started.

Choose the right kind of handler. A **hook** is part of the operation: it runs in
priority order, the publisher waits, and raising stops the operation. A
**subscriber** is only told what happened; order is not promised and a failure is
logged and contained. Releasing the peripherals is a hook because launching with
them still held would be wrong; anything that merely wants to know about a launch
is a subscriber and must not be able to prevent one.

`game.selected` is deliberately subscribers-only. It fires once per wheel stop and
drives decoration - a DOF effect, the art on a DMD panel - so a handler that raises
has failed to decorate a selection, not failed to select. Registering a hook on it
would let a dead device stop the wheel.

An event payload is in-process, so it can hold whatever a handler needs - a `Game`,
the ini config. What reaches the network is a separate decision: `httpapi/events.py`
projects each streamed event into its own shape, so adding an argument here does not
change what an outside subscriber sees. Adding an event means deciding whether it is
streamed at all.

Say when the library changed. `game_repository.refresh_game` announces `game.changed`
and `CollectionStore.save` announces `collections.changed`, so anything holding a view
of the library can re-derive it. Announced at those two chokepoints rather than at each
caller, because every path that edits a game already comes through the first to be
re-read and every path that edits a collection comes through the second to be written.
Re-reading a game *replaces* the object rather than mutating it, so a holder of the old
one is stale with no way to notice - which is why the announcement has to exist at all.

Start, stop and restart things through `common/lifecycle.py`. A request names a scope
(`frontend`, `app`, `system`) and an action (`start`, `stop`, `restart`), so rebooting
the machine is `restart` at system scope rather than a verb of its own, and the
frontend, the Manager UI, an extension and a signal all arrive at one place. Reaching
for the browser directly is what used to skip `shutdown_services` and lose a session's
play data on the way out.

A request also carries **where it came from**, not just what kind of surface it was.
A confirmation is put to the surface that asked and nowhere else - a dialog raised on
the cabinet because somebody pressed something on their phone is a hang on a screen
nobody is watching. Every other surface is told through `lifecycle.acting`, which is
subscribers-only for the usual reason: being told is not being asked. A request nothing
can ask, like a `SIGTERM`, proceeds rather than waiting for an answer that will never
come.

Never pick a game's `.vpx` yourself. A folder can hold several, and picking
differently from everyone else means the metadata a user sees describes a different
file than the one that launches. Use `tables.default_table()`.

Use `config_access.py` when reading common INI values from code outside the
configuration editor itself. This keeps defaults and bool/int coercion in one
place while preserving `ConfigStore.config` for compatibility.

Use `media_specs.py` for media keys, filenames, and playfield path attributes.
Frontend payloads, parser discovery, and VPS media downloads should not each
carry their own filename table.

Use `jobs.JobReporter` for long-running workflows that need both logs and UI
progress callbacks.

Run anything slow through `jobs.submit` (start it on its own thread, hand the
caller a job) or `jobs.track` (wrap work already running on the caller's thread).
Both publish `job.progress` / `job.done` / `job.failed` in the shape `events.py`
documents, so a workflow looks the same on the event stream whether the Manager UI
or the HTTP API started it, and both enforce one job per kind — which is what stops
two library scans rewriting the same `.info` files. `track` chains to whatever
callbacks the caller already had, so an existing progress bar keeps working.

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

1. Add the default or normalization rule in `info_file.py` or
   `game_metadata.py`.
2. Add display/read helpers in `game_metadata.py` when multiple callers need the
   value.
3. Update row builders or filters to consume the helper rather than reading raw
   JSON directly.
4. Add a test covering both current `Info` fields and any legacy fallback.

## Adding Media Types

1. Add the media key, playfield attribute, and filename template to
   `common.media_specs.MEDIA_SPECS`.
2. Use the shared filename/key maps in manager UI, parser, and download code.
3. Update theme documentation if the media becomes part of the frontend API.

## Adding Networked Services

1. Keep the network client small and injectable where practical.
2. Avoid network work in constructors.
3. Store downloaded cache files under `common.paths.CONFIG_DIR`.
4. Catch request failures at the service boundary and return a clear empty or
   error result for UI callers.
