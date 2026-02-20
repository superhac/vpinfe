# Themes

VPinFE supports two rendering backends:
- **pywebview** (master branch) — uses a WebKitGTK/MSHTML browser window with a direct JS bridge (`window.pywebview.api`).
- **Embedded Chromium** (vpinfe-chromium branch) — uses a WebSocket bridge to communicate between the browser and Python backend.

Themes are fully compatible with both backends. The `vpinfe-core.js` library abstracts the communication layer so theme code does not need to know which backend is in use.

### Windows

VPinFE runs up to 3 browser windows, one per monitor:

- `table` — The main screen. Controller for all other screens and input. Handles gamepad/keyboard input and hosts the in-theme menu overlays.
- `bg` — Backglass screen. Receives events from the table window.
- `dmd` — DMD screen (not a "real DMD" like ZeDMD). Receives events from the table window.

Each window has its own webpage but shares an instance of the VPinFE API ([frontend/api.py](https://github.com/superhac/vpinfe/blob/master/frontend/api.py)), accessed via [vpinfe-core.js](#vpinfe-corejs).

---

## Theme Structure

Themes are installed in the user config directory: `~/.config/vpinfe/themes/<THEME NAME>/` (Linux) or the equivalent `platformdirs` location on other platforms.

```
<THEME NAME>
├── manifest.json
├── config.json          (optional - user-customizable theme options)
├── preview.png          (optional - shown in manager UI, can be .png or .gif)
├── index_table.html
├── index_bg.html
├── index_dmd.html
├── style.css
├── theme.js
└── fonts/               (optional - custom font files)
    └── MyFont.otf
```

### manifest.json

Every theme must include a `manifest.json`:
```json
{
  "name": "My Theme",
  "version": "1.0",
  "author": "Your Name",
  "description": "A brief description of the theme.",
  "preview_image": "preview.png",
  "supported_screens": 3,
  "type": "desktop",
  "change_log": "Initial release."
}
```

| Field | Description |
|-------|-------------|
| `name` | Display name shown in the manager UI. |
| `version` | Version string for tracking updates. |
| `author` | Theme author name. |
| `description` | Brief description shown in the manager UI. |
| `preview_image` | Filename of the preview image (`.png` or `.gif`). |
| `supported_screens` | Number of screens the theme supports (typically `3`). |
| `type` | Theme type: `"desktop"` for desktop/flat-screen setups, `"cab"` for cabinet setups. |
| `change_log` | Description of changes in this version. |

---

## HTML Files

Each screen has its own HTML file. These must be named exactly as listed:

| File | Description |
|--------|-----|
| `index_table.html` | The main screen. Controller for all other screens and input. |
| `index_bg.html` | Backglass screen. |
| `index_dmd.html` | DMD screen. |

### index_table.html

This is the main HTML file. It controls input, displays the primary UI, and hosts the in-theme menu overlays. Below is the minimum required structure:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>VPinFE - My Theme</title>
  <link rel="stylesheet" href="/web/common/vpinfe-style.css">
  <link rel="stylesheet" href="style.css">
  <script src="/web/common/vpinfe-core.js"></script>
  <script src="theme.js"></script>
</head>
<body>
  <!-- Your theme content goes here -->
  <div id="fadeContainer">
    <!-- Wrap your content in a container for fade transitions -->
  </div>

  <!-- Required: Menu overlay container. VPinFECore injects the main menu
       and collection menu iframes into this div. -->
  <div id="overlay-root"></div>

  <!-- Optional: Remote launch overlay shown when manager UI triggers a launch -->
  <div id="remote-launch-overlay" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); z-index: 9999; justify-content: center; align-items: center; flex-direction: column;">
    <div style="color: white; font-size: 3em; font-family: Arial, sans-serif; text-align: center;">
      <div style="margin-bottom: 20px;">Remote Launching...</div>
      <div id="remote-launch-table-name" style="font-size: 1.5em; color: #4CAF50;"></div>
    </div>
  </div>
</body>
</html>
```

#### Required Includes

```html
<link rel="stylesheet" href="/web/common/vpinfe-style.css">
<script src="/web/common/vpinfe-core.js"></script>
```

These are served by VPinFE's HTTP server on port 8000. `vpinfe-core.js` provides all API calls, media URL helpers, gamepad/keyboard input, and event handling. `vpinfe-style.css` is required for the in-theme menu system styling.

Your theme's own `style.css` and `theme.js` can be named whatever you want.

#### Required HTML Elements

| Element | Purpose |
|---------|---------|
| `<div id="overlay-root">` | **Required on all windows.** VPinFECore injects the main menu and collection menu iframes here. Without this, menus won't appear. |

#### Optional HTML Elements

| Element | Purpose |
|---------|---------|
| `<div id="fadeContainer">` | Wrap your content for fade-to-black transitions on table launch/return. Style with `transition: opacity` in CSS. |
| `<div id="fadeOverlay">` | Alternative fade pattern: a fixed full-screen black overlay that fades in/out via a CSS class (e.g., `.show { opacity: 1 }`). |
| `<div id="remote-launch-overlay">` | Overlay shown when the manager UI triggers a remote table launch. Include `<div id="remote-launch-table-name">` inside for the table name. |

### index_bg.html & index_dmd.html

Same structure as above but with simpler content. These windows only display media and respond to events — they don't handle input.

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>VPinFE - BG</title>
  <link rel="stylesheet" href="/web/common/vpinfe-style.css">
  <link rel="stylesheet" href="style.css">
  <script src="/web/common/vpinfe-core.js"></script>
  <script src="theme.js"></script>
</head>
<body>
  <div id="fadeContainer">
    <div id="bgImageContainer">
      <!-- BG or DMD image inserted here by theme.js -->
    </div>
  </div>
  <div id="overlay-root"></div>
</body>
</html>
```

### Custom Fonts

You can bundle custom fonts with your theme. Place font files in the theme directory (or a `fonts/` subfolder) and reference them with `@font-face` in your CSS:

```css
@font-face {
  font-family: 'MyFont';
  src: url('fonts/MyFont.otf') format('opentype');
}
```

You can also load web fonts (e.g., Google Fonts) via `<link>` in your HTML:
```html
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500&display=swap" rel="stylesheet">
```

---

## Setting the Theme

The user selects a theme by setting this in `vpinfe.ini`:
```ini
[Settings]
theme = <THEME NAME>
```

---

## theme.js

The main JS file for interacting with VPinFE and controlling the theme UI. All three windows (`table`, `bg`, `dmd`) load the same `theme.js`, so use `windowName` to branch logic per window.

```javascript
/*
Bare minimum theme example.
*/

// Globals
windowName = ""
currentTableIndex = 0;

// init the core interface to VPinFE
const vpin = new VPinFECore();
vpin.init();
window.vpin = vpin // main menu needs this to call back in.

// Register receiveEvent globally BEFORE vpin.ready to avoid timing issues
window.receiveEvent = receiveEvent;

// wait for VPinFECore to be ready
vpin.ready.then(async () => {
    await vpin.call("get_my_window_name")
        .then(result => {
            windowName = result;
        });

    // register your input handler
    vpin.registerInputHandler(handleInput);

    // optional: load a config.json from your theme dir for user-customizable options
    config = await vpin.call("get_theme_config");

    // Initialize the display
    updateScreen();
});

// listener for window events
async function receiveEvent(message) {
    // Let VPinFECore handle the data refresh logic (TableDataChange, filters, sorts)
    await vpin.handleEvent(message);

    if (message.type == "TableIndexUpdate") {
        currentTableIndex = message.index;
        updateScreen();
    }
    else if (message.type == "TableLaunching") {
        tableAudio.stop();
        await fadeOut();
    }
    else if (message.type == "TableRunning") {
        // Table has finished loading and is now running
    }
    else if (message.type == "TableLaunchComplete") {
        fadeIn();
        if (windowName === "table") tableAudio.play(vpin.getAudioURL(currentTableIndex));
    }
    else if (message.type == "RemoteLaunching") {
        // Remote launch from manager UI - message.table_name has the table name
        tableAudio.stop();
        showRemoteLaunchOverlay(message.table_name);
        await fadeOut();
    }
    else if (message.type == "RemoteLaunchComplete") {
        hideRemoteLaunchOverlay();
        fadeIn();
        if (windowName === "table") tableAudio.play(vpin.getAudioURL(currentTableIndex));
    }
    else if (message.type == "TableDataChange") {
        currentTableIndex = message.index;
        updateScreen();
    }
}

// input handler - only called on the "table" window
/*  joyleft, joyright, joyup, joydown,
    joyselect, joymenu, joyback, joycollectionmenu */
async function handleInput(input) {
    switch (input) {
        case "joyleft":
            currentTableIndex = wrapIndex(currentTableIndex - 1, vpin.tableData.length);
            updateScreen();
            vpin.sendMessageToAllWindows({
                type: 'TableIndexUpdate',
                index: currentTableIndex
            });
            break;
        case "joyright":
            currentTableIndex = wrapIndex(currentTableIndex + 1, vpin.tableData.length);
            updateScreen();
            vpin.sendMessageToAllWindows({
                type: 'TableIndexUpdate',
                index: currentTableIndex
            });
            break;
        case "joyselect":
            tableAudio.stop(); // stop audio before launching
            vpin.sendMessageToAllWindows({ type: "TableLaunching" });
            await fadeOut();
            await vpin.launchTable(currentTableIndex);
            break;
        case "joyback":
            break;
    }
}

function updateScreen() {
    if (windowName === "table") {
        // Update table window: images, carousel, info, audio
        tableAudio.play(vpin.getAudioURL(currentTableIndex));
    } else if (windowName === "bg") {
        // Update backglass image
    } else if (windowName === "dmd") {
        // Update DMD image
    }
}

// circular table index helper
function wrapIndex(index, length) {
    return (index + length) % length;
}

// Fade transition helpers
async function fadeOut() {
    const el = document.getElementById('fadeContainer');
    return new Promise(resolve => {
        el.addEventListener('transitionend', e => {
            if (e.propertyName === 'opacity') resolve();
        }, { once: true });
        el.style.opacity = '0';
    });
}

function fadeIn() {
    document.getElementById('fadeContainer').style.opacity = '1';
}

// Remote launch overlay
function showRemoteLaunchOverlay(tableName) {
    const overlay = document.getElementById('remote-launch-overlay');
    const nameEl = document.getElementById('remote-launch-table-name');
    if (overlay && nameEl) {
        nameEl.textContent = tableName || 'Unknown Table';
        overlay.style.display = 'flex';
    }
}

function hideRemoteLaunchOverlay() {
    const overlay = document.getElementById('remote-launch-overlay');
    if (overlay) overlay.style.display = 'none';
}
```

> **Important:** Call `await vpin.handleEvent(message)` at the top of your `receiveEvent` function. This lets VPinFECore handle `TableDataChange` events automatically (collection changes, filter/sort updates) so you don't have to manage that logic yourself.

> **Important:** Set `window.vpin = vpin` so the in-theme menu system can call back into your VPinFECore instance.

### Event Types

Events are sent between windows via `receiveEvent()`. These are the built-in event types:

| Event Type | Properties | Description |
|------------|------------|-------------|
| `TableIndexUpdate` | `index` | User navigated to a different table. Sent by the table window to all others. |
| `TableLaunching` | — | A table is about to launch. Use this to fade out, stop audio, etc. |
| `TableRunning` | — | The launched table has finished loading and is now running. Sent when the table process outputs "Startup done". |
| `TableLaunchComplete` | — | The launched table has exited. Use this to fade back in, resume audio. |
| `RemoteLaunching` | `table_name` | The manager UI triggered a remote table launch. Show an overlay. |
| `RemoteLaunchComplete` | — | The remote-launched table has exited. Hide the overlay. |
| `TableDataChange` | `index`, `collection?`, `filters?`, `sort?` | Table data changed (collection switch, filter/sort update). Handled automatically by `vpin.handleEvent()`. |

You can also define custom event types and send them with `vpin.sendMessageToAllWindows()`.

### Input Actions

The following input actions are passed to your `handleInput` function (table window only):

| Action | Gamepad | Keyboard |
|--------|---------|----------|
| `joyleft` | Mapped button | Left Arrow / Left Shift |
| `joyright` | Mapped button | Right Arrow / Right Shift |
| `joyup` | Mapped button | — |
| `joydown` | Mapped button | — |
| `joyselect` | Mapped button | Enter |
| `joyback` | Mapped button | — |

The following actions are handled internally by VPinFECore and do **not** reach your handler:

| Action | Gamepad | Keyboard | Effect |
|--------|---------|----------|--------|
| `joymenu` | Mapped button | `m` | Toggles the main menu overlay |
| `joycollectionmenu` | Mapped button | `c` | Toggles the collection menu overlay |
| `joyexit` | Mapped button | `Escape` / `q` | Closes the application |

---

## vpinfe-core.js

The JavaScript interface to the VPinFE API. Must be loaded in your theme:
```html
<script src="/web/common/vpinfe-core.js"></script>
```

### Public Properties

These properties are available on the `vpin` instance after `vpin.ready` resolves:

| Property | Type | Description |
|----------|------|-------------|
| `vpin.tableData` | `array` | The current (possibly filtered) table list. Each element is a table object (see [Table Data Object](#table-data-object)). |
| `vpin.monitors` | `array` | List of monitor objects with `name`, `x`, `y`, `width`, `height`. Loaded during init. |
| `vpin.tableOrientation` | `string` | Table playfield orientation from config: `"landscape"` or `"portrait"`. |
| `vpin.tableRotation` | `number` | Table playfield rotation in degrees from config (default `0`). |
| `vpin.themeAssetsPort` | `number` | HTTP server port (default `8000`). |
| `vpin.menuUP` | `boolean` | Whether the main menu overlay is currently visible. |
| `vpin.collectionMenuUP` | `boolean` | Whether the collection menu overlay is currently visible. |

### API Reference

#### init()
Sets up keyboard event listener and connects to the backend (pywebview bridge or WebSocket).

#### registerInputHandler(handler)
Registers an input handler for the table screen. Only works when the current window name is `"table"`. The handler receives a single string argument (the action name).

#### registerInputHandlerMenu(handler)
Registers an input handler for the main menu overlay.

#### registerInputHandlerCollectionMenu(handler)
Registers an input handler for the collection menu overlay.

#### toggleMenu()
Programmatically toggles the main menu overlay open/closed.

#### toggleCollectionMenu()
Programmatically toggles the collection menu overlay open/closed.

#### call(method, ...args)
Invokes a backend API method. Works transparently with both pywebview and WebSocket backends. Returns a Promise.

The following methods are available via `vpin.call()`:

##### Window & App

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_my_window_name` | — | `string` | Returns the window name for this instance (`"table"`, `"bg"`, or `"dmd"`). |
| `close_app` | — | — | Shuts down all browser windows and exits the application. |
| `get_monitors` | — | `array` | Returns list of monitor objects with `name`, `x`, `y`, `width`, `height`. |
| `console_out` | `output` | `string` | Prints a message to the Python CLI console. Useful for debugging. Returns the same string. |

##### Table Data

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_tables` | `reset=false` | `string` (JSON) | Returns JSON string of the current (filtered) table list. Pass `true` to reset to the full unfiltered list. Each table object includes paths, media paths, addon flags, and metadata. |
| `launch_table` | `index` | — | Launches the VPX table at the given index. Blocks until the table exits. Automatically tracks play in the "Last Played" collection. Sends `TableRunning` when the table finishes loading and `TableLaunchComplete` when it exits. |
| `build_metadata` | `download_media=true`, `update_all=false` | `object` | Triggers a background metadata build/refresh. Sends progress events (`buildmeta_progress`, `buildmeta_log`, `buildmeta_complete`, `buildmeta_error`) to all windows. Returns `{success, message}`. |

##### Collections

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_collections` | — | `array` | Returns list of collection names from `collections.ini`. |
| `set_tables_by_collection` | `collection` | — | Filters the table list by the named collection. Supports both VPS ID-based and filter-based collections. |
| `save_filter_collection` | `name`, `letter`, `theme`, `table_type`, `manufacturer`, `year`, `sort_by` | `object` | Saves the current filter settings as a named collection. Returns `{success, message}`. |
| `get_current_collection` | — | `string` | Returns the name of the currently active collection, or `"None"`. |

##### Filters & Sorting

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `apply_filters` | `letter`, `theme`, `table_type`, `manufacturer`, `year` | `number` | Applies VPSdb filters to the full table list. Each arg is optional (pass `null` to keep current). Returns the filtered count. |
| `reset_filters` | — | — | Resets all filters back to the full table list. |
| `apply_sort` | `sort_type` | `number` | Sorts the current filtered tables. `sort_type` is `"Alpha"` or `"Newest"`. Returns the count. |
| `get_current_filter_state` | — | `object` | Returns the current filter state: `{letter, theme, type, manufacturer, year}`. |
| `get_current_sort_state` | — | `string` | Returns the current sort type (`"Alpha"` or `"Newest"`). |
| `get_filter_letters` | — | `array` | Returns available starting letters from all tables (for filter UI). |
| `get_filter_themes` | — | `array` | Returns available themes/categories from all tables. |
| `get_filter_types` | — | `array` | Returns available table types (SS, EM, PM, etc.) from all tables. |
| `get_filter_manufacturers` | — | `array` | Returns available manufacturers from all tables. |
| `get_filter_years` | — | `array` | Returns available years from all tables. |

##### Events & Messaging

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `send_event_all_windows` | `message` | — | Sends an event to all windows except the caller. |
| `send_event_all_windows_incself` | `message` | — | Sends an event to all windows including the caller and iframes. |
| `send_event` | `window_name`, `message` | — | Sends an event to a specific window by name (`"table"`, `"bg"`, or `"dmd"`). |
| `playSound` | `sound` | — | Sends a `playSound` event to the current window. |

##### Input

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_joymaping` | — | `object` | Returns the gamepad button mapping from `vpinfe.ini`. Keys: `joyleft`, `joyright`, `joyup`, `joydown`, `joyselect`, `joymenu`, `joyback`, `joyexit`, `joycollectionmenu`. Values are button index strings. |
| `set_button_mapping` | `button_name`, `button_index` | `object` | Sets a gamepad button mapping and saves to config. Returns `{success, message}`. |

##### Theme & Display Config

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_theme_name` | — | `string` | Returns the active theme name from `vpinfe.ini`. |
| `get_theme_config` | — | `object\|null` | Loads and returns the theme's `config.json` file, or `null` if not found. Use this for user-customizable theme options. |
| `get_theme_assets_port` | — | `number` | Returns the HTTP server port (default `8000`). |
| `get_theme_index_page` | — | `string` | Returns the full URL for this window's theme index page. |
| `get_table_orientation` | — | `string` | Returns the table orientation from config (`"landscape"` or `"portrait"`). |
| `get_table_rotation` | — | `number` | Returns the table rotation angle in degrees from config (default `0`). |

##### Audio (pywebview only)

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `trigger_audio_play` | — | — | Triggers `tableAudio._resumePlay()` via `evaluate_js` to bypass WebKitGTK autoplay policy. No-op on Chromium (direct `audio.play()` works). See [Audio Support](#audio-support). |

#### getImageURL(index, type)
Returns an HTTP URL for a table's image. `type` can be `"table"`, `"bg"`, `"dmd"`, `"wheel"`, or `"cab"`. Returns a fallback `/web/images/file_missing.png` URL if the file doesn't exist.

#### getVideoURL(index, type)
Returns an HTTP URL for a table's video. `type` can be `"table"`, `"bg"`, or `"dmd"`. Returns a fallback `/web/images/file_missing.png` URL if no video exists. See [Video Support](#video-support).

#### getAudioURL(index)
Returns an HTTP URL for a table's audio file, or `null` if no audio exists. See [Audio Support](#audio-support).

#### getTableMeta(index)
Returns the full table object for a given table index. This is the same object as `vpin.tableData[index]`. See [Table Data Object](#table-data-object).

#### getTableCount()
Returns the number of tables in the current (possibly filtered) table list.

#### sendMessageToAllWindows(message)
Sends an event to all windows except the current one. Convenience wrapper around `vpin.call("send_event_all_windows", message)`.

#### sendMessageToAllWindowsIncSelf(message)
Sends an event to all windows including the current one and forwarding to iframes.

#### launchTable(index)
Disables gamepad input, calls backend to launch the selected table, then re-enables gamepad input. Sends `TableRunning` when the table finishes loading and `TableLaunchComplete` when it exits.

#### getTableData(reset=false)
Loads table data from the backend into `vpin.tableData`. Pass `reset=true` to reload from the full unfiltered table list.

#### handleEvent(message)
Handles incoming events with built-in logic for `TableDataChange` (collection/filter/sort changes). Call this at the top of your `receiveEvent` function to get automatic data refresh.

#### registerEventHandler(eventType, handler)
Registers a custom event handler for a specific event type. The handler is called whenever that event type is received via `handleEvent()`.

---

## Table Data Object

Each element in `vpin.tableData` (and the return of `vpin.getTableMeta(index)`) is an object with the following structure:

### Top-Level Properties

| Property | Type | Description |
|----------|------|-------------|
| `tableDirName` | `string` | The table's directory name. |
| `TableImagePath` | `string\|null` | Local path to the table playfield image (`table.png` or `fss.png`). |
| `BGImagePath` | `string\|null` | Local path to the backglass image (`bg.png`). |
| `DMDImagePath` | `string\|null` | Local path to the DMD image (`dmd.png`). |
| `WheelImagePath` | `string\|null` | Local path to the wheel/logo image (`wheel.png`). |
| `CabImagePath` | `string\|null` | Local path to the cabinet image (`cab.png`). |
| `TableVideoPath` | `string\|null` | Local path to the table playfield video (`table.mp4` or `fss.mp4`). |
| `BGVideoPath` | `string\|null` | Local path to the backglass video (`bg.mp4`). |
| `DMDVideoPath` | `string\|null` | Local path to the DMD video (`dmd.mp4`). |
| `AudioPath` | `string\|null` | Local path to the audio file (`audio.mp3`). |
| `meta` | `object` | Nested metadata object (see below). |

> **Note:** You typically don't use the path properties directly. Use `vpin.getImageURL()`, `vpin.getVideoURL()`, and `vpin.getAudioURL()` which convert these paths to HTTP URLs. Direct access to path properties is useful for checking existence (e.g., `if (table.TableVideoPath)` to decide whether to show video or image).

### meta.Info

VPSdb and user-edited metadata:

| Property | Type | Description |
|----------|------|-------------|
| `Title` | `string` | Table display name. |
| `Manufacturer` | `string` | Table manufacturer (e.g., "Williams", "Bally"). |
| `Year` | `string` | Year of manufacture. |
| `Type` | `string` | Table type code: `"SS"` (Solid State), `"EM"` (Electro Mechanical), `"PM"` (Pure Mechanical). |
| `Authors` | `array` | List of VPX table author names. |
| `Theme` | `string` | Table theme/category. |

### meta.VPXFile

Data extracted from the `.vpx` file itself:

| Property | Type | Description |
|----------|------|-------------|
| `filename` | `string` | VPX filename. |
| `manufacturer` | `string` | Manufacturer from VPX metadata. |
| `year` | `string` | Year from VPX metadata. |
| `type` | `string` | Table type from VPX metadata. |

### meta.VPXFile — Detection Flags

Boolean flags indicating detected features/addons in the VPX table:

| Property | Type | Description |
|----------|------|-------------|
| `detectnfozzy` | `boolean` | Nfozzy physics detected. |
| `detectfleep` | `boolean` | Fleep sound pack detected. |
| `detectssf` | `boolean` | SSF (Surround Sound Feedback) detected. |
| `detectfastflips` | `boolean` | FastFlips detected. |
| `detectlut` | `boolean` | LUT (color correction) detected. |
| `detectscorebit` | `boolean` | ScoreBit integration detected. |
| `detectflex` | `boolean` | FlexDMD detected. |
| `altSoundExists` | `boolean` | AltSound pack exists for this table. |
| `altColorExists` | `boolean` | AltColor pack exists for this table. |
| `pupPackExists` | `boolean` | PuP-Pack exists for this table. |

Example usage (feature detection lights):
```javascript
const meta = vpin.getTableMeta(currentTableIndex);
const vpx = meta.meta.VPXFile || {};

const features = [
    { key: "detectnfozzy", label: "Nfozzy" },
    { key: "detectfleep", label: "Fleep" },
    { key: "detectssf", label: "SSF" },
    { key: "detectfastflips", label: "FastFlips" },
    { key: "detectlut", label: "LUT" },
    { key: "detectscorebit", label: "ScoreBit" },
    { key: "detectflex", label: "FlexDMD" },
    { key: "altSoundExists", label: "AltSound" },
    { key: "altColorExists", label: "AltColor" },
    { key: "pupPackExists", label: "PuP-Pack" },
];

features.forEach(({ key, label }) => {
    const isOn = vpx[key] === true || vpx[key] === "true" || vpx[key] === 1;
    // Create a green/red indicator light based on isOn
});
```

### Reading Table Info

Common pattern for getting display-ready table information:

```javascript
const table = vpin.getTableMeta(currentTableIndex);
const info = table.meta.Info || {};
const vpx = table.meta.VPXFile || {};

const title = info.Title || vpx.filename || table.tableDirName || 'Unknown Table';
const manufacturer = info.Manufacturer || vpx.manufacturer || 'Unknown';
const year = info.Year || vpx.year || '';
const authors = Array.isArray(info.Authors) ? info.Authors.join(', ') : 'Unknown';
```

---

## Media Files

All media files are stored per-table in either the `medias/` subfolder or the table's root folder. The `medias/` subfolder is checked first.

```
<Table Folder>
├── medias/
│   ├── table.png (or fss.png)
│   ├── bg.png
│   ├── dmd.png
│   ├── wheel.png
│   ├── cab.png
│   ├── table.mp4 (or fss.mp4)
│   ├── bg.mp4
│   ├── dmd.mp4
│   └── audio.mp3
└── <tablename>.vpx
```

### Images

| File | API Type | Description |
|------|----------|-------------|
| `table.png` / `fss.png` | `"table"` | Table playfield image |
| `bg.png` | `"bg"` | Backglass image |
| `dmd.png` | `"dmd"` | DMD image |
| `wheel.png` | `"wheel"` | Wheel/logo image |
| `cab.png` | `"cab"` | Cabinet image |

Use `vpin.getImageURL(index, type)` to get the URL.

### Videos

| File | API Type | Description |
|------|----------|-------------|
| `table.mp4` / `fss.mp4` | `"table"` | Table playfield video |
| `bg.mp4` | `"bg"` | Backglass video |
| `dmd.mp4` | `"dmd"` | DMD video |

Use `vpin.getVideoURL(index, type)` to get the URL.

### Audio

| File | Description |
|------|-------------|
| `audio.mp3` | Per-table audio (music, callouts, etc.) |

Use `vpin.getAudioURL(index)` to get the URL. Returns `null` if no audio file exists.

---

## Video Support

Themes can display looping videos for table, backglass, and DMD screens in addition to (or instead of) static images.

Use `vpin.getVideoURL(index, type)` to get the video URL. The method returns a fallback `file_missing` URL if no video file exists, so check for this before creating a `<video>` element.

Example with image fallback:
```javascript
const videoUrl = vpin.getVideoURL(currentTableIndex, 'table');
const imageUrl = vpin.getImageURL(currentTableIndex, 'table');

if (videoUrl && !videoUrl.includes('file_missing')) {
    const preview = document.createElement('video');
    preview.className = 'preview';
    preview.poster = imageUrl;  // stable dimensions while video loads
    preview.src = videoUrl;
    preview.autoplay = true;
    preview.loop = true;
    preview.muted = true;
    preview.playsInline = true;
    // Fall back to image if video fails to load
    preview.onerror = () => {
        const fallback = document.createElement('img');
        fallback.className = 'preview';
        fallback.src = imageUrl;
        preview.replaceWith(fallback);
    };
    container.appendChild(preview);
} else {
    const preview = document.createElement('img');
    preview.className = 'preview';
    preview.src = imageUrl;
    container.appendChild(preview);
}
```

Key points:
- Set `muted = true` — browsers require this for autoplay to work without user gesture.
- Set `poster = imageUrl` — gives the video element proper dimensions before metadata loads, preventing layout shifts.
- The `onerror` handler provides a graceful fallback to the static image.
- You can check `vpin.tableData[index].TableVideoPath` directly to decide whether to create a video or image element.

---

## Audio Support

Themes can play per-table audio (e.g., table music or callouts) that changes as the user navigates between tables.

### Audio File

Place an `audio.mp3` file in the table's `medias/` folder (or root folder). `vpin.getAudioURL(index)` returns the URL, or `null` if no audio file exists.

### Implementation

Audio playback requires handling two different autoplay policies depending on the backend:

- **Chromium** (vpinfe-chromium branch): Launches with `--autoplay-policy=no-user-gesture-required`, so direct `audio.play()` calls work without restriction.
- **pywebview** (master branch): WebKitGTK blocks `audio.play()` from non-user-gesture contexts (like gamepad polling via `requestAnimationFrame`). The workaround is to call `vpin.call("trigger_audio_play")`, which uses Python's `evaluate_js` to play from a privileged context.

Here is a complete audio manager that works with both backends, supporting crossfade, retries, and fast navigation:

```javascript
const tableAudio = {
    audio: Object.assign(new Audio(), { loop: true }),
    fadeId: null,
    fadeDuration: 500,   // fade duration in ms
    maxVolume: 0.8,
    currentUrl: null,

    play(url, retries = 3) {
        if (!url) { this.stop(); return; }
        if (this.currentUrl === url && !this.audio.paused) return;

        const audio = this.audio;
        clearInterval(this.fadeId);
        audio.pause();
        audio.volume = 0;
        audio.src = url;
        this.currentUrl = url;

        // Try direct play first (works in Chromium)
        audio.play().then(() => {
            if (this.currentUrl === url) this._fade(0, this.maxVolume);
        }).catch(e => {
            if (e.name === 'NotAllowedError') {
                // Autoplay blocked (pywebview/WebKitGTK) - wait for audio to
                // load, then ask Python to play via evaluate_js
                this._retries = retries;
                this._triggerWhenReady(url);
            } else {
                // Other error (e.g., network) - retry after delay
                if (retries > 0 && this.currentUrl === url) {
                    setTimeout(() => this.play(url, retries - 1), 1000);
                }
            }
        });
    },

    // Wait for audio to load, then request privileged play from Python.
    // URL check ensures stale requests from fast navigation are ignored.
    _triggerWhenReady(url) {
        if (this.currentUrl !== url) return;
        if (this.audio.readyState >= 2) {
            vpin.call("trigger_audio_play").catch(() => {});
        } else {
            this.audio.addEventListener('canplay', () => {
                if (this.currentUrl === url) {
                    vpin.call("trigger_audio_play").catch(() => {});
                }
            }, { once: true });
        }
    },

    // Called from Python via evaluate_js (privileged context).
    // Audio is guaranteed loaded by _triggerWhenReady before this is called.
    _resumePlay() {
        const url = this.currentUrl;
        const retries = this._retries || 0;
        if (!url) return;

        this.audio.play().then(() => {
            if (this.currentUrl === url) this._fade(0, this.maxVolume);
        }).catch(e => {
            if (retries > 0 && this.currentUrl === url) {
                this._retries = retries - 1;
                setTimeout(() => this._triggerWhenReady(url), 500);
            }
        });
    },

    stop() {
        if (this.audio && !this.audio.paused) {
            this._fade(this.audio.volume, 0, () => {
                this.audio.pause();
                this.currentUrl = null;
            });
        } else {
            clearInterval(this.fadeId);
            this.currentUrl = null;
        }
    },

    _fade(from, to, onComplete) {
        clearInterval(this.fadeId);
        const audio = this.audio;
        if (!audio) { if (onComplete) onComplete(); return; }
        audio.volume = from;
        const steps = this.fadeDuration / 20;
        const delta = (to - from) / steps;
        this.fadeId = setInterval(() => {
            const next = audio.volume + delta;
            if ((delta > 0 && next >= to) || (delta < 0 && next <= to) || delta === 0) {
                audio.volume = to;
                clearInterval(this.fadeId);
                if (onComplete) onComplete();
            } else {
                audio.volume = next;
            }
        }, 20);
    }
};
```

### Usage in Your Theme

```javascript
function updateScreen() {
    // ... update images, carousel, etc. ...

    // Play audio only on the table window
    if (windowName === "table") {
        tableAudio.play(vpin.getAudioURL(currentTableIndex));
    }
}

// In your input handler:
case "joyselect":
    tableAudio.stop();  // stop audio before launching table
    vpin.sendMessageToAllWindows({ type: "TableLaunching" });
    await vpin.launchTable(currentTableIndex);
    break;

// In receiveEvent:
if (message.type == "TableRunning") {
    // Table has finished loading and is now running
}
if (message.type == "TableLaunchComplete") {
    fadeIn();
    if (windowName === "table") tableAudio.play(vpin.getAudioURL(currentTableIndex));
}
```

### Backend API Requirement

For audio to work on pywebview, the Python API class must include:
```python
def trigger_audio_play(self):
    """Trigger audio.play() via evaluate_js to bypass WebKitGTK autoplay policy."""
    self.myWindow[0].evaluate_js('tableAudio._resumePlay()')
```

On the Chromium branch, this method is a no-op since `--autoplay-policy=no-user-gesture-required` allows direct playback.

---

## CSS Patterns

### Fade Transitions

Two common patterns for fade-to-black transitions during table launch:

**Pattern 1: Fade container** (used by Carousel Desktop) — wrap all content in a container with `opacity` transition:
```css
#fadeContainer {
  position: fixed;
  top: 0; left: 0;
  width: 100vw; height: 100vh;
  transition: opacity 4.5s ease-in-out;
  opacity: 1;
}
```

**Pattern 2: Fade overlay** (used by Slider Video) — a fixed black overlay toggled via CSS class:
```css
#fadeOverlay {
  position: fixed;
  top: 0; left: 0;
  width: 100%; height: 100%;
  background: black;
  opacity: 0;
  transition: opacity 0.8s ease-in-out;
  pointer-events: none;
  z-index: 9999;
}
#fadeOverlay.show {
  opacity: 1;
}
```

### Base Styles

Recommended base styles to prevent white flash and scrollbars:
```css
html, body {
  margin: 0;
  padding: 0;
  height: 100%;
  overflow: hidden;
  background-color: black;
  color: white;
}
```

### Secondary Windows

For `bg` and `dmd` windows that show a single fullscreen image:
```css
.fullscreen-image-container {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
}
.fullscreen-image-container img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: opacity 0.5s ease-in-out;
}
```
