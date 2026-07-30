# 3.0 compatibility ledger

3.0 is plumbing and housekeeping; the goal for existing users is that they notice
nothing. This file is the complete list of deliberate exceptions — every way 3.0 is
*allowed* to differ from master, each with why it's worth it.

It is enforced, not aspirational: `tests/test_parity.py` compares this tree's
behavior against a captured master baseline (`tests/parity_baseline_master.json`),
and a difference is either named here by its `PAR-` id or the build fails. There is
no third option. Entries marked *(machine-checked)* are asserted directly by the
parity test; the others are covered by the tests referenced in their entry.

To refresh the baseline after master moves:

```
git worktree add /tmp/parity-master master
cd /tmp/parity-master && python <this-tree>/tests/parity_capture.py --out <this-tree>/tests/parity_baseline_master.json
git worktree remove /tmp/parity-master
```

## The exceptions

**PAR-01 — First run writes `VPinFE.id` into `.info` files.**
Every table gets a stable id, minted once and persisted. One-time, versioned via
`VPinFE.schema`; files written by a newer build are left alone. Users see a burst of
`.info` writes on first 3.0 start and nothing after.
*Why:* an id-addressed API, events and collections need an identity that survives
renames and table updates, which VPSId cannot provide. Covered by
`tests/test_table_identity.py`.

**PAR-02 — First run rewrites `collections.ini` membership onto table ids.**
One-time migration, keyed by a schema version so it runs once; entries that don't
resolve are kept rather than dropped.
*Why:* membership keyed on VPSId was orphaned by an ordinary `.vpx` update. Covered
by `tests/test_collections_rekey.py`.

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
file the table's own metadata describes, with a deterministic fallback.
*Why:* three code paths chose three different files, so the metadata a user saw
could describe a different table than the one that launched. Covered by
`tests/test_game_files.py`.

**PAR-06 — Launches from the Remote page and the API now record play data.**
Start count, Last Played, runtime, NVRAM score — previously only wheel launches
recorded any of it.
*Why:* this was a bug; a play is a play regardless of who started it. Users will see
those launches start counting. Covered by `tests/test_launch.py`.

**PAR-07 — The frontend subscribes to launch state instead of polling it.**
One held SSE connection replaces a request every second. Same overlay behavior;
different network pattern for anyone watching traffic.
*Why:* the poll was the only reason `/api/remote-launch` existed; the event stream
serves every future consumer too. Covered by `tests/test_event_stream.py`.

**PAR-08 — The log is much quieter at INFO.**
The logging standard moved routine chatter to DEBUG and gave each level a promise.
*Why:* INFO was unreadable on a real library; a level that promises nothing is
noise. Not machine-checked — prose only.

**PAR-09 — Media resolves through a precedence chain and accepts extension families.**
Master resolved exactly one fixed name per kind (`wheel.png`). 3.0 resolves
`(Wheel) <game-file>.png` over `(Wheel) <folder>.png` over `wheel.png`, trying each kind's
extension family in order — so a spec-named or `.jpg` file that master silently ignored
now displays. A library using only the fixed names behaves identically.
*Why:* hand-placed media was invisible unless it matched one exact name, and a media
refresh could clobber a user's own file; the tiers make "mine" and "downloaded"
structurally distinct. Covered by `tests/test_media_resolution.py`.

**PAR-10 — Imported media keeps its real file extension.**
Importing a `.jpg` wheel used to write JPEG bytes into `medias/wheel.png` — a file that
lies about itself. It now writes `wheel.jpg`, and removes same-kind siblings that would
shadow it.
*Why:* the on-disk name should tell the truth; browsers sniffed past it, other tools
won't. Covered by `tests/test_media_resolution.py`.

**PAR-11 — Six new media kinds: rulecard, topper, topper_video, loading, audiolaunch,
rulesheet.**
*(machine-checked)* Themes gain six payload fields (`RuleCardImagePath`, `TopperPath`,
`TopperVideoPath`, `LoadingVideoPath`, `AudioLaunchPath`, `RuleSheetPath`); every existing
field is unchanged. The rule card is the apron instruction card image, distinct from the
flyer (promo art) and the rulesheet (a document you read); loading is the loading-screen
video; audiolaunch plays when a table starts.

Topper is two kinds, not one with a mixed extension family. `bg`, `dmd` and `table` each
split image and video into separate specs sharing a token, and the resolver is built that
way — the token names the kind, the extension family picks image or video. Topper was the
exception, so `topper.png` and `topper.mp4` collapsed onto one key and a cabinet could
hold a still or a video, never both with the video preferred. It now mirrors the others:
`(Topper) x.png` resolves to `topper`, `(Topper) x.mp4` to `topper_video`.
*Why:* the spec names these and tools ship them; adopting the tokens means media that
circulates for other frontends works here unchanged. Covered by
`tests/test_media_resolution.py`.

**PAR-12 — `logo` is its own media kind, and the wheel falls back to it.**
*(machine-checked)* `logo.png` used to import as a wheel; it now imports as the game's
logo, its own slot with the full chain (token `(Logo)`). A table with a logo and no wheel
shows the logo wherever the wheel would appear — themes, Manager UI, API — because the
fallback lives at the bottom of the wheel's resolution, below every real wheel tier. The
API marks such a wheel `via: "logo"`. Themes gain `LogoImagePath`.
*Why:* the logo is usually the source a wheel is derived from, so showing it beats a
blank slot everywhere at once; making it a kind keeps it addressable instead of buried in
wheel semantics. Covered by `tests/test_media_resolution.py`.

**PAR-13 — A table export is one game by default, not the whole folder.**
The `.vpxz` download and the mobile Web Send used to ship everything: every alternate
game file, all media, every extra. The default is now a standalone bundle for the table's
game file — the chosen `.vpx`, its stem-matched and folder-named companions, `pinmame/`,
`music/`, colorization and sound folders, the author's readme files, and a `.info` whose
`Medias` section lists only what actually shipped. The whole-folder form remains
available to callers through the API (`?full=true`), under its own permission scope.
*Why:* export a game, not a folder — transfers shrink dramatically, and a multi-`.vpx`
folder finally exports the game file you meant instead of all of them. Covered by
`tests/test_export_bundle.py`.

**PAR-14 — Readme files import, display, and travel with the table.**
Files named `readme*` (any extension) and `.nfo` used to fall into the import dialog's
"didn't recognize these" list and were never copied. They're now detected, shown inline in
the import confirmation so the author's notes are readable before anything is written,
copied to the table folder root under their original names (on by default), and included
in the standalone export bundle. Detection is deliberately narrow — never a blanket
`.txt`, which would misfile `alias.txt` and its kin.
*Why:* whoever made the table wrote those notes for whoever installs it; now they arrive.
Covered by `tests/test_asset_upload_services.py` and `tests/test_export_bundle.py`.

**PAR-15 — Manufacturer logos, served from a shared assets root.**
*(machine-checked)* Themes gain one payload field, `ManufacturerLogoPath`: a
`/assets/`-relative web path to the table manufacturer's logo, or `null` when there is
none — which is every install today, since nothing ships and nothing downloads yet. The
assets root is `[Settings] assetsdir` (default: `assets/` under the config dir), served
at `/assets/`, with `manufacturers/user/` overriding `manufacturers/default/`. Lookup
normalizes the VPSdb manufacturer string ("Williams Electronics" finds `williams.png`)
with a `manufacturers.json` alias map for the exceptions.
*Why:* manufacturer is already a first-class metadata and filter dimension; themes just
had nothing to render for it. A shared root exists because a manufacturer logo is neither
per-table nor per-theme. Covered by `tests/test_shared_assets.py`.

**PAR-16 — Game files can be hidden, and several are peers rather than one default.**
A table folder can hold more than one launchable `.vpx` — a desktop game file and a VR build,
or a table and a patched variant. Every visible one is independently launchable; there is
no primary-with-alternates. The `.info` gains a `GameFiles` section keyed by filename
(`{"hidden": true}`), absent meaning visible, so an existing library is unchanged. The
game-files API response gains `hidden`.

`default` in that response no longer means "the one to launch". It names the file the
table's metadata was derived from, which is what export and the metadata build need when
they have to pick one. Consumers listing what to play should filter on `hidden`.
*Why:* applying a patch leaves the base table on disk — it has to stay, since the patched
table cannot be rebuilt without it — but nobody wants to be offered it. Deleting it would
be the wrong fix. Covered by `tests/test_jdiffpatch.py`.

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
`tests/test_vpsdb_media.py`.

**PAR-18 — Addon folders are detected whatever their casing.**
The library scan matched `pupvideos`, `serum`, `vni`, `music` and `medias` against the
folder name exactly as stored, so a folder named `PUPVideos` — the casing PinUP Popper
itself writes — was not detected. The API had always lowercased before comparing, so the
same table reported a PUP pack there and none in the Manager UI and themes. The scan now
folds case too. Tables whose folders are not all-lowercase will start reporting addons
they always had (`pupPackExists`, `altColorExists`, `vniExists`, `altSoundExists`).
*Why:* one table cannot have two answers, and the scan was already case-insensitive about
`.directb2s` and `.ini` three lines away. Covered by `tests/test_media_resolution.py`.

## Explicitly *not* exceptions

The theme-facing payload (`tables_json` keys, media path fields, stable values) and
the on-disk library after a plain scan are asserted **identical** to master. Scans
never write; only the PAR-01/02 first-run migrations do.

The alphabetical sort that ignores a leading "The" is master behavior (shipped
there in July 2026), not a 3.0 change.

## Retiring the gate

The gate is scaffolding for the transition and it dies with it: once this branch *is*
master, there is nothing left to compare against. Whoever does that merge should delete
`tests/test_parity.py`, `tests/parity_capture.py` and `tests/parity_baseline_master.json`,
and drop the `!tests/parity_baseline_master.json` line from `.gitignore` — it only exists
to punch the baseline back through the blanket `*.json` rule, and removing the file
without it leaves a dangling negation.

This file stays. By then it stops being a gate and becomes the list of what changed in
3.0 and why: upgrade notes for anyone coming from 2.x, and the first place to look when a
theme or an API consumer breaks.
