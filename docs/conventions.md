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

## Things we version

Three, each versioning a different kind of thing, each with its own word:

| what | versions | where |
|---|---|---|
| `.info` | a **file's shape** we write and read back | `vpinfe.schema` |
| HTTP surface | a **wire protocol** we serve | `/api/v1` |
| theme surface | an **interface handed to somebody else's code** | `contract` in a theme's `manifest.json` |

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
- **Table** — a launchable artifact for a specific app (`.vpx` today). VPS's `tableFiles`:
  a game has several, by different authors, at different versions. A game is not
  permanently one table.
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
- **App** — the application that plays a format (VPX standalone today).
- **Theme** — a player-facing frontend package.
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
