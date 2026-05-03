# Themes

VPinFE uses an embedded Chromium frontend with a WebSocket bridge to communicate between the browser and Python backend.

Themes interact with the backend through `vpinfe-core.js`, so theme code calls `vpin.call(...)` without handling transport details directly.

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
├── theme.json           (optional - schema plus saved Manager UI theme options)
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
| `type` | Theme type: `"desktop"` for desktop/flat-screen setups, `"cab"` for cabinet setups, or `"both"` for themes that adapt to either. |
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

### Table Rotation, Cab Mode, And Menu Overlays

If your theme supports cabinets or portrait-style table layouts, build that into the `table` window deliberately. In practice, the `table` window is usually the only screen that needs rotation-aware layout changes. `bg` and `dmd` often stay unrotated.

These calls are especially useful:

```javascript
const cabMode = await vpin.call("get_cab_mode");
const rotationDegree = await vpin.call("get_table_rotation");
```

Good questions to answer up front when starting a new theme:

- Should the theme declare `type: "cab"` or `type: "both"`?
- Should portrait mode use a different layout, or just rotate the landscape one?
- Should only the main table UI rotate, or should table-only overlays rotate too?

One easy thing to miss: the built-in menus are injected into `#overlay-root`, not inside your main theme container. If you rotate only your main table wrapper, the menus will still appear unrotated.

In other words:

- Rotating your table wrapper rotates your theme content
- Rotating `#overlay-root` rotates `mainmenu.html` and `collectionmenu.html`
- If you only do the first one, rotated table themes will have mismatched menus

For more advanced themes, it helps to think in layers:

- `#tableViewport`: fullscreen viewport wrapper
- `#tableScreen`: your actual table UI surface that may be rotated and scaled
- `#overlay-root`: injected menu host that may need the same transform as `#tableScreen`

That wrapper approach is much easier to maintain than rotating individual components one by one.

### index_bg.html & index_dmd.html

Same structure as above but with simpler content. These windows only display media and respond to events — they don't handle input.

Important: theme code for these windows should support both static images and videos. In practice that means:

- `bg` windows should prefer `bg.mp4` and fall back to `bg.png`
- `dmd` windows should prefer `dmd.mp4` and fall back to `dmd.png`

Do not hardcode these windows to image-only rendering with `getImageURL()` alone, or `bg.mp4` / `dmd.mp4` will never appear even when the files exist.

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

Typical JS pattern for these windows:

```javascript
function hasUsableMedia(url) {
  return Boolean(url) && !String(url).includes('file_missing');
}

function renderWindowMedia(container, imageUrl, videoUrl, altText) {
  const existingMedia = container.querySelector('video, img');
  const wantsVideo = hasUsableMedia(videoUrl);

  if (existingMedia) {
    if (existingMedia.tagName === 'VIDEO') {
      existingMedia.pause();
      existingMedia.removeAttribute('src');
      existingMedia.load();
    }
    existingMedia.remove();
  }

  if (wantsVideo) {
    const video = document.createElement('video');
    video.src = videoUrl;
    video.poster = hasUsableMedia(imageUrl) ? imageUrl : '';
    video.autoplay = true;
    video.loop = true;
    video.muted = true;
    video.playsInline = true;
    video.style.cssText = 'width: 100%; height: 100%; object-fit: cover;';
    video.onerror = () => {
      if (!hasUsableMedia(imageUrl)) return;
      const fallback = document.createElement('img');
      fallback.src = imageUrl;
      fallback.alt = altText;
      fallback.style.cssText = 'width: 100%; height: 100%; object-fit: cover;';
      video.replaceWith(fallback);
    };
    container.appendChild(video);
    return;
  }

  const img = document.createElement('img');
  img.src = hasUsableMedia(imageUrl) ? imageUrl : '';
  img.alt = altText;
  img.style.cssText = 'width: 100%; height: 100%; object-fit: cover;';
  container.appendChild(img);
}

function updateBGWindow() {
  const container = document.getElementById('rootContainer');
  const bgUrl = vpin.getImageURL(currentTableIndex, 'bg');
  const bgVideoUrl = vpin.getVideoURL(currentTableIndex, 'bg');
  renderWindowMedia(container, bgUrl, bgVideoUrl, 'Backglass');
}

function updateDMDWindow() {
  const container = document.getElementById('rootContainer');
  const dmdUrl = vpin.getImageURL(currentTableIndex, 'dmd');
  const dmdVideoUrl = vpin.getVideoURL(currentTableIndex, 'dmd');
  renderWindowMedia(container, dmdUrl, dmdVideoUrl, 'DMD');
}
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

VPinFE also passes the current window identity in the page URL as `?window=table`, `?window=bg`, or `?window=dmd`. For high-DPI backglass and DMD setups, VPinFE may also include an optional `override` query parameter in the form `x,y,width,height`. Theme authors can read that value when they need to use the configured bounds instead of the auto-detected browser window size.

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

    // optional: load values from theme.json in your theme dir
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
        await fadeOut();
    }
    else if (message.type == "TableRunning") {
        // Table has finished loading and is now running
    }
    else if (message.type == "TableLaunchComplete") {
        fadeIn();
    }
    else if (message.type == "RemoteLaunching") {
        // Remote launch from manager UI - message.table_name has the table name
        showRemoteLaunchOverlay(message.table_name);
        await fadeOut();
    }
    else if (message.type == "RemoteLaunchComplete") {
        hideRemoteLaunchOverlay();
        fadeIn();
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
        vpin.playTableAudio(currentTableIndex);
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

### Strong Recommendation: Keep The Table DOM Persistent

For anything beyond a very simple theme, especially carousel-style table screens, avoid rebuilding the entire table window DOM on every table change.

A much smoother pattern is:

1. Create the table view scaffold once
2. Keep references to the important nodes
3. Update wheel art, title text, media, and tags in place
4. Only swap the specific media layer or text nodes that actually changed

This matters a lot for:

- smoother wheel navigation
- less layout jitter while images load
- cleaner image/video fades
- reduced browser work in Chromium

If a theme feels choppy, a full-screen rebuild on every selection change is one of the first things to remove.

### Media And Transition Performance Tips

The fastest-looking theme is usually the one doing the least work during browsing.

Things that helped in practice:

- preload nearby media such as the current, previous, and next table images
- prefer updating existing `<img>` / `<video>` nodes or swapping a small media layer instead of rerendering the whole screen
- keep fades simple; a plain crossfade is usually smoother than blur-heavy "dissolve" effects
- be careful with simultaneous animation systems; CSS transitions plus a JS animation library or canvas effects can stack up quickly
- if wheel browsing feels sluggish, test without heavy motion libraries first

For table video specifically, image-first browsing with delayed video start is often smoother than immediately starting video while the user is rapidly scrolling.

### Carousel Motion Guidance

If you want a wheel carousel to feel smooth instead of "slotty":

- keep a persistent wheel strip instead of recreating wheel nodes every move
- use a buffered strip with offscreen items if you want real scrolling motion
- anchor any selection halo or highlight to the selected position, not to the moving wheel artwork
- keep the selected/non-selected size difference moderate during motion so the eye follows the scroll instead of the scale jump
- tune motion duration generously; motion that is technically correct but too fast still reads like hopping

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

### Loading Overlay During Table Launch

Themes can show a loading image or animation while VPX is starting. Use the built-in launch lifecycle instead of guessing with timers:

- show the overlay on `TableLaunching`
- hide it on `TableRunning`
- also hide it on `TableLaunchComplete` as a cleanup fallback

Add the overlay markup to every theme page that should show it (`index_table.html`, `index_bg.html`, and/or `index_dmd.html`):

```html
<div id="table-loading-overlay" aria-hidden="true">
  <img src="img/loading.gif" alt="" class="table-loading-spinner">
</div>
```

Keep the overlay transparent if you want the normal screen fade to remain visible underneath:

```css
#table-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  pointer-events: none;
  transition: opacity 180ms ease;
}

#table-loading-overlay.is-visible {
  opacity: 1;
}

.table-loading-spinner {
  width: min(34vw, 34vh, 500px);
  height: min(34vw, 34vh, 500px);
  object-fit: contain;
}
```

Then drive it from `receiveEvent(message)`:

```js
function showTableLoadingOverlay() {
  const overlay = document.getElementById("table-loading-overlay");
  if (!overlay) return;

  overlay.classList.add("is-visible");
  overlay.setAttribute("aria-hidden", "false");
}

function hideTableLoadingOverlay() {
  const overlay = document.getElementById("table-loading-overlay");
  if (!overlay) return;

  overlay.classList.remove("is-visible");
  overlay.setAttribute("aria-hidden", "true");
}

async function receiveEvent(message) {
  await vpin.handleEvent(message);

  if (message.type === "TableLaunching") {
    showTableLoadingOverlay();
    await fadeOut();
  } else if (message.type === "TableRunning") {
    hideTableLoadingOverlay();
  } else if (message.type === "TableLaunchComplete") {
    hideTableLoadingOverlay();
    fadeIn();
  }
}
```

If the table window launches the table from local input, remember that `vpin.sendMessageToAllWindows(...)` excludes the sender. Call `showTableLoadingOverlay()` directly in the local `joyselect` path before `await vpin.launchTable(...)`, or send the event with `vpin.sendMessageToAllWindowsIncSelf(...)`.

### Input Actions

The following input actions are passed to your `handleInput` function (table window only):

| Action | Gamepad | Keyboard |
|--------|---------|----------|
| `joyleft` | Mapped button | `[Input] keyleft` (default `ArrowLeft,ShiftLeft`) |
| `joyright` | Mapped button | `[Input] keyright` (default `ArrowRight,ShiftRight`) |
| `joyup` | Mapped button | `[Input] keyup` (default `ArrowUp`) |
| `joydown` | Mapped button | `[Input] keydown` (default `ArrowDown`) |
| `joyselect` | Mapped button | `[Input] keyselect` (default `Enter`) |
| `joyback` | Mapped button | `[Input] keyback` |
| `joytutorial` | Mapped button | `[Input] keytutorial` when routed to handlers |

The following actions are handled internally by VPinFECore and do **not** reach your handler:

| Action | Gamepad | Keyboard | Effect |
|--------|---------|----------|--------|
| `joymenu` | Mapped button | `[Input] keymenu` (default `m`) | Toggles the main menu overlay |
| `joycollectionmenu` | Mapped button | `[Input] keycollectionmenu` (default `c`) | Toggles the collection menu overlay |
| `joytutorial` | Mapped button | `[Input] keytutorial` (default `t`) | Toggles the Pinball Primer tutorial overlay |
| `joyexit` | Mapped button | `[Input] keyexit` (default `Escape,q`) | Closes the application |

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
Sets up keyboard event listener and connects to the backend over the WebSocket bridge.

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
Invokes a backend API method over the WebSocket bridge. Returns a Promise.

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
| `launch_table` | `index` | — | Launches the VPX table at the given index. Blocks until the table exits. Automatically tracks play in the "Last Played" collection. Sends `TableLaunching` before launch, `TableRunning` when the table finishes loading, and `TableLaunchComplete` when it exits. |
| `build_metadata` | `download_media=true`, `update_all=false` | `object` | Triggers a background metadata build/refresh. Sends progress events (`buildmeta_progress`, `buildmeta_log`, `buildmeta_complete`, `buildmeta_error`) to all windows. Returns `{success, message}`. |

##### Collections

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_collections` | — | `array` | Returns list of collection names from `collections.ini`. |
| `get_collections_metadata` | — | `array` | Returns collection objects with `name`, `type`, `is_filter`, `image`, `image_url`, and `table_count`. `image_url` is a theme-server URL such as `/collection_icons/favorites.png`, or an empty string when no image is set. |
| `get_collection_image_url` | `collection` | `string` | Returns the image URL for one collection, or an empty string when no image is set. |
| `set_tables_by_collection` | `collection` | — | Filters the table list by the named collection. Supports both VPS ID-based and filter-based collections. |
| `save_filter_collection` | `name`, `letter`, `theme`, `table_type`, `manufacturer`, `year`, `sort_by`, `rating`, `rating_or_higher`, `order_by` | `object` | Saves the current filter settings as a named collection. `order_by` is `"Descending"` or `"Ascending"` and defaults to `"Descending"`. Returns `{success, message}`. |
| `get_current_collection` | — | `string` | Returns the name of the currently active collection, or `"None"`. |

##### Filters & Sorting

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `apply_filters` | `letter`, `theme`, `table_type`, `manufacturer`, `year`, `rating`, `rating_or_higher` | `number` | Applies VPSdb filters to the full table list. Each arg is optional (pass `null` to keep current). Returns the filtered count. |
| `reset_filters` | — | — | Resets all filters back to the full table list. |
| `apply_sort` | `sort_type`, `order_by` | `number` | Sorts the current filtered tables. `sort_type` is `"Alpha"`, `"Newest"`, `"LastRun"`, `"Highest StartCount"`, or `"RunTime"`; `order_by` is `"Descending"` or `"Ascending"`. Returns the count. |
| `get_current_filter_state` | — | `object` | Returns the current filter state: `{letter, theme, type, manufacturer, year, rating, rating_or_higher}`. |
| `get_current_sort_state` | — | `string` | Returns the current sort type. |
| `get_current_order_state` | — | `string` | Returns the current sort order (`"Descending"` or `"Ascending"`). |
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

##### Input

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_joymaping` | — | `object` | Returns the gamepad button mapping from `vpinfe.ini`. Keys: `joyleft`, `joyright`, `joyup`, `joydown`, `joyselect`, `joymenu`, `joyback`, `joytutorial`, `joyexit`, `joycollectionmenu`. Values are button index strings. |
| `get_keymapping` | — | `object` | Returns the keyboard mapping from `vpinfe.ini`. Keys: `keyleft`, `keyright`, `keyup`, `keydown`, `keyselect`, `keymenu`, `keyback`, `keytutorial`, `keyexit`, `keycollectionmenu`. Values are comma-separated browser key names or key codes. |
| `set_button_mapping` | `button_name`, `button_index` | `object` | Sets a gamepad button mapping and saves to config. Returns `{success, message}`. |

##### Theme & Display Config

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_theme_name` | — | `string` | Returns the active theme name from `vpinfe.ini`. |
| `get_theme_config` | — | `object\|null` | Loads and returns the theme's current configuration values. When a theme provides `theme.json`, VPinFE flattens the option `value` fields into the object returned to theme code. |
| `get_theme_assets_port` | — | `number` | Returns the HTTP server port (default `8000`). |
| `get_theme_index_page` | — | `string` | Returns the full URL for this window's theme index page. |
| `get_table_orientation` | — | `string` | Returns the table orientation from config (`"landscape"` or `"portrait"`). |
| `get_table_rotation` | — | `number` | Returns the table rotation angle in degrees from config (default `0`). |

##### URL Query Parameters

Theme pages receive the current window name in the `window` query parameter:

- `?window=table`
- `?window=bg`
- `?window=dmd`

For `bg` and `dmd`, VPinFE can also pass an optional high-DPI display override:

- `?override=x,y,width,height`

This is intended for setups where the detected Chromium window bounds are not the values the theme should use, usually on high-DPI screens. The `override` value is a comma-separated string containing:

- `x`: left position
- `y`: top position
- `width`: window width
- `height`: window height

Example:

```javascript
const params = new URLSearchParams(window.location.search);
const windowName = params.get('window') || 'unknown';
const override = params.get('override');

let overrideBounds = null;
if (override) {
  const [x, y, width, height] = override.split(',').map(Number);
  overrideBounds = { x, y, width, height };
}
```

If `override` is present, themes that position or scale BG/DMD content based on window bounds should prefer those values over `window.innerWidth`, `window.innerHeight`, or other automatically detected measurements.

##### Core Audio Helpers

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `playTableAudio` | `indexOrUrl`, `retries=3` | — | Plays table audio using VPinFECore's centralized audio manager. Pass a table index (recommended) or URL string. |
| `stopTableAudio` | `options={}` | — | Stops audio via centralized manager. Supports fade-out; pass `{ immediate: true }` for an immediate stop. |
| `enableCoreAudio` | `enabled=true` | — | Enables or disables centralized audio handling for the current window. Core audio is opt-in by default unless enabled in theme config. |
| `isCoreAudioEnabled` | — | `boolean` | Returns whether centralized audio handling is currently enabled. |
| `setAudioOptions` | `options` | — | Sets runtime audio options. Supported keys: `maxVolume`/`max_volume`/`volume`, `fadeDuration`/`fade_duration_ms`/`fadeMs`, `loop`. |

#### getImageURL(index, type)
Returns an HTTP URL for a table's image. `type` can be `"table"`, `"bg"`, `"dmd"`, `"wheel"`, or `"cab"`. Returns a fallback `/web/images/file_missing.png` URL if the file doesn't exist.

#### getVideoURL(index, type)
Returns an HTTP URL for a table's video. `type` can be `"table"`, `"bg"`, or `"dmd"`. Returns a fallback `/web/images/file_missing.png` URL if no video exists. See [Video Support](#video-support).

#### getAudioURL(index)
Returns an HTTP URL for a table's audio file, or `null` if no audio exists. See [Audio Support](#audio-support).

#### playTableAudio(indexOrUrl, retries=3)
Plays table audio via VPinFECore's centralized audio manager. Normally you pass `currentTableIndex`; passing a URL string is also supported.

#### stopTableAudio(options={})
Stops centralized audio playback. Default behavior is fade-out, or pass `{ immediate: true }` for an immediate stop.

#### enableCoreAudio(enabled=true)
Turns centralized core audio handling on or off for the current window.

#### isCoreAudioEnabled()
Returns `true` when centralized core audio handling is enabled.

#### setAudioOptions(options)
Updates centralized audio options at runtime: volume (`maxVolume`, `max_volume`, or `volume`), fade duration (`fadeDuration`, `fade_duration_ms`, or `fadeMs`), and `loop`.

#### getTableMeta(index)
Returns the full table object for a given table index. This is the same object as `vpin.tableData[index]`. See [Table Data Object](#table-data-object).

#### getTableCount()
Returns the number of tables in the current (possibly filtered) table list.

#### sendMessageToAllWindows(message)
Sends an event to all windows except the current one. Convenience wrapper around `vpin.call("send_event_all_windows", message)`.

#### sendMessageToAllWindowsIncSelf(message)
Sends an event to all windows including the current one and forwarding to iframes.

#### launchTable(index)
Disables gamepad input, calls backend to launch the selected table, then re-enables gamepad input. The launch lifecycle is `TableLaunching` before the process starts, `TableRunning` when the table finishes loading, and `TableLaunchComplete` when it exits.

#### getTableData(reset=false)
Loads table data from the backend into `vpin.tableData`. Pass `reset=true` to reload from the full unfiltered table list.

#### handleEvent(message)
Handles incoming events with built-in logic for:
- `TableDataChange` (collection/filter/sort changes)
- centralized audio transitions on `TableIndexUpdate`, `TableLaunching`, `RemoteLaunching`, `TableLaunchComplete`, and `RemoteLaunchComplete`

Call this at the top of your `receiveEvent` function to get automatic data refresh and default audio behavior.

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
| `vpinplay` | `object\|null` | Cached VPinPlay cumulative rating payload for the table, or `null` until fetched/unavailable. |

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

### meta.User

Per-user stats and preferences stored in each table's `.info` file:

| Property | Type | Description |
|----------|------|-------------|
| `Rating` | `number` | User rating from `0` to `5`. |
| `Favorite` | `number` | Favorite flag (`0` or `1`). |
| `LastRun` | `number\|null` | Unix timestamp (seconds) of the last launch, or `null` if never played. |
| `StartCount` | `number` | Number of times the table has been launched. |
| `RunTime` | `number` | Total accumulated play time in minutes. |
| `Tags` | `array` | User-defined tags (string list). |

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
const user = table.meta.User || {};
const vpx = table.meta.VPXFile || {};

const title = info.Title || vpx.filename || table.tableDirName || 'Unknown Table';
const manufacturer = info.Manufacturer || vpx.manufacturer || 'Unknown';
const year = info.Year || vpx.year || '';
const authors = Array.isArray(info.Authors) ? info.Authors.join(', ') : 'Unknown';
const rating = Number(user.Rating || 0);
const plays = Number(user.StartCount || 0);

const vpinplay = await vpin.getVPinPlayRating(currentTableIndex);
const cumulativeRating = vpinplay?.cumulativeRating ?? null;
const ratingCount = vpinplay?.ratingCount ?? 0;
```

### VPinPlay Rating

`vpinfe-core.js` can fetch the selected table's VPinPlay cumulative rating from the configured `vpinplay.apiendpoint`.

| Method | Returns | Description |
|--------|---------|-------------|
| `await vpin.getVPinPlayRating(index?)` | `object\|null` | Returns the cached rating for the table or fetches it from VPinPlay. |
| `await vpin.refreshVPinPlayRating(index?)` | `object\|null` | Forces a fresh fetch from VPinPlay. |
| `vpin.getCachedVPinPlayRating(index?)` | `object\|null` | Returns only the cached value already attached to the table. |

The returned object matches the API payload shape and is also stored on the table entry as `table.vpinplay`:

```javascript
const table = vpin.getTableMeta(currentTableIndex);
const rating = table.vpinplay?.cumulativeRating ?? null;
const votes = table.vpinplay?.ratingCount ?? 0;
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

For `bg` and `dmd` windows, use the same pattern with:

- `vpin.getVideoURL(currentTableIndex, 'bg')` plus `vpin.getImageURL(currentTableIndex, 'bg')`
- `vpin.getVideoURL(currentTableIndex, 'dmd')` plus `vpin.getImageURL(currentTableIndex, 'dmd')`

Recommended rule for theme authors:

- Table window: optionally prefer `table.mp4` over `table.png` / `fss.png`
- BG window: prefer `bg.mp4`, fall back to `bg.png`
- DMD window: prefer `dmd.mp4`, fall back to `dmd.png`

If you only use `getImageURL()` in BG or DMD renderers, those windows will remain image-only even when the matching video files exist.

Key points:
- Set `muted = true` — browsers require this for autoplay to work without user gesture.
- Set `poster = imageUrl` — gives the video element proper dimensions before metadata loads, preventing layout shifts.
- The `onerror` handler provides a graceful fallback to the static image.
- You can check `vpin.tableData[index].TableVideoPath` directly to decide whether to create a video or image element.

---

## Audio Support

VPinFECore now includes a centralized per-table audio manager. Theme code can use it directly and no longer needs to implement its own `Audio`/fade/retry logic.

### Audio File

Place an `audio.mp3` file in the table's `medias/` folder (or root folder). `vpin.getAudioURL(index)` returns the URL, or `null` if no audio file exists.

### Core Behavior

On the `table` window, `await vpin.handleEvent(message)` automatically manages audio transitions when core audio is enabled.

Core audio is opt-in by default. If your theme does not explicitly enable it (or call `vpin.enableCoreAudio(true)` at runtime), no automatic table audio playback will occur.

When enabled, these transitions are handled automatically:
- `TableIndexUpdate` -> play selected table audio
- `TableLaunching` and `RemoteLaunching` -> fade/stop audio
- `TableLaunchComplete` and `RemoteLaunchComplete` -> resume audio for current selection
- `TableDataChange` (with `index`) -> play audio for that index

### Backend vs Frontend Responsibility

`api.py` knows when table launch starts/completes and emits lifecycle events, but it does not own the browser `Audio` object. Actual playback, fading, retries, and autoplay-policy handling must run in frontend JavaScript (`VPinFECore`/theme code), which owns the in-memory audio state.

### Practical Note: Self-Event Caveat

`vpin.sendMessageToAllWindows(...)` excludes the sender. If your `table` window sends `TableLaunching`, it might not receive that same event back, so backend-emitted lifecycle events are the reliable source of truth for launch state.

For robust behavior, it is valid to also call:
- `vpin.stopTableAudio()` directly in your local `joyselect`/launch path
- `vpin.playTableAudio(currentTableIndex)` directly on local launch-complete handling

This explicit local stop/resume acts as a safety net while still using centralized core audio.

Defaults:
- volume: `0.8`
- fade duration: `500ms`
- loop: `true`

### Usage in Your Theme

```javascript
function updateScreen() {
    // ... update images, carousel, etc ...
    if (windowName === "table") {
        vpin.playTableAudio(currentTableIndex);
    }
}

async function receiveEvent(message) {
    // Keep this call at the top for built-in table-data refresh and core audio handling
    await vpin.handleEvent(message);
    // ... theme-specific event handling ...
}

// Optional immediate stop:
// vpin.stopTableAudio({ immediate: true });
```

### Configuration Schema (theme `theme.json`)

If your theme wants Manager UI-editable options, add a `theme.json` file to the theme root.

`theme.json` now serves as both the option schema and the saved value store. VPinFE Manager UI reads this file to build the configuration dialog and writes the selected values back into each option's `value` field.

Example:

```json
{
  "title": "Carousel Desktop Options",
  "description": "These options control layout and audio behavior.",
  "options": [
    {
      "key": "wheel.scale",
      "name": "Wheel Scale",
      "description": "Controls the wheel image scale multiplier.",
      "type": "number",
      "value": 1,
      "min": 0.5,
      "max": 2,
      "step": 0.1
    },
    {
      "key": "showClock",
      "name": "Show Clock",
      "description": "Show the clock overlay in the table window.",
      "type": "boolean",
      "value": true
    },
    {
      "key": "audio.mode",
      "name": "Audio Mode",
      "description": "Select how the theme should handle table audio.",
      "type": "select",
      "value": "core",
      "options": ["off", "core", "theme"]
    }
  ]
}
```

Full sample `theme.json` for quick testing:

```json
{
  "title": "Sample Theme Options",
  "description": "Example configurable options exposed through the VPinFE Themes page.",
  "options": [
    {
      "key": "showClock",
      "name": "Show Clock",
      "description": "Show a clock overlay on the table screen.",
      "type": "boolean",
      "value": true
    },
    {
      "key": "headerTitle",
      "name": "Header Title",
      "description": "Text displayed in the theme header.",
      "type": "text",
      "value": "My Custom Theme"
    },
    {
      "key": "footerMessage",
      "name": "Footer Message",
      "description": "Multi-line text shown at the bottom of the screen.",
      "type": "textarea",
      "value": "Welcome to VPinFE\nPress Start to Play"
    },
    {
      "key": "wheel.scale",
      "name": "Wheel Scale",
      "description": "Scale multiplier for wheel art.",
      "type": "number",
      "value": 1,
      "min": 0.5,
      "max": 2,
      "step": 0.1
    },
    {
      "key": "themeMode",
      "name": "Theme Mode",
      "description": "Choose the overall layout style.",
      "type": "select",
      "value": "arcade",
      "options": [
        "minimal",
        "arcade",
        "modern"
      ]
    },
    {
      "key": "accentColor",
      "name": "Accent Color",
      "description": "Hex color used for highlights.",
      "type": "text",
      "value": "#ffd84d"
    },
    {
      "key": "audio.enabled",
      "name": "Enable Audio",
      "description": "Turn theme-controlled audio behavior on or off.",
      "type": "boolean",
      "value": true
    },
    {
      "key": "audio.maxVolume",
      "name": "Audio Max Volume",
      "description": "Maximum playback volume for theme audio.",
      "type": "number",
      "value": 0.8,
      "min": 0,
      "max": 1,
      "step": 0.05
    },
    {
      "key": "advancedRules",
      "name": "Advanced Rules JSON",
      "description": "Raw JSON for advanced theme behavior.",
      "type": "json",
      "value": {
        "showTop10": true,
        "animateWheel": false,
        "videoFadeMs": 750
      }
    }
  ]
}
```

Supported field types in `theme.json`:

- `text`
- `textarea`
- `number`
- `boolean`
- `select`
- `json`

Notes:

- `key` is required and identifies the value returned through `get_theme_config()`. Dot notation such as `audio.enabled` creates nested objects in the returned config.
- `name` is the display label shown in Manager UI. If omitted, the `key` is shown.
- `description` is shown as help text in the dialog.
- `value` is the current saved value edited by the user.
- `default` is optional and is used as a fallback if `value` is omitted.
- `select` options may be simple scalar values or `{label, value}` objects.

### Values Returned To Theme Code

Themes should continue reading user configuration through `get_theme_config()`, which returns a plain values object derived from `theme.json`.

For compatibility, if `theme.json` is missing, VPinFE still falls back to a legacy `config.json` file when present.

For the sample schema above, `get_theme_config()` would return an object like this:

```json
{
  "showClock": true,
  "headerTitle": "My Custom Theme",
  "footerMessage": "Welcome to VPinFE\nPress Start to Play",
  "wheel": {
    "scale": 1
  },
  "themeMode": "arcade",
  "accentColor": "#ffd84d",
  "audio": {
    "enabled": true,
    "maxVolume": 0.8
  },
  "advancedRules": {
    "showTop10": true,
    "animateWheel": false,
    "videoFadeMs": 750
  }
}
```

Core audio can be configured from theme config:

```json
{
  "use_core_audio": true,
  "audio": {
    "enabled": true,
    "maxVolume": 0.8,
    "fadeDuration": 500,
    "loop": true
  }
}
```

If omitted, core audio remains disabled by default.

Also accepted for compatibility:
- `useCoreAudio` (camelCase)
- `audio.max_volume` or `audio.volume`
- `audio.fade_duration_ms` or `audio.fadeMs`

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
