# 3.0 compatibility ledger

3.0 is plumbing and housekeeping; the goal for existing users is that they notice
nothing. This file is the complete list of deliberate exceptions — every way 3.0 is
*allowed* to differ from master, each with why it's worth it.

It is enforced, not aspirational: `tests/invariants/test_parity.py` compares this tree's
behavior against a captured master baseline (`tests/fixtures/parity_baseline_master.json`),
and a difference is either named here by its `PAR-` id or the build fails. There is
no third option. Entries marked *(machine-checked)* are asserted directly by the
parity test; the others are covered by the tests referenced in their entry.

To refresh the baseline after master moves:

```
git worktree add /tmp/parity-master master
cd /tmp/parity-master && python <this-tree>/tests/support/parity_capture.py --out <this-tree>/tests/fixtures/parity_baseline_master.json
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
Called only from `frontend/static/common/vpinfe-core.js`, which we serve, so no theme changes.
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
Covered by `tests/media/test_asset_analyzer.py` and `tests/media/test_export_bundle.py`.

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
served in the shape a theme's `min_vpinfe` implies, and absent means
contract 1 — the 2.x shape, synthesised. Covered by `tests/games/test_info_migration.py` and
`tests/theming/test_theme_contract.py`.

**PAR-21 — Four WebSocket methods take VPS's vocabulary, and the old names still answer.**
*(machine-checked)*
`get_table_rating`, `set_table_rating`, `get_table_orientation` and `get_table_rotation`
are now `get_game_rating`, `set_game_rating`, `get_playfield_orientation` and
`get_playfield_rotation`. Each old name stays in the allowlist and forwards to its
replacement, so a theme written against any earlier build keeps working unchanged and gets
an identical payload back.
*Why:* a rating belongs to the machine, which VPS calls a game. The screen ones are the
playfield, which is what `docs/conventions.md` already called it.

**The selection surface is not in this list, and does not change.** `get_tables`,
`get_initial_table_index`, `set_tables_by_collection`, `launch_table` and
`notify_table_selected` keep the names 2.x shipped, because what they address is a row and
a row is a table. A game may offer several, and naming one is how a collection asks for
exactly that build.

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
only sees the new names by declaring `min_vpinfe: "3.0"` in its manifest.
*Why:* three of the four name the machine, which VPS calls a game; the playfield pair is
the playfield, which `docs/conventions.md` already called it in the media list. These are
the first top-level row keys ever to move, so the projection had to grow past `meta` to
reach them.

**PAR-23 — Two `vpin.*` members rename, and both old names still work.**
`vpin.tableRotation` and `tableOrientation` become `playfieldRotation` and
`playfieldOrientation`. Each old name stays as an accessor forwarding to its replacement,
so reads, writes and method calls all still work from a theme written against any earlier
build.
*Why:* the theme contract projects the **payload**; it has never covered the JS surface,
so an alias is the only mechanism available. Removing these would be a hard break with no
migration path, which is why neither is removed.

**The selection members do not rename.** `vpin.tableData`, `getTableMeta`, `getTableData`,
`getTableCount`, `getCurrentTableIndex`, `playTableAudio`, `stopTableAudio` and
`launchTable` keep the names 2.x published — they address a row, and a row is a table.

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

**PAR-83 — `Last Played` derives itself instead of being maintained.** It used to be a
collection the launcher wrote to on every launch — push the game onto the front of a member
array, trim it to 30. It is an ordinary filter collection now: every game with a play date,
most recent first, capped at 30. An existing one is converted in place on first start,
keeping its name, icon and position in the list; the member array goes. That conversion runs
once and the file records that it ran, so deleting the collection, or turning it back into a
list you picked yourself, sticks. A fresh install is seeded with it, empty until something is
played. The `played` criterion behind it is a filter axis like any other, so "never played"
and "the last 10" are collections you can define rather than code.
*Why:* the array and the play date were written by the same launch, so the date already knew
everything the array did — this changes where recency is read from, not what is known. It
also fixes two things an array cannot do. It cannot hold ids matching no game on disk, which
a maintained one does collect and which the wheel renders as raw hex. And play dates are
never trimmed where the 31st entry of the array was destroyed, so raising the limit later
surfaces plays that far back. Measured against a maintained array on a real library: the
derived list gives the same games in the same order, minus the ids that matched nothing, plus
every play the 30-item array had already forgotten. Covered by
`tests/curation/test_last_played.py`.

**PAR-82 — The wheel resolves a collection the same way the API does.** Choosing a
collection in a theme now goes through the one resolver, so the wheel honors what a
collection stores: a member naming one specific table, a table or game it excludes, a row
limit, and the order it was arranged in. Filtering leaves the collection you were in and
shows the library filtered, which is what it already did. `Last Played` still comes back
most-recent-first, and no longer because its name is matched in code — it says what order
it is in, like every other collection. (PAR-83 then made it derive that order.)
*Why:* the frontend had a membership engine of its own that read a collection's game ids
and nothing else, so all four of those were invisible on the wheel while REST answered
correctly for the same collection. Measured on identical collections: two named tables of
one game showed one row, a limit of 2 over three games showed three, and an excluded game
was still there. A theme reading `get_current_sort_state` can now see `"Manual"`, which is
a curated order rather than one of the five sorts. Covered by
`tests/theming/test_collection_view.py` and `tests/theming/test_view_refresh.py`.

**PAR-81 — The `.vpx`'s company fields are not published.** *(machine-checked)* The
entry's table half briefly carried `manufacturer`, `year` and `type` from the `.vpx`'s
`tableinfo`. All three are removed before anything consumed them; `release_date` and
`version`, which come from the same block, stay.
*Why:* measured across the 162 parsable `.vpx` files in a real library, `companyname`,
`companyyear` and `playfieldvariant` are populated in **none** of them - authors fill in
the filename, the version and the release date and leave VPX's company block alone. The
same measurement puts `release_date` at 74% and `version` at 93%, which is why those two
are worth carrying. Two of the three were also duplicates: a table's company and year are
the *game's* company and year, which VPSdb does populate. And `playfieldvariant` is a
rendering mode (`fss` versus a standard playfield), not SS/EM - publishing it as `type`
beside the game's `type` would have put two unrelated meanings behind one word on the same
payload. Re-adding any of them is additive if a library is ever found that fills them in.
Covered by
`tests/curation/test_wire_entry.py`.

**PAR-80 — Reading the wheel's entries takes the view's lock.** *(machine-checked)* The
`entries` property read and sometimes rebuilt `_entries` without holding the lock every
writer takes. No API or payload changes.
*Why:* a sort mutates `filtered_games` in place, so a reader that rebuilt while one was
running walked a list being reordered and got an empty wheel - and could separately see
`_entries` assigned before `_entries_source` caught up. PAR-60 made this reachable by
giving three windows one view: the copies it replaced were accidentally safe. The window
is a few bytecodes wide, which is why it passed locally every time and failed on a shared
CI runner. Measured with an aggressive switch interval: 800 torn reads without the lock,
none with it. The test now sets that interval and runs two sorters against four readers,
so it fails on a laptop rather than only in CI. Covered by
`tests/theming/test_shared_view.py`.

**PAR-79 — A player can check that its library really is the hub's.**
*(machine-checked)* New: `network.verify_shared_library`, off by default, and
`hub_library.verify_shared_library`. With a hub set and the flag on, a player compares its
own tables against the hub's at startup and logs what does not match. Nothing else
changes - no route, no payload, and an install that says nothing does exactly what it did.
*Why:* shared storage is what the residency split assumes and nothing checked. A
`game_root_dir` that is wrong or unmounted fails one game at a time, at launch, as a
file-not-found - the least useful moment to find out. The comparison is by `file_hash`
rather than by path, because the same share is mounted at different places on different
machines and a path comparison would call every install broken; `file_hash` crossing the
wire (PAR-77) is what made this possible. It reports and does not decide: `missing`, 
`differs` and `unverifiable` are three different problems, and what to do about each is a
policy call nobody has made - guessing it here would make an unmounted share fatal on a
machine that was working a moment ago. Nothing verifiable is not a pass, so "everything
matched" cannot mean "nothing was checked". Covered by
`tests/curation/test_library_entries.py`.

**PAR-78 — A hub knows which players it is serving.** *(machine-checked)* New:
`GET/PUT/DELETE /api/v1/devices`, two scopes (`devices:read`, `devices:write`), a
`devices` link in discovery, and `put_json` in `common/http_client.py`. A device with
`network.hub_url` set announces itself at startup. Purely additive - an install with no
hub announces nothing, and every existing route is untouched.
*Why:* the roster storage shipped in PAR-66 with nothing writing to it, so a hub held an
empty file. Events already carry the `install_id` they happened on (PAR-55); a roster is
what turns that id into a name a person recognizes, which is the whole of what item 9 was
scoped to - data, no screen. Routing a launch to a chosen player, aggregating state and
conflict resolution are all deliberately absent: each needs a decision across players that
has not been made. The address is read off the socket rather than the request body,
because a player behind a router does not know how it is reached and a caller that could
name its own address could name someone else's. Announcing is best effort on a background
thread: a hub that refuses or cannot be reached costs a label, not a frontend. It also
mints the install id if there is none - announcing is the first thing that needs one and
it runs before the API, which is the other place that mints. Covered by
`tests/api/test_devices.py` and `tests/theming/test_separation.py`, which registers two
live players with a live hub.

**PAR-77 — The table is a first-class object on the wire.** *(machine-checked)* One
`table_descriptor` builds the table half of both play lenses, so `GET /collections/{name}
/entries` and the contract 2 theme payload carry the same fields. New on both: `hidden`,
and the table's own `release_date`. `default` was
REST-only and is now on both. `GET /games/{id}/tables` gains `id`, the same one the play
lens uses, and `file_hash`. A player restores the storage shape through
`wire_entry.table_of`.
*Why:* a game folder holds several tables and each answers for itself, but the transport
treated the table as a few fields hanging off a game. Three consequences, all real: a
table's own `release_date` never crossed, so nothing could tell one build from another by
when it shipped; `hidden` never crossed, so a player
could only ever be handed a list the hub had already filtered; and the two lenses named
the same table differently, with the management lens carrying no id at all - a client
could not tell that `GET /games/{id}/tables` and an entry described the same table. The
wire names fields for a consumer and storage names them for the parser, so a player that
passed the wire dict through unchanged answered false for every detect flag and lost the
game's default. `table_of` is the counterpart to `WireGame`, and the round trip is
compared field for field. `file_hash` crosses because a shared-storage check is content
rather than path - two installs on one filesystem mount it at different places, so the
hash is what says they hold the same file. `source` deliberately does not cross: its
fields need a matcher that does not exist yet, and building the slot ahead of the producer
is the mistake that document's own audit section exists to prevent. Covered by
`tests/curation/test_wire_entry.py` and `tests/curation/test_entry_lens_parity.py`.

**PAR-76 — A hub publishes where its asset server is.** *(machine-checked)* Discovery
(`GET /api/v1/`) gains `services`, currently `{"assets": {"port": N}}`. Purely additive.
*Why:* artwork is served on a different port from the API, and nothing told a player which
- so `endpoints.assets` paired the hub's host with the *player's* asset port and every
image 404'd. The port only: the host is wherever the caller reached the document, which is
the one address known to route there. A hub that says nothing leaves the player's own
answer standing, which is what a single-machine install has always used. Covered by
`tests/theming/test_chromium_manager.py` and `tests/theming/test_separation.py`.

**PAR-75 — The last-launched row is remembered by id, not by path.** *(machine-checked)*
`state.last_game` stores a table id, falling back to a game id. `save_last_game` becomes
`save_last_launched` and takes the ids; `table.launching` carries `table_id`.
**A saved value written before this does not resolve** - the wheel opens at the first row
once, and the next launch writes the new form. Nothing else reads the key.
*Why:* the identity was the game folder's path, which answers the wrong question twice
over. A game offers several tables, so an expanded wheel came back to whichever row that
folder happened to be first in rather than the table that was played. And a player reading
its library off a hub never sees the hub's filesystem, so a path identifies nothing there
- ids cross the wire, paths deliberately do not. Covered by
`tests/theming/test_last_game.py`.

**PAR-74 — Refreshing the wheel asks the view where its library is.** *(machine-checked)*
`refresh_view` called `all_games()` directly; it now calls `View.reload()`. No
behavior changes on an install that holds its own library - the view loads exactly what
that function returned.
*Why:* a player fetched the hub's entries at startup and then threw them away on the first
`get_games`, because the refresh went to the local disk behind the view's back. The wheel
came up empty with nothing logged, and every unit involved was individually correct - the
separation test is what found it. Reloading through the view means one seam decides where
the library comes from instead of two places agreeing by accident. A reload that fails
keeps what is shown: a stale wheel beats a player blanking its screen because one request
timed out. Covered by `tests/theming/test_separation.py`, which runs a hub and a player as
separate processes and renders the player's wheel in a browser - it fails if this reads the
local disk again.

**PAR-73 — A window is told which machine its hub is on.** *(machine-checked)* Two query
parameters are added to the window url, `hubHost` and `playerPort`, and only when
`network.hub_url` is set. `vpin.endpoints` reads them: `hub` and `assets` follow the hub,
`player` and `frontend_channel` stay on this machine. Purely additive - with no hub set the
url is byte-identical to what it was and every endpoint stays loopback.
*Why:* `endpoints` hardcoded `127.0.0.1` for all four, so a remote player resolved the
library and its art to its own machine. Its own comment said hosts were "loopback until
bind configuration says otherwise", but nothing gave bind configuration a way to say so.
The host travels in the url for the same reason the ports do (PAR-45): the page cannot ask
before it has a connection. `hubPort` and `playerPort` are separate because they are
different machines' ports - a hub on 9000 would otherwise have a player dialling its own
api at 9000, and the hub's at 8001. `assets` follows the hub because art is a file in the
library; `frontend_channel` never does, because it addresses this page's own windows.
Covered by `tests/theming/test_chromium_manager.py` and `tests/js/endpoints.test.js`; the
post-connect port refresh is covered by `tests/theming/test_render_smoke.py`, which caught
it overwriting a remote hub's port with this install's.

**PAR-72 — `network.hub_url` points a player at its hub.** *(machine-checked)* One new
config key, defaulting to empty. Empty - which is every existing install and every
single-machine setup - and the view loads the local library exactly as before. Set, and
`View` holds the entries the hub resolved. `Entry` gains `meta_config` and `creation_time`,
both forwarding to the game it holds.
*Why:* nothing named which hub a player reads from, so the remote path built in PAR-71 had
no way to be switched on. The default preserves 2.x behavior by being the absence of a
setting rather than a mode to opt out of. A remote list is entries, not games, and the two
are not interchangeable: `entries_for` reads a game's table dicts out of its `.info`, and
the hub kept those - re-deriving from what arrived yields an empty wheel, silently. The
frontend's sorts read a title and a creation time off whatever they are handed, so an entry
forwards both rather than every sort learning two shapes. Covered by
`tests/theming/test_remote_view.py`, including that an install saying nothing stays local.

**PAR-71 — A player can read its library from a hub.** New: `GET /library/entries`, the
play lens over the whole library, and `common/games/hub_library.py`, which turns what it
returns back into local `Entry` objects. `WireGame` grows the resolved asset flags, the
media kinds and two deliberately empty paths. Purely additive - no existing route,
payload or stored file changes shape.
*Why:* a player with no library of its own shows everything before a collection is chosen,
and no stored collection means "all of it" - so `GET /collections/{name}/entries` could not
answer for that view, and inventing an "All" collection would put a name in every user's
file to serve a default. Both routes share `_entry_resource`, so the two cannot drift. The
hub returns entries rather than a finished payload because what to show is the player's
question: it knows its theme, its contract and its windows, and a payload built by the hub
would carry one machine's paths into what another renders. `fullPathGame` and
`fullPathVPXfile` arrive empty for that reason, while the asset flags and media kinds
arrive resolved - both are a stat of the hub's disk, which a player cannot redo. Covered by
`tests/curation/test_library_entries.py`, which builds a contract 2 payload from a hub's
answer with no local library behind it.

**PAR-70 — Two surfaces writing collections no longer lose each other's edit.**
`CollectionStore` gains `mutate()`, a context manager that reloads and saves under one
process-wide lock. Every writer goes through it: the theme's collection menu, the four
API routes, the seven Manager UI operations and the launch tracker. No payload, route or
stored file changes shape.
*Why:* the whole file is rewritten on every save, so a writer holding a copy read before
another one saved wrote that stale copy back - dropping the other's collection and
reporting success. `httpapi` had a lock of its own, which serialised API writes against
each other and nothing else; its comment said as much and called it tolerable because
edits are rare. It is reachable from any pair of the four surfaces, and the launch
tracker writes on every game start, so a user creating a collection while a game loads
could lose it. A lock alone would not have fixed it - the stale copy is read before the
lock is taken - which is why `mutate` reloads inside it. Raising inside the block writes
nothing, so a route can validate against the just-reloaded file and refuse. Covered by
`tests/curation/test_collection_writes.py`.

**PAR-69 — Filtering and sorting can read an entry, not just a game.** New:
`common/games/wire_entry.py`, which presents a wire entry in the shape the metadata
accessors read, and an `iso_to_epoch` in `common/timestamps.py`, the inverse of
`epoch_to_iso`.
Nothing existing changes: the axis registry, the sort keys and every caller are
untouched, and no payload gains or loses a field.
*Why:* the seven filter axes and the seven sort orders are written against a `Game` and
reach for `meta_config` - the raw `.info` sections. A client holding its own copy of the
library has entries instead, whose fields the hub already resolved, so it could not ask
the same questions of them. Rebuilding those sections from the entry means one
implementation answers on both sides rather than two that agree until they do not. The
resolution the hub did is not repeated: `name` goes back under `Info.Title` unchanged,
which is only sound because moving a leading article in a title that has had one moved is
a no-op. Covered by `tests/curation/test_wire_entry.py`, which runs every axis and every
order against a game and its entry and compares.

**PAR-68 — The entry says when its folder appeared.** Entries gain `game.created_at`, an
ISO-8601 UTC timestamp, on both the REST lens (`GET /collections/{name}/entries`) and the
contract 2 theme payload. Purely additive. Null where the filesystem gave no answer, which
is the same thing the sort already treated as oldest.
*Why:* "Newest" sorts on the folder's creation time, which is a stat of the hub's disk. A
client holding its own copy of the library cannot stat the hub's filesystem, so a sort that
worked locally had no input at all off the machine - it is the one ordering the wire could
not reproduce. The value is serialized rather than the raw epoch float so it reads the same
on a client in another timezone. Covered by `tests/curation/test_entry_lens_parity.py`.

**PAR-67 — The library and collections changing are on the event stream.** `game.changed`
and `collections.changed` now reach `GET /api/v1/events`. Both already fired in-process and
both keep doing so unchanged; this only adds the projection that puts them on the wire.
Purely additive - a client filtering with `?events=` is unaffected, and one taking
everything gets two more names it can ignore.
*Why:* a frontend on another machine cannot watch the files. Locally, `play_events`
subscribes to both and sends the windows back for the payload; remotely there was no
signal at all, so a copy of the library went stale with nothing to say so. Neither event
carries its path: the bus does, for handlers in this process, but the same collections file
is at a different path on the machine reading about it, and telling it one true only here
is worse than saying nothing. `game.changed` reuses the projection the other game events
use, so it names the game by id rather than by where it lives. Covered by
`tests/api/test_event_stream.py`.

**PAR-66 — A hub can hold a roster of the players it knows.** New: `common/device_registry.py`,
a `devices.json` beside the other config files, keyed by `install_id`. Nothing writes to
it yet and no screen shows it, so an existing install never grows the file and behaves
identically.
*Why:* two players answering one hub were indistinguishable at every layer until install
identity (PAR-52) and event provenance (PAR-55) landed; this is the place their answers
go. Keyed on `install_id` because it is the only thing about a player that does not
change - a display name is meant to be renamed and an address moves with DHCP, so a
roster keyed on either loses the player the first time somebody uses the feature.
`display_name`, `roles` and `address` are a cached copy of what that install last
reported and are refreshed on every sighting; `first_seen` is the roster's own and is not.
One entry is the degenerate case of many, so nothing treats a single player specially.
Data only: routing a launch to a chosen player, aggregating state and resolving conflicts
between them each need real design and none are needed to tell one player from another.
A field a newer build wrote is carried through rather than dropped, so a downgrade does
not silently strip it, and an unreadable roster reads as empty rather than refusing to
start - losing track of who a hub knew is recoverable, not starting is not. Covered by
`tests/api/test_device_registry.py`.

**PAR-65 — The API records whether a caller reached it from this machine.** Every identity
now carries an `origin` of `local` or `network`, decided by the request's own peer
address. **Nothing a caller may do changes**: a network caller keeps exactly the scopes it
had, so no install behaves differently and no request that worked stops working.
*Why:* the hub binds every interface by default and has since 2.x - that is deliberate,
so a phone can administer a cabinet - which means "on this machine" and "able to reach
this machine" have never been the same question, and nothing could tell them apart. Every
caller was identified as `local` whether it was or not, so a policy wanting to treat the
two differently had no fact to build on. This is that fact and nothing more; what a
network caller should be *allowed* is a separate decision with real user cost, since the
phone workflow the open bind exists for is the thing any restriction would land on. Split
out so the mechanism can be reviewed on its own rather than bundled with a policy nobody
has agreed. The peer address is read from the socket and never from `X-Forwarded-For`,
which the caller writes - trusting it would let anyone declare itself local, which is the
whole distinction. An in-process call with no socket reads as local, and `origin` defaults
to `network` so an identity that forgets to say cannot silently claim the machine.
Covered by `tests/api/test_caller_origin.py`.

**PAR-64 — A client cannot claim to be a window it is not.** The player channel refuses a
connection naming a window this process never opened, and refuses a second connection for
a window that already has one; both are closed with 1008. A real window is unaffected -
every one is registered before its browser launches, and a window whose socket dropped is
deregistered on the way out, so a genuine reconnect still fits.
*Why:* the channel read a window name out of the query string and believed it. Any name
was accepted, and a second client naming an open window *replaced* it -
`self._connections[window_name] = websocket` overwrote. The impostor then received the
real window's events and inherited its whole API surface, `shutdown_system` and
`build_metadata` included, while the real window carried on believing it was connected.
This was reached accidentally during a diagnostic session rather than found by reading:
a probe connecting as `window=scoreview` knocked the real scoreview window off its channel
several times before anyone noticed. The origin check from PAR-51 does not help here - a
page served from loopback passes it and can still take a window's name. No new mechanism
was needed: the set of valid names is already known before any browser starts. Covered by
`tests/theming/test_device_channel_identity.py`.

**PAR-63 — The port on 8001 is the hub's, not the Manager UI's.**
`network.manager_ui_port` is `network.hub_port` and `network.manager_ui_bind` is
`network.hub_bind`; the WebSocket method `get_manager_ui_port` is `get_hub_port`; the
window URL carries `hubPort=` and a theme reads `vpin.hubPort`. Every old spelling still
resolves - the config names through the same alias machinery that has carried
`manageruiport` since PAR-44, and the method through `_RENAMED_METHODS`, which forwards it
the way every renamed method is forwarded. Nothing about the port, the default or what
answers on it changes.
*Why:* the port was named after one of the four things listening on it. It serves
`/api/v1`, the Manager UI at `/`, and the remote and mobile pages - and the API is
explicitly not part of the Manager UI (`docs/http_api.md`: "it belongs to the platform").
So `endpoints.hub` and `endpoints.device` were being built from a port named for a UI,
which read as though the library were fetched from the Manager UI. What the four have in
common is the role: all of them are hub-side, the Manager UI included, since the Manager
UI is hub-only. Naming it `hub_api_port` would have repeated the original mistake from the
other end - naming one listener while three others share the port. One consequence is
visible and deliberate: `endpoints.device` points at the hub's port for now, because one
`/api/v1` still answers for both roles. That is honest about today's topology rather than
inventing an address, and it is the seam the remaining consolidation splits. Covered by
`tests/invariants/test_config_conventions.py` and `tests/invariants/test_parity.py`.

**PAR-62 — The endpoint block says what each address is for.** `vpin.endpoints` becomes
`{ hub, device, assets, frontend_channel }`. `assets` is new and is where media, theme
packages and shared art come from; `hub` now points at the API rather than the asset
server, which is where the library actually answers; `bridge` is `frontend_channel`.
Introduced in PAR-53 and corrected here before any theme reads it, so there is nothing to
alias.
*Why:* two of the keys were wrong and the third did not read. `hub` pointed at the asset
server on port 8000, but the library, collections and uploads are on `/api/v1` - so a
theme following the documented meaning would have asked the wrong service. The files are
a distinct thing worth naming, hence `assets`. `hub` and `player` are the same address
today because one `/api/v1` answers for both, and they stay separate keys because they
are separate questions: a theme built against them keeps working when the two are
separate machines. `bridge` said where the thing sat rather than what it was for, and
"the one case where transport and residency coincide" is a rationale rather than a name
anybody could read; `frontend_channel` names the surface that owns it, which stays correct
as other surfaces on a player arrive - `SURFACE_EXTENSION` is already declared alongside
`SURFACE_FRONTEND`. Three of the four are addresses a path is appended to; the fourth is a
line held open, and the block now says so rather than implying it is keyed by role when
one key never was. Covered by `tests/js/endpoints.test.js`.

**PAR-61 — `ws_bridge` is `device_channel`.** The `ws_bridge` module under `frontend/`
becomes `frontend/device_channel.py`, and `WebSocketBridge` becomes `PlayerChannel`. Internal
Python only: no theme imports it, the port is still `network.ws_port`, the window URL
still carries `?wsPort=`, and `vpin.endpoints.bridge` is unchanged. Nothing outside the
repo can tell.
*Why:* "bridge" was a 2.x migration artifact - the module docstring said it "replaces
legacy frontend's JS API bridge", so the name only ever meant "the thing between JS and
Python", which describes where it sits and nothing about what it does. That is why every
discussion of it had to re-explain it, and part of why the residency mix inside it went
unnoticed for so long. It is the connection between a player and its own windows: never
to a hub, never window to window. Renamed now rather than earlier because the name had to
wait for consolidation to settle what the channel contains. No alias is added - the old
name has no callers outside this repo, so one would be dead code on arrival.
*(`vpin.endpoints.bridge` keeps its name deliberately: the block is keyed by role, and
`player` there already means this machine's HTTP API. A second `player`-ish key would be
worse than the inconsistency.)*

**PAR-60 — The windows share one view instead of deriving the same one each.** The
library, the filter, the sort, the collection and the entry list move from the per-window
`API` instance onto a `View` the windows hold in common. Every WebSocket method keeps its
name, arguments and answers, and `API` exposes the same attributes it always did, so no
theme sees a difference. Measured on a 653-game library: three windows asking for the
payload at startup went from three builds and 108ms to one build and 32ms.
*Why:* a cabinet opens three windows onto one library and one selection, and each was
re-reading the library, re-sorting it, rebuilding its own entry list and serializing its
own 1.5MiB payload - three derivations of an answer that was identical by construction.
Only the controller window takes input (`vpinfe-core.js` gates `registerInputHandler` on
it), so only one of the three could ever change what all three were deriving; holding it
once makes that structural rather than a convention enforced in the browser on an
unauthenticated socket. One behavior change follows from it: a display window can no
longer hold a view that differs from the controller's, which was previously possible
after a channel drop and reconnect. That is the intended behavior rather than a
regression - the windows are showing one wheel. A refresh is coalesced, so the
`GameDataChange` broadcast that sends all three windows back for the payload re-derives
once instead of once per window. Covered by `tests/theming/test_shared_view.py`.

**PAR-59 — A theme's index is converted to a game before it leaves the window.** The five
index-taking WebSocket methods keep their names, arguments and answers; internally they now
resolve the index to an entry through one place (`API.entry_at`) and act on the game rather
than the position. `set_game_rating` writes through the same `set_game_rating` in
`common/games/game_metadata.py` the API uses, and returns the shape it always did. One behavior change, which is a fix: a negative index is refused instead of counting
back from the end of the list.
*Why:* an index is a position in *one window's* filtered list, so the same number names
different games in two windows filtered differently - which is why rating had no HTTP
equivalent and could not trivially get one. Converting at the boundary is what makes these
operations expressible by id, and it is the prerequisite for the hub half of the window
channel moving onto HTTP at all. `-1` previously reached `entries[-1]` and launched or
rated the last game in the list: Python's negative indexing answering a question a theme
counting up from zero never meant to ask. The duplicate rating implementation in
`frontend/game_state.py` is deleted rather than left beside the one in `common/`, so a
rating set from a theme and one set over HTTP are the same write. Covered by
`tests/theming/test_index_addressing.py`, which the five methods had no test of at all.

**PAR-58 — What a library can be filtered on is answerable over the API.** New:
`GET /api/v1/library/filters`, returning every filter axis with its scope, kind, summary
and the values this library holds. Additive - nothing is removed, and the window channel's
`get_filter_*` methods answer exactly as before.
*Why:* the five `get_filter_*` methods existed only on the window channel, which is
reachable by a theme window and nothing else, so no other client could learn what a filter
collection could filter by. The axes are projected from the same registry the resolver
matches on rather than listed again, so a client cannot be offered an axis nothing would
resolve, and an axis added there needs no second edit here. The values are the ones the
library actually holds, because a choice that matches nothing is not a choice. A `rating`
axis carries `null` instead of a list: it is 0-5 on every install, and enumerating the
ratings in use would offer a different scale to two libraries and a shrinking one as
ratings change. `filter_options` in `frontend/game_state.py` was a second copy of this
computation and now delegates to `GameListFilters.available_options()`, so the frontend
and the API answer from one implementation - a parity test asserts they agree. Covered by
`tests/api/test_library_filters.py`.

**PAR-57 — A game can be rated over the API.** New: `PUT /api/v1/games/{id}/rating`,
taking `{"rating": 0-5}` and carrying the `games:write` scope. `GET /games/{id}` reported
a rating already, so this is the write half of a field that was read-only; a rating set
from the frontend and one set here land in the same `User.Rating`, and nothing about the
frontend's own path changes.
*Why:* the only way to rate a game was the window channel, which addresses games by their
position in one window's filtered list - so no other caller could reach it, and the
asymmetry was the last real gap between the channel's hub half and the HTTP API. A rating
outside 0-5 is refused with a 422 rather than clamped, which is a deliberate difference
from `normalize_rating`: clamping is right when reading whatever a hand-edited `.info`
holds, and wrong for a caller that just sent 9, because storing 5 hides its bug. A whole
value PUT rather than a PATCH - the rating is the resource, so sending it twice says the
same thing rather than incrementing. The write itself moved to
`common/games/game_metadata.py` beside `game_rating`, and re-reads the `.info` first so a
rating set from one surface does not overwrite what another wrote while the copy was held.
Covered by `tests/api/test_game_rating.py`.

**PAR-56 — Shared services move out from under the Manager UI.** Nine modules move:
`game_service`, `game_index_service`, `media_service`, `asset_registry`,
`archive_service` and `export_bundle` to `common/games/`, and `upload_session_service`,
`asset_analyzer_service` and `asset_import_service` to a new `common/uploads/`. The four
things the Manager UI does to a player - enumerate displays, find the browser, read input
bindings, request a lifecycle change - go through `common/device_client.py` instead of
importing `frontend` directly. No behavior changes and no endpoint moves; this is where
the code lives.
*Why:* `httpapi` imported `managerui.services` at nine sites for game, archive, upload and
asset logic, and none of it was UI - business logic filed under a UI package, which is the
clearest layering break in the tree. It also made the incumbent UI privileged: a
replacement would have had to import it, which is a skin rather than a replacement. Of the
18 modules under `managerui/services/`, 17 imported no NiceGUI, so the logic was written
UI-independent and only filed in the wrong place. The move is by what a module knows about,
which is how `docs/common.md` already draws these boundaries; `uploads` is its own package
because it depends on `games` and nothing in `games` depends on it. The four `frontend`
imports were not a tangle either - they are a precise map of the player-administration
surface, so they became one interface that resolves in-process today and can resolve over
HTTP later, which is also the thing to authenticate once a hub administers a player over a
network. Both rules were prose that nothing checked, which is how they drifted; they are
now asserted by `tests/invariants/test_layering.py`.

**PAR-55 — Every event says which install it happened on.** Each payload on
`GET /api/v1/events` carries `install_id` alongside the fields it already had. Purely
additive: a client reading `state` or `job_id` is unaffected, and on a single-machine
install the value is the same on every event and can be ignored. It is absent rather than
empty when the install has no id yet.
*Why:* the bus is in-process and its wire projection drops the origin's address, both
correct while one process is one machine and both wrong the moment a hub holds more than
one player - a player's `table.launched` would arrive with nothing saying which player it
came from. The comment on the dropped field collapsed a distinction worth keeping: *which
surface asked* names one user's browser tab and stays dropped, while *which install it
happened on* is what a subscriber can act on and is safe to publish. Adding it to the
envelope rather than to each projection means a new event gets provenance by existing
instead of by remembering. Crossing the boundary - a player's events actually reaching a
hub - is a separate mechanism and is not built here; what is built is that the wire shape
can carry provenance when it is, rather than needing a breaking change then. The id is
read once and cached, because `_dispatch` runs on the publishing thread and reading it off
disk cost 2ms an event, which a launch and every `job.progress` tick would have paid.
Covered by `tests/api/test_event_stream.py`.

**PAR-54 — Each server's listening address is configurable, per port.** Two new settings,
`network.theme_assets_bind` and `network.manager_ui_bind` (renamed `hub_bind` by PAR-63,
which kept the old spelling working). Both default to what that
server already did - `127.0.0.1` for theme assets and table media, `0.0.0.0` for the
Manager UI - so nothing about an existing install changes until somebody sets one. The
window channel gets no such setting.
*Why:* the theme assets port answers this machine only, so pointing a browser on another
machine at a VPinFE install got nothing, and correcting the URLs it builds (PAR-53) only
gets a remote viewer as far as being refused. Making it configurable is what turns
"develop a theme from another machine" from broken into supported. An address rather than
a boolean, because binding one interface is a real case and `0.0.0.0` should not be the
only alternative to loopback. Deliberately per port and not one switch: this port serves
the table library, and the window channel reaches `shutdown_system`, `launch_game` and
`build_metadata`, so a single setting would mean anybody wanting to preview a theme
remotely also exposed machine control. That is also why the window channel has no bind
setting at all - it stays loopback until it can authenticate a caller, and adding the
setting before the auth would be offering the exposure. A blank value falls back to the
default rather than through to the socket layer, where an empty host means every
interface - the opposite of what clearing the setting looks like it means. Covered by
`tests/theming/test_asset_server_scope.py`.

**PAR-53 — The page is told where the services are, instead of asserting one machine.**
*(machine-checked)* `vpin.endpoints` gives a theme complete base URLs instead of a host to
assume - see PAR-62 for the keys it settled on - and the window URL now carries `themeAssetsPort` and
`managerUiPort` alongside the `wsPort` it already carried. Same values as before and the
same defaults when nothing says otherwise, so a single-machine install is unchanged.
`vpin.themeAssetsPort` keeps working and keeps its meaning; the block derives from it.
*Why:* `vpinfe-core.js` hardcoded `127.0.0.1` in six places - theme media, table media by
two path shapes, the manufacturer logo, the window channel and the Manager UI event
stream. PR #66 reported four; two more were added by 3.0's own media and logo work while
the report was open, which is the cost of the pattern rather than an accident. Six
assertions of one fact make a seventh easy to add and nothing notices. `window.location`
is not the fix: it replaces one one-machine assumption with another, and it fails only for
remote viewers, so it looks right on the machine it was written on. The block is keyed by
role rather than by transport because the window channel is one transport serving two
roles, so `assets`/`bridge`/`api` could not express "hub calls go there, player calls go
here" - it would encode the assumption it exists to undo. It is derived on read, so the
port correction the bridge sends during init reaches every URL built from it; resolving
once at construction made that correction land on the port and stop, which fails silently
whenever the default is also the right answer. Covered by `tests/js/endpoints.test.js`,
`tests/theming/test_chromium_manager.py`, and `tests/theming/test_render_smoke.py`, which
runs against ports chosen at random precisely so an assumed one fails.

**PAR-52 — An install has an identity of its own.** A new `[install]` section holds `id`,
`display_name` and `roles`. `id` is minted once on first start and written to the config;
`display_name` defaults to this machine's hostname and is not written down by reading it;
`roles` defaults to `hub,player`, which is what every existing install already is. All
three are additive to `GET /api/v1`, so no client breaks and nothing looks different to
anyone running one machine.
*Why:* `GET /api/v1` returned `"name": "VPinFE"` and nothing else, byte-identical on every
install, so two installs answering one hub were indistinguishable at every layer - no
field to address one, none to attribute anything to one. That is correct for the
one-to-one design 2.x had, and it is what has to change before a hub can hold more than
one player. The id follows `common/games/game_identity.py`, which already solved this
shape: opaque, minted explicitly, and reading never writes. Minting happens once at
startup rather than on a request, so discovery only reads and a read-only install is not
a bug report. `display_name` deliberately addresses nothing - renaming an install must not
break a roster, which is only true while nothing resolves through the name - and an
unreadable or misspelled `roles` falls back to both rather than to none, so a typo cannot
decide that a machine has stopped launching games. Covered by
`tests/config/test_install_identity.py`.

**PAR-51 — The window channel refuses connections from other pages.** A WebSocket
handshake carrying an `Origin` from anywhere but this machine is closed with 1008 instead
of being served. A real window is served from loopback and passes; a client that sends no
`Origin` at all - anything that is not a browser - is unaffected.
*Why:* the channel reaches `shutdown_system`, `launch_game` and `build_metadata`, and the
loopback bind was doing none of the work people assumed. A WebSocket handshake is not
subject to the same-origin policy the way `XMLHttpRequest` is, so any page open in any
browser on the machine could connect to `ws://127.0.0.1:8002` and call them. A browser
sets `Origin` itself and a page cannot forge it, which is what makes one comparison at
connect sufficient. Refusing a missing `Origin` was considered and rejected: it stops no
attacker, because a non-browser client already runs code on the machine, and it would
break scripts that legitimately drive the channel. Covered by
`tests/theming/test_device_channel_origin.py`, which asserts against a real handshake rather than only
the predicate.

**PAR-50 — The two roles are `hub` and `player`, and `acquisition` is `uploads`.**
Discovery's `residency` values change from `catalog` and `play_host` to `hub` and
`player`, and the capability named `acquisition` becomes `uploads`. `GET /api/v1` is the
only place these strings appear.
*Why:* `catalog` named one of the role's jobs rather than the role - `jobs` and `uploads`
are declared there and neither is a catalog - and `play_host` reads as dedicated hardware
when a laptop someone plays on is a player in full. `acquisition` was an abstraction over
something with a plain name, and the router was already `/uploads`. Done now because
nothing consumes these values yet: no client, no extension, and the frontend does not
resolve against discovery, so today it is two constants and eight declarations. Once
anything reads them it becomes a permanent alias, exactly like the config section rename
in PAR-44.

**PAR-49 — Core's own files are served at `/core/`, and `/web/` still works.** `web/` is
now `frontend/static/`, mounted at `/core/` - what core provides, against `/themes/` for what
a theme provides. Every published theme asks for `vpinfe-core.js` and `vpinfe-style.css` by
the `/web/` URL, so `/web/` stays mounted on the same directory: not a redirect, an alias, so
an un-updated theme keeps working and there is one copy of the files.
*Why:* `web/` was named for a technology rather than an owner, so it became the default home
for anything non-Python and collected files no browser ever asked for. The name said where the
files were, not whose they are. Nothing about the URL had to change for that, but leaving core
served from `/web/` while it lives in `frontend/static/` would mean the path and the URL
disagree forever. Verified against a real PyInstaller build rather than the suite - no test
exercises `--add-data`, and a wrong path here is a missing splash in a release artifact, not a
red test. Both URLs return the same 99,500-byte file from the frozen binary, and the theme
harness deliberately keeps one window on the old URL so the alias stays covered.

**PAR-48 — Quitting, restarting and powering off go through one place, and can ask
first.** `close_app` and `shutdown_system` keep their names and their behavior on a
default install; both now route through `common/lifecycle.py`, which addresses a request
by scope (`frontend`, `app`, `system`) and action (`start`, `stop`, `restart`). Themes get
`lifecycle_request` and `lifecycle_needs_confirmation`, and `vpin.requestLifecycle(scope,
action)` wraps both. The new `lifecycle.confirm` setting lists the scopes to ask about and
is empty by default, so nothing prompts unless it is turned on.
*Why:* there were four ways out of VPinFE and no path in common. Only a signal ran
`shutdown_services`, so quitting from a theme or the Manager UI lost the session's play
data before it reached VPinPlay; the frontend could power the machine off but not reboot
it; and the Manager UI's Remote page carried its own confirmation dialogs that no other
surface had. Two axes rather than four verbs makes reboot an ordinary member and makes
"open the windows on a headless instance" expressible at all. The question is put to
whichever surface asked - a dialog raised on the cabinet because somebody pressed
something on their phone is a hang on a screen nobody is watching - and every other
surface is told through `lifecycle.acting` without being able to block. A request that
cannot be asked, like a `SIGTERM`, proceeds; a surface that should answer and has gone
away denies. Covered by `tests/host/test_lifecycle.py`.

**PAR-47 — A superseded VPS override is set aside instead of deleted.** A manual
`alt_vpsid` match stops applying when the default table's hash changes, exactly as it did
before - matching falls back to `Info.VPSId` and every consumer resolves identically. What
changes is that the value moves to `vpinfe.alt_vpsid_previous` (`{value, table,
set_aside}`) rather than being overwritten with `""`. Only the most recent is kept, and
nothing resolves through it.
*Why:* the override is a user-typed correction to VPSdb matching, and deleting it was right
about the claim and wrong about the value. A file-hash change cannot tell a genuinely
different table from the same table updated to a newer build - and the newer build is the
common case, which is exactly when somebody is fixing the match. 2.x's own Manager UI
re-orders rebuild-then-save specifically to defeat the deletion and keep what the user
typed, which is the clearest evidence the storage was wrong rather than the workflow. The
Manager UI control that offers it back lands after 3.0, so today the value is on disk where
a hand-edit reaches it instead of gone. Covered by `tests/games/test_game_identity.py` and
`tests/invariants/test_parked_override.py`, the latter asserting no code path resolves an
id through the parked value.

**PAR-46 — An upload can say what its files are, instead of being guessed at.** The import
endpoint accepts a `declared` map, keyed by the name each file arrived under, carrying
`vps_file_id` + `host_item_id`, `game_id`, `table_id` and `confirmed_by`. What is declared is
written into that file's `source` block in the `.info`. Purely additive: an empty body imports
exactly as before, and a caller that says nothing records nothing. In the Manager UI the drop
target is the declaration - letting go on a game row names that game - so no dialog asks again
for what the gesture already said.
*Why:* whatever delivered the bytes knows what it asked for, and VPinFE was throwing that away
and re-deriving it afterwards. That inference was measured at 32% top-1 against 32% random and
57% confidently wrong, which is why identification is observation-only. `confirmed_by` is the
caller's *basis*, never a policy flag: the accepted set is `declared` (it fetched the file from
that record) and `user` (a person picked it), with **no value meaning "I guessed"** - a
`confirm: false` parameter would have let a client skip the human by asserting confidence it
had not earned. A weaker claim never overwrites a stronger one, and an equal one does not
either, so re-importing the same file does not churn the file. Written client-neutral: the API
takes a declared identity and does not know what produced it. Covered by
`tests/curation/test_declared_identity.py`.

**PAR-45 — The browser is told which ports to use instead of assuming them.**
*(machine-checked)* One WebSocket method is added, `get_manager_ui_port` (renamed
`get_hub_port` by PAR-63, which kept the old name forwarding), and the bridge's
own port now travels in the window URL as `?wsPort=`. Purely additive: a theme never calls
either, and both fall back to the values they assumed before.
*Why:* `network.ws_port` and `network.manager_ui_port` are settings the browser ignored.
`vpinfe-core.js` hardcoded 8002 for the bridge and 8001 for the Manager UI event stream, so
changing either port left the frontend dialling the old one - a blank frontend in the first
case and remote-launch overlays that silently never appear in the second. The bridge port
cannot be fetched over the bridge, so it is the one value that has to arrive in the URL;
the `/app/` bootstrap and the splash page already forward the query string, so it survives
every path a window opens by. Covered by `tests/theming/test_render_smoke.py`, which runs
against ports chosen at random precisely so an assumed one fails.

**PAR-44 — Config sections are snake_case, and `[Settings]` is `general`.** The nine
PascalCase sections and the one kebab-case section are renamed: `Settings` to `general`,
and `Displays`, `Logger`, `Media`, `Mobile`, `Network`, `State`, `VPSdb`, `DOF` and
`pinmame-score-parser` to their snake_case spellings. Every key was already snake_case, so
this is the section line alone. Every former section name resolves permanently, in the
same way renamed keys have since PAR-37, and an existing file is rewritten in place on
first read - a `vpinfe.ini` from any 2.x build and a `vpinfe.json` from any 3.0 build both
convert without losing a value. A new `cfg_set` writes through the same resolution reads
have used since PAR-37, so a caller naming a section by an old name no longer writes a
second copy of the setting under it.
*Why:* `docs/conventions.md` mandates snake_case for JSON and the settings file is JSON,
but only the keys were ever brought over - leaving a file that disagreed with itself line
by line, `settings.Settings` reading as a mistake in the envelope, and every new section
a guess about which convention applied. The names are now asserted rather than
remembered: `tests/invariants/test_config_conventions.py` fails on a section or key that
is not snake_case, and checks every legacy spelling against a frozen list rather than
against the schema - because iterating the schema would delete the assertion along with
the alias it guards, and pass. Covered by that file and
`tests/fixtures/config_legacy_names.json`.

**PAR-43 — Themes can come from more than one place, and a repository can be a theme on
its own.** A new `themes` config section holds two lists: `registries`, catalogs to read
`themes.json` from, and `repositories`, individual theme repos each treated as one theme.
A theme is named by whoever chose the name: the entry's own `name` where the registry
shape carries one, the registry key in the shape published today, and `manifest.json`'s
`name` for a bare repository url, which names nothing on its own. Repositories resolve
before registries and the first mention of a name wins, with the loser logged; because a
repository's name is not known until its manifest arrives, that contest is settled in
source order rather than in whichever order the network answered. A repository
may carry `#<ref>` to pin it to a branch or tag, which overrides release selection but
still honors the contract of a declared line serving that ref. The stock
registry is an ordinary entry in `registries` rather than a constant, so it can be
reordered, mirrored or dropped; an install listing nothing loads no catalog and still runs
its installed theme, while an install whose every listed source fails is an error. Neither
list appears in the Manager UI - a source is a URL VPinFE fetches and installs code from,
so it stays a deliberate edit. Refs are now spelled bare in every URL we build
(`v2`, not `refs/heads/v2`), and `HEAD` is no longer rewritten to `master` - so the source
archive for a theme with no declared release line is `archive/HEAD.zip` rather than
`archive/refs/heads/master.zip`. That is the same commit either way and the extracted
folder is found by diffing the directory rather than by name, so all twelve published
themes install exactly as before.
*Why:* the registry URL was hardcoded to one repository on GitHub, so a theme could only
be installed by its owner publishing it there - which makes private, in-development and
site-local themes uninstallable, and leaves an offline or mirrored cab fetching an
internet URL it cannot reach. The ref spelling is the same problem one layer down: GitHub
serves `/raw/refs/heads/x/` and 404s on Forgejo's `/raw/branch/x/`, Forgejo does the
reverse, and bare is the only form both resolve - so before this a non-GitHub theme worked
only while its release sat on the default branch, and silently vanished from the list the
moment it declared a branch per contract, which is the layout `theme_publishing.md`
recommends. The `HEAD`-to-`master` rewrite is the same problem: GitHub quietly falls back
to the default branch when `master` does not exist, so it cost nothing there, but Forgejo
returns 404 and it would have broken every repository not defaulting to `master`.
Where a theme came from does not decide what it may install - a repository resolves
through the same contract gate a registry entry does. Covered by
`tests/theming/test_theme_sources.py` and `tests/theming/test_theme_releases.py`.

**PAR-42 — A theme can publish one release per contract, and the registry stops
gating that.** A theme repository may carry `vpinfe-theme.json` on its default branch
listing its release lines - a contract and the ref serving it. VPinFE installs the highest
contract it can run, taking that line's `manifest.json` and source archive from that ref,
and does not offer a theme whose only release needs a newer build. A repository without
the file is read exactly as before: one contract 1 release, `manifest.json` on the default
branch. All twelve published themes are that case and resolve unchanged.
*Why:* contract 2 splits the theme population, and the registry entry named a single
manifest URL - so an author moving to contract 2 broke every installed 2.x client, and the
only alternatives were registering a second theme or asking the registry owner to
re-point the entry on every release. Neither scales, and neither is the author's to
control. Identity belongs in the registry, which is written once; what changes per release
belongs in the author's own repository. A 2.x build ignores the file and installs
`master.zip` regardless, so an author keeps those installs working by leaving contract 1
on the default branch and putting contract 2 on a branch - which is what
`theme_publishing.md` now recommends. Covered by `tests/theming/test_theme_releases.py`.

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

**PAR-24 — Window messages do not rename. Withdrawn.**
`TableIndexUpdate`, `TableDataChange`, `TableLaunching`, `TableRunning` and
`TableLaunchComplete` briefly became the `Game*` spellings, broadcast under both names.
They are back to the single spelling 2.x published, so there is nothing to translate and
no dual send: a message names a row, and a row is a table.
*Why it is still listed:* the entry described a promise, and withdrawing it is part of the
record. The alias machinery stays in `vpinfe-core.js` and `frontend/play_events.py` with
nothing in it, because the next message rename is what fills it again.

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

**PAR-40 — Input actions are named for intent, and a binding names its own device.**
The twelve `joy*` actions become ten: `previous`, `next`, `page_previous`, `page_next`,
`select`, `back`, `menu`, `collection_menu`, `tutorial`, `exit`. `joyup`/`joydown` and
`joypageup`/`joypagedown` were one intent under two names - carousel-desktop used up and
down for a page-sized jump - so they merge, which is also what fixes that theme's dead
paging cases.

Each action now holds **one ordered list of bindings** rather than a key per device:
`previous = key:ArrowLeft,key:ShiftLeft,pad:0/button:3`. The two-key shape existed only
because a stored value could not say which device it came from, and a `key:`/`pad:`
selector says it. That is the front of the binding grammar, so modifiers, axes,
`@hold:<ms>` and `chord(a+b)` are later *selectors in this same list* - a parser change,
not another migration. One WebSocket method is added, `get_bindings`; `get_keymapping`
and `get_joymaping` still answer, projected out of the lists.

**A contract 1 theme sees none of it.** Core dispatches the current names and translates
at the theme boundary, so every `case "joyleft"` in the twelve registry themes keeps
matching. Existing `[Input]` keys migrate into the lists on first read (schema 3) and
keep resolving afterwards.
*What it costs someone:* a contract 1 theme that handled `joyup` for something other
than paging loses it, because up is a paging action now and core answers paging by
default. Revolution and Trinidad do: both put a collection list in the wheel, and with
core paging on, up and down page the game list underneath it and broadcast the move,
which both read as the selection changing. Picking a collection with the flippers drops
back to the games. carousel-desktop routes every direction through one function that
checks which list is showing, so it is unaffected. Covered by
`tests/theming/test_input_actions.py` and `tests/js/input.test.js`.

**PAR-41 — Core moves the wheel, and a dialog can own the keys.**
`core_navigation` is a capability, **on for a theme that declares `min_vpinfe: "3.0"` and
off for one that does not**, so at contract 2 `previous` and `next` move the selection in
core: it wraps, sets the index, broadcasts `TableIndexUpdate` and fires the selection
listeners.

It is off below that because core taking those two actions is not invisible to a theme
that already uses them. Revolution, Trinidad and carousel-desktop move their own
collection list with `previous`/`next`, and core consumes the press before the theme's
handler runs - so the picker exits onto whatever game the broadcast landed on. Those themes
run on 2.x as well, which is exactly what declaring an older minimum says. A theme that has
not moved yet but does want core navigation declares `navigation.enabled: true` in its
`theme.json`; that is the only opt-in, and there is no `enableCoreNavigation` method.
**At contract 2 paging is part of it.** `previous`, `next` and the two paging actions are
one capability with one key, because they are one concern: a page is a bigger step, not a
different feature. Below contract 2 they stay separate, and they have to — 2.x core pages
for a theme but leaves its cursor alone, so the two need opposite defaults there. That is
the whole of what `core_paging` is for now, and it retires with contract 1. A theme that
declares `paging.enabled: false` gets what it asked either way.
*Why:* all four themes read reimplemented the same wrap-and-broadcast, two of the
installed three shipped the same undefined-index bug in it, and the Reference theme -
written to demonstrate best practice - could not avoid the boilerplate either. When the
exemplar cannot avoid it, it belongs to core. The broadcast now carries `previous`,
`direction` and `moving`, which is also the fast-scroll signal a theme needs to decide
whether to load full art or wait.

Alongside it, an **input mode stack**: `navigation`, `modal` and `text`. A dialog pushes
one and the actions stop reaching what is behind it. That is what makes the collection
menu's save-filter dialog completable from a cabinet - it had no such state, so the arrows
drove the menu underneath and Enter fired select and opened a dropdown instead of reaching
the field. Covered by `tests/js/input.test.js`.

**PAR-84 — Five sort and filter methods leave the theme API.**
`apply_filters`, `apply_sort`, `get_current_filter_state`, `get_current_sort_state` and
`get_current_order_state` are still dispatched, so the collection menu VPinFE ships keeps
working, but they are out of `docs/theme.md` and `vpin.call` refuses them by name. A theme
that calls one gets the same `Method not allowed` it would get for a name that was never
in the allowlist, plus a console line and a line in the log on the machine.
*Why:* `frontend/api.py` carried one flat allowlist and said in its own docstring that
adding a name to it adds to the theme surface, so core had no way to have a private call —
and these five exist only for core's own collection-menu overlay. Not one of the twelve
themes in the registry calls any of them, so there is nobody to break today; ship 3.0 with
them published and that stops being true. Once core owns the list the wheel steps through
it owns sorting too, and they stop being a bridge concern at all.
*What this does not do:* a theme's iframe is same-origin and can reach whatever the
overlays reach if it goes looking. This is not a sandbox and does not try to be. It moves
the five from documented and allowed to deliberately circumvented. The refusal is logged
rather than silent because the measurement covers the registry, and a theme installed from
somewhere else is outside it.
PAR-82 noted that a theme reading `get_current_sort_state` can see `"Manual"`; that read
is core's own now. Covered by `tests/invariants/test_theme_api_surface.py` and
`tests/js/internal-methods.test.js`.

**PAR-86 — One overlay string replaces three booleans, and nine old names still answer.**
`vpin.overlay` names the open overlay, or is `null`. It replaces `menuUP`,
`collectionMenuUP` and `tutorialUP`, and `toggleOverlay(name)` and
`registerOverlayHandler(name, handler)` replace the three toggles and three registration
methods that each named one overlay. All nine keep working: the booleans read the string,
and the six methods call the new pair with the overlay's name already supplied. They are
derived rather than forwarded, so they are not in the renamed-members map.
Each overlay is also told `{event: "overlay_open", overlay, context}` when it opens and
`{event: "overlay_close", overlay}` when it closes; the older `menu_open`, `tutorial_open`
and `reset state` messages are still sent behind them.
*Why:* at most one overlay is ever up - opening one closes any other - so three
independent booleans could only ever disagree, and every consumer re-derived which was
open. Adding a fourth overlay meant eleven edits across JavaScript, CSS and Python.

**PAR-85 — The paging actions are `page_previous` and `page_next`, and page-up now pages
backward.**
PAR-40 renamed the directional actions to say what the player meant and stopped one row
short: `page_up` and `page_down` kept their key names. `page_up` is now `page_previous`
and `page_down` is `page_next`. The 2.x spellings — `joypageup`, `keypageup`, `joyup`,
`keyup` and their down counterparts — keep resolving, and a contract 1 theme still
receives `joypageup`/`joypagedown`. `page_up` and `page_down` are not carried: they only
ever existed in 3.0, which has not shipped, so a config holding one falls back to the
default binding for that action.
*Why:* "page up" has no answer on a horizontal wheel, and core gave two — `page_up` moved
*previous* in the main menu and the collection menu and *next* in the wheel's paging, in
the same branch. Two themes, in two repos, independently read it the wrong way and shipped
paging that ran backwards to real cabinets. No test could catch that: the themes live in
different repos from the convention they have to match. A name that states the intent
leaves nothing to get backwards.
*What you will notice:* the default bindings are unchanged — `PageUp`/`ArrowUp` and
`PageDown`/`ArrowDown` — but they now mean previous and next, so **page-up moves the wheel
backward** where it used to move forward. That direction was the odd one out: the same key
already moved *up* a menu in both overlays. Swap the two values in `[input]` to get the old
feel back. ArrowUp and ArrowDown keep moving up and down in the menus. Covered by
`tests/js/input.test.js` and `tests/theming/test_input_actions.py`.

**PAR-87 — Digits and symbols are one letter group, `#`, for filtering as well as paging.**
Master had two definitions of "a letter". Paging bucketed a title starting with anything
other than a letter into `#`; the filter compared the first character literally, and the
picker listed that character raw. So a game called `300` paged under `#`, was offered as
`3` in the picker, and selecting `3` matched it while `#` did not. `letter_of` is now the
one definition, used by paging, by the filter, and by the list of letters offered.
*What it costs someone:* a filter collection saved under 2.x with a digit or symbol as its
letter — `letter = 3` — now matches nothing, where it used to match the games starting with
that digit. Re-save it against `#` to get those games back. The picker no longer offers
digits, so this cannot be created going forward.
*Why:* the two definitions could not both be right, and the filter's was the one that
disagreed with what the user saw on the wheel. Keeping it would have meant paging to a
group the filter cannot express, which is what group paging needs to work at all. Covered
by `tests/curation/test_collection_filters.py` and `tests/theming/test_paging.py`.

**PAR-88 — A page press is grouped by the sort, and a collection may say otherwise.**
Master paged by letter only when the sort was alphabetical, and stepped a fixed number the
rest of the time without saying so. A press now moves to the next group in whatever the
list is ordered by — the next letter under title order, the next year under year order —
and where an order gives every table its own value there are no groups, so it moves a fixed
number. The `[frontend]` setting is `paging_group`, `sort` or `count`; the 2.x spellings
`alpha` and `numeric` still resolve, to `sort` and `count`. A collection can override the
player's choice in its `order` block, and says nothing there by default, so changing the
player setting still reaches every collection that never expressed a preference.
*What it costs someone:* nothing chosen in 2.x stops working — `alpha` and `numeric` both
carry over and mean what they meant. What changes is that a collection ordered by year or
rating now pages by year or rating, where master stepped.
*Also added:* one WebSocket method, `get_paging_state`, so the collection menu can say what
a press will do. It is refused to themes — core's own overlay is the caller. Covered by
`tests/theming/test_paging.py`, `tests/curation/test_order_direction.py` and
`tests/invariants/test_theme_api_surface.py`.

## Explicitly *not* exceptions

The theme-facing payload (`tables_json` keys, media path fields, stable values) and
the on-disk library after a plain scan are asserted **identical** to master. Scans
never write; only the PAR-01/02 first-run migrations do.

The alphabetical sort that ignores a leading "The" is master behavior (shipped
there in July 2026), not a 3.0 change.

## Retiring the gate

The gate is scaffolding for the transition and it dies with it: once this branch *is*
master, there is nothing left to compare against. Whoever does that merge should delete
`tests/invariants/test_parity.py`, `tests/support/parity_capture.py` and `tests/fixtures/parity_baseline_master.json`,
and drop the `!tests/fixtures/parity_baseline_master.json` line from `.gitignore` — it only exists
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
`tests/js/media-resolution.test.js` and `tests/media/test_asset_registry.py`.

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

