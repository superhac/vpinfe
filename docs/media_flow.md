# Media Flow

This document explains how per-table images, videos, and audio move from the filesystem into a VPinFE theme.

## Overview

Themes do not receive image or video bytes directly over the WebSocket bridge. Instead, the backend sends media file paths as part of the table metadata payload, and `vpinfe-core.js` converts those filesystem paths into HTTP URLs that theme code can use in `<img>`, `<video>`, and `<audio>` elements.

High-level flow:

1. `common/tableparser.py` scans each table folder for standard media filenames.
2. `frontend/api.py` includes the discovered file paths in the table JSON returned to the browser.
3. `web/common/vpinfe-core.js` stores that table data in `this.tableData`.
4. Theme code calls helper methods such as `vpin.getImageURL(index, type)` or `vpin.getVideoURL(index, type)`.
5. `vpinfe-core.js` converts the local path into a URL under `/tables/...`.
6. The local HTTP server serves the file to the theme.

## Media Discovery

`common/tableparser.py` checks the table's `medias/` subfolder first, then falls back to the table root folder.

Standard filenames include:

- Images: `table.png`, `fss.png`, `bg.png`, `dmd.png`, `wheel.png`, `cab.png`, `realdmd.png`, `realdmd-color.png`, `flyer.png`
- Videos: `table.mp4`, `fss.mp4`, `bg.mp4`, `dmd.mp4`
- Audio: `audio.mp3`

Relevant code:

- [common/tableparser.py](/home/superhac/repos/testing/vpinfe/common/tableparser.py#L67)

## Backend To Browser Payload

When the browser requests table data, `frontend/api.py` serializes the discovered media paths into each table entry. These are plain string paths such as:

- `TableImagePath`
- `BGImagePath`
- `DMDImagePath`
- `TableVideoPath`
- `BGVideoPath`
- `DMDVideoPath`
- `AudioPath`

Relevant code:

- [frontend/api.py](/home/superhac/repos/testing/vpinfe/frontend/api.py#L254)

## Theme Access In vpinfe-core.js

After loading the table JSON, `vpinfe-core.js` exposes helper methods for themes:

- `vpin.getImageURL(index, type)`
- `vpin.getVideoURL(index, type)`
- `vpin.getAudioURL(index)`
- `vpin.getTableMeta(index)`

Relevant code:

- [web/common/vpinfe-core.js](/home/superhac/repos/testing/vpinfe/web/common/vpinfe-core.js#L123)
- [web/common/vpinfe-core.js](/home/superhac/repos/testing/vpinfe/web/common/vpinfe-core.js#L262)
- [web/common/vpinfe-core.js](/home/superhac/repos/testing/vpinfe/web/common/vpinfe-core.js#L325)

## URL Conversion

`vpinfe-core.js` converts a local media path into a URL that points at the built-in HTTP server.

Examples:

- `/tables/Addams Family/medias/dmd.mp4`
- `http://127.0.0.1:<themeassetsport>/tables/Addams%20Family/medias/dmd.mp4`

If the file lives directly in the table folder instead of `medias/`, the URL becomes:

- `http://127.0.0.1:<themeassetsport>/tables/<tableDir>/<file>`

Relevant code:

- [web/common/vpinfe-core.js](/home/superhac/repos/testing/vpinfe/web/common/vpinfe-core.js#L794)

The HTTP server mount that makes this work is configured here:

- [main.py](/home/superhac/repos/testing/vpinfe/main.py#L202)

## DMD Video Flow

For `dmd.mp4` support specifically, the key flow is:

- [common/tableparser.py](/home/superhac/repos/testing/vpinfe/common/tableparser.py#L85)
- [frontend/api.py](/home/superhac/repos/testing/vpinfe/frontend/api.py#L269)
- [web/common/vpinfe-core.js](/home/superhac/repos/testing/vpinfe/web/common/vpinfe-core.js#L271)
- [web/common/vpinfe-core.js](/home/superhac/repos/testing/vpinfe/web/common/vpinfe-core.js#L808)

That means:

1. `common/tableparser.py` finds `dmd.mp4` and stores it as `DMDVideoPath`.
2. `frontend/api.py` includes `DMDVideoPath` in the table payload.
3. `vpin.getVideoURL(index, "dmd")` reads `table.DMDVideoPath`.
4. `#convertPathToURL()` maps that path to `http://127.0.0.1:<port>/tables/<table>/medias/dmd.mp4`.

## Theme Pattern: Prefer dmd.mp4, Fall Back To dmd.png

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

## Events And Refresh Behavior

Media is not pushed into the theme as binary event data. Instead, events tell the theme that table state changed, and the theme should refresh its media URLs for the new table index.

Common cases:

- `TableIndexUpdate`
- `TableDataChange`

Relevant code:

- [web/common/vpinfe-core.js](/home/superhac/repos/testing/vpinfe/web/common/vpinfe-core.js#L351)

In practice, when a new table becomes active, theme code should:

1. Read the current index.
2. Call `getImageURL()` and `getVideoURL()` again.
3. Update the DOM elements for that screen.
