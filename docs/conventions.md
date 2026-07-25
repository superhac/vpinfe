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
- Route handlers stay thin. Logic belongs in a service where the other callers can reach it.

## Comments and docstrings

The codebase is deliberately sparse — around 5% of lines are comments or docstrings. Match
that.

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

## Vocabulary

- **Table** — the pinball-machine concept: folder, identity, metadata, media.
- **Game file** — a launchable artifact for a specific app (`.vpx` today).
- **App** — the application that plays a format (VPX standalone today).
- **Theme** — a player-facing frontend package.
- **Extension** — a feature extending VPinFE under a manifest. Never "plugin", which is
  reserved for VPX standalone plugins.

A table is not permanently one `.vpx`; prefer "game file" when that is what is meant.

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
