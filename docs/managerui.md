# Manager UI Architecture

The Manager UI is a NiceGUI application under `managerui/`. Its current refactor direction is to keep page rendering thin and move shared paths, styling, page metadata, and reusable UI primitives into small modules.

## Structure

- `managerui/managerui.py`: application shell, header, navigation, page routing, Manager UI API endpoints, and NiceGUI startup/shutdown.
- `managerui/page_registry.py`: the canonical list of shell navigation pages and URL aliases.
- `managerui/paths.py`: shared config paths and path helpers such as `get_tables_path()`.
- `managerui/ui_helpers.py`: reusable UI helpers such as shared style loading and standard nav/action buttons.
- `managerui/filters.py`: shared filter option building and filtering for table-shaped rows.
- `managerui/services/`: non-UI behavior shared by routes and pages.
- `managerui/static/manager.css`: shared Manager UI theme variables, shell layout, and nav styling.
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

Page-specific styles can remain in page modules during the transition, but the target architecture is:

- shared tokens and common components in `manager.css`
- page-specific classes grouped by feature
- minimal inline styles in page rendering code

## Shared Paths

Use `managerui.paths` for Manager UI config paths:

```python
from managerui.paths import CONFIG_DIR, VPINFE_INI_PATH, COLLECTIONS_PATH, get_tables_path
```

Avoid redefining `Path(user_config_dir("vpinfe", "vpinfe"))` in new Manager UI code.

## Shared Services

Service modules live under `managerui/services/` and should not depend on page layout. They can perform filesystem, config, archive, and repository operations, then return plain Python data for the UI layer to render.

Current services:

- `archive_service.py`: validates table folders and creates temporary `.vpxz` archives.
- `table_service.py`: shared table metadata, VPSdb, collection, upload, and table-association operations.

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
- Prefer classes in `manager.css` over repeated inline style strings.
- Keep standalone routes like `/remote` and `/mobile` explicit in `managerui.py`.
- Treat cross-page shared behavior as a service or helper only after it appears in more than one place.
