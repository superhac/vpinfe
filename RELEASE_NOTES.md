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
- `--reset-3x-state` keeps a copy of your device list before removing it, named in what it
  reports. A phone you added by hand is not something any install re-announces, so it is the
  one thing there that could not be rebuilt.
- To take 3.0 back off entirely, `--reset-3x-state` removes the settings and collections
  files 3.0 wrote, the `.info` files it made and every backup it kept, so the next start
  migrates from scratch. Settings you changed under 3.0 are lost, and so is any rating or
  play count on a table 3.0 added. It refuses while VPinFE is running; `--dry-run` lists
  what would go, and `--config-only` leaves the library alone.
- **The API has no authentication, and it answers on every interface.** Anything that can
  reach the port can read your library, change settings, upload files and launch tables.
  That is how VPinFE has always worked and 3.0 does not change it — but 3.0 is the release
  that makes the API worth building against, so it is worth saying plainly: run it on a
  network you trust, and do not forward the port to the internet. Set `network.hub_bind`
  to `127.0.0.1` to keep it on the machine itself, at the cost of the remote and mobile
  pages working from other devices.

### What's New
- **Core** — VPinFE can ask before it quits or powers off the machine. Off by default,
  which is how it has always behaved; tick Confirm Before Exit on the Frontend settings
  page, or set `[frontend] confirm`. Closing the frontend never asks — those windows reopen
  from the Manager UI, so there is nothing to lose. The question appears on whatever you
  used to ask — the cabinet asks on the cabinet, the remote page asks on your phone — and
  every other screen is told what is about to happen rather than left to go dark without
  explanation.
- **Frontend** — Back at the wheel's root leaves, down the same path the exit action takes,
  so it asks when you have asked to be asked rather than becoming a second way out that
  never does. Themes that have not moved to 3.0 keep `back` as their own action, and inside
  a dialog or a text field it still means dismiss.
- **Frontend** — A page press moves by the groups in whatever the list is ordered by: the
  next letter under title order, the next year under year order. Orders where every table
  has a value of its own — last played, date added, play count — have no groups, so a press
  moves a fixed number instead. `[frontend] paging_group` picks which (`sort` or `count`),
  `[frontend] paging_size` says how far a `count` jump goes, and a collection can override
  both for itself. The 2.x spellings `alpha` and `numeric` still resolve.
- **Core, Themes** — A theme declares the oldest VPinFE it runs on, as `min_vpinfe` in its
  `manifest.json`. Installing one that needs a newer build than yours is refused before
  anything downloads, and the message names the version it wants.
- **Core** — What a theme or an overlay throws now reaches `vpinfe.log`, tagged with the
  window it came from and the overlay if that is what threw. A Chromium console goes
  nowhere anyone reads on a cabinet, so a theme that broke looked like a frontend that had
  stopped answering the buttons.
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
  (`[general] assets_dir`, default `assets/` under the config dir) at `/assets/`. Nothing
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
- **Manager UI** — A second interface, the Console, at `/console`. It is the control
  plane: one place for the library, media, devices and settings, with a table grid that
  can draw art in a column instead of a tick, and a media map laid out like a pinball
  machine so a game's coverage reads before any label does. Column layouts are kept on the
  hub, so they follow you between machines. It ships beside the Manager UI, not instead of
  it — the Manager UI is still the complete one, and parts of the Hub UI are unfinished.
- **Core** — A hub keeps a list of the devices it serves. An install pointed at a hub with
  `network.hub_url` announces itself on startup, and the hub records what it said and when
  it last said it, so an event carrying an id turns into a name someone recognizes. A
  device on your phone can be in that list too, added by hand — several of them, which the
  single `[mobile]` address could never express. Your existing one is imported on the first
  start.
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
- **Core** — The two roles an install can serve are `hub` and `device`. If you set
  `[install] roles` on a 3.0 preview build, change `player` to `device` — an unrecognised
  role is ignored, so the install would report only the half it still recognises. Nothing
  else reads it, and a config that never set it is unaffected.
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
- **Manager UI** — Paging and Confirm Before Exit sit on the Frontend settings page now,
  rather than under General and Additional Input Settings. They say what the frontend does
  when a button is pressed, which is a different question from which button does what. The
  ini keys you already have are still read.

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
- **Manager UI** — Editing an input binding and nothing else now offers a Save button. The
  binding fields are kept apart from the rest and the save bar was not watching them.
- **Frontend** — Core takes the wheel's previous and next only from a theme that says it
  runs on 3.0. Revolution, Trinidad and carousel-desktop drive their own collection list
  with those two actions, and core was consuming the press first, so their picker exited
  onto an unrelated table. A theme that wants core navigation without declaring 3.0 sets
  `navigation.enabled` in its `theme.json`.

### For theme and API authors
- **Themes** — The selection surface keeps the names 2.x published: `get_tables`,
  `launch_table`, `TableIndexUpdate`, `vpin.tableData` and the rest. A row on the wheel is
  a table — a collection may hold two tables of one game, and both are rows — so these went
  back after an earlier 3.0 build renamed them.
- **Themes** — `min_vpinfe` in `manifest.json` replaces naming a contract number. Declaring
  nothing still means the 2.x payload shape.
- **Themes** — Core owns the wheel's list and cursor, and the menus run on the same one, so
  a theme can open the collection picker and let core apply the choice and announce it.
  `vpin.enableCorePaging(false)` still hands paging back to you.
- **Themes** — Core's files are served at `/core/` now, against `/themes/` for what a theme
  provides. Your existing theme keeps working: `/web/` still serves the same files, so there
  is nothing to change unless you want to.
- **Themes** — Nothing changes unless you opt in. The payload is served in the shape your
  `manifest.json` declares as `contract`, and no declaration means the 2.x shape.
- **Themes** — The paging actions are `page_previous` and `page_next`, not `page_up` and
  `page_down`. `page up` had no answer on a horizontal wheel and core gave two, so two
  themes shipped paging that ran backwards. A contract 1 theme still receives
  `joypageup`/`joypagedown`.
- **Themes** — `vpin.endpoints.player` is `vpin.endpoints.device`, and the window url
  carries `devicePort` rather than `playerPort`. It is the address of the machine a game
  launches on — this one — as against `endpoints.hub`, which is where the library lives.
  A theme that never read it is unaffected; one that did reads a different key and gets no
  error if it does not, so it is worth checking.
- **Core** — Breaking: `/api/v1/players` is `/api/v1/devices`, its scopes are
  `devices:read` and `devices:write`, and a capability's residency says `device` where it
  said `player`. A device is something a game can be launched on and played; a player is a
  person, and every pinball machine ever built prints PLAYER 1 on its display.
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
