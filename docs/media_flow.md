# Media Flow

This document explains how per-game images, videos, and audio move from the filesystem into a VPinFE theme.

## Overview

Themes do not receive image or video bytes directly over the WebSocket bridge. Instead, the backend sends media file paths as part of the game metadata payload, and `vpinfe-core.js` converts those filesystem paths into HTTP URLs that theme code can use in `<img>`, `<video>`, and `<audio>` elements.

High-level flow:

1. `common/games/game_parser.py` scans each game folder for standard media filenames.
2. `frontend/api.py` includes the discovered file paths in the game JSON returned to the browser.
3. `frontend/static/common/vpinfe-core.js` stores that game data in `this.tableData`.
4. Theme code calls helper methods such as `vpin.getImageURL(index, type)` or `vpin.getVideoURL(index, type)`.
5. `vpinfe-core.js` converts the local path into a URL under `/games/...`.
6. The local HTTP server serves the file to the theme.

## Media Discovery

`common/games/game_parser.py` checks the game's `medias/` subfolder first, then falls back to the game folder root.

Standard filenames include:

- Images: `table.png`, `fss.png`, `bg.png`, `dmd.png`, `wheel.png`, `logo.png`, `cab.png`, `realdmd.png`, `realdmd-color.png`, `flyer.png`, `instructioncard.png`, `topper.png`
- Videos: `table.mp4`, `fss.mp4`, `bg.mp4`, `dmd.mp4`, `topper.mp4`, `loading.mp4`
- Audio: `audio.mp3`, `audiolaunch.mp3`
- Documents: `rulesheet.pdf`

Each kind also accepts the rest of its extension family (for images: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.gif`), and spec-named files outrank the fixed names: `(Wheel) <table name>.png` beats `(Wheel) <folder name>.png` beats `wheel.png`. The full precedence rules live in `common/media_specs.py`.

### Media tokens

The token in brackets names the kind. Visual Pinball publishes these in its own [FileLayout.md](https://github.com/vpinball/vpinball/blob/master/docs/FileLayout.md), under "Zero install table deployment guidelines", and VPinFE reads them:

| Kind | Token | Kind | Token |
|---|---|---|---|
| Playfield | `(Playfield)` | Wheel | `(Wheel)` |
| Backglass | `(Backglass)` | Logo | `(Logo)` |
| DMD | `(DMD)` | Instruction card | `(InstructionCard)` |
| Real DMD | `(RealDMD)` | Game flyer | `(Flyer)` |
| Real color DMD | `(RealColorDMD)` | Rulesheet | `(RuleSheet)` |
| Topper | `(Topper)` | Loading video | `(Loading)` |
| Cabinet | `(Cabinet)` | Audio | `(Audio)` |
| FSS | `(FSS)` | Launch audio | `(AudioLaunch)` |

A video uses its image counterpart's token and is told apart by extension, so `(Topper) Name.png` and `(Topper) Name.mp4` are different kinds.

Two of these differ from the published names. Visual Pinball calls the instruction card `(GameHelp)` and the game flyer `(GameInfo)`; VPinFE leads with `(InstructionCard)` and `(Flyer)` because they say what the file is, and **still accepts `(GameHelp)` and `(GameInfo)`** so media packaged either way works. `(RuleCard)`, which VPinFE recommended earlier in 3.0 development, is accepted too. If both are present the preferred name wins, but a table-specific file always beats a folder-level one whichever token it uses. `(Cabinet)`, `(FSS)`, `(Logo)` and `(RuleSheet)` have no published equivalent and are VPinFE's own.

The playfield is one kind with two variants. `playfield` resolves `table.png` or `fss.png` depending on `[Media] playfieldvariant`; `playfield_fss` is the FSS render on its own, addressable whichever variant is active, and is what the playfield falls back to when it has no render of its own. Full Single Screen is a Visual Pinball view mode, so an `fss.png` is the same subject as a `table.png` photographed differently - not a separate kind.

### Manufacturer logos

Manufacturer logos are not per-game media: they live in a shared assets root (`[Settings] assetsdir`, defaulting to `assets/` under the config dir) served at `/assets/`. Files in `manufacturers/user/` win over a pack in `manufacturers/default/`; lookup normalizes the game's `Info.Manufacturer` string (so "Williams Electronics" finds `williams.png`) with a `manufacturers.json` alias map for exceptions. The game payload carries the result as `ManufacturerLogoPath`, and themes call `vpin.getManufacturerLogoURL(index)`.

You never have to guess a filename: VPinFE generates `manufacturers/manufacturers-reference.json` from VPSdb (refreshed at startup and on every VPSdb sync) listing every known manufacturer with its computed slug, the alias currently applied, and the logo that resolves — `logo: null` rows are what's missing. The same data is served at `GET /api/v1/manufacturers`, with per-manufacturer library game counts. To supply your own logo, either name the file after the slug shown there and drop it in `manufacturers/user/`, or name it however you like and add one line to `manufacturers/user/manufacturers.json` (`{"Premier Technology": "my-file-stem"}`). Alias map keys accept the full name or its slug; values are file stems; empty values are ignored; user aliases override a pack's.

### Wheel sets

A game can carry alternate wheel art in named folders under `medias/wheels/<set name>/`, each set resolving through the same precedence chain. The active set is `[Media] wheelset` in `vpinfe.ini`, which the active theme may override through a `wheelSet` option (see [theme.md](theme.md)). The reserved set name `logo` fills the wheel slot from the game's logo instead of a wheels folder. A spec-named wheel the user placed always beats the active set, and a game with no art for the set keeps its plain wheel.

Relevant code:

- [common/games/game_parser.py](../common/games/game_parser.py)

## Backend To Browser Payload

When the browser requests game data, `frontend/api.py` serializes the discovered media paths into each game entry. These are plain string paths such as:

- `PlayfieldImagePath`
- `BGImagePath`
- `DMDImagePath`
- `PlayfieldVideoPath`
- `BGVideoPath`
- `DMDVideoPath`
- `AudioPath`

Relevant code:

- [frontend/api.py](../frontend/api.py)

## Theme Access In vpinfe-core.js

After loading the game JSON, `vpinfe-core.js` exposes helper methods for themes:

- `vpin.getImageURL(index, type)`
- `vpin.getVideoURL(index, type)`
- `vpin.getAudioURL(index)`
- `vpin.getTableMeta(index)`

Relevant code:

- [frontend/static/common/vpinfe-core.js](../frontend/static/common/vpinfe-core.js)
- [frontend/static/common/vpinfe-core.js](../frontend/static/common/vpinfe-core.js)
- [frontend/static/common/vpinfe-core.js](../frontend/static/common/vpinfe-core.js)

## URL Conversion

`vpinfe-core.js` converts a local media path into a URL that points at the built-in HTTP server.

Examples:

- `/games/Addams Family/medias/dmd.mp4`
- `http://127.0.0.1:<themeassetsport>/tables/Addams%20Family/medias/dmd.mp4`

If the file lives directly in the game folder instead of `medias/`, the URL becomes:

- `http://127.0.0.1:<themeassetsport>/tables/<gameDir>/<file>`

Relevant code:

- [frontend/static/common/vpinfe-core.js](../frontend/static/common/vpinfe-core.js)

The HTTP server mount that makes this work is configured here:

- [main.py](../main.py)

## DMD Video Flow

For `dmd.mp4` support specifically, the key flow is:

- [common/games/game_parser.py](../common/games/game_parser.py)
- [frontend/api.py](../frontend/api.py)
- [frontend/static/common/vpinfe-core.js](../frontend/static/common/vpinfe-core.js)
- [frontend/static/common/vpinfe-core.js](../frontend/static/common/vpinfe-core.js)

That means:

1. `common/games/game_parser.py` finds `dmd.mp4` and stores it as `DMDVideoPath`.
2. `frontend/api.py` includes `DMDVideoPath` in the game payload.
3. `vpin.getVideoURL(index, "dmd")` reads `game.DMDVideoPath`.
4. `#convertPathToURL()` maps that path to `http://127.0.0.1:<port>/tables/<game>/medias/dmd.mp4`.

## Playfield Video Flow

For playfield video support, the key flow is:

- [common/games/game_parser.py](../common/games/game_parser.py)
- [frontend/api.py](../frontend/api.py)
- [frontend/static/common/vpinfe-core.js](../frontend/static/common/vpinfe-core.js)
- [frontend/static/common/vpinfe-core.js](../frontend/static/common/vpinfe-core.js)

That means:

1. `common/games/game_parser.py` finds `table.mp4` or `fss.mp4` and stores it as `PlayfieldVideoPath`.
2. `frontend/api.py` includes `PlayfieldVideoPath` in the game payload.
3. `vpin.getVideoURL(index, "table")` reads `game.PlayfieldVideoPath`.
4. `#convertPathToURL()` maps that path to a `/tables/.../medias/<file>.mp4` URL.

## Backglass Video Flow

For `bg.mp4` support specifically, the key flow is:

- [common/games/game_parser.py](../common/games/game_parser.py)
- [frontend/api.py](../frontend/api.py)
- [frontend/static/common/vpinfe-core.js](../frontend/static/common/vpinfe-core.js)
- [frontend/static/common/vpinfe-core.js](../frontend/static/common/vpinfe-core.js)

That means:

1. `common/games/game_parser.py` finds `bg.mp4` and stores it as `BGVideoPath`.
2. `frontend/api.py` includes `BGVideoPath` in the game payload.
3. `vpin.getVideoURL(index, "bg")` reads `game.BGVideoPath`.
4. `#convertPathToURL()` maps that path to `http://127.0.0.1:<port>/tables/<game>/medias/bg.mp4`.

## Fallback Behavior

`vpinfe-core.js` does not automatically choose between video and image for a theme. It only exposes both URLs.

That means fallback behavior is the theme's responsibility:

- Playfield screen: prefer `table.mp4` or `fss.mp4`, fall back to `table.png` or `fss.png`
- BG screen: prefer `bg.mp4`, fall back to `bg.png`
- DMD screen: prefer `dmd.mp4`, fall back to `dmd.png`

If the theme only calls `vpin.getImageURL()`, it will remain image-only even when the matching video file exists.

If the theme uses `vpin.getVideoURL()`, it should check whether the returned URL is usable. When no video exists, `getVideoURL()` returns the fallback missing-file URL rather than `null`.

## Theme Pattern: Prefer Video, Fall Back To Image

Typical theme usage is to ask for both the video and image for a screen and then decide what to render.

```js
const index = vpin.getCurrentTableIndex();
const playfieldVideoUrl = vpin.getVideoURL(index, "table");
const playfieldImageUrl = vpin.getImageURL(index, "table");
const bgVideoUrl = vpin.getVideoURL(index, "bg");
const bgImageUrl = vpin.getImageURL(index, "bg");
const dmdVideoUrl = vpin.getVideoURL(index, "dmd");
const dmdImageUrl = vpin.getImageURL(index, "dmd");
```

### DMD Example

Typical theme usage is to ask for both the DMD video and DMD image and then decide what to render.

```js
const index = vpin.getCurrentTableIndex();
const dmdVideoUrl = vpin.getVideoURL(index, "dmd");
const dmdImageUrl = vpin.getImageURL(index, "dmd");
```

A practical pattern is:

```html
<div class="dmd-stage">
  <video id="dmd-video" muted autoplay loop playsinline hidden></video>
  <img id="dmd-image" alt="DMD preview">
</div>
```

```js
function updateDmdMedia(index) {
  const videoEl = document.getElementById("dmd-video");
  const imageEl = document.getElementById("dmd-image");

  const dmdVideoUrl = vpin.getVideoURL(index, "dmd");
  const dmdImageUrl = vpin.getImageURL(index, "dmd");

  videoEl.onerror = () => {
    videoEl.hidden = true;
    imageEl.hidden = false;
    imageEl.src = dmdImageUrl;
  };

  if (dmdVideoUrl && !dmdVideoUrl.endsWith("/file_missing.png")) {
    videoEl.src = dmdVideoUrl;
    videoEl.hidden = false;
    imageEl.hidden = true;
    videoEl.load();
  } else {
    videoEl.removeAttribute("src");
    videoEl.hidden = true;
    imageEl.hidden = false;
    imageEl.src = dmdImageUrl;
  }
}
```

### Reusable Pattern For Playfield, BG, And DMD

```js
function hasUsableMedia(url) {
  return Boolean(url) && !String(url).includes("file_missing");
}

function renderWindowMedia(container, imageUrl, videoUrl, altText) {
  const existingMedia = container.querySelector("video, img");
  const wantsVideo = hasUsableMedia(videoUrl);

  if (existingMedia) {
    if (existingMedia.tagName === "VIDEO") {
      existingMedia.pause();
      existingMedia.removeAttribute("src");
      existingMedia.load();
    }
    existingMedia.remove();
  }

  if (wantsVideo) {
    const video = document.createElement("video");
    video.src = videoUrl;
    video.poster = hasUsableMedia(imageUrl) ? imageUrl : "";
    video.autoplay = true;
    video.loop = true;
    video.muted = true;
    video.playsInline = true;
    video.onerror = () => {
      if (!hasUsableMedia(imageUrl)) return;
      const fallback = document.createElement("img");
      fallback.src = imageUrl;
      fallback.alt = altText;
      video.replaceWith(fallback);
    };
    container.appendChild(video);
    return;
  }

  const img = document.createElement("img");
  img.src = hasUsableMedia(imageUrl) ? imageUrl : "";
  img.alt = altText;
  container.appendChild(img);
}

function updatePlayfieldMedia(index) {
  const container = document.getElementById("playfield-root");
  renderWindowMedia(
    container,
    vpin.getImageURL(index, "table"),
    vpin.getVideoURL(index, "table"),
    "Playfield"
  );
}

function updateBgMedia(index) {
  const container = document.getElementById("bg-root");
  renderWindowMedia(
    container,
    vpin.getImageURL(index, "bg"),
    vpin.getVideoURL(index, "bg"),
    "Backglass"
  );
}

function updateDmdMedia(index) {
  const container = document.getElementById("dmd-root");
  renderWindowMedia(
    container,
    vpin.getImageURL(index, "dmd"),
    vpin.getVideoURL(index, "dmd"),
    "DMD"
  );
}
```

## Events And Refresh Behavior

Media is not pushed into the theme as binary event data. Instead, events tell the theme that game state changed, and the theme should refresh its media URLs for the new game index.

Common cases:

- `TableIndexUpdate`
- `TableDataChange`

Relevant code:

- [frontend/static/common/vpinfe-core.js](../frontend/static/common/vpinfe-core.js)

In practice, when a new game becomes active, theme code should:

1. Read the current index.
2. Call `getImageURL()` and `getVideoURL()` again.
3. Update the DOM elements for that screen.
