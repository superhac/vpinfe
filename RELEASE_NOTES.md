## VPinFE Release Notes

### Summary
vpinfe v3.0-beta.1. First preview of the 3.0 line: a stable id for every table, a
documented HTTP API at `/api/v1`, media that resolves the way the rest of the hobby names
it, and support for table folders holding more than one playable file. This is a preview
build and it changes how your library is stored — read the next section first.

### Before you upgrade
- **Install v2.6.0 first, even if you plan to stay on 3.0.** If you go back, only v2.6.0
  or newer knows how to put 3.0's backups back. Earlier releases do not look for them.
- First start rewrites every table's `.info` and your `collections.ini`. The original of
  each `.info` is kept beside it as `<Table>.info.vpinfe-<timestamp>` and collections are
  backed up the same way. Expect a burst of writes on first start and nothing after.
- To undo it: the Tables page offers a restore when it finds backups, or run
  `--restore-info`.
- **The API has no authentication, and it answers on every interface.** Anything that can
  reach the port can read your library, change settings, upload files and launch tables.
  That is how VPinFE has always worked and 3.0 does not change it — but 3.0 is the release
  that makes the API worth building against, so it is worth saying plainly: run it on a
  network you trust, and do not forward the port to the internet. Set `network.hub_bind`
  to `127.0.0.1` to keep it on the machine itself, at the cost of the remote and mobile
  pages working from other devices.

### What's New
- **Core** — VPinFE can ask before it quits, restarts or powers off the machine. Off by
  default, which is how it has always behaved; set `lifecycle.confirm` to the scopes you
  want checked. The question appears on whatever you used to ask — the cabinet asks on the
  cabinet, the remote page asks on your phone — and every other screen is told what is about
  to happen rather than left to go dark without explanation.
- **Core** — Every table gets a stable id, minted once and kept in its `.info`. It survives
  renaming a folder and updating a `.vpx`, which VPSId does not. Collection membership is
  keyed by it now, so an ordinary table update no longer orphans a table out of its
  collections.
- **Core** — An HTTP API at `/api/v1` with a written contract: table catalog, launch, media,
  assets, collections, uploads, VPS search and export, one error envelope, permission
  scopes on every endpoint. Documented in `docs/`.
- **Core** — A live event stream at `/api/v1/events`. The frontend subscribes to launch
  state instead of asking for it once a second.
- **Core, Frontend** — A table folder can hold several playable files. A desktop build and a
  VR build, or a table and a patched variant, are peers — each launches on its own, and any
  of them can be hidden so it stops being offered.
- **Core** — Apply `.dif` patches directly, with no external tool. The base file stays on
  disk because the patched table cannot be rebuilt without it, and VPinFE records which
  base and which patch produced the result.
- **Core, Themes** — Six new media kinds: instruction card, topper, topper video, loading
  video, launch audio and rulesheet. Topper image and topper video are separate kinds now, so a
  cabinet can hold both instead of one shadowing the other.
- **Core, Themes** — `logo` is its own media kind. A table with a logo and no wheel shows
  the logo wherever the wheel would appear — themes, Manager UI and API alike.
- **Core** — Media resolves through a precedence chain and accepts extension families:
  `(Wheel) <game file>.png` over `(Wheel) <folder>.png` over `wheel.png`, and a `.jpg`
  where the old code only ever looked for one exact `.png`. Art you placed by hand that was
  silently ignored now shows up. The token in brackets names the kind — Visual Pinball
  publishes the list, and VPinFE reads it. Two are named for what they are rather than what
  Visual Pinball calls them: use `(InstructionCard)` and `(Flyer)` if you are naming files
  yourself, and `(GameHelp)` and `(GameInfo)` keep working if your media came that way.
- **Core, Themes** — Wheel sets, chosen in the ini or by the theme.
- **Core, Themes** — Manufacturer logos, served from a shared assets root
  (`[Settings] assetsdir`, default `assets/` under the config dir) at `/assets/`. Nothing
  ships or downloads yet, so today it is a slot for themes to fill.
- **Manager UI, Core** — A table export is one game, not the whole folder: the chosen
  `.vpx`, its companions, `pinmame/`, `music/`, colorization and sound folders and the
  author's readme files. Transfers shrink a lot, and a multi-`.vpx` folder finally exports
  the game you meant. Whole-folder export is still available through the API.
- **Manager UI** — Readme and `.nfo` files are recognized on import, shown inline before
  anything is written, copied into the table folder, and included in the export. Whoever
  made the table wrote those notes for whoever installs it.
- **Core** — ROM sets are audited through the VPX install's own PinMAME, and VPinFE can tell
  whether a table's script drives PinMAME at all.
- **Core, Manager UI** — Slow work runs in the background and reports progress on the event
  bus instead of blocking the page that started it.
- **Manager UI** — The Tables page says when the library has been upgraded and where to undo
  it, and can upgrade or restore table info for the whole library in one pass.

### Changes you may notice
These are deliberate. `docs/compatibility-3.0.md` has the full list with the reasoning.

- **Frontend** — A folder with several `.vpx` files may launch a different one than before.
  VPinFE now picks the file the table's own metadata describes; it used to take whatever
  the filesystem listed first, so the metadata you saw could describe a different table
  than the one that started.
- **Core** — Launches from the Remote page and the API count as plays now. Start count, last
  played, runtime and NVRAM score were only ever recorded for wheel launches.
- **Core** — Tables whose folders are not all lowercase start reporting the PUP packs,
  colorizations, VNI and altsound they always had. The scan compared folder names exactly,
  so `PUPVideos` — the casing PinUP Popper itself writes — went undetected.
- **Core** — Your own media is protected by hash rather than by claiming it. Any file
  already on disk is compared against the MD5 VPinMediaDB publishes; a match is ours, and
  anything else is left alone. That covers art you never got around to claiming, and art of
  ours you later replaced. `--claim-user-media` does nothing now, and the "Use my own media"
  toggle is gone.
- **Core** — Imported media keeps its real extension. A `.jpg` wheel is written as
  `wheel.jpg` instead of JPEG bytes inside a file called `wheel.png`.
- **Core** — The log is much quieter at INFO. Routine chatter moved to DEBUG.
- **Frontend** — Page-up moves the wheel backward now, and page-down forward. The keys are
  unchanged; what they mean is. Page-up was the odd one out — the same key already moved
  *up* a menu — and the two paging actions are named `page_previous` and `page_next` for it.
  Swap the two values under `[input]` if you prefer the old feel. If you ran a 3.0
  development build and customized a paging binding, set it again — `page_up` and
  `page_down` are no longer read as config keys.

### Fixes
- **Frontend** — Tables no longer start paused on Windows. VPX pauses whenever its window
  loses focus, and Windows will not let one program hand the foreground to another it
  started, so a table came up paused until you alt-tabbed. The frontend windows now get out
  of the way and come back when you are done.
- **Frontend** — Holding a direction no longer freezes the wheel.
- **Frontend** — Chromium no longer leaves a profile directory behind for every window on
  every launch. On a cabinet where `/tmp` is a tmpfs, that was RAM.
- **Core** — A `.info` is written through a temporary file and renamed into place, so an
  interrupted write cannot leave a truncated one behind.
- **Core** — One unreadable `.info` no longer stops the whole library from loading. That
  table is left out and named in the log, and its file is not touched.
- **Manager UI** — Remote launch failures are logged instead of failing silently, and a
  remote launch no longer raises on Linux.

### For theme and API authors
- **Themes** — Core's files are served at `/core/` now, against `/themes/` for what a theme
  provides. Your existing theme keeps working: `/web/` still serves the same files, so there
  is nothing to change unless you want to.
- **Themes** — Nothing changes unless you opt in. The payload is served in the shape your
  `manifest.json` declares as `contract`, and no declaration means the 2.x shape.
- **Themes** — The paging actions are `page_previous` and `page_next`, not `page_up` and
  `page_down`. `page up` had no answer on a horizontal wheel and core gave two, so two
  themes shipped paging that ran backwards. A contract 1 theme still receives
  `joypageup`/`joypagedown`.
- **Core** — Breaking: the endpoints that predate `/api/v1` are removed, not aliased.
  `/api/remote-launch`, `/api/asset-upload/*` and `/api/download-table-vpxz` are gone and
  their replacements live under `/api/v1`.
- **Core** — Breaking: the WS bridge method `update_frontend_dof_for_table` is now
  `notify_table_selected`. It drove DOF and the real DMD both, so the old name was wrong.
- **Core** — The `.info` is reshaped: `VPXFile` becomes `game_files` with one entry per
  `.vpx`, `Medias` becomes `assets`, the `VPinFE` section becomes `vpinfe` with snake_case
  keys, and `Info` gives up `Rom` and `Authors` to the game file that owns them.

### Notes
This is a beta. Back up your library before you run it, keep a v2.6.0 build to hand, and
report what breaks.
