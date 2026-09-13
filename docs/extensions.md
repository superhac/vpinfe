# Extensions

An extension adds a feature to an install without being part of VPinFE. It ships as a
directory, declares what it needs in a manifest, and is handed a context it reaches
everything through. It never receives the application.

The word is **extension** throughout. *Plugin* means a Visual Pinball standalone plugin,
which is a different thing with its own page.

## What one looks like

```
my-extension/
    extension.json
    __init__.py
```

The directory name is the extension's name, and the manifest has to agree: the name
addresses it in a URL, a scope, a log namespace, a config file and the Python package
core imports, so two answers to what it is called would each be right somewhere.

`__init__.py` defines `register(ctx)`. Core calls it once at startup and never again.

Two places are searched, in this order: `extensions/` under the config directory, then the
`extensions/` the build ships. An installed extension with the same name as a bundled one
answers, and the bundled one is left alone.

```python
from fastapi import APIRouter


def register(ctx):
    router = APIRouter()

    @router.get("/rating/{game_id}")
    def rating(game_id: str) -> dict:
        return {"stars": ctx.config.get("default_stars", "0")}

    ctx.add_router(router, scope=ctx.scope("read"))
    ctx.events.subscribe("game.selected", lambda **payload: ctx.logger.debug("%s", payload))
```

## The manifest

`extension.json`, snake_case like every other JSON we write.

| key | what it is |
|---|---|
| `name` | Lowercase letters, digits and `_`, starting with a letter. Matches the directory, and is the Python package core imports - so it has to be a legal module name |
| `display_name` | What to call it on screen. Defaults to `name` |
| `version` | The extension's own version. Shown, never interpreted |
| `description` | One line, shown beside it |
| `requires_platform` | The platform ABI it was built against. This build offers `1` |
| `scopes` | Core scopes it asks to use, e.g. `games:read` |
| `provides` | The actions it gates its own routes on. Core mints `ext:<name>:<action>` |
| `capabilities` | What it asks of the machine: `ui:mount`, `config:own`, `net:outbound`, `proc:spawn`, `hardware:usb`, `fs:read`, `fs:write` |
| `requires_features` | Install features it needs: `library`, `frontend`, `devices`, `overview` |
| `platforms` | `linux`, `windows`, `macos`. Empty means every one |
| `events` | Event names it publishes, without its namespace |

Everything in it is a declaration a person can be shown before installing, which is why an
unknown capability, feature or platform is refused rather than ignored: a name nobody has
heard of is not something anybody could have agreed to.

An extension whose manifest names a platform this machine is not, or a feature this
install does not have, is not loaded. It is still listed, with the reason.

## The context

`ctx` is the whole of an extension's reach. There is no way to get from it to the
application, and that is the guarantee the model rests on.

| on `ctx` | what it does |
|---|---|
| `ctx.name`, `ctx.manifest` | What this extension is and what it declared |
| `ctx.logger` | A logger in `vpinfe.ext.<name>` |
| `ctx.config` | `get`, `set`, `all` over its own settings |
| `ctx.events` | `subscribe` to a core event; `publish` one of its own |
| `ctx.files` | `set_roots` — the folders it works from, so core will take a path from inside one. Needs `fs:read` |
| `ctx.jobs` | `submit(kind, work)` — slow work, one at a time per kind, answerable on `/api/v1/jobs` |
| `ctx.games` | The library. `kinds`, `folder`, `folder_name_for`, `existing`, `create`, `add_table`, `put_media`, plus every operation core offers by name — `reaches()` lists them. Each needs the core scope its manifest declared |
| `ctx.apps` | `provide(...)` — add a way to play a table. `suffixes`, `plays`, `names` say what this build can play. Providing needs `apps:provide` |
| `ctx.games.launch_game(...)` | Start a game on this play host. Needs `launch:invoke`, which `games:write` does not grant |
| `ctx.scope(action)` | The scope name for one of its declared actions |
| `ctx.entries` | `contribute(key, fetch)` — add something to every entry a theme is handed |
| `ctx.ui` | `action(...)` — offer a verb for the Console to draw. Needs `ui:mount` |
| `ctx.add_router(router, scope=...)` | Serve routes under `/api/v1/ext/<name>/` |

`ctx.games` is not a second implementation of the HTTP API — it calls the API's own route
functions. They are plain functions; the scope gate lives in each route's dependencies and
only fires for a request arriving over the wire, so the gate is applied here against the
manifest instead. An extension reaches the same code an HTTP client reaches, and the two
cannot drift.

That matters because they had. While the host kept its own smaller copy of the library,
the importer worked out for itself what folder a game's name would become and got it
wrong, on names core strips a character from. Anything core offers is now reachable by the
name it is offered under:

```python
found = ctx.games.list_games(q="taxi", limit=10, offset=0)
ctx.games.rate_table(game_id, table_id, 8)
ctx.games.reaches()      # what this extension may actually call
```

Launching is gated apart from the rest. It takes over the cabinet rather than editing a
record, and the scope vocabulary already said so before extensions existed: reading what
is happening is not the same as causing it to happen, and stopping a table somebody may be
mid-game on is a third permission again. So `games:write` does not grant it — an extension
that starts a game asks for `launch:invoke` by name, and whoever installs it reads it by
name.

An extension in this process cannot use the API over HTTP — a synchronous call into the
server it is running inside deadlocks — and may not import the library, so this is the
door.

It is bounded twice. The manifest's `scopes` decide which of those an extension may call
at all, which is what makes declaring them mean something. And a path it hands over has to
be inside a folder it declared through `ctx.files`, which is a tighter check than the same
one on a route: this one knows which extension is asking, where a route only knows a path.

There is deliberately no hook seam yet. A hook can stop a core operation, and handing that
out before the isolation story for it is designed would let a broken extension stop a
launch.

Routers are collected during `register` and mounted once. One added afterwards would never
be reachable, so it is refused rather than left to answer nothing.

## Adding a way to play a table

VPinFE plays Visual Pinball, and through the generic app anything a person can point at a
binary. An extension is how another format becomes first-class: it claims its own
suffixes, so a library of them is worth importing rather than read and dropped.

```python
ctx.apps.provide(
    id="fp",
    name="Future Pinball",
    suffixes=(".fpt",),
    fields=({"key": "bam_path", "label": "BAM folder", "path": "dir"},),
    command=lambda entry, settings: ["/opt/fp", "--play", entry["table"]],
)
```

It is described in plain data because an extension cannot import the app contract — its
one door is `common.extensions.contract`, which is what makes the import boundary
checkable. `command` answers with a list of arguments, never a string: splitting one is
how a path with a space in it becomes a crash or an injection, and only the extension
knows where its own arguments end. Answering with nothing runs the launcher's configured
binary and arguments instead.

Apps this build ships are offered first, so a provided one cannot take `.vpx` out from
under Visual Pinball by loading before somebody looks. An id already in use is refused:
ids are stored in a table's record and read back long afterwards. What an extension
provides is taken back when it unloads, so a disabled extension leaves no suffix claimed
by something that is no longer there.

A provided app does not get the rest of the app contract — parsing a table, resolving a
ROM, a settings surface. Those are declared absent rather than half-answered, the same way
the generic app declares them.

## Adding something to an entry

A theme reads `entry.ext.<key>`. It never learns which extension answered, and no
extension gets a method of its own on the theme surface — the alternative needs a new call
for every connector that follows.

```python
def rating_for(game):
    # game is {game_id, vps_id, name, manufacturer, year} - a description, never our
    # object. Return whatever a theme should read, or None where there is nothing.
    return {"stars": look_it_up(game["vps_id"])}

ctx.entries.contribute("rating", rating_for)
```

**Core makes the call; the browser makes none.** `fetch` runs on core's thread when the
player moves to a game, so it may block — but it must not raise for a game it simply has
no answer about. One that raises costs its own key and nothing else.

Three things core does that no theme author sees. The answer is held per process, so one
fetch serves every window and survives a reload. The games either side are fetched on the
same signal, so what somebody sees is the answer fetched a step ago and the gap only shows
on the first game of a cold start. And the message that carries an answer names the game
it is about, so one arriving after the wheel has moved lands on the entry it belongs to.

The slot is always present and empty at library load — a list of four hundred games cannot
wait on four hundred calls to somebody else's server. A theme written as
`if (entry.ext.rating)` is correct throughout without knowing there is a waiting state.

## Offering something to do

An extension does not draw. It declares an **action** — a verb — and core renders it, so
every action looks like the Console rather than like whoever wrote the extension, and it
keeps working if that extension later runs out of process, which a drawn page would not.

```python
ctx.ui.action(key="import", label="Bring in a library", base="/wizard",
              description="Convert a library from another frontend into game folders.")
```

Two calls on the extension's own router, under `base`:

| call | answers |
|---|---|
| `GET {base}` | `title`, `help`, `fields`, `confirm` — what to ask, if anything |
| `POST {base}/check` | `ready`, `summary`, `notes`, more `fields`, `confirm` — what would happen |
| `POST {base}/run` | `{"job_id": …}`, or the outcome directly |

**How many steps an action has is read off what it answers, never declared.** No `fields`
means press it and it happens. `fields` means fill them in first. A `confirm` means a step
showing what would happen before it runs. A declared mode would be a second statement of
what the answers already say, and the two come apart.

A run returns a `job_id` where the work is slow — core watches it on `/api/v1/jobs` — or
the outcome where it is not, with an optional `message` and `summary`. An action that is
one call and a sentence should not have to wear a progress bar.

`fields` are `{key, type, label, value, help}`, where type is `path`, `string` or `multi`
(with `choices`). Both `check` and `run` receive `{"values": {…}}`.

`confirm` is the verb at the point of no return, and it is the action's own: a generic
"Confirm" makes every action look like every other one. `notes` travel with the summary,
because a count that stays quiet about what the job cannot do describes something that
will not happen.

## Scopes and the gate

Core attaches the gate. An extension names an action it declared; core turns that into
`ext:<name>:<action>` and puts it on every route in the router. An extension cannot ship a
route without a gate, because it never attaches one.

A scope belonging to an extension is granted only while that extension is running.

## Config

Two homes, because there are two owners.

| file | holds |
|---|---|
| `extensions.json` | core's record of what is installed and what is switched off |
| `extension_settings/<name>.json` | that extension's own settings |

Never `vpinfe.ini` - that file holds what core is configured with, and it is where a token
would go.

A file each rather than a namespace inside one, for the same reason: a namespace in
somebody else's file is a weaker form of "own" than a file. One unreadable
`extensions.json` used to cost every extension its settings and switch the disabled ones
back on. Now one extension's bad file costs that extension.

Whether an extension is switched off stays core's record, because core has to know before
it loads anything - reading a file per extension to answer "what am I not loading" is
worse than reading one. An extension switched off is not loaded at all.

Settings are not beside an extension's code: one the build ships has no directory in the
config dir, so they need a home that does not depend on where the code came from.

## Logs

`vpinfe.ext.<name>`, issued by the context. An extension never logs into a core namespace,
because the namespace is how "which extension did this?" stays answerable.

## When one breaks

Reading the manifest, importing the package and calling `register` are each somebody
else's code, and any of them failing costs one extension. Afterwards, an unhandled error
out of one of its routes, or out of a handler it subscribed, takes that extension out:

- its subscriptions are dropped, so it is told nothing more
- its scopes go with it, so nothing holds a grant into something that is not running
- its routes keep their paths and answer `501` naming the extension and the reason,
  because a `404` reads as a typo

That is for the run it happened in. It is not written down: a fault that happened once
must not take an extension away until somebody notices a setting they never set.

An error an extension raises deliberately - a `NotFoundError`, an `HTTPException` - is an
answer, not a fault, and changes nothing.

## Where the code is

- `common/extensions/contract.py` - the manifest and the shape of the context. The only
  module of ours an extension imports.
- `common/extensions/context.py` - what `register(ctx)` is handed.
- `common/extensions/host.py` - loading, the registry, and the kill switch.
- `common/extensions/store.py` - `extensions.json`.
- `httpapi/extensions.py` - the gate, the mount, and `GET /api/v1/extensions`.

`tests/fixtures/extensions/sample/` is a worked example that uses all of it.
