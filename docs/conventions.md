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
| Modules and packages | `snake_case` | `table_identity.py`, `httpapi/` |
| Classes | `CapWords` | `MetaConfig`, `TableParser` |
| Exceptions | `CapWords` ending in `Error` | `NotFoundError`, `InvalidRequestError` |
| Constants | `UPPER_SNAKE_CASE` | `API_PREFIX`, `CURRENT_VPINFE_SCHEMA` |
| Internal helpers | leading underscore | `_catalog()`, `_resource()` |

Python does not use camelCase. PEP 8 permits it "only in contexts where that's already the
prevailing style, to retain backwards compatibility" — which is why `tableDirName`,
`metaConfig` and `writeConfigMeta()` still exist. They are legacy, not the standard.

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

`vpinfe.ini` keys are lowercase and unseparated (`tablerootdir`, `manageruiport`). That is
established and user-facing; leave it alone. `.info` keys follow their existing section style.

## Layout

- A new subsystem gets its own top-level package, not another module in `common/`. `httpapi/`
  is the current example.
- Keep `common/` UI-independent.
- `common/` is a layer, not a bucket. Domain code goes in `common/tables/`, `common/online/`
  or `common/host/`; `common/` itself holds only what knows nothing about any of them, and may
  never import from those packages. See `docs/common.md`.
- Route handlers stay thin. Logic belongs in a service where the other callers can reach it.

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
  # file changing, which is exactly when altvpsid is cleared.
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
  table launched or exited, an import finished, an extension loaded, config changed.
- **DEBUG** — everything else, including per-item detail and progress narration.

**Summarise bulk work at INFO, never one line per item.** Assigning ids to a library once
wrote a line per table and buried the rest of the log; it is one line with a count now, and
the per-table detail is DEBUG.

The bar to hold: an idle startup produces tens of INFO lines, not hundreds. Measure it rather
than guess — start the app and count.

### Logger names

`vpinfe.<area>.<module>`, matching where the code lives:

```python
logger = logging.getLogger("vpinfe.common.table_identity")
logger = logging.getLogger("vpinfe.httpapi.tables")
```

Areas are `common`, `frontend`, `manager`, `httpapi`. Extensions get `vpinfe.ext.<name>`,
issued by the extension context — an extension never logs into a core namespace, because the
namespace is how "which extension did this?" stays answerable.

### Exceptions

Use `logger.exception` inside an `except` block. It keeps the traceback;
`logger.error(str(exc))` throws away the only part that locates the fault.

```python
except OSError:
    logger.exception("Failed to enumerate table directory: %s", table_dir)
```

### Say which thing

When a message is about one unit of work, name it — table id, job id, upload id. Someone
reporting "my import failed" has to be findable in the file.

### Never log secrets

No tokens, API keys, or raw config dumps, at any level. Configuration holds an API key once
the auth seam exists, and a log is the easiest way to leak one.

### Formatting

Pass arguments to the logger rather than formatting into it, so the work is skipped when the
level is off:

```python
logger.debug("Assigned table id %s to %s", minted, table.tableDirName)   # yes
logger.debug(f"Assigned table id {minted} to {table.tableDirName}")      # no
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

- **Table** — the pinball-machine concept: folder, identity, metadata, media, assets.
- **Game file** — a launchable artifact for a specific app (`.vpx` today).
- **Media** — artwork VPinFE shows *about* a table while you browse: playfield, backglass,
  DMD, wheel, cab, FSS, flyer, their video variants, audio. This is `common/media_paths.py`
  and nothing else.
- **Asset** — content a table needs to *play* as intended, beyond its game file:
  `.directb2s`, ROM, alt colour, alt sound, PUP pack, music, the per-table `.ini`.
  The per-table `.ini` is config-shaped but is still an asset: without it the table
  plays differently than intended, which is the whole definition.

A **declared ROM name is not a ROM asset.** A table's script sets `cGameName`, and
`vpxparser` records it, but that name means one of two different things:

- **A PinMAME dependency (hard).** The script drives the emulator, and without the ROM
  set in `<table>/pinmame/roms` the table does not run.
- **A DOF key (soft).** The table needs no emulator — EM tables have no ROM to have —
  and the name exists only so DOF can map feedback effects to it.

Nothing recorded today tells the two apart, and the shape of the name is a hint rather
than a rule: PinMAME sets look like `mm_109c`, DOF keys like `GTB2001_1971`. Measured
against a 653-table library, **244 of the 579 tables that declare a name have no ROM
file, and they are overwhelmingly EM tables that never needed one.** So "declares a ROM,
has no ROM file" is a normal, healthy state for most of the library, and reporting ROM
presence as a plain missing/present flag would call hundreds of working tables broken.

That is why the table resource carries the declared name as metadata (`rom`) but no ROM
entry under `assets`. **Trigger for revisiting:** a detector for whether the script
actually instantiates the PinMAME controller — `runDetectors` in `vpxparser` already
greps the script for exactly this kind of thing. Once the dependency's kind is known,
ROM can be reported honestly.
- **App** — the application that plays a format (VPX standalone today).
- **Theme** — a player-facing frontend package.
- **Extension** — a feature extending VPinFE under a manifest. Never "plugin", which is
  reserved for VPX standalone plugins.
- **Third-party** — a library VPinFE bundles and loads at runtime, written by someone else
  and not installed by the user: DOF and libdmdutil today. They ship in `third-party/` and
  are loaded through `common/third_party.py`. They are neither extensions (no manifest,
  nothing declared) nor plugins (that word belongs to VPX standalone), so say "third-party"
  and not "integration" or "external service".

A table is not permanently one `.vpx`; prefer "game file" when that is what is meant.

Media and assets are not the same thing, and the line is what each is *for*: media is what
you look at while browsing, assets are what the table consumes while playing. A backglass is
the case worth knowing — the `.directb2s` is an asset, because the B2S server runs it, while
the backglass *art* the wheel renders is media. Do not call an asset "media" because it
happens to be a file in the table folder.

`asset_registry.ASSET_SPECS` uses "asset" more broadly, as the lifecycle role of anything
being imported — including the game file and media. That is the import pipeline's word for
"a thing being added", not a content category, and it never reaches the HTTP contract, whose
endpoints are `/uploads/*`. Prefer the definitions above anywhere the distinction matters.

Two table identifiers exist and are not interchangeable:

- `vpinfe_id` — this install's stable id. Addresses a table in the API, in events, in jobs.
- `vpsid` / `altvpsid` — correlation with VPSdb and services keyed by it.

## Linting

`ruff` handles formatting-adjacent rules, import order, PEP 8 naming and common bugs.
Configuration is in `pyproject.toml`.

```bash
ruff check .          # what the CI advisory run reports
ruff check . --fix    # apply the safe fixes
```

CI runs it two ways:

- **Advisory over the whole tree.** Reports and does not fail. ~1,600 findings today, mostly
  line length and legacy naming. It is a visible debt register, not a gate.
- **Blocking on newly added files.** Any `.py` file added in a PR must be clean. This is what
  "get it right going forward" means in practice: new code is born compliant, and existing
  code is cleaned up when it is touched rather than in one enormous diff.

Some rules are ignored per-file for good reasons — `main.py` and `managerui/managerui.py`
import after executing statements because config has to be resolved before anything under
`common/` is imported. Those exemptions are listed in `pyproject.toml` with their reasons.

### Auto-fix is not always safe

`--fix` will remove an import it thinks is unused, including one that exists purely for its
side effects. A trailing comment does not protect it; `# noqa` does:

```python
# Imported for the side effect of registering the Manager UI's routes.
import managerui.managerui  # noqa: F401
```

Run the tests after `--fix`, not just the linter.
