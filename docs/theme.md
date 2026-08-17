# Themes

VPinFE uses an embedded Chromium frontend with a WebSocket bridge to communicate between the browser and Python backend.

Themes interact with the backend through `vpinfe-core.js`, so theme code calls `vpin.call(...)` without handling transport details directly.

### Windows

VPinFE runs up to 3 browser windows, one per monitor:

- `playfield` — The main screen. Controller for all other screens and input. Handles gamepad/keyboard input and hosts the in-theme menu overlays. Contract 1 calls this window `table`.
- `bg` — Backglass screen. Receives events from the controller.
- `dmd` — DMD screen (not a "real DMD" like ZeDMD). Receives events from the controller.

Each window has its own webpage but shares an instance of the VPinFE API ([frontend/api.py](https://github.com/superhac/vpinfe/blob/master/frontend/api.py)), accessed via [vpinfe-core.js](#vpinfe-corejs).

---

## Theme Structure

Themes are installed in the user config directory: `~/.config/vpinfe/themes/<THEME NAME>/` (Linux) or the equivalent `platformdirs` location on other platforms.

```
<THEME NAME>
├── manifest.json
├── theme.json           (optional - schema plus saved Manager UI theme options)
├── preview.png          (optional - shown in manager UI, can be .png or .gif)
├── index_playfield.html  (one per declared window: index_<window>.html)
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
  "type": "desktop",
  "change_log": "Initial release.",
  "min_vpinfe": "3.0",
  "windows": ["playfield", "bg", "dmd"]
}
```

| Field | Description |
|-------|-------------|
| `name` | Display name shown in the manager UI. |
| `version` | Version string for tracking updates. |
| `author` | Theme author name. |
| `description` | Brief description shown in the manager UI. |
| `preview_image` | Filename of the preview image (`.png` or `.gif`). |
| `type` | Theme type: `"desktop"` for desktop/flat-screen setups, `"cab"` for cabinet setups, or `"both"` for themes that adapt to either. |
| `change_log` | What changed in this version. Optional. Shown as "What's new" in the Manager UI, and only to someone who has not installed your theme or has an update waiting — so it is worth writing for them, not as a running history. |
| `min_vpinfe` | The oldest VPinFE your theme runs on. Optional; absent means it runs on 2.x, which serves contract 1. Declaring `"3.0"` is what gets you the contract 2 surface. See [Theme contract](#theme-contract). |
| `windows` | The windows your theme wants, **controller first**. Optional; absent means the three VPinFE has always opened. See [Declaring windows](#declaring-windows). |
| `supported_screens` | Legacy. A count of screens, shown in the Manager UI and nothing more - it never decided which windows opened. `windows` replaces it and names them. Still accepted. |

`version` is your theme's own release number. `min_vpinfe` is the oldest VPinFE it runs
on. They are different questions and they move independently.

You do not declare a contract number. VPinFE knows which contract each of its own
versions serves, so the version you need already says which surface you get.

### Declaring windows

By default a theme gets three windows, named for the contract it declares — `table`, `bg`
and `dmd` at contract 1, `playfield`, `bg` and `dmd` at contract 2. Declaring nothing keeps
what you have.

Declaring nothing and shipping fewer pages also works: a default window whose
`index_<name>.html` is missing is not opened, so a single-screen theme that ships only its
main page gets one window rather than two that 404. That only applies to the default — a
window you declare is opened whether or not its page is there, because a declaration is
intent and hiding a missing page would hide your bug.

```json
"windows": ["playfield", "bg", "dmd", "topper"]
```

Everything about a window follows from its name:

| | |
|---|---|
| the file it loads | `index_<name>.html` |
| what it is passed | `?window=<name>` |
| the monitor it opens on | `[Displays] <name>screenid` |

**The first window is the controller.** It owns input, audio and the selection, and
`vpin.isController()` is how a window knows. A window with no monitor set is not opened,
so declaring four on a two-monitor machine is fine.

Name a window after a media kind and `vpin.getImageURL(index, windowName)` gives you that
kind's art — which is what several published themes already rely on for `bg` and `dmd`.

### Theme contract

VPinFE serves the game payload in the shape your theme's `min_vpinfe` implies, so a theme
keeps working when the data behind it is reshaped. You never name a contract yourself: each
VPinFE version serves one, and saying which version you need says which you get.

| Contract | Declared by | What the payload looks like |
|---|---|---|
| `1` (default) | no `min_vpinfe`, or one below `3.0` | An **array of game rows**. Each row is one game, with its default table folded into `meta.VPXFile` and a media path per kind at the top level. This is what every theme written before 3.0 reads, and it is unchanged. |
| `2` | `"min_vpinfe": "3.0"` or newer | An **object with an `entries` array**. Each entry is one *table*, with the game it belongs to attached. A game that offers several tables can appear more than once. |

These are different shapes, not the same shape with different key names — asking for 3.0
changes how you iterate the payload, not just what you call things. See
[Contract 2 payload](#contract-2-payload).

**You do not need to raise `min_vpinfe` when VPinFE adds things.** New media kinds, new fields
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
        "manufacturer_logo": "/assets/manufacturers/bally.png",
        "created_at": "2026-08-01T09:30:00Z",
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
      "media": ["playfield", "bg", "wheel"]
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
| `entries[].table.file_hash` | The sha256 of the `.vpx`. Two installs sharing a filesystem can agree they hold the same file without comparing paths, which differ by mount point. |
| `entries[].table.hidden` | The user chose not to be offered this table. A wheel skips these; the hub has already dropped them from what it serves. |
| `entries[].table.release_date` | When this build was published, which is the table's own answer rather than the game's. Null where the `.vpx` did not say. |
| `entries[].table.default` | Whether this is the table its game defaults to. A game offering several appears once per table when expanded; this says which one is the game's own. |
| `entries[].table.user` | The same counters for this table alone — `last_played`, `play_count`, `play_time_seconds`. A game and its tables accumulate independently, so deleting a table does not un-play the game's hours. |
| `entries[].assets` | What the game needs to play as intended, as booleans. |
| `entries[].siblings` | How many tables this entry's game offers. `1` means there is nothing to switch to. |
| `entries[].media` | The media kinds this game **has a file for** — `playfield`, `bg`, `wheel` and the rest, the same names `vpin.getMedia(index, kind)` takes. Names, not paths: fetch one from `/media/<table id>/<kind>`. |
| `entries[].game.manufacturer_logo` | Web path to the manufacturer's shared logo, or `null`. Art about the manufacturer rather than about this game, which is why it is not a media kind. |
| `entries[].game.created_at` | When the game's folder appeared, ISO 8601 UTC, or `null` where the filesystem gave no answer. What a "Newest" sort orders on. |

**`detects` loses the `detect_` prefix.** `table.detects.ssf`, not `detect_ssf` — the
prefix was storage, not vocabulary.

**`vpin.entries` is the list you iterate.** `vpin.tableData` holds the same array, but at
contract 2 its items are entries rather than games, so `entries` is the name that
describes them. The view they came from travels alongside as `vpin.collection` and
`vpin.expanded`. Every ordinal helper — `getTableCount()`, `getCurrentTableIndex()`,
`getTableMeta(index)` — counts and addresses entries.

**Media is named, not located.** `entries[].media` lists the kinds this game has a file
for. To show one, request `/media/<table id>/<kind>` from the theme assets port — the same
server your theme is loaded from. Contract 1 carried a filesystem path per kind and left
every theme to turn it into a URL; contract 2 does not put the filesystem in a web page,
and on a large library it keeps several hundred kilobytes off the wire each time the list
is rebuilt. Responses carry an `ETag` and ask to be revalidated, so replacing art in the
Manager UI shows up without a hard refresh.

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
leaning on decides whether asking for 3.0 changes anything for you.

**The payload follows the contract your `min_vpinfe` implies.** At `1` — which is what you
get by declaring nothing — VPinFE builds the row shape 2.x themes read, including the names 2.x
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
| `vpin.playfieldRotation` | `vpin.tableRotation` |
| `vpin.playfieldOrientation` | `vpin.tableOrientation` |

**The selection members and the window messages need no alias.** `vpin.tableData`,
`getTableData()`, `getTableCount()`, `getCurrentTableIndex()`, `getTableMeta()`,
`playTableAudio()`, `stopTableAudio()`, `launchTable()`, and the `TableIndexUpdate`,
`TableDataChange`, `TableLaunching`, `TableRunning` and `TableLaunchComplete` messages,
are the names 2.x published and the names 3.0 uses. They address a row, and a row is a
table — one game may offer several.

The aliases are not a second API. Write new themes against the `playfield` names for the
screens and the `table` names for the wheel — those are what the rest of this document
uses.

---

## HTML Files

Each window has its own HTML file, named after the window: `index_<window>.html`. So a
theme's files follow from the windows it declares, and a theme that declares a `topper`
ships `index_topper.html` without anything else changing.

Declare nothing and you get three, named for your contract:

| Contract | Files |
|---|---|
| 2 | `index_playfield.html`, `index_bg.html`, `index_dmd.html` |
| 1 | `index_table.html`, `index_bg.html`, `index_dmd.html` |

**The main screen is `index_playfield.html` here.** Contract 1 called that window `table`,
and a contract 2 theme shipping `index_table.html` gets a 404 — nothing looks for it.

### index_playfield.html

This is the main HTML file. It controls input, displays the primary UI, and hosts the in-theme menu overlays. Below is the minimum required structure:

> Core's own files are served at `/core/`, against `/themes/` for what a theme provides.
> Themes written before 3.0 ask for them at `/web/`, which still serves the same files —
> nothing needs updating, and both spellings reach the same place.

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>VPinFE - My Theme</title>
  <link rel="stylesheet" href="/core/common/vpinfe-style.css">
  <link rel="stylesheet" href="style.css">
  <script src="/core/common/vpinfe-core.js"></script>
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
<link rel="stylesheet" href="/core/common/vpinfe-style.css">
<script src="/core/common/vpinfe-core.js"></script>
```

These are served by VPinFE's HTTP server on port 8000. `vpinfe-core.js` provides all API calls, media URL helpers, gamepad/keyboard input, and event handling. `vpinfe-style.css` is required for the in-theme menu system styling.

Your theme's own `style.css` and `theme.js` can be named whatever you want.

#### Required HTML Elements

| Element | Purpose |
|---------|---------|
| `<div id="overlay-root">` | **Required on the controller window.** VPinFECore injects the overlay iframes here; without it, no overlay appears. Harmless on the other windows, and nothing is ever injected into them. |

### Overlays

An overlay is a page VPinFE hosts above your theme: the main menu, the collection menu and
the tutorial. Core owns the hosting — it creates the iframe once, fades it in, hides rather
than destroys it, and closes any other overlay first, so **at most one is ever open**.

```javascript
vpin.overlay                      // "menu", "collectionMenu", "tutorial", or null
vpin.toggleOverlay("menu")        // open it, or close it if it is the one that is open
```

`vpin.overlay` is the whole state. A theme that dims itself while a menu is up reads it:

```javascript
if (vpin.overlay) document.body.classList.add("dimmed");
```

**An open overlay owns every action.** While one is up, core sends input to that overlay's
own handler and your theme's `handleInput` is not called. Nothing has to check for this;
it is what the guard already does.

Bindings are unchanged: `menu`, `collection_menu` and `tutorial` are input actions the user
configures, and core toggles the matching overlay when one fires.

| 2.x name | now |
|---|---|
| `vpin.menuUP` / `collectionMenuUP` / `tutorialUP` | `vpin.overlay` |
| `vpin.toggleMenu()` / `toggleCollectionMenu()` / `toggleTutorial()` | `vpin.toggleOverlay(name)` |
| `vpin.registerInputHandlerMenu(fn)` and its two siblings | `vpin.registerOverlayHandler(name, fn)` |

All nine old names keep working — the booleans read the string, and the methods call the
new pair with the overlay's name filled in.

#### Optional HTML Elements

| Element | Purpose |
|---------|---------|
| `<div id="fadeContainer">` | Wrap your content for fade-to-black transitions on game launch/return. Style with `transition: opacity` in CSS. |
| `<div id="fadeOverlay">` | Alternative fade pattern: a fixed full-screen black overlay that fades in/out via a CSS class (e.g., `.show { opacity: 1 }`). |
| `<div id="remote-launch-overlay">` | Overlay shown when the manager UI triggers a remote game launch. Include `<div id="remote-launch-table-name">` inside for the game name. |

### Playfield Geometry: Mounting, Rotation And Cab Mode

Three settings describe one physical fact, and they are easy to confuse. This is what each
one means and how they combine.

| setting | section | what it turns |
|---|---|---|
| `playfieldorientation` | `[Displays]` | nothing — it states how the monitor is **mounted** |
| `playfieldrotation` | `[Displays]` | the **UI**, so it faces the player |
| `playfieldmediarotation` | `[Media]` | the **art**, so it fills the surface |
| `cabmode` | `[Displays]` | nothing — **context** only: type scale, target size, affordances |

#### The three setups

| | monitor mounted | does the OS rotate it? | window arrives | what has to turn |
|---|---|---|---|---|
| **A** | portrait | yes | portrait | the art only — the page is already upright |
| **B** | portrait | no | landscape | the whole page, then the art |
| **C** | landscape | n/a | landscape | nothing |

A is `portrait` + `0`. B is `portrait` + `90` or `270` — which one depends on which way the
panel was turned in the cabinet. C is `landscape` + `0`.

**B is the case people miss.** If the desktop appears sideways on the playfield screen, or
the taskbar runs up the side of it, the OS is not rotating and VPinFE has to.

#### What your theme reads

```javascript
vpin.layout = {
  cabinet: false,        // context, never geometry
  uprightRotation: 0,    // turn the whole UI this far to face the player
  surface: "portrait",   // the shape to design for, AFTER that turn
}
```

**`surface` is the one you want.** It is identical in setups A and B — a portrait cabinet
reads `"portrait"` whether the OS turned the screen or VPinFE turns the UI — so one layout
serves both. Design for `surface` and the difference stops being yours to handle.

`vpin.playfieldOrientation` and `vpin.playfieldRotation` remain as the raw ini values, but a
theme should not need them.

Do **not** infer any of this from `window.innerWidth` and `window.innerHeight`. Those move
with OS orientation, DPI, monitor placement and any transform your own theme has applied, so
a layout that reads them ends up fighting its own output.

#### Letting core do it

Set this in your `config.json` and core turns both the UI and the art for you:

```json
{ "layout": { "enabled": true } }
```

Then mark the two elements it should act on. `vpinfe-style.css`, which your theme already
links, carries the rules:

```html
<div class="vpinfe-upright">…your whole UI…</div>
<img class="vpinfe-playfield-media" id="playfield">
```

```javascript
vpin.applyPlayfieldMediaRotation(document.getElementById("playfield"));
```

That is the whole integration — no rotation arithmetic anywhere in your theme.

**The art is measured, not assumed.** There is no reliable convention for how playfield
captures are authored: a library may be landscape desktop shots, portrait FSS renders, or a
mix. Core compares each image's own aspect against `surface` and turns it only when they
disagree, so FSS art on a portrait cabinet is correctly left alone. `[Media]
playfieldmediarotation` is `auto` for that reason; set it to `0`, `90`, `180` or `270` only
for what measuring cannot see — art that is upside down, or art you would rather letterbox
than turn.

#### Doing it yourself

If your theme lays itself out, leave `core_layout` off and read `vpin.layout` directly. Two
rules matter:

- **Rotate the media, not the page**, unless the page genuinely has to turn — rotating the
  whole surface stands your text and controls on their side too.
- **Size a rotated element from the viewport** (`100vh` × `100vw` for a quarter turn), never
  from `getBoundingClientRect()`. That method reports the box *after* your transform, so
  feeding it back shrinks the image a little more on every pass.

Good questions to answer up front when starting a new theme:

- Should the theme declare `type: "cab"` or `type: "both"`?
- Should portrait mode use a different layout, or just rotate the landscape one?
- Should only the main playfield UI rotate, or should playfield-only overlays rotate too?

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
  <link rel="stylesheet" href="/core/common/vpinfe-style.css">
  <link rel="stylesheet" href="style.css">
  <script src="/core/common/vpinfe-core.js"></script>
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

The main JS file for interacting with VPinFE and controlling the theme UI. Every window loads the same `theme.js`, so use `vpin.windowName` to branch logic per window - or `vpin.isController()`, which does not care what the controller is called. Older themes read a global `windowName` that they set themselves from `get_my_window_name`; `vpin.windowName` is the same answer without the round trip.

VPinFE also passes the current window identity in the page URL as `?window=playfield`, `?window=bg`, or `?window=dmd`. For high-DPI backglass and DMD setups, VPinFE may also include an optional `override` query parameter in the form `x,y,width,height`. Theme authors can read that value when they need to use the configured bounds instead of the auto-detected browser window size.

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
    // Let VPinFECore handle the data refresh logic (TableDataChange, filters, sorts)
    await vpin.handleEvent(message);

    if (message.type == "TableIndexUpdate") {
        currentGameIndex = message.index;
        updateScreen();
    }
    else if (message.type == "TableLaunching") {
        await fadeOut();
    }
    else if (message.type == "TableRunning") {
        // Game has finished loading and is now running
    }
    else if (message.type == "TableLaunchComplete") {
        fadeIn();
    }
    else if (message.type == "RemoteLaunching") {
        // Remote launch from manager UI - message.game_name has the game name
        showRemoteLaunchOverlay(message.game_name);
        await fadeOut();
    }
    else if (message.type == "RemoteLaunchComplete") {
        hideRemoteLaunchOverlay();
        fadeIn();
    }
    else if (message.type == "TableDataChange") {
        currentGameIndex = message.index;
        updateScreen();
    }
}

// input handler - only called on the controller window
/*  joyleft, joyright, joyup, joydown,
    joyselect, joymenu, joyback, joycollectionmenu */
async function handleInput(input) {
    switch (input) {
        case "joyleft":
            currentGameIndex = wrapIndex(currentGameIndex - 1, vpin.tableData.length);
            updateScreen();
            vpin.sendMessageToAllWindows({
                type: 'TableIndexUpdate',
                index: currentGameIndex
            });
            break;
        case "joyright":
            currentGameIndex = wrapIndex(currentGameIndex + 1, vpin.tableData.length);
            updateScreen();
            vpin.sendMessageToAllWindows({
                type: 'TableIndexUpdate',
                index: currentGameIndex
            });
            break;
        case "joyselect":
            vpin.sendMessageToAllWindows({ type: "TableLaunching" });
            await fadeOut();
            await vpin.launchTable(currentGameIndex);
            break;
        case "joyback":
            break;
    }
}

function updateScreen() {
    if (vpin.isController()) {
        // Update the playfield window: images, carousel, info, audio
        vpin.playTableAudio(currentGameIndex);
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

> **Important:** Call `await vpin.handleEvent(message)` at the top of your `receiveEvent` function. This lets VPinFECore handle `TableDataChange` events automatically (collection changes, filter/sort updates) so you don't have to manage that logic yourself.

> **Important:** Set `window.vpin = vpin` so the in-theme menu system can call back into your VPinFECore instance.

### Strong Recommendation: Keep The Playfield DOM Persistent

For anything beyond a very simple theme, especially carousel-style playfield screens, avoid rebuilding the entire playfield window DOM on every game change.

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
| `TableIndexUpdate` | `index`, `previous`, `direction`, `reason`, `source`, `moving`, `group`, `groupKind`, `list`, `kind` | The selection moved. Sent by the controller to all others, on every path. |
| `TableLaunching` | — | A game is about to launch. Frontend keyboard/gamepad routing is suspended until `TableLaunchComplete`; use this to fade out, stop audio, etc. |
| `TableRunning` | — | The launched game has finished loading and is now running. Sent when the table process outputs "Startup done". |
| `TableLaunchComplete` | — | The launched game has exited and frontend input routing is restored. Use this to fade back in, resume audio. |

**What `TableIndexUpdate` carries.** Every one of these is on every index message — a step,
a page and a startup restore all announce themselves the same way:

| Field | Meaning |
|---|---|
| `index` | where the selection is now |
| `previous` | where it was. A local diff cannot tell a wrap from a jump: 149 → 0 is either one step forward or 149 back |
| `direction` | `"previous"` or `"next"`, empty when the move had no direction |
| `reason` | how far and why — `"step"` for one item, `"page"` for a page press, `"restore"` at startup, `"enter"` and `"leave"` when core descends into a list or comes back out. A page press moves to the next group when group paging is on and a fixed number of rows otherwise; both report `"page"`, because both want the same treatment |
| `source` | who moved it — `"user"` today; core will move it on a timer later |
| `moving` | true while the wheel is still settling, so you can defer full-resolution art. Time-based, so a single distant move reports `false` — use `reason` to tell a page from a step |
| `group` | the group the selection landed in — `"T"`, `"1985"`, `"#"`. Empty when the list's order has no groups |
| `groupKind` | what kind of group that is — `"letter"`, `"year"`, `"rating"`. Empty alongside `group`, so you can tell "no grouping here" from "the group happens to be empty" |
| `list` | which list this index is in — the collection name for the wheel, `"collections"` for the picker |
| `kind` | what that list holds — `"table"` or `"collection"`. Read this instead of keeping a mode flag: an index message can no longer be mistaken for "a game was picked" |

If you animate between positions, read `reason`: sliding one item is right for a `"step"`
and wrong for a `"page"`, which should cut. A page can move the selection a long way —
group paging jumps to the next letter, year or rating — so sliding through it is what
produces the two-wheels-stacked artifact.

`group` and `groupKind` are what you draw a "now in the Ts" badge from. They ride on every
index message, not just a page, so the badge stays right when the user steps across a
boundary too. Both are empty while a picker is open — the groups belong to the wheel.

### Lists core holds

Core can descend into a list of its own and move that instead of the wheel. Today that is
the collection picker, opened with `vpin.openCollectionPicker()`.

While a list is open, `list` and `kind` on every index message say which list moved, and
core owns `select` and `back` — select applies what the cursor is on and closes, back
closes without applying. It has to own them: your theme cannot pop a stack it does not
know about.

**Nothing that follows the wheel fires while a picker is open.** The selected game does not
change, `onSelection` listeners do not run, and window media is not re-rendered. So a theme
does not need a mode flag, and does not need to undo anything when the picker closes — the
wheel is exactly where the player left it.

```js
// Render whichever list core is moving.
window.receiveEvent = (message) => {
  if (message.type !== "TableIndexUpdate") return;
  if (message.kind === "collection") highlightCollection(message.index);
  else moveWheelTo(message.index);
};
```
| `RemoteLaunching` | `game_name`, `table_name` | The manager UI triggered a remote game launch. Both names carry the same value; `table_name` is the 2.x spelling. Frontend keyboard/gamepad routing is suspended until `RemoteLaunchComplete`; show an overlay. |
| `RemoteLaunchComplete` | — | The remote-launched game has exited and frontend input routing is restored. Hide the overlay. |
| `TableDataChange` | `index`, `collection?`, `filters?`, `sort?` | Game data changed (collection switch, filter/sort update, a finished game's play data, a Manager UI edit). Handled automatically by `vpin.handleEvent()`. |

`TableDataChange` also arrives unprompted: when a game exits, and when the Manager UI
changes a game or a collection. Those are raised by the backend, which has no wheel
index to send, so `vpin.handleEvent()` fills `index` in before your handler sees it —
and it fills in where the game you were on has *moved to*, not the slot it used to
occupy. Assigning `message.index` to your wheel is therefore still correct after a
refresh reorders the list, which is what a `LastRun` sort does when a game is played.

You can also define custom event types and send them with `vpin.sendMessageToAllWindows()`.

### Loading Overlay During Game Launch

Themes can show a loading image or animation while VPX is starting. Use the built-in launch lifecycle instead of guessing with timers:

- show the overlay on `TableLaunching`
- hide it on `TableRunning`
- also hide it on `TableLaunchComplete` as a cleanup fallback

Add the overlay markup to every theme page that should show it (`index_playfield.html`, `index_bg.html`, and/or `index_dmd.html`):

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

If the controller launches the game from local input, remember that `vpin.sendMessageToAllWindows(...)` excludes the sender. Call `showTableLoadingOverlay()` directly in the local `joyselect` path before `await vpin.launchTable(...)`, or send the event with `vpin.sendMessageToAllWindowsIncSelf(...)`.

### Attract Mode During Game Launch

If your theme implements attract mode, treat game launch as a hard suspension boundary. Clearing the current timer is not enough, because user-activity listeners, menu events, or `TableRunning` handling can accidentally schedule a new idle timer while VPX is still open.

Use a separate launch/remote-launch suspension flag:

- set `attractSuspended = true` and clear both idle and advance timers on `TableLaunching` and `RemoteLaunching`
- keep `shouldPauseAttractMode()` returning `true` while `attractSuspended` is set
- make user-activity handlers clear timers and return without scheduling a new idle timer while suspended
- clear `attractSuspended` only on `TableLaunchComplete` or `RemoteLaunchComplete`
- after launch completion, restart the idle countdown instead of immediately starting attract mode
- in a local `joyselect` launch path, suspend attract mode before calling `vpin.launchTable(...)` so the sender is protected before backend events arrive

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

  if (message.type === "TableLaunching" || message.type === "RemoteLaunching") {
    suspendAttractMode();
  } else if (message.type === "TableLaunchComplete" || message.type === "RemoteLaunchComplete") {
    attractSuspended = false;
    markUserActivity();
  }
}
```

### Input Actions

The following input actions are passed to your `handleInput` function (controller window only):

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
where the press should land (`get_page_index`) and broadcasts a `TableIndexUpdate`
to every window. Your theme moves its wheel through the same `receiveEvent` path it
already uses for external index updates, so paging works with no theme changes.

The user controls the behavior with two `[Input]` settings in `vpinfe.ini`:

- `pagingtype` — `group` (default) jumps to the next boundary in whatever the list is
  ordered by: the next letter under title order (numbers and symbols share one `#`
  group), the next year under year order, the next rating under rating order. `step`
  jumps a fixed number of games. Orders where every value is its own — last played,
  date added, play count, play time — have no groups, and neither does a curated
  collection's manual order; a press steps there, and so does a list that is all one
  group. The 2.x names `alpha` and `numeric` still resolve, to `group` and `step`.
- `pagingsize` — how many games a `step` jump moves (default `10`). All paging wraps
  around.

A theme that wants its own paging behavior calls `vpin.enableCorePaging(false)`;
the actions are then routed to `handleInput` like any other, and
`vpin.getPageIndex(direction)` is available if you want the config-aware target
index while animating the move yourself. While a core overlay (menu, collection
menu, tutorial) is up, these actions bypass core paging and go to the overlay's
handler regardless.

**Core paging is decided before your handler runs.** While it is on, a paging action
never reaches `handleInput`, so a `case "joypageup"` added without the
`enableCorePaging(false)` call never fires. A theme whose wheel shows something other
than the game list wants the call: core pages the game list and broadcasts the move
either way.

---

## vpinfe-core.js

The JavaScript interface to the VPinFE API. Must be loaded in your theme:
```html
<script src="/core/common/vpinfe-core.js"></script>
```

### Public Properties

These properties are available on the `vpin` instance after `vpin.ready` resolves:

| Property | Type | Description |
|----------|------|-------------|
| `vpin.tableData` | `array` | The current (possibly filtered) game list. At contract 2 each element is an entry (see [Entry Data Object](#entry-data-object)); at contract 1 it is a game row. |
| `vpin.monitors` | `array` | List of monitor objects with `name`, `x`, `y`, `width`, `height`. Loaded during init. |
| `vpin.playfieldOrientation` | `string` | Playfield orientation from config: `"landscape"` or `"portrait"`. |
| `vpin.playfieldRotation` | `number` | Playfield rotation in degrees from config (default `0`). |
| `vpin.layout` | `object` | The resolved layout answers — `{ cabinet, uprightRotation, surface }`. This is what a theme should read; the two properties above it are the raw ini values. See [Playfield geometry](#playfield-geometry-mounting-rotation-and-cab-mode). |
| `vpin.themeAssetsPort` | `number` | Asset server port (default `8000`). Prefer `vpin.endpoints.assets`, which is the whole base URL. |
| `vpin.endpoints` | `object` | Where the things this page talks to are — `{ hub, player, assets, frontend_channel }`. The first three are addresses you add a path to: `hub` is the library and what's known about it, `player` is this machine (launching, play state, hardware), `assets` is the files themselves (theme packages, table media, shared art). `frontend_channel` is not an address but a line held open — how this page and VPinFE talk to each other, both ways — so nothing is appended to it. Build URLs from these rather than assuming a host or a port: the halves can be separate machines, and only this knows where they are. |
| `vpin.menuUP` | `boolean` | Whether the main menu overlay is currently visible. |
| `vpin.capabilities` | `object` | What this build does on your behalf, and whether each is on — `{ core_paging: true, core_audio: false, core_preload: false }`. A name that is absent is a behavior this build does not have, so check before relying on it. Reading it gives you a copy; use `enableCorePaging()` / `enableCoreAudio()` to change anything. At contract 2 `core_navigation` covers stepping *and* paging, so `enableCorePaging(false)` turns off both — a page is a bigger step, not a separate feature. |
| `vpin.contract` | `number` | Which contract you are being served. |
| `vpin.windowName` | `string` | This window's name — which page it loaded, and its media kind when it has one. Known before the socket opens, so there is nothing to await. |
| `vpin.collectionMenuUP` | `boolean` | Whether the collection menu overlay is currently visible. |

### API Reference

#### enabled(name)
`true` when core is doing that for you right now. `vpin.enabled("core_audio")`. An unknown
name is `false` rather than an error, so a theme can ask about something a build might not
have.

Each capability has one stated default: **core paging is on** (opt out if your theme does
its own), **core audio is off** (opt in), **core preloading is off** (opt in).

Turn one on in your **`config.json`** — the author's file. A capability's settings live in
a block named after it, and `enabled` is one of those settings:

```json
{
  "audio":   { "enabled": true, "max_volume": 0.8 },
  "preload": { "enabled": true, "kinds": ["playfield", "bg", "wheel"] }
}
```

That shape is the one to write, because it is the only one that carries a capability's
other settings — there is no flat spelling of `preload.kinds`. Core audio also answers to
`use_core_audio` and `audio.use_core_audio`, which accumulated before anything said which
was meant; both still work and neither is worth adding to a new theme.

#### Core preloading

With `core_preload` on, core fetches the media for the selection and its two neighbors —
but only once the wheel has stopped, after about 180 ms of quiet. That delay is the point.
A held key repeats around 30 times a second, so a theme preloading on every step asks for
hundreds of images that are obsolete before they decode, and the browser is still draining
that queue long after the key is released. Waiting for the wheel to settle turns a
two-second hold into one batch.

`preload.kinds` chooses what gets fetched; the default is `["playfield", "bg", "wheel"]`.
A theme showing a cabinet shot wants `cab` in there, and one with no wheel should drop it.

```json
{ "preload": { "enabled": true, "kinds": ["playfield", "bg", "wheel"] } }
```

**If you switch this on, delete your own preloading.** Running both just doubles the
requests, which is why this is opt-in rather than on by default.

#### init()
Sets up keyboard event listener and connects to the backend over the WebSocket bridge.

#### registerInputHandler(handler)
Registers an input handler for the playfield screen. Only works on the controller - the first window your theme declares, `playfield` unless you say otherwise. The handler receives a single string argument (the action name).

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
| `get_my_window_name` | — | `string` | Returns the window name for this instance (`"playfield"`, `"bg"`, or `"dmd"` by default). |
| `close_app` | — | — | Shuts down all browser windows and exits the application. |
| `shutdown_system` | — | — | Powers off the machine. |
| `lifecycle_request` | `scope`, `action`, `reason`, `confirmed` | `bool` | Starts, stops or restarts something. Returns whether it is going ahead. |
| `lifecycle_needs_confirmation` | `scope`, `action` | `object` | `{confirm, description}` — whether to ask the user first, and the wording to ask with. |
| `get_monitors` | — | `array` | Returns list of monitor objects with `name`, `x`, `y`, `width`, `height`. |
| `console_out` | `output` | `string` | Prints a message to the Python CLI console. Useful for debugging. Returns the same string. |

###### Starting, stopping and restarting

`scope` is what the action applies to and `action` is what happens to it:

| | `frontend` | `app` | `system` |
|---|---|---|---|
| `start` | yes | — | — |
| `stop` | yes | yes | powers off |
| `restart` | yes | yes | yes |

`close_app` and `shutdown_system` still work and are unchanged — they are `app`/`stop`
and `system`/`stop` under the old names.

Use `vpin.requestLifecycle(scope, action)` rather than calling the two methods directly.
It confirms first when the user has turned that on for the scope, and resolves `false`
when they say no, so a menu can stay open:

```js
if (await vpin.requestLifecycle("system", "restart")) {
  // going ahead - the machine is restarting
}
```

Core draws the confirmation, so a theme gets it for free. A theme that wants its own
asks the user itself, then calls `lifecycle_request` with `confirmed` set to `true`.

The user chooses which scopes get confirmed with the `lifecycle.confirm` setting, which
is empty by default. The question is always put on the surface that asked; every other
window is told through the `lifecycle.acting` event and cannot block it.

##### Game Data

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_tables` | `reset=false` | `string` (JSON) | Returns JSON string of the current (filtered) game list. Pass `true` to reset to the full unfiltered list. Each game object includes paths, media paths, addon flags, and metadata. |
| `launch_table` | `index` | — | Launches the game at the given index. Blocks until the table exits. Records the play against the game — start count, last-played date and runtime — which is what the "Last Played" collection is built from. Sends `TableLaunching` before launch, `TableRunning` when the table finishes loading, and `TableLaunchComplete` when it exits. |
| `build_metadata` | `download_media=true`, `update_all=false` | `object` | Triggers a background metadata build/refresh. Sends progress events (`buildmeta_progress`, `buildmeta_log`, `buildmeta_complete`, `buildmeta_error`) to all windows. Returns `{success, message}`. |

##### Collections

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `get_collections` | — | `array` | Returns list of collection names from `collections.ini`. |
| `get_collections_metadata` | — | `array` | Returns collection objects with `name`, `type`, `is_filter`, `image`, `image_url`, and `table_count`. `image_url` is a theme-server URL such as `/collection_icons/favorites.png`, or an empty string when no image is set. |
| `get_collection_image_url` | `collection` | `string` | Returns the image URL for one collection, or an empty string when no image is set. |
| `set_tables_by_collection` | `collection` | — | Shows the named collection: what it holds, in the order it stores. Works for a hand-picked collection and a filter-based one alike. |
| `save_filter_collection` | `name`, `letter`, `theme`, `table_type`, `manufacturer`, `year`, `sort_by`, `rating`, `rating_or_higher`, `order_by` | `object` | Saves the current filter settings as a named collection. `order_by` is `"Descending"` or `"Ascending"` and defaults to `"Descending"`. Returns `{success, message}`. |
| `get_current_collection` | — | `string` | Returns the name of the currently active collection, or `"None"`. |

##### Filters & Sorting

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `reset_filters` | — | — | Resets all filters back to the full game list. |
| `get_filter_letters` | — | `array` | Returns available starting letters from all games (for filter UI). |
| `get_filter_themes` | — | `array` | Returns available themes/categories from all games. |
| `get_filter_types` | — | `array` | Returns available game types (SS, EM, PM, etc.) from all games. |
| `get_filter_manufacturers` | — | `array` | Returns available manufacturers from all games. |
| `get_filter_years` | — | `array` | Returns available years from all games. |

Applying a filter or a sort is not on this list. The collection menu VPinFE ships owns
those controls, so `apply_filters`, `apply_sort`, `get_current_filter_state`,
`get_current_sort_state` and `get_current_order_state` are core's own and `vpin.call`
refuses them (PAR-84). Show the library the way a collection stores it and let the menu
change it — `set_tables_by_collection` and the lists above are what a theme needs for that.

##### Events & Messaging

| Method | Args | Returns | Description |
|--------|------|---------|-------------|
| `send_event_all_windows` | `message` | — | Sends an event to all windows except the caller. |
| `send_event_all_windows_incself` | `message` | — | Sends an event to all windows including the caller and iframes. |
| `send_event` | `window_name`, `message` | — | Sends an event to a specific window by name (`"playfield"`, `"bg"`, or `"dmd"` by default). |

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

- `?window=playfield`
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
| `playTableAudio` | `indexOrUrl`, `retries=3` | — | Plays game audio using VPinFECore's centralized audio manager. Pass a game index (recommended) or URL string. |
| `stopTableAudio` | `options={}` | — | Stops audio via centralized manager. Supports fade-out; pass `{ immediate: true }` for an immediate stop. |
| `enableCoreAudio` | `enabled=true` | — | Enables or disables centralized audio handling for the current window. Core audio is opt-in by default unless enabled in theme config. |
| `isCoreAudioEnabled` | — | `boolean` | Returns whether centralized audio handling is currently enabled. |
| `setAudioOptions` | `options` | — | Sets runtime audio options. Supported keys: `maxVolume`/`max_volume`/`volume`, `fadeDuration`/`fade_duration_ms`/`fadeMs`, `loop`. |

#### getImageURL(index, kind)
Returns an HTTP URL for a table's image. `kind` can be `"playfield"`, `"bg"`, `"dmd"`, `"wheel"`, or `"cab"`. Returns a fallback `/core/images/file_missing.png` URL if the file doesn't exist.

#### getVideoURL(index, kind)
Returns an HTTP URL for a table's video. `kind` can be `"playfield"`, `"bg"`, or `"dmd"`. Returns a fallback `/core/images/file_missing.png` URL if no video exists. See [Video Support](#video-support).

#### getMediaURL(index, kind)
Returns an HTTP URL using the user's configured media priority from Manager UI > Configuration > Media > Media Priorities. For `"playfield"`, `"bg"`, and `"dmd"`, VPinFE chooses image or video first based on the setting and falls back to the alternate when the preferred file is missing. For `"real_dmd"`, VPinFE chooses `realdmd-color.png` or `realdmd.png` first based on the setting and falls back to the other frame.

Kind names are snake_case, the same strings the payload and `/api/v1` use. The spellings earlier builds accepted — `table`, `table_video`, `fss`, `realdmd`, `realdmd-color`, `rulecard`, `audiolaunch`, `rulesheet` — still work.

#### getMedia(index, kind)
Returns the same priority-aware selection with metadata: `{ url, kind, priority, path }`. Real DMD selections also include `variant` with `"color"` or `"standard"`.

#### getAudioURL(index)
Returns an HTTP URL for a game's audio file, or `null` if no audio exists. See [Audio Support](#audio-support).

#### getManufacturerLogoURL(index)
Returns an HTTP URL for the game manufacturer's logo, or `null` if none is installed. Logos live in the shared assets folder (`[Settings] assetsdir`, `manufacturers/` subfolder) and are matched to the game's `Info.Manufacturer` metadata, so "Williams Electronics" and "Williams" find the same file. Always handle `null` — a fresh install has no logos.

#### playTableAudio(indexOrUrl, retries=3)
Plays game audio via VPinFECore's centralized audio manager. Normally you pass `currentGameIndex`; passing a URL string is also supported.

#### stopTableAudio(options={})
Stops centralized audio playback. Default behavior is fade-out, or pass `{ immediate: true }` for an immediate stop.

#### enableCoreAudio(enabled=true)
Turns centralized core audio handling on or off for the current window.

#### isCoreAudioEnabled()
Returns `true` when centralized core audio handling is enabled.

#### setAudioOptions(options)
Updates centralized audio options at runtime: volume (`maxVolume`, `max_volume`, or `volume`), fade duration (`fadeDuration`, `fade_duration_ms`, or `fadeMs`), and `loop`.

#### enableCorePaging(enabled=true)
Turns core-handled wheel paging (`joypageup`/`joypagedown`) on or off. Disable it if your theme does its own paging; the actions then arrive in `handleInput`. Call it before you rely on those cases — while core paging is on it answers first, so the case never fires. See [Wheel Paging](#wheel-paging).

#### isCorePagingEnabled()
Returns `true` when core-handled wheel paging is enabled.

#### getPageIndex(direction="next", index=current)
Asks the backend where a page press should land and returns the target index. Convenience wrapper around the `get_page_index` API method for themes doing their own paging animation.

#### getTableMeta(index)
Returns the full object for a given index - an entry at contract 2, a game row at contract 1. The same object as `vpin.tableData[index]`. See [Entry Data Object](#entry-data-object).

#### getTableCount()
Returns the number of games in the current (possibly filtered) game list.

#### sendMessageToAllWindows(message)
Sends an event to all windows except the current one. Convenience wrapper around `vpin.call("send_event_all_windows", message)`.

#### sendMessageToAllWindowsIncSelf(message)
Sends an event to all windows including the current one and forwarding to iframes.

#### launchTable(index)
Suspends frontend keyboard/gamepad routing, calls backend to launch the selected game, then restores input after the launch lifecycle completes. The launch lifecycle is `TableLaunching` before the process starts, `TableRunning` when the table finishes loading, and `TableLaunchComplete` when it exits.

#### getTableData(reset=false)
Loads game data from the backend into `vpin.tableData`. Pass `reset=true` to reload from the full unfiltered game list.

#### handleEvent(message)
Handles incoming events with built-in logic for:
- `TableDataChange` (collection/filter/sort changes)
- centralized audio transitions on `TableIndexUpdate`, `TableLaunching`, `RemoteLaunching`, `TableLaunchComplete`, and `RemoteLaunchComplete`

Call this at the top of your `receiveEvent` function to get automatic data refresh and default audio behavior.

#### registerEventHandler(eventType, handler)
Registers a custom event handler for a specific event type. The handler is called whenever that event type is received via `handleEvent()`.

---

## Entry Data Object

Each element of `vpin.entries` is one table with the game it belongs to attached. The
fields are listed under [Contract 2 payload](#contract-2-payload); this section is about
reading them.

```javascript
const entry = vpin.getTableMeta(currentGameIndex);
const { game, table, media, assets, siblings } = entry;
```

> **Contract 1 serves a different shape** — a flat game row with the `.info` passed
> through as `meta`. None of it is served here. See
> [theme-contract-1.md](theme-contract-1.md).

### Reading game info

Everything a theme displays has a named home, so there is nothing to resolve or fall back
through:

```javascript
const entry = vpin.getTableMeta(currentGameIndex);

const title = entry.game.name;
const manufacturer = entry.game.manufacturer;
const year = entry.game.year;
const authors = entry.table.authors.join(', ');
const rating = entry.game.user.rating;
const plays = entry.game.user.play_count;
```

`game.name` is display-ready — a user-set alternate title has already replaced it, and a
leading "The " has already moved to the end so themes sort by the second word.

### Play stats

`game.user` counts the machine; `table.user` counts one `.vpx` of it. They accumulate
independently, so deleting a table does not un-play the game's hours.

```javascript
const { play_count, play_time_seconds, last_played } = entry.game.user;

const hours = Math.round(play_time_seconds / 360) / 10;
const lastPlayed = last_played ? new Date(last_played).toLocaleDateString() : 'Never';
```

Durations name their unit and timestamps are ISO 8601 UTC, whatever the `.info` happens to
store.

### Feature indicators

```javascript
const { detects } = vpin.getTableMeta(currentGameIndex).table;
const { alt_sound, alt_color, pup_pack } = vpin.getTableMeta(currentGameIndex).assets;

const lights = [
    ['Nfozzy', detects.nfozzy], ['Fleep', detects.fleep], ['SSF', detects.ssf],
    ['FastFlips', detects.fastflips], ['LUT', detects.lut],
    ['Scorbit', detects.scorbit], ['FlexDMD', detects.flex],
    ['PinMAME', detects.pinmame],
    ['AltSound', alt_sound], ['AltColor', alt_color], ['PuP-Pack', pup_pack],
];

lights.forEach(([label, on]) => {
    // Real booleans, so no coercion. `detects` describes the .vpx, `assets` the folder.
});
```

### Media

`entry.media` names the kinds this game has a file for. It does not carry paths — request
one from the asset server, the same one your theme was loaded from:

```javascript
const entry = vpin.getTableMeta(currentGameIndex);

function mediaURL(kind) {
    if (!entry.media.includes(kind)) return null;
    return `${vpin.endpoints.assets}/media/${entry.table.id}/${kind}`;
}

const playfield = mediaURL('playfield_video') || mediaURL('playfield');
if (playfield) showMedia(playfield);
```

Checking `media` first is what tells you whether to show a video, an image, or nothing —
there is no request to make and no placeholder to detect. Responses carry an `ETag` and
ask to be revalidated, so replacing art in the Manager UI shows up without a hard refresh.

`vpin.getMedia(index, kind)`, `getImageURL` and `getVideoURL` still work and still honor
the user's media priority. Use them when you want that behavior; use `media` when you want
to know what exists.

### A game's other tables

`siblings` is how many tables the entry's game offers. `1` means there is nothing to
switch to, which is the common case — so a "other versions" affordance can hide itself
without asking the backend anything:

```javascript
const entry = vpin.getTableMeta(currentGameIndex);
if (entry.siblings > 1) {
    showVersionBadge(`${entry.siblings} versions`);
}
```

Whether a game contributes one entry or all of its tables is the user's `expanded` setting,
read as `vpin.expanded`. A theme does not have to do anything differently either way.

### VPinPlay Rating

`vpinfe-core.js` can fetch the selected game's VPinPlay cumulative rating from the configured `vpinplay.apiendpoint`.

| Method | Returns | Description |
|--------|---------|-------------|
| `await vpin.getVPinPlayRating(index?)` | `object\|null` | Returns the cached rating for the table or fetches it from VPinPlay. |
| `await vpin.refreshVPinPlayRating(index?)` | `object\|null` | Forces a fresh fetch from VPinPlay. |
| `vpin.getCachedVPinPlayRating(index?)` | `object\|null` | Returns only the cached value already attached to the table. |

The returned object matches the API payload shape and is also stored on the table entry as `table.vpinplay`:

```javascript
const table = vpin.getTableMeta(currentGameIndex);
const rating = table.vpinplay?.cumulativeRating ?? null;
const votes = table.vpinplay?.ratingCount ?? 0;
```

---

## Media Files

Media lives in a game's folder, in `medias/` or at the folder root. `medias/` is canonical
and the root is the fallback, at every tier below.

### The kinds

Twenty. `entry.media` lists the ones a game has a file for, using exactly these names, and
`/media/<table id>/<kind>` serves one.

| Kind | Default filename | Spec token | Also accepted |
|---|---|---|---|
| `playfield` | `table.png` | `(Playfield)` | |
| `playfield_fss` | `fss.png` | `(FSS)` | |
| `bg` | `bg.png` | `(Backglass)` | |
| `dmd` | `dmd.png` | `(DMD)` | |
| `wheel` | `wheel.png` | `(Wheel)` | |
| `logo` | `logo.png` | `(Logo)` | |
| `cab` | `cab.png` | `(Cabinet)` | |
| `flyer` | `flyer.png` | `(Flyer)` | `(GameInfo)` |
| `instruction_card` | `instructioncard.png` | `(InstructionCard)` | `(RuleCard)`, `(GameHelp)` |
| `topper` | `topper.png` | `(Topper)` | |
| `real_dmd` | `realdmd.png` | `(RealDMD)` | |
| `real_dmd_color` | `realdmd-color.png` | `(RealColorDMD)` | |
| `playfield_video` | `table.mp4` | `(Playfield)` | |
| `bg_video` | `bg.mp4` | `(Backglass)` | |
| `dmd_video` | `dmd.mp4` | `(DMD)` | |
| `topper_video` | `topper.mp4` | `(Topper)` | |
| `loading` | `loading.mp4` | `(Loading)` | |
| `audio` | `audio.mp3` | `(Audio)` | |
| `audio_launch` | `audiolaunch.mp3` | `(AudioLaunch)` | |
| `rule_sheet` | `rulesheet.pdf` | `(RuleSheet)` | |

`wheel` falls back to `logo` when the game has no wheel of its own. A game set to
full-single-screen serves `fss.png` as its `playfield` — the filename changes, the kind
name does not.

### How a file is chosen

Three tiers per kind, most specific first:

1. `(Token) <table stem>.<ext>` — art for one `.vpx`
2. `(Token) <folder name>.<ext>` — shared by every table in the folder
3. the default filename — what VPinMediaDB writes

```
Attack from Mars (Bally 1995)/
├── medias/
│   ├── (Wheel) Attack from Mars VR.png   tier 1 - only the VR table
│   ├── (Wheel) Attack from Mars.png      tier 2 - the folder's tables
│   ├── wheel.png                         tier 3 - the default
│   ├── table.png
│   ├── bg.png
│   └── audio.mp3
├── Attack from Mars.vpx
└── Attack from Mars VR.vpx
```

Within a tier the kind's extension family is tried in order, first hit wins:

| Family | Extensions |
|---|---|
| image | `.png` `.jpg` `.jpeg` `.webp` `.bmp` `.gif` |
| video | `.mp4` |
| audio | `.mp3` `.ogg` |
| document | `.pdf` `.md` `.txt` `.html` |

Matching is case-insensitive. A hand-placed `wheel.jpg` resolves; it does not have to be a
`.png`.

### Wheel sets

`wheel` supports named sets — a folder of alternate wheel art under
`medias/wheels/<set>/`. When a set is active it slots between tiers 1 and 2, so a
table-specific wheel still wins and a media refresh never beats the set. A theme picks the
set it wants with `wheelSet` in its `theme.json`.

### Shared assets

Manufacturer logos are art about the manufacturer, not about a game, so they live under
`/assets/` and are not a media kind. `vpin.getManufacturerLogoURL(index)` returns one, and
`entry.game.manufacturer_logo` carries the web path.

### Reaching media from a theme

Two ways, and they answer different questions.

`entry.media` tells you **what exists**, with no request:

```javascript
const entry = vpin.getTableMeta(currentGameIndex);
const url = (kind) => entry.media.includes(kind)
    ? `${vpin.endpoints.assets}/media/${entry.table.id}/${kind}`
    : null;

showMedia(url('playfield_video') || url('playfield'));
```

`vpin.getMedia(index, kind)` **resolves what to show**, honoring the user's Manager UI
media priority and falling back on its own:

```javascript
const media = vpin.getMedia(currentGameIndex, 'playfield');
// media.kind is "video", "image", or "missing"; media.url is always something to put in src
```

Use the first when your theme decides; use the second when the user's priority should.

## Video Support

Themes can display looping videos for table, backglass, and DMD screens in addition to (or instead of) static images.

For new themes, prefer `vpin.getMedia(index, kind)` or `vpin.getMediaURL(index, kind)` when you want to honor the user's Manager UI media priority. The default priority is video for table, backglass, and DMD media, and colorized for Real DMD frames. If the preferred file is missing, VPinFE automatically falls back to the available alternate.

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
- You can check `vpin.tableData[index].PlayfieldVideoPath` directly to decide whether to create a video or image element.

---

## Audio Support

VPinFECore now includes a centralized per-game audio manager. Theme code can use it directly and no longer needs to implement its own `Audio`/fade/retry logic.

### Audio File

Place an `audio.mp3` file in the table's `medias/` folder (or root folder). `vpin.getAudioURL(index)` returns the URL, or `null` if no audio file exists.

### Core Behavior

On the controller, `await vpin.handleEvent(message)` automatically manages audio transitions when core audio is enabled.

Core audio is opt-in by default. If your theme does not explicitly enable it (or call `vpin.enableCoreAudio(true)` at runtime), no automatic game audio playback will occur.

When enabled, these transitions are handled automatically:
- `TableIndexUpdate` -> play selected game audio
- `TableLaunching` and `RemoteLaunching` -> fade/stop audio
- `TableLaunchComplete` and `RemoteLaunchComplete` -> resume audio for current selection
- `TableDataChange` (with `index`) -> play audio for that index

### Backend vs Frontend Responsibility

`api.py` knows when table launch starts/completes and emits lifecycle events, but it does not own the browser `Audio` object. Actual playback, fading, retries, and autoplay-policy handling must run in frontend JavaScript (`VPinFECore`/theme code), which owns the in-memory audio state.

### Practical Note: Self-Event Caveat

`vpin.sendMessageToAllWindows(...)` excludes the sender. If your playfield window sends `TableLaunching`, it might not receive that same event back, so backend-emitted lifecycle events are the reliable source of truth for launch state.

For robust behavior, it is valid to also call:
- `vpin.stopTableAudio()` directly in your local `joyselect`/launch path
- `vpin.playTableAudio(currentGameIndex)` directly on local launch-complete handling

This explicit local stop/resume acts as a safety net while still using centralized core audio.

Defaults:
- volume: `0.8`
- fade duration: `500ms`
- loop: `true`

### Usage in Your Theme

```javascript
function updateScreen() {
    // ... update images, carousel, etc ...
    if (vpin.isController()) {
        vpin.playTableAudio(currentGameIndex);
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
      "description": "Show the clock overlay in the playfield window.",
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
      "description": "Show a clock overlay on the playfield screen.",
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
