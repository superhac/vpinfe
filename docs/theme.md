# Themes

VPinFE uses an embedded Chromium frontend with a WebSocket bridge to communicate between the browser and Python backend.

Themes interact with the backend through `vpinfe-core.js`, so theme code calls `vpin.call(...)` without handling transport details directly.

### Windows

VPinFE runs up to 3 browser windows, one per monitor:

- `table` — The main screen. Controller for all other screens and input. Handles gamepad/keyboard input and hosts the in-theme menu overlays.
- `bg` — Backglass screen. Receives events from the `table` window.
- `dmd` — DMD screen (not a "real DMD" like ZeDMD). Receives events from the `table` window.

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
  "change_log": "Initial release.",
  "contract": 2
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
| `contract` | Which VPinFE theme contract this theme is written against. Optional; absent means `1`. See [Theme contract](#theme-contract). |

`version` is your theme's own release number. `contract` is the VPinFE surface it reads.
They are different questions and they move independently.

### Theme contract

VPinFE serves the game payload in the shape your theme declares, so a theme keeps working
when the data behind it is reshaped.

| Contract | What the payload looks like |
|---|---|
| `1` (default) | An **array of game rows**. Each row is one game, with its default table folded into `meta.VPXFile` and a media path per kind at the top level. This is what every theme written before 3.0 reads, and it is unchanged. |
| `2` | An **object with an `entries` array**. Each entry is one *table*, with the game it belongs to attached. A game that offers several tables can appear more than once. |

These are different shapes, not the same shape with different key names — declaring
`contract: 2` changes how you iterate the payload, not just what you call things. See
[Contract 2 payload](#contract-2-payload).

**You do not need to bump `contract` when VPinFE adds things.** New media kinds, new fields
and new `vpin.*` methods are visible at every contract — check for what you want and use it
if it is there:

```javascript
if (typeof vpin.someNewMethod === "function") {
    vpin.someNewMethod();
}
```

A contract only goes up when something a theme already reads is **removed or reshaped**, so
bumps are rare. If you declare a contract newer than the VPinFE you are running on, you get
the newest that build has and a warning in the log.

### Contract 2 payload

At `contract: 2` the payload is an object, and the list you iterate is `entries`:

```json
{
  "collection": "Friday Night",
  "expanded": false,
  "count": 3,
  "entries": [
    {
      "game": {
        "id": "tuF3WogthK", "vps_id": "9Paf7-CL",
        "name": "Attack from Mars", "manufacturer": "Bally",
        "year": "1995", "type": "SS", "themes": ["Aliens"],
        "dir_name": "Attack from Mars (Bally 1995)",
        "path": "/games/Attack from Mars (Bally 1995)",
        "user": { "rating": 4, "favorite": false, "tags": [],
                  "last_played": "2026-08-01T20:14:00Z",
                  "play_count": 12, "play_time_seconds": 5400 }
      },
      "table": {
        "id": "Ls3JyWq7Fm", "filename": "Attack from Mars VPW Mod 1.2.vpx",
        "path": "/games/.../Attack from Mars VPW Mod 1.2.vpx",
        "version": "1.3.0", "rom": "afm_113b", "authors": ["jpsalas"],
        "detects": { "ssf": true, "nfozzy": false, "fleep": false }
      },
      "assets": { "pup_pack": true, "alt_color": false, "alt_sound": false },
      "siblings": 2,
      "media": { "PlayfieldImagePath": "…", "BGImagePath": "…" }
    }
  ]
}
```

**An entry is a table, not a game.** A game folder can hold several `.vpx` — a desktop
build, a VR build, a patched variant — and they are peers. One entry is one of them, with
the game it belongs to attached.

| Field | What it is |
|---|---|
| `collection` | The collection being shown, or `""` for an ad-hoc filtered view. |
| `expanded` | `false` means one entry per game — its default table. `true` means one entry per table, so a game with three tables contributes three. The user sets this; your theme does not have to do anything differently either way. |
| `count` | How many entries. The same as `entries.length`. |
| `entries[].game` | Identity and metadata for the machine. The same names `/api/v1/games` uses. |
| `entries[].game.user` | What this user did with the game: `rating`, `favorite`, `tags`, `last_played`, `play_count`, `play_time_seconds`. Timestamps are ISO 8601 UTC and durations name their unit, whatever the `.info` stores. |
| `entries[].table` | The `.vpx` this entry is. `id` is stable across renames; `filename` is not. |
| `entries[].table.user` | The same counters for this table alone — `last_played`, `play_count`, `play_time_seconds`. A game and its tables accumulate independently, so deleting a table does not un-play the game's hours. |
| `entries[].assets` | What the game needs to play as intended, as booleans. |
| `entries[].siblings` | How many tables this entry's game offers. `1` means there is nothing to switch to. |
| `entries[].media` | The resolved media paths, the same keys contract 1 puts at the top of a row. |

**`detects` loses the `detect_` prefix.** `table.detects.ssf`, not `detect_ssf` — the
prefix was storage, not vocabulary.

**There is no `meta` at contract 2.** `meta` was the `.info` file passed through, so a
storage change reached themes whether or not it meant anything to them. Contract 2 serves
a payload of its own instead, and `.info` can be reshaped without touching your theme.
Everything `meta` carried that a theme actually reads has a home above.

**There is no entry id.** `table.id` is the identity — a table appears at most once in a
collection, so nothing else is needed.

### Names that changed in 3.0

3.0 takes its nouns from the Virtual Pinball Spreadsheet: the machine is a **game**, the
`.vpx` is a **table**, and the main screen is the **playfield**. Nothing was removed, and a
2.x theme needs no edits. Two different mechanisms keep it working, and which one you are
leaning on decides whether declaring `contract: 2` changes anything for you.

**The payload follows the contract you declare.** At `1` — which is what you get by
declaring nothing — VPinFE builds the row shape 2.x themes read, including the names 2.x
used:

| the 3.0 name | what contract 1 serves |
|---|---|
| `gameDirName` | `tableDirName` |
| `fullPathGame` | `fullPathTable` |
| `PlayfieldImagePath` | `TableImagePath` |
| `PlayfieldVideoPath` | `TableVideoPath` |
| `meta.tables` | `meta.VPXFile` |
| `meta.vpinfe` | `meta.VPinFE` |

**The `vpin.*` surface does not follow the contract.** The projection reshapes the payload
and has never covered the JavaScript API, so the old names are aliases on the same object
instead. They work at every contract, for reads, writes and calls alike:

| use | still works |
|---|---|
| `vpin.gameData` | `vpin.tableData` |
| `vpin.playfieldRotation` | `vpin.tableRotation` |
| `vpin.playfieldOrientation` | `vpin.tableOrientation` |
| `vpin.getGameMeta()` | `vpin.getTableMeta()` |
| `vpin.getGameData()` | `vpin.getTableData()` |
| `vpin.getGameCount()` | `vpin.getTableCount()` |
| `vpin.getCurrentGameIndex()` | `vpin.getCurrentTableIndex()` |
| `vpin.getAllGames()` | `vpin.getAllTables()` |
| `vpin.playGameAudio()` | `vpin.playTableAudio()` |
| `vpin.stopGameAudio()` | `vpin.stopTableAudio()` |
| `vpin.launchGame()` | `vpin.launchTable()` |

**Window messages carry both spellings.** Every one below is broadcast under its new name
and its old one, so a theme listening for either keeps receiving it. Inbound messages are
accepted either way too.

| new | legacy |
|---|---|
| `GameIndexUpdate` | `TableIndexUpdate` |
| `GameDataChange` | `TableDataChange` |
| `GameLaunching` | `TableLaunching` |
| `GameRunning` | `TableRunning` |
| `GameLaunchComplete` | `TableLaunchComplete` |

The aliases are not a second API. Write new themes against the `game` and `playfield`
names — those are what the rest of this document uses.

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
| `<div id="fadeContainer">` | Wrap your content for fade-to-black transitions on game launch/return. Style with `transition: opacity` in CSS. |
| `<div id="fadeOverlay">` | Alternative fade pattern: a fixed full-screen black overlay that fades in/out via a CSS class (e.g., `.show { opacity: 1 }`). |
| `<div id="remote-launch-overlay">` | Overlay shown when the manager UI triggers a remote game launch. Include `<div id="remote-launch-table-name">` inside for the game name. |

### Playfield Rotation, Cab Mode, And Menu Overlays

If your theme supports cabinets or portrait-style playfield layouts, build that into the `table` window deliberately. In practice, the `table` window is usually the only screen that needs rotation-aware layout changes. `bg` and `dmd` often stay unrotated.

There are two different rotation concepts to keep separate:

- **OS monitor orientation**: If the user sets the playfield monitor to Portrait in the operating system, Chromium receives a portrait-shaped window. For example, CSS `100vw` is the narrow edge and `100vh` is the long edge.
- **VPinFE playfield rotation**: `[Displays] playfieldrotation` is exposed to themes as `vpin.playfieldRotation` and `get_playfield_rotation`. This tells the theme how to rotate its playfield UI inside that Chromium window.

VPinFE does not automatically rotate arbitrary theme markup. The backend launches Chromium on the configured monitor and `vpinfe-core.js` loads display values during `vpin.ready`; the theme decides how to use those values.

These calls are especially useful:

```javascript
const cabMode = await vpin.call("get_cab_mode");
const rotationDegree = await vpin.call("get_playfield_rotation");
```

After `await vpin.ready`, the same values are also available as:

```javascript
vpin.playfieldOrientation; // "landscape" or "portrait"
vpin.playfieldRotation;    // degrees, default 0
```

Do not infer cabinet Portrait mode from `window.innerWidth` and `window.innerHeight`. VPinFE can run through the bundled embedded Chromium build or through a user-installed Chrome, and desktop window bounds can be affected by OS display orientation, monitor placement, DPI behavior, and theme transforms. Treat viewport dimensions as layout measurements only. Use VPinFE's display config as the source of truth:

```javascript
const playfieldOrientation = String(await vpin.call("get_playfield_orientation") || "").toLowerCase();
const playfieldRotation = Number(await vpin.call("get_playfield_rotation")) || 0;
const tableDisplayPortrait = playfieldOrientation === "portrait";
const normalizedRotation = ((playfieldRotation % 360) + 360) % 360;
```

When adapting an existing landscape theme to OS-level Portrait mode, decide separately how each layer should behave:

- The page/layout surface may need to rotate as a whole, like Basic Cab.
- A portrait-aware layout may stay upright while only playfield media is corrected.
- Table media (`table.png` / `table.mp4`) may need its own per-theme correction even when the surrounding page is right. Do this in the table media element only, not in `bg` or `dmd`.
- Avoid guessing from screenshots alone whether the media needs a mirror. If playfield text is backwards, that is a flip/mirror problem. If the apron/top are on the wrong end but text is still readable, that is a rotation problem.

For themes that correct playfield media separately, keep the media transform isolated and size rotated media from the untransformed layout box, not from `getBoundingClientRect()` after parent transforms:

```javascript
function sizeRotatedTableMedia(mediaEl) {
  const frame = mediaEl.closest(".hero-media-frame") || mediaEl.parentElement;
  const frameWidth = frame?.clientWidth || frame?.offsetWidth || 0;
  const frameHeight = frame?.clientHeight || frame?.offsetHeight || 0;

  if (frameWidth > 0 && frameHeight > 0) {
    mediaEl.style.width = `${frameHeight}px`;
    mediaEl.style.height = `${frameWidth}px`;
  }
}
```

`getBoundingClientRect()` includes CSS transforms from rotated parents. That makes it easy to feed already-rotated visual dimensions back into your media sizing and produce narrow, clipped, or badly scaled playfield images.

Good questions to answer up front when starting a new theme:

- Should the theme declare `type: "cab"` or `type: "both"`?
- Should portrait mode use a different layout, or just rotate the landscape one?
- Should only the main playfield UI rotate, or should playfield-only overlays rotate too?
- Is the playfield media orientation tied to the whole page surface, or does it need a theme-specific correction?

#### Basic Cab portrait pattern

The Basic Cab theme works on an OS-level Portrait playfield by treating the page as layers:

- `#fadeContainer` contains the playfield UI and media.
- `#remote-launch-overlay` is rotated with the playfield UI so launch feedback appears in the same orientation.
- `#overlay-root` stays as the injected menu host, but a child wrapper (`#menu-overlay-container`) catches the menu iframes and applies menu-specific rotation.

The key trick is that a 90-degree or 270-degree rotated surface must swap its CSS dimensions before rotation:

```javascript
const rotation = Number(vpin.playfieldRotation) || 0;
const swapAxes = Math.abs(rotation) === 90 || Math.abs(rotation) === 270;
const rotatedWidth = swapAxes ? "100vh" : "100vw";
const rotatedHeight = swapAxes ? "100vw" : "100vh";

[document.getElementById("fadeContainer"), document.getElementById("remote-launch-overlay")]
  .filter(Boolean)
  .forEach((element) => {
    element.style.position = "absolute";
    element.style.top = "50%";
    element.style.left = "50%";
    element.style.width = rotatedWidth;
    element.style.height = rotatedHeight;
    element.style.transformOrigin = "center center";
    element.style.transform = `translate(-50%, -50%) rotate(${rotation}deg)`;
  });
```

Without the width/height swap, the rotated landscape surface is clipped inside the portrait browser window. With the swap, the theme gets a full-size virtual playfield surface and then rotates it into the monitor.

One easy thing to miss: the built-in menus are injected into `#overlay-root`, not inside your main theme container. If you rotate only your main playfield wrapper, the menus will still appear unrotated.

In other words:

- Rotating your playfield wrapper rotates your theme content
- Rotating `#overlay-root` rotates `mainmenu.html` and `collectionmenu.html`
- If you only do the first one, rotated playfield themes will have mismatched menus

Basic Cab handles this by keeping `#overlay-root` aligned to the same virtual surface and moving injected children into a stable wrapper:

```html
<div id="overlay-root">
  <div id="menu-overlay-container"></div>
</div>
```

```javascript
function ensureMenuOverlayContainer() {
  const overlayRoot = document.getElementById("overlay-root");
  if (!overlayRoot) return null;

  let container = document.getElementById("menu-overlay-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "menu-overlay-container";
    overlayRoot.appendChild(container);
  }

  Array.from(overlayRoot.children).forEach((child) => {
    if (child !== container) container.appendChild(child);
  });

  if (!overlayRoot._menuObserver) {
    const observer = new MutationObserver(() => {
      Array.from(overlayRoot.children).forEach((child) => {
        if (child !== container) container.appendChild(child);
      });
    });
    observer.observe(overlayRoot, { childList: true });
    overlayRoot._menuObserver = observer;
  }

  return container;
}
```

Then size and center the root surface, and rotate the inner menu wrapper as needed for that theme:

```javascript
const overlayRoot = document.getElementById("overlay-root");
if (overlayRoot) {
  overlayRoot.style.position = "absolute";
  overlayRoot.style.top = "50%";
  overlayRoot.style.left = "50%";
  overlayRoot.style.width = rotatedWidth;
  overlayRoot.style.height = rotatedHeight;
  overlayRoot.style.transformOrigin = "center center";
  overlayRoot.style.transform = "translate(-50%, -50%)";
}

const menuOverlay = ensureMenuOverlayContainer();
if (menuOverlay) {
  menuOverlay.style.transformOrigin = "center center";
  menuOverlay.style.transform = `rotate(${menuRotation}deg)`;
}
```

`menuRotation` is theme-specific. Basic Cab uses a separate menu rotation because its playfield UI, wheel art, and metadata panel are already designed for cabinet viewing, while the injected menus have their own landscape assumptions. When extending this to another theme, copy the layer structure and dimension swap first, then tune `menuRotation` until the main and collection menus read correctly on the cabinet.

For more advanced themes, it helps to think in layers:

- `#tableViewport`: fullscreen viewport wrapper
- `#tableScreen`: your actual table UI surface that may be rotated and scaled
- `#overlay-root`: injected menu host that may need the same transform as `#tableScreen`

That wrapper approach is much easier to maintain than rotating individual components one by one.

Recommended CSS baseline:

```css
html,
body {
  margin: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: black;
}

#fadeContainer {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  transform-origin: center center;
}

#overlay-root {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

#menu-overlay-container {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transform-origin: center center;
  pointer-events: none;
}

#menu-overlay-container > iframe,
#menu-overlay-container > * {
  pointer-events: auto;
}
```

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
  const bgUrl = vpin.getImageURL(currentGameIndex, 'bg');
  const bgVideoUrl = vpin.getVideoURL(currentGameIndex, 'bg');
  renderWindowMedia(container, bgUrl, bgVideoUrl, 'Backglass');
}

function updateDMDWindow() {
  const container = document.getElementById('rootContainer');
  const dmdUrl = vpin.getImageURL(currentGameIndex, 'dmd');
  const dmdVideoUrl = vpin.getVideoURL(currentGameIndex, 'dmd');
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
currentGameIndex = 0;

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
    // Let VPinFECore handle the data refresh logic (GameDataChange, filters, sorts)
    await vpin.handleEvent(message);

    if (message.type == "GameIndexUpdate") {
        currentGameIndex = message.index;
        updateScreen();
    }
    else if (message.type == "GameLaunching") {
        await fadeOut();
    }
    else if (message.type == "GameRunning") {
        // Game has finished loading and is now running
    }
    else if (message.type == "GameLaunchComplete") {
        fadeIn();
    }
    else if (message.type == "RemoteLaunching") {
        // Remote launch from manager UI - message.table_name has the game name
        showRemoteLaunchOverlay(message.table_name);
        await fadeOut();
    }
    else if (message.type == "RemoteLaunchComplete") {
        hideRemoteLaunchOverlay();
        fadeIn();
    }
    else if (message.type == "GameDataChange") {
        currentGameIndex = message.index;
        updateScreen();
    }
}

// input handler - only called on the "table" window
/*  joyleft, joyright, joyup, joydown,
    joyselect, joymenu, joyback, joycollectionmenu */
async function handleInput(input) {
    switch (input) {
        case "joyleft":
            currentGameIndex = wrapIndex(currentGameIndex - 1, vpin.gameData.length);
            updateScreen();
            vpin.sendMessageToAllWindows({
                type: 'GameIndexUpdate',
                index: currentGameIndex
            });
            break;
        case "joyright":
            currentGameIndex = wrapIndex(currentGameIndex + 1, vpin.gameData.length);
            updateScreen();
            vpin.sendMessageToAllWindows({
                type: 'GameIndexUpdate',
                index: currentGameIndex
            });
            break;
        case "joyselect":
            vpin.sendMessageToAllWindows({ type: "GameLaunching" });
            await fadeOut();
            await vpin.launchGame(currentGameIndex);
            break;
        case "joyback":
            break;
    }
}

function updateScreen() {
    if (windowName === "table") {
        // Update the table window: images, carousel, info, audio
        vpin.playGameAudio(currentGameIndex);
    } else if (windowName === "bg") {
        // Update backglass image
    } else if (windowName === "dmd") {
        // Update DMD image
    }
}

// circular game index helper
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
function showRemoteLaunchOverlay(gameName) {
    const overlay = document.getElementById('remote-launch-overlay');
    const nameEl = document.getElementById('remote-launch-table-name');
    if (overlay && nameEl) {
        nameEl.textContent = gameName || 'Unknown Game';
        overlay.style.display = 'flex';
    }
}

function hideRemoteLaunchOverlay() {
    const overlay = document.getElementById('remote-launch-overlay');
    if (overlay) overlay.style.display = 'none';
}
```

> **Important:** Call `await vpin.handleEvent(message)` at the top of your `receiveEvent` function. This lets VPinFECore handle `GameDataChange` events automatically (collection changes, filter/sort updates) so you don't have to manage that logic yourself.

> **Important:** Set `window.vpin = vpin` so the in-theme menu system can call back into your VPinFECore instance.

### Strong Recommendation: Keep The Playfield DOM Persistent

For anything beyond a very simple theme, especially carousel-style playfield screens, avoid rebuilding the entire `table` window DOM on every game change.

A much smoother pattern is:

1. Create the playfield view scaffold once
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

- preload nearby media such as the current, previous, and next game images
- prefer updating existing `<img>` / `<video>` nodes or swapping a small media layer instead of rerendering the whole screen
- keep fades simple; a plain crossfade is usually smoother than blur-heavy "dissolve" effects
- be careful with simultaneous animation systems; CSS transitions plus a JS animation library or canvas effects can stack up quickly
- if wheel browsing feels sluggish, test without heavy motion libraries first

For playfield video specifically, image-first browsing with delayed video start is often smoother than immediately starting video while the user is rapidly scrolling.

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
| `GameIndexUpdate` | `index` | User navigated to a different game. Sent by the `table` window to all others. |
| `GameLaunching` | — | A game is about to launch. Frontend keyboard/gamepad routing is suspended until `GameLaunchComplete`; use this to fade out, stop audio, etc. |
| `GameRunning` | — | The launched game has finished loading and is now running. Sent when the table process outputs "Startup done". |
| `GameLaunchComplete` | — | The launched game has exited and frontend input routing is restored. Use this to fade back in, resume audio. |
| `RemoteLaunching` | `table_name` | The manager UI triggered a remote game launch. Frontend keyboard/gamepad routing is suspended until `RemoteLaunchComplete`; show an overlay. |
| `RemoteLaunchComplete` | — | The remote-launched game has exited and frontend input routing is restored. Hide the overlay. |
| `GameDataChange` | `index`, `collection?`, `filters?`, `sort?` | Game data changed (collection switch, filter/sort update). Handled automatically by `vpin.handleEvent()`. |

You can also define custom event types and send them with `vpin.sendMessageToAllWindows()`.

### Loading Overlay During Game Launch

Themes can show a loading image or animation while VPX is starting. Use the built-in launch lifecycle instead of guessing with timers:

- show the overlay on `GameLaunching`
- hide it on `GameRunning`
- also hide it on `GameLaunchComplete` as a cleanup fallback

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

  if (message.type === "GameLaunching") {
    showTableLoadingOverlay();
    await fadeOut();
  } else if (message.type === "GameRunning") {
    hideTableLoadingOverlay();
  } else if (message.type === "GameLaunchComplete") {
    hideTableLoadingOverlay();
    fadeIn();
  }
}
```

If the `table` window launches the game from local input, remember that `vpin.sendMessageToAllWindows(...)` excludes the sender. Call `showTableLoadingOverlay()` directly in the local `joyselect` path before `await vpin.launchGame(...)`, or send the event with `vpin.sendMessageToAllWindowsIncSelf(...)`.

### Attract Mode During Game Launch

If your theme implements attract mode, treat game launch as a hard suspension boundary. Clearing the current timer is not enough, because user-activity listeners, menu events, or `GameRunning` handling can accidentally schedule a new idle timer while VPX is still open.

Use a separate launch/remote-launch suspension flag:

- set `attractSuspended = true` and clear both idle and advance timers on `GameLaunching` and `RemoteLaunching`
- keep `shouldPauseAttractMode()` returning `true` while `attractSuspended` is set
- make user-activity handlers clear timers and return without scheduling a new idle timer while suspended
- clear `attractSuspended` only on `GameLaunchComplete` or `RemoteLaunchComplete`
- after launch completion, restart the idle countdown instead of immediately starting attract mode
- in a local `joyselect` launch path, suspend attract mode before calling `vpin.launchGame(...)` so the sender is protected before backend events arrive

Example pattern:

```javascript
let attractIdleTimer = null;
let attractAdvanceTimer = null;
let attractSuspended = false;

function clearAttractTimers() {
  clearTimeout(attractIdleTimer);
  clearTimeout(attractAdvanceTimer);
  attractIdleTimer = null;
  attractAdvanceTimer = null;
}

function suspendAttractMode() {
  attractSuspended = true;
  clearAttractTimers();
}

function markUserActivity() {
  if (attractSuspended) {
    clearAttractTimers();
    return;
  }
  clearAttractTimers();
  attractIdleTimer = setTimeout(startAttractMode, ATTRACT_IDLE_MS);
}

async function receiveEvent(message) {
  await vpin.handleEvent(message);

  if (message.type === "GameLaunching" || message.type === "RemoteLaunching") {
    suspendAttractMode();
  } else if (message.type === "GameLaunchComplete" || message.type === "RemoteLaunchComplete") {
    attractSuspended = false;
    markUserActivity();
  }
}
```

### Input Actions

The following input actions are passed to your `handleInput` function (`table` window only):

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
| `joypageup` / `joypagedown` | Mapped button | `[Input] keypageup`/`keypagedown` (defaults `PageUp`/`PageDown`) | Pages the game wheel (see below) |

#### Wheel Paging

By default the core handles `joypageup`/`joypagedown` itself: it asks the backend
where the press should land (`get_page_index`) and broadcasts a `GameIndexUpdate`
to every window. Your theme moves its wheel through the same `receiveEvent` path it
already uses for external index updates, so paging works with no theme changes.

The user controls the behavior with two `[Input]` settings in `vpinfe.ini`:

- `pagingtype` — `alpha` (default) jumps to the next/previous letter of the current
  Alpha sort (numbers and symbols share one `#` group); `numeric` jumps by a fixed
  number of games. Alpha paging falls back to numeric when the active sort isn't
  `Alpha` or the list is all one letter.
- `pagingsize` — how many games a numeric jump moves (default `10`). All paging wraps
  around.

A theme that wants its own paging behavior calls `vpin.enableCorePaging(false)`;
the actions are then routed to `handleInput` like any other, and
`vpin.getPageIndex(direction)` is available if you want the config-aware target
index while animating the move yourself. While a core overlay (menu, collection
menu, tutorial) is up, these actions bypass core paging and go to the overlay's
handler regardless.

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
| `vpin.gameData` | `array` | The current (possibly filtered) game list. Each element is a game object (see [Game Data Object](#game-data-object)). |
| `vpin.monitors` | `array` | List of monitor objects with `name`, `x`, `y`, `width`, `height`. Loaded during init. |
| `vpin.playfieldOrientation` | `string` | Playfield orientation from config: `"landscape"` or `"portrait"`. |
| `vpin.playfieldRotation` | `number` | Playfield rotation in degrees from config (default `0`). |
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

##### Game Data

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_games` | `reset=false` | `string` (JSON) | Returns JSON string of the current (filtered) game list. Pass `true` to reset to the full unfiltered list. Each game object includes paths, media paths, addon flags, and metadata. |
| `launch_game` | `index` | — | Launches the game at the given index. Blocks until the table exits. Automatically tracks play in the "Last Played" collection. Sends `GameLaunching` before launch, `GameRunning` when the table finishes loading, and `GameLaunchComplete` when it exits. |
| `build_metadata` | `download_media=true`, `update_all=false` | `object` | Triggers a background metadata build/refresh. Sends progress events (`buildmeta_progress`, `buildmeta_log`, `buildmeta_complete`, `buildmeta_error`) to all windows. Returns `{success, message}`. |

##### Collections

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_collections` | — | `array` | Returns list of collection names from `collections.ini`. |
| `get_collections_metadata` | — | `array` | Returns collection objects with `name`, `type`, `is_filter`, `image`, `image_url`, and `table_count`. `image_url` is a theme-server URL such as `/collection_icons/favorites.png`, or an empty string when no image is set. |
| `get_collection_image_url` | `collection` | `string` | Returns the image URL for one collection, or an empty string when no image is set. |
| `set_games_by_collection` | `collection` | — | Filters the game list by the named collection. Supports both VPS ID-based and filter-based collections. |
| `save_filter_collection` | `name`, `letter`, `theme`, `table_type`, `manufacturer`, `year`, `sort_by`, `rating`, `rating_or_higher`, `order_by` | `object` | Saves the current filter settings as a named collection. `order_by` is `"Descending"` or `"Ascending"` and defaults to `"Descending"`. Returns `{success, message}`. |
| `get_current_collection` | — | `string` | Returns the name of the currently active collection, or `"None"`. |

##### Filters & Sorting

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `apply_filters` | `letter`, `theme`, `table_type`, `manufacturer`, `year`, `rating`, `rating_or_higher` | `number` | Applies VPSdb filters to the full table list. Each arg is optional (pass `null` to keep current). Returns the filtered count. |
| `reset_filters` | — | — | Resets all filters back to the full game list. |
| `apply_sort` | `sort_type`, `order_by` | `number` | Sorts the current filtered games. `sort_type` is `"Alpha"`, `"Newest"`, `"LastRun"`, `"Highest StartCount"`, or `"RunTime"`; `order_by` is `"Descending"` or `"Ascending"`. Returns the count. |
| `get_current_filter_state` | — | `object` | Returns the current filter state: `{letter, theme, type, manufacturer, year, rating, rating_or_higher}`. |
| `get_current_sort_state` | — | `string` | Returns the current sort type. |
| `get_current_order_state` | — | `string` | Returns the current sort order (`"Descending"` or `"Ascending"`). |
| `get_filter_letters` | — | `array` | Returns available starting letters from all games (for filter UI). |
| `get_filter_themes` | — | `array` | Returns available themes/categories from all games. |
| `get_filter_types` | — | `array` | Returns available game types (SS, EM, PM, etc.) from all games. |
| `get_filter_manufacturers` | — | `array` | Returns available manufacturers from all games. |
| `get_filter_years` | — | `array` | Returns available years from all games. |

##### Events & Messaging

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `send_event_all_windows` | `message` | — | Sends an event to all windows except the caller. |
| `send_event_all_windows_incself` | `message` | — | Sends an event to all windows including the caller and iframes. |
| `send_event` | `window_name`, `message` | — | Sends an event to a specific window by name (`"table"`, `"bg"`, or `"dmd"`). |

##### Input

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_joymaping` | — | `object` | Returns the gamepad button mapping from `vpinfe.ini`. Keys: `joyleft`, `joyright`, `joyup`, `joydown`, `joypageup`, `joypagedown`, `joyselect`, `joymenu`, `joyback`, `joytutorial`, `joyexit`, `joycollectionmenu`. Values are button index strings. |
| `get_keymapping` | — | `object` | Returns the keyboard mapping from `vpinfe.ini`. Keys: `keyleft`, `keyright`, `keyup`, `keydown`, `keypageup`, `keypagedown`, `keyselect`, `keymenu`, `keyback`, `keytutorial`, `keyexit`, `keycollectionmenu`. Values are comma-separated browser key names or key codes. |
| `set_button_mapping` | `button_name`, `button_index` | `object` | Sets a gamepad button mapping and saves to config. Returns `{success, message}`. |
| `get_page_index` | `index`, `direction` | `number` | Returns the wheel index a page press should land on, from `index` in the given `direction` (`"next"` or `"prev"`). Honors `[Input] pagingtype`/`pagingsize` and the current sort. See [Wheel Paging](#wheel-paging). |

##### Theme & Display Config

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_theme_name` | — | `string` | Returns the active theme name from `vpinfe.ini`. |
| `get_theme_config` | — | `object\|null` | Loads and returns the theme's current configuration values. When a theme provides `theme.json`, VPinFE flattens the option `value` fields into the object returned to theme code. |
| `get_theme_assets_port` | — | `number` | Returns the HTTP server port (default `8000`). |
| `get_theme_index_page` | — | `string` | Returns the full URL for this window's theme index page. |
| `get_playfield_orientation` | — | `string` | Returns the playfield orientation from config (`"landscape"` or `"portrait"`). |
| `get_playfield_rotation` | — | `number` | Returns the playfield rotation angle in degrees from config (default `0`). |

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
| `playGameAudio` | `indexOrUrl`, `retries=3` | — | Plays game audio using VPinFECore's centralized audio manager. Pass a game index (recommended) or URL string. |
| `stopGameAudio` | `options={}` | — | Stops audio via centralized manager. Supports fade-out; pass `{ immediate: true }` for an immediate stop. |
| `enableCoreAudio` | `enabled=true` | — | Enables or disables centralized audio handling for the current window. Core audio is opt-in by default unless enabled in theme config. |
| `isCoreAudioEnabled` | — | `boolean` | Returns whether centralized audio handling is currently enabled. |
| `setAudioOptions` | `options` | — | Sets runtime audio options. Supported keys: `maxVolume`/`max_volume`/`volume`, `fadeDuration`/`fade_duration_ms`/`fadeMs`, `loop`. |

#### getImageURL(index, type)
Returns an HTTP URL for a table's image. `type` can be `"table"`, `"bg"`, `"dmd"`, `"wheel"`, or `"cab"`. Returns a fallback `/web/images/file_missing.png` URL if the file doesn't exist.

#### getVideoURL(index, type)
Returns an HTTP URL for a table's video. `type` can be `"playfield"`, `"bg"`, or `"dmd"`. Returns a fallback `/web/images/file_missing.png` URL if no video exists. See [Video Support](#video-support).

#### getMediaURL(index, type)
Returns an HTTP URL using the user's configured media priority from Manager UI > Configuration > Media > Media Priorities. For `"playfield"`, `"bg"`, and `"dmd"`, VPinFE chooses image or video first based on the setting and falls back to the alternate when the preferred file is missing. For `"real_dmd"`, VPinFE chooses `realdmd-color.png` or `realdmd.png` first based on the setting and falls back to the other frame.

Kind names are snake_case, the same strings the payload and `/api/v1` use. The spellings earlier builds accepted — `table`, `table_video`, `fss`, `realdmd`, `realdmd-color`, `rulecard`, `audiolaunch`, `rulesheet` — still work.

#### getMedia(index, type)
Returns the same priority-aware selection with metadata: `{ url, kind, priority, path }`. Real DMD selections also include `variant` with `"color"` or `"standard"`.

#### getAudioURL(index)
Returns an HTTP URL for a game's audio file, or `null` if no audio exists. See [Audio Support](#audio-support).

#### getManufacturerLogoURL(index)
Returns an HTTP URL for the game manufacturer's logo, or `null` if none is installed. Logos live in the shared assets folder (`[Settings] assetsdir`, `manufacturers/` subfolder) and are matched to the game's `Info.Manufacturer` metadata, so "Williams Electronics" and "Williams" find the same file. Always handle `null` — a fresh install has no logos.

#### playGameAudio(indexOrUrl, retries=3)
Plays game audio via VPinFECore's centralized audio manager. Normally you pass `currentGameIndex`; passing a URL string is also supported.

#### stopGameAudio(options={})
Stops centralized audio playback. Default behavior is fade-out, or pass `{ immediate: true }` for an immediate stop.

#### enableCoreAudio(enabled=true)
Turns centralized core audio handling on or off for the current window.

#### isCoreAudioEnabled()
Returns `true` when centralized core audio handling is enabled.

#### setAudioOptions(options)
Updates centralized audio options at runtime: volume (`maxVolume`, `max_volume`, or `volume`), fade duration (`fadeDuration`, `fade_duration_ms`, or `fadeMs`), and `loop`.

#### enableCorePaging(enabled=true)
Turns core-handled wheel paging (`joypageup`/`joypagedown`) on or off. Disable it if your theme does its own paging; the actions then arrive in `handleInput`. See [Wheel Paging](#wheel-paging).

#### isCorePagingEnabled()
Returns `true` when core-handled wheel paging is enabled.

#### getPageIndex(direction="next", index=current)
Asks the backend where a page press should land and returns the target index. Convenience wrapper around the `get_page_index` API method for themes doing their own paging animation.

#### getGameMeta(index)
Returns the full game object for a given game index. This is the same object as `vpin.gameData[index]`. See [Game Data Object](#game-data-object).

#### getGameCount()
Returns the number of games in the current (possibly filtered) game list.

#### sendMessageToAllWindows(message)
Sends an event to all windows except the current one. Convenience wrapper around `vpin.call("send_event_all_windows", message)`.

#### sendMessageToAllWindowsIncSelf(message)
Sends an event to all windows including the current one and forwarding to iframes.

#### launchGame(index)
Suspends frontend keyboard/gamepad routing, calls backend to launch the selected game, then restores input after the launch lifecycle completes. The launch lifecycle is `GameLaunching` before the process starts, `GameRunning` when the table finishes loading, and `GameLaunchComplete` when it exits.

#### getGameData(reset=false)
Loads game data from the backend into `vpin.gameData`. Pass `reset=true` to reload from the full unfiltered game list.

#### handleEvent(message)
Handles incoming events with built-in logic for:
- `GameDataChange` (collection/filter/sort changes)
- centralized audio transitions on `GameIndexUpdate`, `GameLaunching`, `RemoteLaunching`, `GameLaunchComplete`, and `RemoteLaunchComplete`

Call this at the top of your `receiveEvent` function to get automatic data refresh and default audio behavior.

#### registerEventHandler(eventType, handler)
Registers a custom event handler for a specific event type. The handler is called whenever that event type is received via `handleEvent()`.

---

## Game Data Object

Each element in `vpin.gameData` (and the return of `vpin.getGameMeta(index)`) is an object with the following structure:

### Top-Level Properties

| Property | Type | Description |
|----------|------|-------------|
| `gameDirName` | `string` | The game's directory name. |
| `PlayfieldImagePath` | `string\|null` | Local path to the table playfield image (`table.png` or `fss.png`). |
| `BGImagePath` | `string\|null` | Local path to the backglass image (`bg.png`). |
| `DMDImagePath` | `string\|null` | Local path to the DMD image (`dmd.png`). |
| `WheelImagePath` | `string\|null` | Local path to the wheel/logo image (`wheel.png`). |
| `CabImagePath` | `string\|null` | Local path to the cabinet image (`cab.png`). |
| `PlayfieldVideoPath` | `string\|null` | Local path to the table playfield video (`table.mp4` or `fss.mp4`). |
| `BGVideoPath` | `string\|null` | Local path to the backglass video (`bg.mp4`). |
| `DMDVideoPath` | `string\|null` | Local path to the DMD video (`dmd.mp4`). |
| `AudioPath` | `string\|null` | Local path to the audio file (`audio.mp3`). |
| `LogoImagePath` | `string\|null` | Local path to the game logo image (`logo.png`). |
| `InstructionCardImagePath` | `string\|null` | Local path to the apron instruction card image (`instructioncard.png`, or `(InstructionCard) …` / `(RuleCard) …` / `(GameHelp) …`). |
| `TopperPath` | `string\|null` | Local path to the topper image or video (`topper.png` / `topper.mp4`). |
| `LoadingVideoPath` | `string\|null` | Local path to the loading-screen video (`loading.mp4`). |
| `AudioLaunchPath` | `string\|null` | Local path to the launch audio file (`audiolaunch.mp3`). |
| `RuleSheetPath` | `string\|null` | Local path to the rulesheet document (`rulesheet.pdf`). |
| `ManufacturerLogoPath` | `string\|null` | Web path to the manufacturer's logo under `/assets/`; use `vpin.getManufacturerLogoURL(index)`. |
| `meta` | `object` | The game's `.info`, with `Title` adjusted for display (see [meta.Info](#metainfo)). **Contract 1 only** — contract 2 has no `meta`; see [Contract 2 payload](#contract-2-payload). |
| `vpinplay` | `object\|null` | Cached VPinPlay cumulative rating payload for the game, or `null` until fetched/unavailable. |

> **Note:** You typically don't use the path properties directly. Use `vpin.getImageURL()`, `vpin.getVideoURL()`, and `vpin.getAudioURL()` which convert these paths to HTTP URLs. Direct access to path properties is useful for checking existence (e.g., `if (game.PlayfieldVideoPath)` to decide whether to show video or image).

### meta.Info

VPSdb and user-edited metadata.

`meta` is the game's `.info`, but not a raw copy of it: `Title` is adjusted for display
before you see it. It also carries any section VPinFE does not own, because the `.info` is
written back with unknown sections preserved — which is exactly why contract 2 stopped
serving it. A storage change reached themes whether or not it meant anything to them.

| Property | Type | Description |
|----------|------|-------------|
| `Title` | `string` | Game display name. **Not the stored title.** A user-set alternate title replaces it, and otherwise a leading "The " is moved to the end so themes sort by the second word — "The Addams Family" arrives as "Addams Family, The". Read `vpin.getGameMeta(index)` for display; do not treat it as the value on disk. |
| `Manufacturer` | `string` | Game manufacturer (e.g., "Williams", "Bally"). |
| `Year` | `string` | Year of manufacture. |
| `Type` | `string` | Game type code: `"SS"` (Solid State), `"EM"` (Electro Mechanical), `"PM"` (Pure Mechanical). |
| `Authors` | `array` | List of VPX table author names. |
| `Theme` | `string` | Game theme/category. |

### meta.User

Per-user stats and preferences stored in each game's `.info` file:

| Property | Type | Description |
|----------|------|-------------|
| `Rating` | `number` | User rating from `0` to `5`. |
| `Favorite` | `number` | Favorite flag (`0` or `1`). |
| `LastRun` | `number\|null` | Unix timestamp (seconds) of the last launch, or `null` if never played. |
| `StartCount` | `number` | Number of times the game has been launched. |
| `RunTime` | `number` | Total accumulated play time in minutes. |
| `Tags` | `array` | User-defined tags (string list). |

### meta.tables *(contract 2)*

Every `.vpx` in the game folder, keyed by filename — a desktop build and a VR build, or a
table and a patched variant, are peers and each answers for itself. At contract 1 this
section does not exist; read `meta.VPXFile`, which describes only one.

```javascript
const meta = vpin.getGameMeta(currentGameIndex).meta;
const playable = Object.entries(meta.tables || {})
    .filter(([, entry]) => !entry.hidden);
```

| Property | Type | Description |
|----------|------|-------------|
| `file_hash` | `string` | Hash of the `.vpx`, which is how a replaced file is noticed. |
| `vbs_hash` | `string` | Hash of the table script. |
| `version` | `string` | Table version from VPX metadata. |
| `release_date` | `string` | Release date, ISO 8601 at whatever precision the author gave — `2019-06-22`, `2016-08` and `2017` are all valid. An ambiguous date degrades to the year. Empty when the author wrote nothing usable. |
| `save_date` | `string` | When the author last saved, ISO 8601 (`2022-12-13T16:03:21`). |
| `save_rev` | `string` | Author's save revision. |
| `rom` | `string` | ROM name. At contract 1 this is `Info.Rom`. |
| `authors` | `array` | Author names. At contract 1 this is `Info.Authors`. |
| `manufacturer` | `string` | Manufacturer from VPX metadata, which may disagree with `Info`. |
| `year` | `string` | Year from VPX metadata, which may disagree with `Info`. |
| `type` | `string` | Table type from VPX metadata. |
| `hidden` | `boolean` | Absent means visible. A hidden file is still launchable but should not be offered — a patch leaves its base on disk, and the base cannot be deleted because the patched table cannot be rebuilt without it. |
| `source` | `object` | Present only on a file VPinFE made by patching: `base` (`file`, `hash`) and `patch` (`format`, `applied`). An ordinary `.vpx` has none. |

Detection flags ride on each entry too, as real booleans: `detect_nfozzy`, `detect_fleep`,
`detect_ssf`, `detect_lut`, `detect_scorbit`, `detect_fastflips`, `detect_flex`,
`detect_pinmame`. Note the snake_case — contract 1 spells the same flags `detectnfozzy`
and so on. The addon flags `altSoundExists` / `altColorExists` / `pupPackExists` describe
the folder rather than one file, so they stay on the game row at both contracts.

**Which one is "the" table.** `meta.vpinfe.default_table` names it when somebody
chose; absent means resolve from the folder, which is the normal case. It is what the
places that must pick exactly one use — an export, a game row, contract 1's `VPXFile`.
It is *not* "the one to launch": every visible table is launchable, so filter on
`hidden` to decide what to offer.

### meta.VPXFile *(contract 1)*

The game's default table. At contract 2 this section does not exist — read `meta.tables`
instead, which describes every `.vpx` in the folder rather than only one.

Data extracted from the `.vpx` file itself:

| Property | Type | Description |
|----------|------|-------------|
| `filename` | `string` | VPX filename. |
| `manufacturer` | `string` | Manufacturer from VPX metadata. |
| `year` | `string` | Year from VPX metadata. |
| `type` | `string` | Table type from VPX metadata. |

### meta.VPXFile — Detection Flags *(contract 1)*

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
const meta = vpin.getGameMeta(currentGameIndex);
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

### Reading Game Info

Common pattern for getting display-ready game information. This one is written to work at
either contract — `VPXFile` is what contract 1 receives, `tables` what contract 2 does,
and only one of them is ever present:

```javascript
const game = vpin.getGameMeta(currentGameIndex);
const info = game.meta.Info || {};
const user = game.meta.User || {};

// Contract 1 serves meta.VPXFile; contract 2 serves meta.tables, so pick the
// chosen entry. Authors and Rom move onto the table at contract 2.
const files = game.meta.tables;
const chosenName = game.meta.vpinfe?.default_table || Object.keys(files || {})[0];
const vpx = files ? { filename: chosenName, ...(files[chosenName] || {}) }
                  : (game.meta.VPXFile || {});

const title = info.Title || vpx.filename || game.gameDirName || 'Unknown Game';
const manufacturer = info.Manufacturer || vpx.manufacturer || 'Unknown';
const year = info.Year || vpx.year || '';
const authors = Array.isArray(info.Authors) && info.Authors.length ? info.Authors.join(', ')
    : Array.isArray(vpx.authors) && vpx.authors.length ? vpx.authors.join(', ')
    : 'Unknown';
const rating = Number(user.Rating || 0);
const plays = Number(user.StartCount || 0);

const vpinplay = await vpin.getVPinPlayRating(currentGameIndex);
const cumulativeRating = vpinplay?.cumulativeRating ?? null;
const ratingCount = vpinplay?.ratingCount ?? 0;
```

### VPinPlay Rating

`vpinfe-core.js` can fetch the selected game's VPinPlay cumulative rating from the configured `vpinplay.apiendpoint`.

| Method | Returns | Description |
|--------|---------|-------------|
| `await vpin.getVPinPlayRating(index?)` | `object\|null` | Returns the cached rating for the table or fetches it from VPinPlay. |
| `await vpin.refreshVPinPlayRating(index?)` | `object\|null` | Forces a fresh fetch from VPinPlay. |
| `vpin.getCachedVPinPlayRating(index?)` | `object\|null` | Returns only the cached value already attached to the table. |

The returned object matches the API payload shape and is also stored on the table entry as `table.vpinplay`:

```javascript
const table = vpin.getGameMeta(currentGameIndex);
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
| `table.png` / `fss.png` | `"playfield"` | Table playfield image |
| `bg.png` | `"bg"` | Backglass image |
| `dmd.png` | `"dmd"` | DMD image |
| `wheel.png` | `"wheel"` | Wheel/logo image |
| `cab.png` | `"cab"` | Cabinet image |

Use `vpin.getImageURL(index, type)` to get the URL.

### Videos

| File | API Type | Description |
|------|----------|-------------|
| `table.mp4` / `fss.mp4` | `"playfield"` | Table playfield video |
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

For new themes, prefer `vpin.getMedia(index, type)` or `vpin.getMediaURL(index, type)` when you want to honor the user's Manager UI media priority. The default priority is video for table, backglass, and DMD media, and colorized for Real DMD frames. If the preferred file is missing, VPinFE automatically falls back to the available alternate.

Priority-aware example:
```javascript
const media = vpin.getMedia(currentGameIndex, 'bg');
const preview = document.createElement(media.kind === 'video' ? 'video' : 'img');
preview.className = 'preview';
preview.src = media.url;

if (media.kind === 'video') {
    preview.autoplay = true;
    preview.loop = true;
    preview.muted = true;
    preview.playsInline = true;
}

container.appendChild(preview);
```

Use `vpin.getVideoURL(index, type)` to get the video URL. The method returns a fallback `file_missing` URL if no video file exists, so check for this before creating a `<video>` element.

Example with image fallback:
```javascript
const videoUrl = vpin.getVideoURL(currentGameIndex, 'playfield');
const imageUrl = vpin.getImageURL(currentGameIndex, 'playfield');

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

- `vpin.getVideoURL(currentGameIndex, 'bg')` plus `vpin.getImageURL(currentGameIndex, 'bg')`
- `vpin.getVideoURL(currentGameIndex, 'dmd')` plus `vpin.getImageURL(currentGameIndex, 'dmd')`

Recommended rule for theme authors:

- Table window: optionally prefer `table.mp4` over `table.png` / `fss.png`
- BG window: prefer `bg.mp4`, fall back to `bg.png`
- DMD window: prefer `dmd.mp4`, fall back to `dmd.png`

If you only use `getImageURL()` in BG or DMD renderers, those windows will remain image-only even when the matching video files exist.

Key points:
- Set `muted = true` — browsers require this for autoplay to work without user gesture.
- Set `poster = imageUrl` — gives the video element proper dimensions before metadata loads, preventing layout shifts.
- The `onerror` handler provides a graceful fallback to the static image.
- You can check `vpin.gameData[index].PlayfieldVideoPath` directly to decide whether to create a video or image element.

---

## Audio Support

VPinFECore now includes a centralized per-table audio manager. Theme code can use it directly and no longer needs to implement its own `Audio`/fade/retry logic.

### Audio File

Place an `audio.mp3` file in the table's `medias/` folder (or root folder). `vpin.getAudioURL(index)` returns the URL, or `null` if no audio file exists.

### Core Behavior

On the `table` window, `await vpin.handleEvent(message)` automatically manages audio transitions when core audio is enabled.

Core audio is opt-in by default. If your theme does not explicitly enable it (or call `vpin.enableCoreAudio(true)` at runtime), no automatic table audio playback will occur.

When enabled, these transitions are handled automatically:
- `GameIndexUpdate` -> play selected table audio
- `GameLaunching` and `RemoteLaunching` -> fade/stop audio
- `GameLaunchComplete` and `RemoteLaunchComplete` -> resume audio for current selection
- `GameDataChange` (with `index`) -> play audio for that index

### Backend vs Frontend Responsibility

`api.py` knows when table launch starts/completes and emits lifecycle events, but it does not own the browser `Audio` object. Actual playback, fading, retries, and autoplay-policy handling must run in frontend JavaScript (`VPinFECore`/theme code), which owns the in-memory audio state.

### Practical Note: Self-Event Caveat

`vpin.sendMessageToAllWindows(...)` excludes the sender. If your `table` window sends `GameLaunching`, it might not receive that same event back, so backend-emitted lifecycle events are the reliable source of truth for launch state.

For robust behavior, it is valid to also call:
- `vpin.stopGameAudio()` directly in your local `joyselect`/launch path
- `vpin.playGameAudio(currentGameIndex)` directly on local launch-complete handling

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
        vpin.playGameAudio(currentGameIndex);
    }
}

async function receiveEvent(message) {
    // Keep this call at the top for built-in table-data refresh and core audio handling
    await vpin.handleEvent(message);
    // ... theme-specific event handling ...
}

// Optional immediate stop:
// vpin.stopGameAudio({ immediate: true });
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
- A `select` may set `"source": "wheelsets"` instead of a static `options` list. Manager UI then fills the dropdown from the library: every wheel set folder found under any table's `medias/wheels/`, plus the built-in `logo` set, plus a Default entry (saved as `""`, meaning no set). Use the key `wheelSet`; a non-empty saved value overrides the `[Media] wheelset` setting from `vpinfe.ini` while this theme is active.

```json
{
  "key": "wheelSet",
  "name": "Wheel Set",
  "description": "Which wheel art set this theme uses.",
  "type": "select",
  "source": "wheelsets",
  "value": ""
}
```

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
