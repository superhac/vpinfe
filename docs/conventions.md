# Coding Conventions

These follow the standard conventions for each language rather than anything invented here.
Where the existing code disagrees, the existing code is the thing that changes — but only when
it is being touched anyway, not in a sweep.

`ruff` enforces the mechanical half. See [Linting](#linting) for what is advisory and what is
blocking.

## Naming

### Python — PEP 8

| Thing | Convention | Example |
|-------|-----------|---------|
| Functions, methods, variables | `snake_case` | `table_id`, `ensure_unique_ids` |
| Modules and packages | `snake_case` | `game_identity.py`, `httpapi/` |
| Classes | `CapWords` | `MetaConfig`, `TableParser` |
| Exceptions | `CapWords` ending in `Error` | `NotFoundError`, `InvalidRequestError` |
| Constants | `UPPER_SNAKE_CASE` | `API_PREFIX`, `CURRENT_VPINFE_SCHEMA` |
| Internal helpers | leading underscore | `_catalog()`, `_resource()` |

Python does not use camelCase. PEP 8 permits it "only in contexts where that's already the
prevailing style, to retain backwards compatibility" — which is why `gameDirName` still
exists. It is legacy, not the standard.

The distinction that decides these: a camelCase name **a theme reads** is a contract and
stays, because renaming it costs every theme a change. A camelCase name that never leaves
Python is just old, and `MetaConfig`'s was retired in 3.0 — `metaConfig`, `writeConfigMeta`
and the rest are snake_case now. `gameDirName` is in the contract 1 payload, so it stays.

### JavaScript

`camelCase` for variables and functions, `PascalCase` for classes. JS reading a snake_case
JSON field is normal and needs no translation layer:

```javascript
const uploadId = (await begin.json()).id;
const summary = await (await fetch(`/api/v1/uploads/${uploadId}`)).json();
console.log(summary.total_bytes);
```

### JSON over HTTP

`snake_case`. There is no single industry standard here — camelCase is common for
JavaScript-facing APIs, and snake_case is equally standard (GitHub, Stripe and Slack all use
it). snake_case wins for this codebase because it matches Python, so nothing is translated at
the boundary, and it matches the JSON the app already returned.

### Spelling

US English, in identifiers, comments and docs alike — `color`, `analyze`, `behavior`,
`authorization`. The codebase is already consistent about it, and `config_access.py` even
maps `colour` → `color` on the way in, so the choice is settled rather than open.

It matters most in a field name: `alt_color` is part of the API contract, and a spelling
change there would be a breaking change for a caller.

### Config keys

`vpinfe.ini` keys are lowercase and unseparated (`gamerootdir`, `manageruiport`). That is
established and user-facing; leave it alone.

`.info` keys are `snake_case` in the sections we own — `vpinfe`, `tables`, `assets`,
and so are those section names.
`Info` and `User` keep PascalCase: other frontends read them, so their shape is a contract
rather than a style choice.

### The nouns, in identifiers

`## Vocabulary` below defines them. In code: `game_dir` is a game's folder and
`game_dir_name` is that folder's name; `game_root_dir` is the library holding them;
`vpx_path` is a table file. A playfield is never `table`.

`tests/invariants/test_game_and_table_names.py` checks this by meaning rather than by
spelling - it calls the launch builder to confirm the argument named for a table really is
what the launcher is handed. Two passes got it backwards before that test existed, and the
second did it while fixing the first, because both stated the rule as a shape - which names
refer to the folder - and a shape cannot see the case that contradicts it.

### Kind, not type

A closed set of named variants is a **kind** — media kinds, job kinds, asset kinds, the
kind of control a filter wants. `kind` in identifiers, in the JSON we write, and in the
fields we serve.

`type` is for the places somebody else already chose the word, and only those:

- Python's own: `type()`, `isinstance`, `typing`, `TypeVar`.
- HTTP and HTML: `Content-Type`, Starlette's `media_type=`, `<input type=>`.
- A library's parameter: NiceGUI's `ui.notify(type=...)`.
- A key already on disk. `Info.Type` is in every `.info` a user has, so `game_type` reads
  it and keeps that word end to end. Translating at the boundary would leave a reader
  converting in their head at every call site, which is worse than one name that says
  where it came from.

The cost of not picking one is measurable rather than theoretical. `MEDIA_SPECS` and
`MEDIA_TYPES` were the same closed set of media kinds under two words, one module
importing the other, and the second had fallen seven kinds behind before anything noticed
- which cost a KeyError on upload and an empty filename on lookup, in the two kinds people
replace most. There is one list now.

## Things we version

Three, each versioning a different kind of thing, each with its own word:

| what | versions | where |
|---|---|---|
| `.info` | a **file's shape** we write and read back | `vpinfe.schema` |
| HTTP surface | a **wire protocol** we serve | `/api/v1` |
| theme surface | an **interface handed to somebody else's code** | the contract, implied by `min_vpinfe` in a theme's `manifest.json` |

They stay separate words because they answer different questions and move on different
triggers — a `.info` reshape says nothing about the HTTP API. `schema` is deliberately not
reused for themes: a schema describes data, and the theme surface is data plus methods plus
events.

One rule across all three, which is the consistency worth having:

> **Additive changes never bump a version. Only a removal or a reshape does.**

New fields, new endpoints, new methods are visible at every version and consumers
feature-detect them. That is what keeps bumps rare enough to be worth doing properly.

## Layout

- A new subsystem gets its own top-level package, not another module in `common/`. `httpapi/`
  is the current example.
- Keep `common/` UI-independent.
- `common/` is a layer, not a bucket. Domain code goes in `common/games/`, `common/online/`
  or `common/host/`; `common/` itself holds only what knows nothing about any of them, and may
  never import from those packages. See `docs/common.md`.
- Route handlers stay thin. Logic belongs in a service where the other callers can reach it.
- Files we ship that are not Python live in `<owner>/static/` — `frontend/static/` for what a
  browser fetches, `managerui/static/` for the Manager UI's, `common/host/static/` for what
  goes to hardware. Named for who owns them, so a directory does not become the home for
  anything that has no other one.
- `scripts/` is what the build *runs*; `packaging/` is what it *ships*. The fetch scripts are
  the first, the icon and the PyInstaller spec are the second.
- Reach a shipped file through `common.paths.bundled()`. It answers for a source checkout and
  for both kinds of frozen build, so nothing needs its own chain of guesses.
- A directory added to `<owner>/static/` must also be listed in `packaging/vpinfe.spec`, or it
  is simply absent from the build. No test covers that — the failure is a missing image in a
  release artifact, not a red suite.

## Comments and docstrings

The codebase is deliberately sparse — around 5% of lines are comments or docstrings. Match
that.

Treat the ratio as a smell test rather than a budget. It misfires on short files: a forty-line
module whose two public functions each state a real contract can sit well above 5% and be
right. What matters is whether the prose restates the code — cut it — or states something the
caller cannot infer from the name and signature, which is worth keeping.

- **Module docstring: one line.** A second only if the module's *existence* is non-obvious.
  Long rationale goes in `docs/` with a pointer, not in the file.
- **Comment for guardrails** — where a plausible, well-meaning edit would break something.
  These earn their place:

  ```python
  # Outside the filehash check below on purpose: the id must survive the table
  # changing, which is exactly when alt_vpsid is cleared.
  ```

- **No docstring where the name and signature already say it.** Write one when there is a real
  contract: what it raises, what it writes, what it deliberately does not do.
- Reference data — a schema version history beside its constant, a lookup table — is fine.
  That is data, not prose.

## Logging

Logs are read by one person trying to work out what happened, usually from the Logs page in
the Manager UI. Everything below serves that.

### Levels

The level is a promise about who needs to read the line.

- **ERROR** — the operation failed and the user is affected. Always actionable.
- **WARNING** — degraded, unavailable, or ignored, but we carried on. A configured feature
  that silently does nothing belongs here, not at INFO.
- **INFO** — state changes worth having in a timeline afterwards: startup and shutdown, a
  game launched or exited, an import finished, an extension loaded, config changed.
- **DEBUG** — everything else, including per-item detail and progress narration.

**Summarise bulk work at INFO, never one line per item.** Assigning ids to a library once
wrote a line per game and buried the rest of the log; it is one line with a count now, and
the per-game detail is DEBUG.

The bar to hold: an idle startup produces tens of INFO lines, not hundreds. Measure it rather
than guess — start the app and count.

### Logger names

`vpinfe.<area>.<module>`, matching where the code lives:

```python
logger = logging.getLogger("vpinfe.common.games.game_identity")
logger = logging.getLogger("vpinfe.httpapi.games")
```

Areas are `common`, `frontend`, `manager`, `httpapi`. Extensions get `vpinfe.ext.<name>`,
issued by the extension context — an extension never logs into a core namespace, because the
namespace is how "which extension did this?" stays answerable.

### The browser side

A theme and the overlays run in Chromium, and their consoles go nowhere anyone reads on a
cabinet - an overlay is an iframe with a console of its own. Core forwards both to the
same log: whatever a page sends through `console_out`, and every uncaught error and
unhandled rejection without being asked. They arrive at INFO as `[<window>] ...`, or `[<window>/<overlay>] ...` when an
overlay is what threw. The window comes from the connection, so it cannot be
claimed; the overlay comes from the caller, because only it knows which frame it is.

The automatic half is the one that matters. A page that throws stops responding and
reports nothing, which reads as a dead button rather than a fault, and the deliberate
half cannot help - the code that would have called it is what threw.

### Exceptions

Use `logger.exception` inside an `except` block. It keeps the traceback;
`logger.error(str(exc))` throws away the only part that locates the fault.

```python
except OSError:
    logger.exception("Failed to enumerate game directory: %s", game_dir)
```

### Say which thing

When a message is about one unit of work, name it — game id, job id, upload id. Someone
reporting "my import failed" has to be findable in the file.

### Never log secrets

No tokens, API keys, or raw config dumps, at any level. Configuration holds an API key once
the auth seam exists, and a log is the easiest way to leak one.

### Formatting

Pass arguments to the logger rather than formatting into it, so the work is skipped when the
level is off:

```python
logger.debug("Assigned game id %s to %s", minted, game.gameDirName)     # yes
logger.debug(f"Assigned game id {minted} to {game.gameDirName}")        # no
```

### What we deliberately do not do

**Structured (JSON) logging.** This is a single-user appliance whose Logs page reads a text
file. JSON would break that page and serve nobody. Revisit only if remote diagnostics becomes
a goal.

**Per-request access logs.** `uvicorn.access` is filtered to warnings and above. A theme
polling once a second would drown the file. The API logs failures; successes are the caller's
business.

Worth knowing when moving an endpoint: NiceGUI logs every unmatched URL as a warning, so a
client still polling a path that has moved writes one warning per poll. Retiring a polled
endpoint means moving its callers in the same change, not leaving them to 404.

### Files

One `vpinfe.log` in the config directory, rotated at 2 MB with 3 backups, and rolled once at
startup so each run begins in a fresh file with the previous run kept. Restarting to reproduce
a problem no longer destroys the log of the run that showed it.

## Vocabulary

These follow the Virtual Pinball Spreadsheet, because VPS is where a user goes to identify
what they have. Ours used to say the opposite of VPS on both nouns, which meant anyone
reading both had to invert twice.

- **Game** — the pinball-machine concept: folder, identity, metadata, media, assets.
  VPS's top-level entry. One game, one folder.
- **Table** — a launchable artifact for a specific launcher (`.vpx` today). VPS's
  `tableFiles`: a game has several, by different authors, at different versions. A game
  is not permanently one table.
- **Playfield** — the main screen, and the media shown on it. Not "table": the playfield is
  a facet of a game, and `table` now means the file.
- **Media** — artwork VPinFE shows *about* a game while you browse: playfield, backglass,
  DMD, wheel, logo, cab, FSS, flyer, instruction card, topper, loading video, launch audio,
  rulesheet, their video variants, audio. The logo is the game's title art - usually what a
  wheel is derived from, which is why a wheel-less game shows its logo in the wheel slot. This is `common/media_specs.py` and nothing else. Instruction card
  (the apron card image), game flyer (promo art) and rulesheet (a document you
  read) are three different things - keep the words apart.
- **Asset** — content a game needs to *play* as intended, beyond its table:
  `.directb2s`, ROM, alt color, alt sound, PUP pack, music, the per-table `.ini`.
  The per-table `.ini` is config-shaped but is still an asset: without it the table
  plays differently than intended, which is the whole definition.

A **declared ROM name is not a ROM asset.** A table's script sets `cGameName`, and
`vpxparser` records it, but that name means one of two different things:

- **A PinMAME dependency (hard).** The script drives the emulator, and without the ROM
  set in `<game>/pinmame/roms` the table does not run.
- **A DOF key (soft).** The table needs no emulator — EM games have no ROM to have —
  and the name exists only so DOF can map feedback effects to it.

Nothing recorded today tells the two apart, and the shape of the name is a hint rather
than a rule: PinMAME sets look like `mm_109c`, DOF keys like `GTB2001_1971`. Measured
across a large library, **most tables that declare a name have no ROM file, and they are
overwhelmingly EM games that never needed one.** So "declares a ROM, has no ROM file" is
a normal, healthy state for most of a library, and reporting ROM presence as a plain
missing/present flag would call hundreds of working tables broken.

That is why ROM is a *dependency*, not an asset: assets are found by naming rule with no
help from the script (the way VPX finds a `.directb2s` or a table `.ini`), while a
dependency is declared by the script and satisfied by content on disk. FlexDMD is the
second member of that family. The API reports the chain — declared, alias-rewritten,
effective, installed — and `installed` is true-or-null, never false, for the reasons
above. `required` on the chain comes from the `detectpinmame` flag: the script drives
the emulator when it calls `LoadVPM`, `vpmInit`, or creates `VPinMAME.Controller`
directly — measured on the comment-stripped script, because EM tables commonly carry
dead VPM code, and a commented-out `LoadVPM` is not a dependency. Measured against a
validation set covering both cases: every ROM-installed table hits, every DOF-key EM
table misses. One known ambiguity: some EM/PM recreations *conditionally* drive PinMAME for
chime sounds (the `cOptRom` pattern), and read as required when the player may run
happily without the ROM. The flag lands on the table on the next metadata rebuild;
until then the chain reports `required: null`.
- **Launcher** — the application that runs a table file (VPX standalone today).
  Not "app": that is VPinFE itself, and the lifecycle scopes use it that way.
- **Install** — one VPinFE installation: its files, its config, its `install_id`. It
  survives restarts, and it is what a hub or a device is addressed as.
- **App** — VPinFE running. What a lifecycle request starts, stops or restarts, as against
  the `frontend` it opens and the `system` it runs on. The install is still there when the
  app is not.
- **Theme** — a player-facing frontend package.
- **Device** — something a game can be launched on and played. A VPinFE install is
  one kind; a phone running VPX Mobile is another that never runs our code.
- **Player** — a human who plays. Reserved for that and used for nothing else:
  it meant the machine until 2026-08-19, and every pinball machine ever built
  prints PLAYER 1 on its display.
- **Extension** — a feature extending VPinFE under a manifest. Never "plugin", which is
  reserved for VPX standalone plugins.
- **Third-party** — a library VPinFE bundles and loads at runtime, written by someone else
  and not installed by the user: DOF and libdmdutil today. They ship in `third_party/` and
  are loaded through `common/third_party.py`. They are neither extensions (no manifest,
  nothing declared) nor plugins (that word belongs to VPX standalone), so say "third-party"
  and not "integration" or "external service".

A game is not permanently one `.vpx`; say "table" when the file is what is meant.

Media and assets are not the same thing, and the line is what each is *for*: media is what
you look at while browsing, assets are what the table consumes while playing. A backglass is
the case worth knowing — the `.directb2s` is an asset, because the B2S server runs it, while
the backglass *art* the wheel renders is media. Do not call an asset "media" because it
happens to be a file in the game folder.

`asset_registry.ASSET_SPECS` uses "asset" more broadly, as the lifecycle role of anything
being imported — including the table and its media. That is the import pipeline's word for
"a thing being added", not a content category, and it never reaches the HTTP contract, whose
endpoints are `/uploads/*`. Prefer the definitions above anywhere the distinction matters.

Two game identifiers exist and are not interchangeable:

- `vpinfe_id` — this install's stable id. Addresses a game in the API, in events, in jobs.
- `vpsid` / `altvpsid` — correlation with VPSdb and services keyed by it. Note this
  identifies the VPS **game**, not which of its tables you have.

## Hub UI

The stylesheet is the design system. `hubui/theme.py` holds every token and every class the
hub uses, and there is no second place a treatment is defined. **Grep it before inventing
one** — a heading, a chip, a state, a control. Something that looks like it needs a new class
usually has one already, and two spellings of the same idea is how a surface stops looking
like one product.

### One shape per kind of value

A panel that shows facts uses the same control for the same kind of value, everywhere:

| Value | Control |
|---|---|
| Binary the user can set | a switch, `color=positive` |
| A list to pick from | a select |
| A state the user cannot set | a chip |
| Free text the user can set | a field, with a resting edge so it does not read as text |

Mixing them — a checkbox here, a text state and a button there — makes the reader work out
three times what one convention says once.

### Chips say what the absence costs

A chip's color is about consequence, not about whether something is merely true:

- `hub-tier--on` — present, installed, in use
- `hub-tier--off` — absent and unremarkable. Quiet, but filled and outlined enough to still
  read as a chip
- `hub-tier--unknown` — not determined yet, which is not the same as "no"
- `hub-tier--warn` — absent and worth fixing
- `hub-tier--bad` — absent and breaking

Green is present. **Amber means go and fix this, and nothing softer.** Each fact keeps its own
words: a rom is *Installed*, a script is *Extracted*, a file is *Present*. Do not flatten them
to Yes/No.

State chips are not media tiers. `hubui/tiers.py` answers "whose file is this", and its amber
means the exception worth spotting in a map of twenty.

### Type

- **A heading inside a panel** is `.hub-card-title` — `--accent` cyan, uppercase,
  `--fs-caption`, `0.08em`. Group headings take the same treatment plus a rule and space
  above; the separation carries the break, not extra weight.
- **Headings take title case. Sentences and phrases stay sentence case. The app nav is
  uppercase, alone** — a second uppercase column would rank a page's sections with the
  product.
- **A value is a name or a state, not a sentence.** Names keep their own casing
  (`Visual Pinball X`, `TAF_L7`); states are capitalized noun phrases. Show a display name
  rather than an id — an id on screen is a leak.
- **A fragment takes no full stop.** Sentences are punctuated; labels, states, counts and
  fragments are not. "Nothing in it yet." is a fragment wearing a period.
- **The shortest true word wins.** A chip reads `Missing`, not "Not in this library"; the
  sentence goes in the tooltip where it costs nothing.
- **A badge on every row is not a badge** — where the badge is *constant*. A chip reading
  the same thing on every row, or an action identical on all of them, says nothing and
  comes off. This does **not** cover a state that varies per row: that is data, and hiding
  its common value removes a column rather than removing noise. Show varying state on every
  row and dim the ordinary value, so the scan still lands on the exception without meaning
  being read from absence.
- **Cut anything that only restates what is on screen.** Explanatory prose above a control
  that already explains itself is filler, and filler is what makes a panel feel unfinished.
- **Gate an affordance on the input, not on the width.** Hover-to-reveal is
  `@media (hover: hover) and (pointer: fine)`, never a breakpoint: a touchscreen laptop
  is as wide as a desk one, and hiding a control behind hover on a device that cannot
  hover makes it unreachable. Visible is the default; revealing on hover is the
  enhancement. Pair it with `:focus-within` or a keyboard never reaches it either.
- **On screen, use the word a person would use.** The wire's `filter` is **Dynamic** to a
  reader. A label names the thing, not the model.
- **In a menu, the group label is chrome and the item is content.** One language for every
  menu - dropdowns, grid header and cell menus, bulk actions, pickers:
  - A **group header** takes `.hub-group`'s treatment: small, uppercase, tracked, `--ink-3`.
    It is a signpost and recedes. Never larger or brighter than the items it labels.
  - An **item** is body voice: sentence case, `--ink-2`, no letter-spacing. You read a
    name and click it, and a name only survives in sentence case.
  - **Hover and focus paint a full-width band.** A colour change alone is too weak to say
    *this row is the target*, and an item that sizes to its own text draws the band to the
    end of the words rather than the edge of the menu.
  - **Accent is the current value and nothing else** - the chosen item, the checkmark. When
    every item is accent-coloured the colour stops meaning anything.
  - **One leading slot**, fixed width, for whatever marks the item; items with no mark
    indent to it so the labels line up.
  - **The trailing slot is state** - a checkmark, a count, a shortcut. Never a second action.
  - A **destructive** item colours its *text*; the band stays the ordinary one. A red row
    reads as an error that has already happened.
  - **A separator divides groups**, never decorates.
  - **An open menu suppresses tooltips.** The control that opened it usually has one, and
    it lands on top of the menu.
  - **Group a long picker by what the columns are about**, groups named in the user's
    words. The grouping answers *which columns exist*; where a column sits is the grid's
    own order and the user drags that - so a group is a bucket, not a run of neighbours.
- **A label comes from the registry that owns the thing, never from its key.** Every
  closed set here already carries one - `MediaSpec.label`, `AssetSpec.label`,
  `config_schema.label_for` - and each has its acronyms cased once, correctly, in the one
  place that knows how the word expands. Deriving a label with `key.replace("_", " ")` is
  what put `real dmd color` in a column picker beside `Manufacturer`. Where a key must be
  shown because nothing has named it, derive it as an explicit *fallback* after asking the
  registry, the way `config_schema.label_for` does. `humanize()` in `common/labels.py` is that
  fallback: it knows this project's acronyms, so `rom_audit` reads **ROM Audit**.
- **A grid column is as wide as its header unless its values are longer.** Width is
  derived, not chosen: pass one only for a title, an author or a path, and treat it as a
  floor. A hand-picked number on a column of short values is a guess that outlives whoever
  made it.
- **Sort by what is shown, not by what is stored.** A list ordered on its keys while
  displaying labels reads as unsorted, because the reader cannot see the thing it is
  sorted on.

### Two traps that have both been walked into

- **Source order decides between equal specificity.** `.hub-tier` sets `border` as a
  *shorthand*, so a variant declaring `border-color` above it is silently reset to
  transparent. When adding a property to a base rule, check what overrides it later, and put
  the override below.
- **A row whose value is not text must be drawn in the same grid as the rows around it.** A
  second grid sizes a `max-content` label column of its own, and its values start somewhere
  else entirely.

### The page grid is above unpositioned backgrounds

`body::before` is a fixed `z-index: 0` layer, so it paints over any background beneath it —
"opaque" is not opaque until the element is lifted. A panel that must cover it takes
`position: relative; z-index: 1`, as `.nicegui-aggrid` does. Being above it is also what lets
a region *dim* the grid rather than sit behind it: what shows through is then the region's own
alpha.

## Linting

`ruff` handles formatting-adjacent rules, import order, PEP 8 naming and common bugs.
Configuration is in `pyproject.toml`; it installs from `requirements-dev.txt`.

```bash
pip install -r requirements-dev.txt

ruff check .          # what the CI advisory run reports
ruff check . --fix    # apply the safe fixes
```

CI runs it three ways:

- **Advisory over the whole tree.** Reports and does not fail. ~1,600 findings today, mostly
  line length and legacy naming. It is a visible debt register, not a gate.
- **Blocking on `tests/`.** The test packages were taken to zero findings and every file in
  them is checked, new or not. The tests are the foundation the rest of the cleanup is done
  against, so they are the one tree that is not allowed to drift.
- **Blocking on newly added files.** Any `.py` file added in a PR must be clean. This is what
  "get it right going forward" means in practice: new code is born compliant, and existing
  code is cleaned up when it is touched rather than in one enormous diff.

Some rules are ignored per-file for good reasons — `main.py` and `managerui/managerui.py`
import after executing statements because config has to be resolved before anything under
`common/` is imported. `tests/games/test_score_parser.py` does the same, because the module
it tests reads `roms.json` and the config paths at import. Those exemptions are listed in
`pyproject.toml` with their reasons.

### Auto-fix is not always safe

`--fix` will remove an import it thinks is unused, including one that exists purely for its
side effects. A trailing comment does not protect it; `# noqa` does:

```python
# Imported for the side effect of registering the Manager UI's routes.
import managerui.managerui  # noqa: F401
```

Run the tests after `--fix`, not just the linter.
