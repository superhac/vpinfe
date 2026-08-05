# 3.0 compatibility ledger

3.0 is plumbing and housekeeping; the goal for existing users is that they notice
nothing. This file is the complete list of deliberate exceptions — every way 3.0 is
*allowed* to differ from master, each with why it's worth it.

It is enforced, not aspirational: `tests/invariants/test_parity.py` compares this tree's
behavior against a captured master baseline (`tests/parity_baseline_master.json`),
and a difference is either named here by its `PAR-` id or the build fails. There is
no third option. Entries marked *(machine-checked)* are asserted directly by the
parity test; the others are covered by the tests referenced in their entry.

To refresh the baseline after master moves:

```
git worktree add /tmp/parity-master master
cd /tmp/parity-master && python <this-tree>/tests/support/parity_capture.py --out <this-tree>/tests/parity_baseline_master.json
git worktree remove /tmp/parity-master
```

## The exceptions

**PAR-01 — First run writes `vpinfe.game_id` into `.info` files.**
Every game gets a stable id, minted once and persisted. One-time, versioned via
`VPinFE.schema`; files written by a newer build are left alone. Users see a burst of
`.info` writes on first 3.0 start and nothing after.
*Why:* an id-addressed API, events and collections need an identity that survives
renames and table updates, which VPSId cannot provide. Covered by
`tests/games/test_game_identity.py`.

**PAR-02 — First run rewrites `collections.ini` membership onto game ids.**
One-time migration, keyed by a schema version so it runs once; entries that don't
resolve are kept rather than dropped.
*Why:* membership keyed on VPSId was orphaned by an ordinary `.vpx` update. Covered
by `tests/curation/test_collections_rekey.py`.

**PAR-03 — The pre-`/api/v1` endpoints are removed, not aliased.** *(machine-checked)*
`/api/remote-launch`, `/api/asset-upload/*`, `/api/download-table-vpxz` are gone;
their replacements live under `/api/v1`. Their only consumers were our own frontend
and Manager UI pages, which moved with them — but it's a hard break for anything
outside the repo that called them.
*Why:* one API surface with one contract, instead of dual-maintaining both across
the major.

**PAR-04 — WS bridge method `update_frontend_dof_for_table` is now
`notify_table_selected`.** *(machine-checked)*
Called only from `web/common/vpinfe-core.js`, which we serve, so no theme changes.
*Why:* the old name said DOF while the method drove DOF and the real DMD both;
selection is now an event with independent subscribers.

**PAR-05 — A folder with several `.vpx` files may launch a different one than before.**
Master picked by directory scan order, which is filesystem-dependent; 3.0 picks the
file the game's own metadata describes, with a deterministic fallback.
*Why:* three code paths chose three different files, so the metadata a user saw
could describe a different table than the one that launched. Covered by
`tests/games/test_tables.py`.

**PAR-06 — Launches from the Remote page and the API now record play data.**
Start count, Last Played, runtime, NVRAM score — previously only wheel launches
recorded any of it.
*Why:* this was a bug; a play is a play regardless of who started it. Users will see
those launches start counting. Covered by `tests/host/test_launch.py`.

**PAR-07 — The frontend subscribes to launch state instead of polling it.**
One held SSE connection replaces a request every second. Same overlay behavior;
different network pattern for anyone watching traffic.
*Why:* the poll was the only reason `/api/remote-launch` existed; the event stream
serves every future consumer too. Covered by `tests/api/test_event_stream.py`.

**PAR-08 — The log is much quieter at INFO.**
The logging standard moved routine chatter to DEBUG and gave each level a promise.
*Why:* INFO was unreadable on a real library; a level that promises nothing is
noise. Not machine-checked — prose only.

**PAR-09 — Media resolves through a precedence chain and accepts extension families.**
Master resolved exactly one fixed name per kind (`wheel.png`). 3.0 resolves
`(Wheel) <game-file>.png` over `(Wheel) <folder>.png` over `wheel.png`, trying each kind's
extension family in order — so a spec-named or `.jpg` file that master silently ignored
now displays. A library using only the fixed names behaves identically.
Two kinds accept more than one token. Visual Pinball's `FileLayout.md` names the
instruction card `(GameHelp)` and the game flyer `(GameInfo)`; VPinFE leads with
`(InstructionCard)` and `(Flyer)` and accepts the published names as well, so media
packaged either way resolves. The instruction card also accepts `(RuleCard)`, which VPinFE
recommended earlier in 3.0 development. Within a tier the preferred token wins; tier still
outranks token, so a game-file-specific `(GameHelp)` file beats a folder-level
`(InstructionCard)` one.
*Why:* hand-placed media was invisible unless it matched one exact name, and a media
refresh could clobber a user's own file; the tiers make "mine" and "downloaded"
structurally distinct. The published tokens for those two say the role rather than the
thing, which reads as a different asset to anyone naming files by hand — and since VPinFE
only ever *reads* tokens and writes the fixed names, accepting both costs nothing on disk.
Covered by `tests/media/test_media_resolution.py`.

**PAR-10 — Imported media keeps its real file extension.**
Importing a `.jpg` wheel used to write JPEG bytes into `medias/wheel.png` — a file that
lies about itself. It now writes `wheel.jpg`, and removes same-kind siblings that would
shadow it.
*Why:* the on-disk name should tell the truth; browsers sniffed past it, other tools
won't. Covered by `tests/media/test_media_resolution.py`.

**PAR-11 — Six new media kinds: instruction_card, topper, topper_video, loading,
audio_launch, rule_sheet.**
*(machine-checked)* Themes gain six payload fields (`InstructionCardImagePath`,
`TopperPath`, `TopperVideoPath`, `LoadingVideoPath`, `AudioLaunchPath`, `RuleSheetPath`);
every existing field is unchanged. The instruction card is the apron card image, distinct
from the flyer (promo art) and the rulesheet (a document you read); loading is the
loading-screen video; audio_launch plays when a table starts.

Topper is two kinds, not one with a mixed extension family. `bg`, `dmd` and `table` each
split image and video into separate specs sharing a token, and the resolver is built that
way — the token names the kind, the extension family picks image or video. Topper was the
exception, so `topper.png` and `topper.mp4` collapsed onto one key and a cabinet could
hold a still or a video, never both with the video preferred. It now mirrors the others:
`(Topper) x.png` resolves to `topper`, `(Topper) x.mp4` to `topper_video`.
*Why:* the spec names these and tools ship them; adopting the tokens means media that
circulates for other frontends works here unchanged. Covered by
`tests/media/test_media_resolution.py`.

**PAR-12 — `logo` is its own media kind, and the wheel falls back to it.**
*(machine-checked)* `logo.png` used to import as a wheel; it now imports as the game's
logo, its own slot with the full chain (token `(Logo)`). A game with a logo and no wheel
shows the logo wherever the wheel would appear — themes, Manager UI, API — because the
fallback lives at the bottom of the wheel's resolution, below every real wheel tier. The
API marks such a wheel `via: "logo"`. Themes gain `LogoImagePath`.
*Why:* the logo is usually the source a wheel is derived from, so showing it beats a
blank slot everywhere at once; making it a kind keeps it addressable instead of buried in
wheel semantics. Covered by `tests/media/test_media_resolution.py`.

**PAR-13 — A game export is one table by default, not the whole folder.**
The `.vpxz` download and the mobile Web Send used to ship everything: every alternate
table, all media, every extra. The default is now a standalone bundle for the game's
default table — the chosen `.vpx`, its stem-matched and folder-named companions, `pinmame/`,
`music/`, colorization and sound folders, the author's readme files, and a `.info` whose
`assets` section lists only what actually shipped. The whole-folder form remains
available to callers through the API (`?full=true`), under its own permission scope.
*Why:* export a game, not a folder — transfers shrink dramatically, and a multi-`.vpx`
folder finally exports the game file you meant instead of all of them. Covered by
`tests/media/test_export_bundle.py`.

**PAR-14 — Readme files import, display, and travel with the game.**
Files named `readme*` (any extension) and `.nfo` used to fall into the import dialog's
"didn't recognize these" list and were never copied. They're now detected, shown inline in
the import confirmation so the author's notes are readable before anything is written,
copied to the game folder root under their original names (on by default), and included
in the standalone export bundle. Detection is deliberately narrow — never a blanket
`.txt`, which would misfile `alias.txt` and its kin.
*Why:* whoever made the table wrote those notes for whoever installs it; now they arrive.
Covered by `tests/media/test_asset_upload_services.py` and `tests/media/test_export_bundle.py`.

**PAR-15 — Manufacturer logos, served from a shared assets root.**
*(machine-checked)* Themes gain one payload field, `ManufacturerLogoPath`: a
`/assets/`-relative web path to the game manufacturer's logo, or `null` when there is
none — which is every install today, since nothing ships and nothing downloads yet. The
assets root is `[Settings] assetsdir` (default: `assets/` under the config dir), served
at `/assets/`, with `manufacturers/user/` overriding `manufacturers/default/`. Lookup
normalizes the VPSdb manufacturer string ("Williams Electronics" finds `williams.png`)
with a `manufacturers.json` alias map for the exceptions.
*Why:* manufacturer is already a first-class metadata and filter dimension; themes just
had nothing to render for it. A shared root exists because a manufacturer logo is neither
per-game nor per-theme. Covered by `tests/media/test_shared_assets.py`.

**PAR-16 — Game files can be hidden, and several are peers rather than one default.**
A game folder can hold more than one launchable `.vpx` — a desktop table and a VR build,
or a table and a patched variant. Every visible one is independently launchable; there is
no primary-with-alternates. The `.info` gains a `GameFiles` section keyed by filename
(`{"hidden": true}`), absent meaning visible, so an existing library is unchanged. The
game-files API response gains `hidden`.

`default` in that response no longer means "the one to launch". It names the file the
game's metadata was derived from, which is what export and the metadata build need when
they have to pick one. Consumers listing what to play should filter on `hidden`.
*Why:* applying a patch leaves the base table on disk — it has to stay, since the patched
table cannot be rebuilt without it — but nobody wants to be offered it. Deleting it would
be the wrong fix. Covered by `tests/games/test_jdiff_patch.py`.

**PAR-17 — Your own media is protected by hash, and claiming it is gone.**
On master, artwork was protected by marking it `"Source": "user"` — something you had to
know about and run. The downloader now hashes any file already on disk and compares it to
the MD5 VPinMediaDB publishes: a match means it is demonstrably our file and stays
managed, anything else is left alone. That covers every file, claimed or not, including
the case marking could never handle — our art that you later replaced.
So `--claim-user-media` is a no-op stub kept for scripts, the Manager UI's "Use my own
media" toggle is gone, and `--user-media` now only means "fetch nothing". Existing
`"Source": "user"` marks stop being consulted; nobody's artwork changes state.
*Why:* protection that depends on the user having run a command only protects the people
who already knew about it. One loss worth naming: a file byte-identical to VPinMediaDB's
could previously be pinned by claiming it, and can no longer be pinned at all. Covered by
`tests/media/test_vpsdb_media.py`.

**PAR-19 — The `.info` is reshaped, and themes declare which shape they read.**
`VPXFile` becomes `game_files` (one entry per `.vpx`, since a folder can hold several),
`Medias` becomes `assets`, the `VPinFE` section becomes `vpinfe` with snake_case keys, and
`Info` gives up `Rom` and `Authors` to the game file that owns them. A 2.x file is migrated
on read, keeping the original alongside it as `<Game>.info.vpinfe-<timestamp>`.
*Why:* the format described one game file per folder, which stopped being true the first
time anybody patched a table. Themes are unaffected unless they opt in: the payload is
served in the shape a theme declares as `contract` in its `manifest.json`, and absent means
contract 1 — the 2.x shape, synthesised. Covered by `tests/games/test_info_migration.py` and
`tests/theming/test_theme_contract.py`.

**PAR-21 — The WebSocket methods take VPS's vocabulary, and the old names still answer.**
*(machine-checked)*
`get_tables`, `get_initial_table_index`, `set_tables_by_collection`, `launch_table`,
`notify_table_selected`, `get_table_rating`, `set_table_rating`, `get_table_orientation`
and `get_table_rotation` are now `get_games`, `get_initial_game_index`,
`set_games_by_collection`, `launch_game`, `notify_game_selected`, `get_game_rating`,
`set_game_rating`, `get_playfield_orientation` and `get_playfield_rotation`.
Every old name stays in the allowlist and forwards to its replacement, so a theme written
against any earlier build keeps working unchanged and gets an identical payload back.
*Why:* VPS calls the machine a game and the `.vpx` a table; ours said the opposite. The
screen ones are the playfield, which is what `docs/conventions.md` already called it.

**PAR-22 — The theme payload's own keys take the new vocabulary at contract 2.**
*(machine-checked)*
`TableImagePath`, `TableVideoPath`, `fullPathTable` and `tableDirName` become
`PlayfieldImagePath`, `PlayfieldVideoPath`, `fullPathGame` and `gameDirName`.
The same applies inside `meta.VPinFE`, whose keys moved to snake_case in the `.info`:
contract 1 gets `deletedNVRamOnClose`, `altlauncher`, `pluginprofile`, `alttitle` and
`altvpsid` back. That was **broken until 2026-08-04** - the projection restored the section
name and not the keys inside it, so five keys a 2.x theme could read simply vanished. The
gate compared only top-level payload keys, so nothing caught it; it compares every key now.
**Contract 1 still receives the old four**, restored by the projection in
`frontend/theme_contract.py`, so every theme written before 3.0 is unaffected - a theme
only sees the new names by declaring `contract: 2` in its manifest.
*Why:* three of the four name the machine, which VPS calls a game; the playfield pair is
the playfield, which `docs/conventions.md` already called it in the media list. These are
the first top-level row keys ever to move, so the projection had to grow past `meta` to
reach them.

**PAR-23 — The `vpin.*` JavaScript surface renames, and every old member still works.**
`vpin.tableData`, `tableRotation`, `tableOrientation`, `getTableMeta`, `getTableData`,
`getTableCount`, `getCurrentTableIndex`, `playTableAudio`,
`stopTableAudio` and `launchTable` become the `game`/`playfield` spellings. Each old name
stays as an accessor forwarding to its replacement, so reads, writes and method calls all
still work from a theme written against any earlier build.
*Why:* the theme contract projects the **payload**; it has never covered the JS surface,
so an alias is the only mechanism available. Removing these would be a hard break with no
migration path, which is why none of them is removed.

**PAR-31 — Contract 2 names its media kinds; a route serves them by game id.**
`entries[].media` is the list of kinds a game has a file for, and the bytes come from
`GET /media/<table id>/<kind>` on the theme assets port. Addressed by table because tier 1
of the media chain keys off the table that launches, even though the scan resolves once
per game today - so the URL survives that being fixed. The manufacturer logo moves onto
`game.manufacturer_logo`, since it is art about the manufacturer rather than about the
game. **Contract 1 is unchanged**: it keeps a filesystem path per kind at the top of each
row, which is what every published theme reads.
*Why:* the payload used to hand a browser absolute filesystem paths and leave each theme to
reverse-engineer a URL out of them. That is where the `medias/` string surgery in
`vpinfe-core.js` came from, and it needed a special case the first time a wheel set put a
file one level deeper. Naming the kinds instead also takes several hundred kilobytes off a
large library's payload, which crosses the socket on every filter and sort. Responses carry
an `ETag` and `Cache-Control: no-cache`, so a media change in the Manager UI is visible
without a version baked into the URL - which would have meant stat-ing every resolved file
of every game every time the list was built. Covered by `tests/media/test_media_route.py`.

**PAR-32 — A theme may declare its windows, and one method reports them.**
`get_theme_windows()` returns the windows the active theme declared, controller first.
A theme that declares nothing gets the three VPinFE has always opened, **under the names
its contract uses** - `table`, `bg`, `dmd` at contract 1, so `index_table.html` and
`?window=table` are unchanged and no fallback lookup exists anywhere.
*Why:* the window list was a literal in two files that had to be kept in step, the name
decided the HTML file, the `?window=` value, the WebSocket identity and the `<window>screenid`
key, and a theme could not add one. `topper` and `loading` media shipped in 3.0 with no
window to show them on. A window's monitor is now read generically from
`<window>screenid`, so a theme can name a window VPinFE has never heard of. Blank means
not launched, which is the rule that already applied. Covered by
`tests/theming/test_theme_windows.py`.

**PAR-30 — One WebSocket method is added so the browser can ask which contract it serves.**
`get_theme_contract()` returns the level the active theme declared. Purely additive: a
theme never calls it, and no existing method changes.
*Why:* `contract` used to govern the payload and nothing else, so the `vpin.*` aliases, the
legacy media kind spellings and the dual-spelling window messages were unconditional - and
therefore permanent, because nothing ever signalled that a theme had stopped needing them.
A theme already declares what it was written against; `vpinfe-core.js` now asks once at
init and serves that surface alone. Contract 1 is unchanged and is what a theme gets by
declaring nothing, including when the build is too old to answer at all. Covered by
`tests/js/contract-surface.test.js`.

**PAR-27 — One WebSocket method is added so the browser can report a deprecated name.**
`report_deprecated_use(key, name)` takes a shim key and the legacy name a theme reached,
and hands both to `common/deprecations.py`. Purely additive: a theme that never calls it
is unaffected, and no existing method changes.
*Why:* the WebSocket methods and the ini keys announce their own legacy use into the log,
so a maintainer can see what is still needed before retiring a shim. The `vpin.*` aliases
could not - a theme runs in Chromium, and a console line on a cabinet is invisible. This
is the one surface that had no evidence behind it, and it is the surface a theme is most
likely to be using. Covered by `tests/invariants/test_deprecations.py`.

**PAR-26 — `--table` still works on the CLI; the flag is `--game`.**
`--game` takes the folder name for `--buildmeta`, `--upgrade-info` and `--restore-info`.
`--table` is accepted as an alias and kept out of `--help`, so a script written against
2.x keeps running while the documented flag is the current one.
*Why:* the CLI sits with the API rather than with the Manager UI, which keeps saying
Tables for 3.0 — see the Manager UI note in `docs/conventions.md`. A flag in somebody's
script is exactly the kind of thing that should not need editing to survive an upgrade.

**PAR-25 — `vpinfe.ini` keys are read under their old names and written under the new.**
`tablescreenid`, `tableorientation`, `tablerotation`, `tablerootdir`, `restorelasttable`,
`tabletype`, `tableresolution`, `tablevideoresolution`, `tablemediapriority` and
`lasttable` become the `playfield*` and `game*` spellings. The old key is read once and
the new one written, so an existing `vpinfe.ini` keeps working and is corrected in place
on first load. `cabmode`, `enabledof` and `splashscreen` are moved between sections by
the same pass — that one predates 3.0.
*Why:* an ini is hand-edited and lives in the user's config directory, so the rename has
to be invisible. Both passes run *before* the defaults are filled in: every key here has
a default, and with one already written "copy only if absent" copies nothing and the
user's real value is dropped. That was a live bug for the section moves.
Covered by `tests/config/test_config_store.py`.

**PAR-24 — Window messages carry both spellings, and inbound is accepted either way.**
`TableIndexUpdate`, `TableDataChange`, `TableLaunching`, `TableRunning` and
`TableLaunchComplete` become the `Game*` spellings. Every one is broadcast twice — current
name then legacy — so a theme matching either receives it, and `vpin.handleEvent` maps an
inbound legacy name onto the current one before anything matches on it.
*Why:* a message type is a string a theme compares against, so there is no projection to
hang this on and both have to arrive. The dual send first landed in `vpinfe-core.js` alone,
which covers only the messages a theme originates; the launch lifecycle is broadcast by
`frontend/play_events.py`, so it kept sending the 2.x names by themselves. Installed themes
match those and were unaffected, which is exactly why it went unnoticed — but a theme
written against the names `docs/theme.md` documents received no launch events at all.
Covered by `tests/api/test_play_events.py`, which also asserts the Python and JavaScript alias
maps are the same map.

**PAR-18 — Addon folders are detected whatever their casing.**
The library scan matched `pupvideos`, `serum`, `vni`, `music` and `medias` against the
folder name exactly as stored, so a folder named `PUPVideos` — the casing PinUP Popper
itself writes — was not detected. The API had always lowercased before comparing, so the
same game reported a PUP pack there and none in the Manager UI and themes. The scan now
folds case too. Games whose folders are not all-lowercase will start reporting addons
they always had (`pupPackExists`, `altColorExists`, `vniExists`, `altSoundExists`).
*Why:* one game cannot have two answers, and the scan was already case-insensitive about
`.directb2s` and `.ini` three lines away. Covered by `tests/media/test_media_resolution.py`.

**PAR-20 — The 2.x restore module is removed; 3.0 restores through its own.**
`common/info_restore.py`, its Manager UI dialog and its tests shipped in the 2.x line so a
release older than 3.0 could put back the backups 3.0 writes. They are deleted here.
`common/games/info_maintenance.py` does the same job and generalizes it: `restorable_backup`
takes the highest schema this build can read, so one walk serves every future schema bump.
*Why:* that module exists to serve the release *before* 3.0. Once 3.0 is master there is no
older build to run it, and two implementations of one operation means fixing each bug twice.
The backup filename and the read-the-shape-from-the-file rule are unchanged, so a 2.x
install can still restore what a 3.0 install wrote — that contract lives in the file format,
not in this module. Covered by `tests/games/test_info_maintenance.py`.

**PAR-33 — One WebSocket method is added so the browser can learn how to turn playfield art.**
`get_playfield_media_rotation()` returns `[Media] playfieldmediarotation`, which is `auto` by
default. Additive: a theme that never calls it is unaffected, and master has no equivalent.
*Why:* `[Displays] playfieldrotation` says how far to turn the **UI** so it faces the player;
this says how far to turn the **art** so it fills the surface. Four published themes each
derived the second from the first and no two agreed, so the same ini produced different
geometry depending on which theme was installed. Core resolves it once now, measuring the
image rather than assuming an authoring convention - there is no reliable one - and this
setting states the turn for what measuring cannot see, such as art that is upside down.
*(machine-checked)*

**PAR-34 — A contract 2 theme's playfield window is titled and addressed `playfield`.**
The window a contract 1 theme calls `table` is called `playfield` at contract 2, so its
page title becomes `VPinFE Playfield` rather than `VPinFE Table` and it is served from
`/app/playfield` rather than `/app/table`. Chromium runs each window with `--app=<url>`
and derives the window's application id from that url, so the id moves with it.
**This only happens when a theme declares contract 2** - every published theme is
contract 1 and sees no change at all.
*Why:* the window name determines the page file, the media kind and the `[Displays]` key,
so one theme cannot have it be `table` in some of those and `playfield` in others.
*What it costs someone:* window rules keyed on the old title or application id stop
matching, and a cabinet compositor places the window wrong with no error - windows pile
onto one screen. Anyone running a Sway or KWin rule for `VPinFE Table` or `app_table`
wants a second rule before switching a theme to contract 2. Covered by
`tests/theming/test_theme_windows.py`.

**PAR-35 — Settings move from `vpinfe.ini` to `vpinfe.json`.**
The first 3.0 run reads an existing `vpinfe.ini`, writes the same settings to
`vpinfe.json` beside it, and copies the ini aside. **The original is left in place**, so a
downgrade still finds the file 2.x reads. Every value carries over, including keys that
were renamed or moved section along the way, and the new file carries a schema version.
Booleans and integers are stored as booleans and integers rather than as strings; a blank
integer stays blank, because blank means "no window on this screen" and is not zero.
*Why:* every other file VPinFE owns is already JSON, and this was the only one that was
both hand-edited and machine-written - which is exactly why it was the only one whose
comments `configparser.write()` destroyed on first load. It also makes the settings the
same shape over HTTP as on disk, which is what lets the API and an extension read them
without a translation. **Comments in an existing ini are not carried over** - they were
already destroyed by the first write of any 2.x build, so nothing that survives today is
lost. The Manager UI is the intended editor and covers 84 of the 86 settings.
Covered by `tests/config/test_config_store.py`.

**PAR-36 — Theme options you set move out of the theme, and survive an update.**
They were written into the installed theme package, and updating a theme deletes that
package — so **every theme update silently reset every option back to its default**, with
no backup and no warning. They live in `theme_user_options/<folder>.json` now, one file
per theme, keyed by the folder name because a local or side-loaded theme has no registry
key. The first 3.0 run lifts existing values out of each installed theme, before anything
installs or updates one; a theme that already has a user file is left alone, so it runs
once. The author's schema file is no longer written to at all.
*Why:* this was data loss on a routine action, and the only reason it was survivable is
that most themes ship few options. Nothing a theme author does changes — `theme.json` is
still where options are declared. Covered by `tests/theming/test_theme_options.py`, including the
sequence that used to lose them: install, configure, update, check.

**PAR-37 — Setting names are snake_case, and every old spelling still resolves.**
`gamerootdir` is `game_root_dir`, `cabmode` is `cab_mode`, `MMhideQuitButton` is
`hide_quit_button` - 53 of the 87 settings moved. A stored file is rewritten to the new
names on first read (schema 2), and **every previous spelling stays a permanent alias**,
so a config written by any earlier build still loads and a caller written against the old
name still reads. Two settings changed more than their casing: `defaultmissingmediaimg`
spells out `default_missing_media_image`, matching every other `[Media]` key.
**`[Input]` is deliberately untouched** - those names are the theme-facing action
vocabulary and rename with that work, not this.
*Why:* the ini forced a second spelling of nearly every setting - the file said
`gamerootdir` while the code said `game_root_dir` - and a mapping between them that had to
be maintained by hand. One name now, and it is the one `docs/conventions.md` asks for.
Canonical-plus-alias is the pattern Visual Pinball uses upstream for the same problem.
Covered by `tests/config/test_config_schema.py` and `tests/config/test_config_store.py`.

**PAR-38 — Each window's settings live under that window, named as Visual Pinball names it.**
The fourteen settings that faked a hierarchy with a prefix - `playfieldscreenid`,
`bgmediapriority` and the rest - are a section per window now, and the sections use VPX's
own window names: `windows.playfield`, `windows.backglass`, `windows.scoreview`. On disk
that is a real object per window rather than fourteen flat keys. Migrated on first read
(schema 3), and **every previous location keeps resolving**, section and spelling both, so
a config from any earlier build still loads and code asking for `[Displays] playfieldscreenid`
still reads. A window a theme invented is unaffected: it has no schema entry, and both
`windows.<name>.screen_id` and the old `[Displays] <name>screenid` are read.
`cabmode` stays in `[Displays]` because it is context rather than a window, and
`realdmd_media_priority` stays in `[Media]` because the real DMD is hardware, not a window.
*Why:* the prefixes were a hierarchy the format could not express, and the whole
`playfieldmediarotation` naming argument was spent deciding which tier of an imaginary one
a key belonged to. VPX models per-window config exactly this way, which is also why the
names follow its plugin contract - `Backglass` and `ScoreView`, not `bg` and `dmd`.
**This is the config file only.** The window names a *theme* sees are contract 2's and
move with that work. Covered by `tests/config/test_config_schema.py` and `tests/config/test_config_store.py`.

**PAR-39 — At contract 2 the windows and media kinds are `playfield`, `backglass` and
`scoreview`.** Visual Pinball's plugin ABI declares `VPXWINDOW_Playfield`, `Backglass`,
`ScoreView` and `Topper`, and VPinFE fronts VPX, so those are the names. A contract 2
theme's default windows are `playfield` / `backglass` / `scoreview`, it ships
`index_backglass.html` and `index_scoreview.html`, and `entries[].media` lists `backglass`
and `scoreview`. In VPX a DMD is a render *style*; the window that shows a score is
ScoreView, which is why `dmd` is the one that changed word rather than just casing.

**Contract 1 sees none of it.** Its default windows are still `table` / `bg` / `dmd`, it
still loads `index_bg.html`, its payload still carries `BGImagePath` and `DMDImagePath`,
and `vpin.getMedia(i, "bg")` still answers - `bg` and `dmd` are permanent aliases, and a
published kind name answers forever once it has been asked for. All twelve registry themes
are contract 1.

**No file moves.** `bg.png` and `dmd.png` are what VPinMediaDB ships and what everyone has
on disk; only the keys moved. Keys renamed, files frozen - the same split every other
rename on this branch made. Covered by `tests/theming/test_theme_windows.py`,
`tests/media/test_media_resolution.py` and `tests/js/media-resolution.test.js`.

## Explicitly *not* exceptions

The theme-facing payload (`tables_json` keys, media path fields, stable values) and
the on-disk library after a plain scan are asserted **identical** to master. Scans
never write; only the PAR-01/02 first-run migrations do.

The alphabetical sort that ignores a leading "The" is master behavior (shipped
there in July 2026), not a 3.0 change.

## Retiring the gate

The gate is scaffolding for the transition and it dies with it: once this branch *is*
master, there is nothing left to compare against. Whoever does that merge should delete
`tests/invariants/test_parity.py`, `tests/support/parity_capture.py` and `tests/parity_baseline_master.json`,
and drop the `!tests/parity_baseline_master.json` line from `.gitignore` — it only exists
to punch the baseline back through the blanket `*.json` rule, and removing the file
without it leaves a dangling negation.

This file stays. By then it stops being a gate and becomes the list of what changed in
3.0 and why: upgrade notes for anyone coming from 2.x, and the first place to look when a
theme or an API consumer breaks.

**PAR-29 — Media kind names are snake_case, and the old spellings still answer.**
The strings a theme passes to `vpin.getMedia(index, kind)` — and the ones `/api/v1` uses
in `/games/{id}/media/{kind}` — are `playfield`, `playfield_fss`, `playfield_video`,
`real_dmd`, `real_dmd_color`, `instruction_card`, `audio_launch` and `rule_sheet`.
`table`, `table_video`, `fss`, `realdmd`, `realdmd-color`, `realdmd_color`, `rulecard`,
`audiolaunch` and `rulesheet` are accepted and map to them, so a theme written against any
earlier build keeps resolving media.
*Why:* the set was half converted — `table_video` and `realdmd_color` used underscores
while the rest ran together — and these keys are JSON over HTTP, which `docs/conventions.md`
settles as snake_case. The playfield rename also retires a name that collided with the
`[Media] playfieldvariant` values: `fss` was simultaneously a kind and a variant.
**Payload attribute names are unchanged** — `TableImagePath` and the rest are contract 1's
keys and shipped, so only the kind vocabulary moved. Covered by
`tests/js/media-resolution.test.js` and `tests/media/test_asset_upload_services.py`.

**PAR-28 — the theme payload at contract 2 is an entry list, not a row array.**

Contract 1 is unchanged and is what every published theme reads: an array of game rows,
built from the game exactly as 2.x built it. The parity gate holds it against master.

Contract 2 is an object — `{collection, expanded, count, entries}` — where an entry is a
table with its game attached. A game offering several tables can appear more than once,
which a row array cannot express. `meta` is gone at contract 2: it was the `.info` passed
through, so a storage change reached themes whether or not it meant anything to them.

`meta` going away means contract 2 has to serve what themes actually read out of it, so
each entry carries a `user` block on both `game` and `table` - rating, favorite, tags, and
the play counters. `User.LastRun` is an epoch integer and `User.RunTime` is minutes, both
fixed by the VPX spec; the payload converts to ISO 8601 and seconds rather than making a
theme know that.

`vpinfe-core.js` reads it: `vpin.entries` is the list, `vpin.collection` and
`vpin.expanded` are the view it came from, and the media, metadata and VPinPlay
accessors take an entry as readily as a row. Contract 1 keeps its array and its
paths.

Nothing published declares contract 2, so this reshapes a surface no theme reads yet.

