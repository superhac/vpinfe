# Manager UI Architecture

The Manager UI is a NiceGUI application under `managerui/`. Its current refactor direction is to keep page rendering thin and move shared paths, styling, page metadata, and reusable UI primitives into small modules.

## Structure

- `managerui/managerui.py`: application shell, header, navigation, page routing, Manager UI API endpoints, and NiceGUI startup/shutdown.
- `managerui/page_registry.py`: the canonical list of shell navigation pages and URL aliases.
- `common/paths.py`: shared config paths and path helpers used across Manager UI, frontend, and common services.
- `managerui/paths.py`: Manager UI-specific path exports such as static asset paths, backed by `common.paths`.
- `managerui/ui_helpers.py`: reusable UI helpers such as shared style loading and standard nav/action buttons.
- `managerui/filters.py`: shared filter option building and filtering for table-shaped rows.
- `managerui/config_fields.py`: declarative config field metadata such as checkbox fields and input ordering.
- `managerui/config_support.py`: non-UI support helpers for config pages such as display detection and field option shaping.
- `managerui/remote_actions.py`: declarative remote control button definitions.
- `managerui/remote_launch.py`: remote launch table scanning and collection filter matching.
- `managerui/services/`: non-UI behavior shared by routes and pages.
- `managerui/static/manager.css`: shared Manager UI theme variables, shell layout, and nav styling.
- `managerui/static/<page>.css`: page-specific CSS that has been moved out of Python modules.
- `managerui/pages/`: feature pages. Each page should expose a `render_panel()` function, except standalone pages that intentionally expose a different entry point such as `mobile.build()`.

## Shell Flow

1. `managerui.py` registers NiceGUI routes with `@ui.page`.
2. `/` calls `build_app()`.
3. `build_app()` loads `/static/manager.css`, renders the header, builds the left navigation from `NAV_PAGES`, and renders the selected page into the content container.
4. URL query aliases such as `?page=config` are resolved through `PAGE_ALIASES`.
5. Page rendering is dispatched through `_PAGE_RENDERERS`.

The shell owns navigation and routing. Feature pages should not need to know how the shell is built.

## Styling

Shared shell styling belongs in `managerui/static/manager.css`.

Use CSS classes for repeated styles instead of long inline `.style(...)` strings. Inline styles are still fine for one-off layout values or values that are easier to compute in Python.

Page-specific styles should move into `managerui/static/<page>.css` and be loaded with:

```python
from managerui.ui_helpers import load_page_style

load_page_style("tables.css")
```

Some older page-specific styles can remain in page modules during the transition, but the target architecture is:

- shared tokens and common components in `manager.css`
- page-specific classes grouped by feature, for example `tables.css`
- minimal inline styles in page rendering code

## Shared Paths

Use `common.paths` for shared app config paths, or `managerui.paths` when Manager UI-specific exports are needed:

```python
from common.paths import CONFIG_DIR, VPINFE_INI_PATH, COLLECTIONS_PATH, get_tables_path
```

Avoid redefining `Path(user_config_dir("vpinfe", "vpinfe"))` in new Manager UI code.

## Shared Services

Service modules live under `managerui/services/` and should not depend on page layout. They can perform filesystem, config, archive, and repository operations, then return plain Python data for the UI layer to render.

Current services:

- `archive_service.py`: validates table folders and creates temporary `.vpxz` archives.
- `app_control.py`: restart, quit, reboot, and shutdown actions that can be used without importing the remote page.
- `collections_service.py`: collection manager access, table search, filter option building, and collection mutations.
- `media_service.py`: media scanning, thumbnail cache paths, media replacement, and media cache invalidation.
- `system_service.py`: reusable system-page formatters, disk target resolution, and platform helpers.
- `table_catalog.py`: shared table scanning and row shaping for mobile transfers and remote launching.
- `table_index_service.py`: shared Manager UI table cache and lookup indexes (`table_path`, folder, VPS ID, search blobs, missing rows).
- `table_service.py`: shared table metadata, VPSdb, collection, upload, and table-association operations.
- `theme_service.py`: active theme, theme registry, install, and delete operations.
- `vpx_config_service.py`: VPX config path lookup and backup management.

Use services from page event handlers instead of reaching into another page module. For example, use `create_vpxz_archive()` instead of calling a helper from `pages/mobile.py`.

## Shared Filtering

Use `managerui.filters` when a page filters table-shaped rows by name, manufacturer, year, theme, or type:

```python
from managerui.filters import apply_table_filters, build_table_filter_options
```

Pages can pass extra predicates for page-specific filters such as "has PUP pack" or "missing DMD media".

## Adding a New Page

1. Create a module in `managerui/pages/`, for example `managerui/pages/network.py`.
2. Add a render entry point:

```python
from nicegui import ui


def render_panel():
    with ui.column().classes("w-full"):
        ui.label("Network").classes("text-2xl font-bold")
```

3. Import the page in `managerui/managerui.py`.
4. Add a renderer entry in `_PAGE_RENDERERS`:

```python
"network": tab_network.render_panel,
```

5. Add a navigation entry in `managerui/page_registry.py`:

```python
ManagerPage("network", "Network", "hub"),
```

6. Add aliases to `PAGE_ALIASES` only when the page needs friendly URL names beyond its key.

## Adding Shared UI Helpers

Add small, generic helpers to `managerui/ui_helpers.py` when a pattern appears across multiple pages. Good candidates:

- standard action buttons
- dialog shells
- section headers
- safe notification wrappers
- repeated table/pagination slot helpers

Keep feature-specific behavior in the page or a service module instead of making `ui_helpers.py` a large mixed utility file.

## Adding Or Changing Config Fields

Use `managerui/config_fields.py` for field behavior that is metadata rather than page layout.

- Add boolean fields to `CHECKBOX_FIELDS`.
- Adjust controller/keyboard ordering through `INPUT_MAPPING_ACTION_ORDER`.
- Keep labels in the page-level `FRIENDLY_NAMES` map until labels are shared by another page.

For a new special field renderer, keep the NiceGUI component creation in `pages/vpinfe_config.py`, but put reusable classification rules in `config_fields.py`.

## Adding Table Dialogs

Large table dialogs live outside the table-list page:

- `pages/table_detail_dialog.py`
- `pages/table_import_dialog.py`
- `pages/table_match_dialog.py`

These modules are the public import points for dialog entry functions and own the dialog bodies. `pages/tables.py` owns table scanning/list rendering and keeps only compatibility wrappers for older private dialog names.

`pages/table_dialog_context.py` provides a small context object for refresh callbacks. New table dialog code should accept callbacks through this context or explicit function parameters instead of importing another page to trigger refreshes.

When changing table dialogs:

- keep NiceGUI layout and event wiring in the dialog module
- put filesystem, metadata, VPSdb, and cache behavior in `services/table_service.py` or `services/table_index_service.py`
- use `services/media_service.invalidate_media_cache()` after changes that affect media listings
- avoid adding more dialog body code to `pages/tables.py`

## Remote Imports

Do not import `pages/remote.py` from the shell or unrelated pages just to restart or quit the app. Use `managerui.services.app_control` instead. The remote page lazy-loads `KeySimulator`/`pynput` only when the remote UI is opened so headless imports and tests do not require an active display server.

## Cache Ownership

Cache ownership should live with services, not page modules. For example, media cache invalidation is exposed by `managerui.services.media_service.invalidate_media_cache()`, so table services and dialogs do not need to import `pages/media.py`.

When adding a new cache:

- keep the cache and invalidation function in the service that owns the data
- have pages read/update through that service
- avoid page-to-page imports for cache refreshes

## Table Index

Use `managerui.services.table_index_service` for table rows that need to be reused across pages. It owns the Manager UI table cache and derived lookup maps, so pages should avoid keeping their own long-lived table lists.

Good uses:

- table list rows and missing rows after a scan
- table lookups by path, folder name, or VPS ID
- collection membership updates
- lightweight search against already-loaded table rows
- remote-launch dropdown rows

When a page performs a full table scan, call `scan_table_data(reload=True)` so rows and missing rows are refreshed together.

## Adding Service Logic

When a page function starts mixing filesystem work, config writes, data scanning, network calls, and UI rendering, split the non-UI behavior into a service module.

Suggested pattern:

- `managerui/services/<feature>.py`: data and side-effect functions
- `managerui/pages/<feature>.py`: NiceGUI layout and event wiring

For example, table import and VPS matching logic should live in table-focused service/dialog modules instead of growing `pages/tables.py`.

## Guidelines

- Keep `managerui.py` focused on shell, routes, and lifecycle.
- Add pages through `page_registry.py` instead of hard-coding new nav buttons.
- Use `paths.py` for shared Manager UI paths.
- Use `services/` for behavior that is reused by multiple pages or routes.
- Use `filters.py` for common table-shaped filtering.
- Use `config_fields.py` for reusable config field rules.
- Prefer classes in `manager.css` over repeated inline style strings.
- Keep standalone routes like `/remote` and `/mobile` explicit in `managerui.py`.
- Treat cross-page shared behavior as a service or helper only after it appears in more than one place.
