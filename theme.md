# Themes

VPinFE supports two rendering backends:
- **pywebview** (master branch) — uses a WebKitGTK/MSHTML browser window with a direct JS bridge (`window.pywebview.api`).
- **Embedded Chromium** (vpinfe-chromium branch) — uses a WebSocket bridge to communicate between the browser and Python backend.

Themes are fully compatible with both backends. The `vpinfe-core.js` library abstracts the communication layer so theme code does not need to know which backend is in use.

- `table` — The main screen. Controller for all other screens and input.
- `bg` — Backglass screen.
- `dmd` — DMD screen (not a "real DMD" like ZeDMD).

Each window has its own webpage but shares an instance of the VPinFE API ([frontend/api.py](https://github.com/superhac/vpinfe/blob/master/frontend/api.py)), accessed via [vpinfe-core.js](#vpinfe-corejs).

## Theme Structure

Themes are installed in the user config directory: `~/.config/vpinfe/themes/<THEME NAME>/` (Linux) or the equivalent `platformdirs` location on other platforms.

```
<THEME NAME>
├── manifest.json
├── config.json        (optional - user-customizable theme options)
├── preview.png        (optional - shown in manager UI)
├── index_bg.html
├── index_dmd.html
├── index_table.html
├── style.css
└── theme.js
```

### manifest.json

Every theme should include a `manifest.json`:
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

## HTML Files

Each screen has its own HTML file. These must be named exactly as listed:

| File | Description |
|--------|-----|
| `index_table.html` | The main screen. Controller for all other screens and input. |
| `index_bg.html` | Backglass screen. |
| `index_dmd.html` | DMD screen. |

### index_table.html

This is the main HTML file used to control and interact with the VPinFE API. This is also the window where the in-theme main menu gets rendered. Below is the minimum required to make things work.

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>VPinFE - My Theme</title>
  <link rel="stylesheet" href="../../common/vpinfe-style.css">
  <link rel="stylesheet" href="style.css">
  <script src="../../common/vpinfe-core.js"></script>
  <script src="theme.js"></script>
</head>
<body>
  <div id="rootContainer">
  </div>
  <div id="overlay-root">
        <!-- Independent popup or menu overlay -->
  </div>
</body>
</html>
```

The `common` includes:

```html
<link rel="stylesheet" href="../../common/vpinfe-style.css">
<script src="../../common/vpinfe-core.js"></script>
```

These are the core of the VPinFE interface. `vpinfe-core.js` provides all calls for getting table data, media URLs, and joystick/keyboard input. `vpinfe-style.css` is required for the in-theme menu system.

`theme.js` and `style.css` are your theme's JS and CSS respectively. You can name those whatever you want.

### index_bg.html & index_dmd.html

Same structure as above, with content appropriate for each screen.

## Setting the Theme

The user selects a theme by setting this in `vpinfe.ini`:
```ini
[Settings]
theme = <THEME NAME>
```

## theme.js

The main JS file for interacting with VPinFE and controlling the theme UI.

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
        // table is launching - fade out, stop audio, etc.
    }
    else if (message.type == "TableLaunchComplete") {
        // returned from table - fade in, resume audio, etc.
    }
    else if (message.type == "RemoteLaunching") {
        // remote launch from manager UI
    }
    else if (message.type == "RemoteLaunchComplete") {
        // remote launch completed
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
            await vpin.launchTable(currentTableIndex);
            break;
        case "joyback":
            break;
    }
}

function updateScreen() {
    // Update images, info, audio for currentTableIndex
    // Only play audio on the table window
    if (windowName === "table") {
        tableAudio.play(vpin.getAudioURL(currentTableIndex));
    }
}

// circular table index helper
function wrapIndex(index, length) {
    return (index + length) % length;
}
```

> **Important:** Call `await vpin.handleEvent(message)` at the top of your `receiveEvent` function. This lets VPinFECore handle `TableDataChange` events automatically (collection changes, filter/sort updates) so you don't have to manage that logic yourself.

---

## vpinfe-core.js

The JavaScript interface to the VPinFE API. Must be loaded in your theme:
```html
<script src="../../common/vpinfe-core.js"></script>
```

### API Reference

#### init()
Sets up keyboard event listener and connects to the backend (pywebview bridge or WebSocket).

#### registerInputHandler(handler)
Registers an input handler for the table screen. Only works when the current window name is `"table"`.

#### registerInputHandlerMenu(handler)
Registers an input handler for the main menu overlay.

#### registerInputHandlerCollectionMenu(handler)
Registers an input handler for the collection menu overlay.

#### call(method, ...args)
Invokes a backend API method. Works transparently with both pywebview and WebSocket backends. Returns a Promise.

#### getImageURL(index, type)
Returns an HTTP URL for a table's image. `type` can be `"table"`, `"bg"`, `"dmd"`, `"wheel"`, or `"cab"`. Returns a fallback missing-image URL if the file doesn't exist.

#### getVideoURL(index, type)
Returns an HTTP URL for a table's video. `type` can be `"table"`, `"bg"`, or `"dmd"`. Returns a fallback missing-image URL if no video exists. See [Video Support](#video-support).

#### getAudioURL(index)
Returns an HTTP URL for a table's audio file, or `null` if no audio exists. See [Audio Support](#audio-support).

#### getTableMeta(index)
Returns the full metadata object for a given table, including VPSdb info, VPX file detection flags, and paths.

#### getTableCount()
Returns the number of tables in the current (possibly filtered) table list.

#### sendMessageToAllWindows(message)
Sends an event to all windows except the current one.

#### sendMessageToAllWindowsIncSelf(message)
Sends an event to all windows including the current one.

#### launchTable(index)
Disables gamepad input, calls backend to launch the selected table, then re-enables gamepad input. Sends `TableLaunchComplete` event to all windows when the table exits.

#### getTableData(reset=false)
Loads table data from the backend into `vpin.tableData`. Pass `reset=true` to reload from the full unfiltered table list.

#### handleEvent(message)
Handles incoming events with built-in logic for `TableDataChange` (collection/filter/sort changes). Call this at the top of your `receiveEvent` function to get automatic data refresh.

#### registerEventHandler(eventType, handler)
Registers a custom event handler for a specific event type. The handler is called whenever that event type is received via `handleEvent()`.

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

Use `vpin.getVideoURL(index, type)` to get the video URL. The method returns a fallback missing-image URL if no video file exists, so check for this before creating a `<video>` element.

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
