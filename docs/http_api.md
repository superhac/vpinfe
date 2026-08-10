# HTTP API

VPinFE serves a versioned HTTP API at `/api/v1`, on the same port as the Manager UI
(`manageruiport`, default 8001).

> **Unstable.** The API is under active development and may change without notice until v1
> is declared stable. Nothing outside this repo should depend on it yet.

## Structure

- `httpapi/__init__.py`: the app factory (`create_api_app()`) and the mount (`register(app)`).
- `httpapi/errors.py`: the error envelope — `ApiError` and the handlers that shape it.
- `httpapi/instance.py`: discovery and health — what this instance is.
- `httpapi/capabilities.py`: the capability registry discovery reads from.
- `httpapi/events.py`: the event stream — the internal bus (`common/events.py`) on the wire.

The API is not part of the Manager UI. It's served by the same process today, but it belongs
to the platform — the Manager UI, the frontend themes, the mobile page, and any outside
integration are all just clients of it.

## Why it's a mounted app

`register()` mounts a separate `FastAPI` app at `/api/v1` rather than adding routes to the
NiceGUI app directly. That boundary does real work:

- The error envelope, CORS, and eventually the authorization boundary apply to `/api/v1` and to nothing
  else. The Manager UI's pages can't be affected by an API-level change, by construction.
- NiceGUI disables OpenAPI on its own app and installs 404/500 handlers that render HTML
  pages. Routes added there get no generated spec and no JSON errors; a mounted app gets
  both.

One consequence worth knowing: a request for exactly `/api/v1` would normally redirect to
`/api/v1/`. `register()` also serves discovery from the parent app at the un-slashed path so
the documented entry point is a plain 200. Both spellings work.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1` | Discovery — what this instance is and what it can do |
| GET | `/api/v1/health` | Liveness |
| GET | `/api/v1/openapi.json` | Generated OpenAPI spec |
| GET | `/api/v1/docs` | Swagger UI |
| GET | `/api/v1/events` | Subscribe to the event stream (SSE). `?events=` filters by name |
| GET | `/api/v1/play/state` | What this play host is doing. The snapshot you take once; `play.state_changed` on the stream is how you hear about it after that |
| GET | `/api/v1/collections` | List collections |
| GET | `/api/v1/collections/{name}` | One collection |
| GET | `/api/v1/collections/{name}/games` | Its games, resolved — works for both kinds |
| POST | `/api/v1/collections` | Create one. `filters` makes it filter-based, `games` makes it manual |
| DELETE | `/api/v1/collections/{name}` | Delete it |
| PUT | `/api/v1/collections/{name}/games/{id}` | Add a game (idempotent) |
| DELETE | `/api/v1/collections/{name}/games/{id}` | Remove a game |
| GET | `/api/v1/jobs` | Slow work, running first. `?kind=` filters |
| GET | `/api/v1/jobs/{id}` | One job — state, last progress, outcome |
| GET | `/api/v1/library/filters` | Every filter axis, with the values this library holds |
| POST | `/api/v1/library/scan` | Rebuild game metadata from VPSdb. Returns `202` and a job; optional `{"download_media": bool, "update_all": bool}` |
| GET | `/api/v1/manufacturers` | Every manufacturer VPSdb or the library knows: computed slug, effective alias, resolved logo (or `null`), library game count. The reference for logo packs and alias maps |
| GET | `/api/v1/games` | List games (`q`, `limit`, `offset`) |
| GET | `/api/v1/games/{id}` | One game |
| GET | `/api/v1/games/{id}/tables` | The game's tables, with resolved assets and dependencies |
| GET | `/api/v1/games/{id}/media` | Every media kind, present or not |
| GET | `/api/v1/games/{id}/media/{kind}` | Stream one media file |
| GET | `/api/v1/games/{id}/archive` | Download a game as `.vpxz` — one table by default; `?file=` picks which table. `?full=true` (whole folder) carries its own scope, `games:export_full` |
| POST | `/api/v1/games/{id}/launch` | Launch a game here. Optional `{"file": "..."}` picks which table |
| PUT | `/api/v1/games/{id}/rating` | Rate a game, `{"rating": 0-5}`. `0` is unrated |
| POST | `/api/v1/uploads` | Begin an upload session → `{"id": ...}` |
| POST | `/api/v1/uploads/{id}/files` | Add a file (multipart: `relpath`, `file`) |
| GET | `/api/v1/uploads/{id}` | Session summary → `{"file_count", "total_bytes"}` |
| DELETE | `/api/v1/uploads/{id}` | Abort a session |
| GET | `/api/v1/uploads/{id}/analysis` | Analyze what was uploaded |
| POST | `/api/v1/uploads/{id}/plan` | Build an import plan |
| POST | `/api/v1/uploads/{id}/import` | Execute the plan |
| GET | `/api/v1/vps/search?q=&limit=` | VPSdb lookup |

Discovery is the entry point: an integrator learns what an instance offers by asking it,
rather than matching a version number against a document.

```json
{
  "name": "VPinFE",
  "install_id": "7Kq2mVx9Ab",
  "display_name": "basement cab",
  "roles": ["hub", "player"],
  "api_version": "v1",
  "app_version": "2.5.0",
  "capabilities": [],
  "extensions": [],
  "links": {
    "self": "/api/v1",
    "health": "/api/v1/health",
    "openapi": "/api/v1/openapi.json",
    "docs": "/api/v1/docs",
    "events": "/api/v1/events"
  }
}
```

Links are relative so they stay correct behind a reverse proxy. A link that is present but
`null` is a known part of the contract that this instance doesn't offer — clients should
branch on that rather than on its absence.

`name` is the product and reads the same on every install, so it can't tell two apart.
`install_id` can: it's minted once on first start, opaque, and stable for the life of the
install. Address an install by it and nothing else — `display_name` is for showing a
person, defaults to the machine's hostname, and is meant to be renamed, so anything
resolving through it breaks the first time somebody does.

`roles` says which halves this install serves. It defaults to both, which is what a
desktop install and a standalone cabinet are.

## Conventions

Field names are `snake_case` (see `docs/conventions.md`), matching Python's own convention (PEP 8) so nothing has to be
translated on the way out, and matching the repo's existing JSON. Plenty of JSON APIs use
snake_case for the same reason — GitHub's and Stripe's among them.

A game resource carries `id` (this install's id) and `vps_id` (correlation with VPSdb and
friends). Sub-resources are linked from `links` rather than assembled by the client.

Path segments are hyphenated (`/games`); JSON field names are `snake_case`
(`links.tables`). Different namespaces, different conventions — hyphens read better in a
URL and nothing has to be translated on the way into Python.

**Media and assets are not the same thing** (`docs/conventions.md`). Media is the artwork
VPinFE shows you while browsing; assets are what the game needs to *play* as intended.

Media is served under `GET /games/{id}/media`: every kind from `common/media_specs.py`,
present or not, so a client enumerates what is possible instead of guessing from omissions.
A present kind links to `/media/{kind}`, which streams the file with its real content type.
Resolution is the same three-tier chain the scan uses, applied to the folder as it is at
request time: a spec-named file for the launching table (`(Wheel) <table>.png`) beats a
folder-named one (`(Wheel) <folder>.png`) beats the fixed default (`wheel.png`), each kind
trying its extension family in order, `medias/` before the folder root throughout.
Consumers never learn these rules — every kind still reports exactly one winning file.
One cross-kind rule: a game with a `logo` and no wheel serves the logo in the wheel slot,
below every real wheel tier; such an entry carries `via: "logo"` so a client that cares can
tell a fallback from the real thing. An unknown kind is an
`invalid_request` naming the known kinds; a known-but-absent kind is a `not_found`.

Assets come in two lenses, both computed from the folder at request time:

- **The launch lens** — each entry in `GET .../tables` reports what *that* table
  would use on launch, mirroring VPX's own lookup order per kind: `dedicated` (a file named
  for the table), `shared` (the folder-named fallback), or `none` — plus the winning
  filename. A `.pov` never falls back to the folder name, because VPX doesn't.
- **The inventory lens** — `GET /games/{id}` attributes every asset file in the folder:
  `dedicated` to the table it serves, `shared`, or `orphaned` (stem-named for a table
  that is no longer there — what an audit wants to see). The list endpoint carries a
  presence summary only.

Games also carry `dependencies` — things the *script* declares and content on disk
satisfies, which is a different mechanism from an asset found by naming rule:

- `pinmame` is a chain: `declared` (the script's ROM name) → `alias_of` (rewritten by the
  game's `pinmame/alias.txt`, the way PinMAME itself does) → `effective` → `installed`,
  with `required` saying whether the script actually drives the emulator — measured from
  the script, not guessed from the name's shape. `required: true` with `installed: null`
  is the case worth surfacing; `required: false` means the declared name is a DOF key;
  `null` means the game's metadata predates the detector and a rebuild will fill it in.

  When the machine's own VPX install ships `libpinmame` (discovery declares this as the
  `rom_audit` capability), the chain also carries PinMAME's own answer: `catalog` (the
  engine knows this set), `clone_of` (the parent set an unmerged clone needs),
  `description` (the version label), and `audit` — `ok` upgrades `installed` to true with
  chip-level certainty, `missing` finally makes `installed: false` sayable,
  `unknown_set` means the name isn't in this PinMAME's catalog (an alias may be needed,
  or the set is newer than the shipped library), and `unavailable` leaves the name-match
  conclusion standing. The library is borrowed from the configured launcher's install,
  never bundled — a machine that can't launch has no use for the audit.
  `installed` is true or null, never false: the name may be a DOF key on a ROM-less EM
  game, an unmerged set may need a parent zip, and global ROM locations aren't searched —
  so "not found here" is not "missing". `nvram` rides the chain (`present`, `file`,
  `modified_at`, stat-ed live) because a competition harvester's question is "is there a
  score newer than my last visit".
- `flexdmd` reports whether the script uses FlexDMD and what `.UltraDMD` content exists;
  `declared` stays null until the project-folder extraction is built.

The script-declared facts are only known for the table the game's metadata records;
other tables report `null` with a reason rather than inheriting the wrong answer.

`rom` on the game resource is the recorded table's **declared** ROM name kept as plain
metadata; the full chain (alias, effective, installed, nvram) lives on the table's
`dependencies.pinmame`.

## Errors

Every failure under `/api/v1` comes back in one shape, with a real HTTP status:

```json
{"error": {"code": "not_found", "message": "No such game", "details": null}}
```

`code` is the contract. Branch on it; don't parse `message`, which is meant for humans and
may be reworded. `details` is optional structured context — for a validation failure it
carries the offending fields.

Raise, don't build responses by hand:

```python
from httpapi.errors import NotFoundError, InvalidRequestError, FeatureUnavailableError

raise NotFoundError(f"No game with id {game_id}")
raise InvalidRequestError("sort must be one of: name, year", details={"got": sort})
raise FeatureUnavailableError("DOF is not configured on this instance")
```

For anything else, `ApiError(code, message, status_code=..., details=...)`. Uncaught
exceptions become a logged `internal_error` with no detail in the response — put anything the
user needs into an explicit `ApiError`.

Codes defined so far: `not_found`, `invalid_request`, `method_not_allowed`, `conflict`,
`feature_unavailable`, `internal_error`, plus `unauthorized` and `forbidden` reserved for the
authorization boundary. Add new codes to `httpapi/errors.py` rather than inventing them at a call site.

## Authorization

Every request into `/api/v1` passes one middleware that stamps an identity on it, and every
route declares the scope it needs:

```python
@router.get("/games", dependencies=[requires(scopes.TABLES_READ)])
```

**The policy is dormant.** Today whoever can reach the instance is granted every scope, which
is exactly how the app has always behaved — this changes nothing for anyone. What exists now
is the mechanism, so tightening later is a policy change rather than a retrofit across every
endpoint. Replacing `LocalTrustPolicy` is the whole of it.

An identity does carry `origin` — `local` or `network` — decided by the request's own peer
address, so a policy that wants to treat the two differently has the fact without re-deriving
it. It is read from the socket and never from `X-Forwarded-For`, which the caller writes.
Nothing acts on it yet: the hub binds every interface by default so a phone can administer a
cabinet, and what a network caller should be allowed is a decision that lands on that
workflow.

Three properties keep it honest:

- The middleware runs before any route, so no route is reachable without passing it.
- **Startup fails if a route declares no scope.** A boundary you can forget to use is not a
  boundary, so forgetting is made impossible rather than discouraged.
- Core services never learn about any of this. Authorization stays at the edge; nothing under
  `common/` takes an identity argument.

"Public" is not something a route asserts about itself. Discovery and health carry
`instance:read` like everything else, and a policy decides whether to grant it to a caller who
presented nothing.

Scopes are `<resource>:<action>`. Extensions get `ext:<name>:<action>`, which is what stops an
extension ever claiming a core scope. The vocabulary is in `httpapi/scopes.py`; most entries
are reserved for endpoints that don't exist yet, because settling a name is cheap and renaming
one after callers depend on it is not.

## Capabilities

Discovery reports what this instance can actually do, so a feature that needs hardware or
configuration it doesn't have isn't advertised as if it worked:

```python
from httpapi import capabilities

capabilities.declare(capabilities.Capability(
    name="peripherals",
    residency=[capabilities.RESIDENCY_PLAYER],
    description="DOF and real-DMD output",
    is_available=lambda: (dof_configured(), "DOF is not configured"),
))
```

`is_available` runs per request, not once at import, so the answer stays honest after the
user changes a setting. Return `(False, reason)` rather than a bare `False` — the reason is
shown to users, so say what's missing and how to fix it.

`residency` records which roles a capability lives in: `hub` for the shared,
machine-independent half — the library, metadata, and work not tied to a screen — and
`player` for things true only of the machine they came from, where games launch and
hardware lives. Neither name implies hardware: a laptop someone plays on is a player in
full.

It's a list because some capabilities belong to both — the event stream carries library
events and launch events alike. Listing both means each role serves its own, not that one
capability spans the two: if the hub and the player are ever separate machines, they
each have an event stream, carrying their own events. Test for a role with
`"player" in residency`, which reads the same whether a capability has one or two.

## Launching

`POST /api/v1/games/{id}/launch` starts a game on this play host. It returns `202` as soon
as the launch is under way — not when the game exits, which can be hours later. Watch
`/api/v1/events` to find out what happens next.

```
POST /api/v1/games/6f1c9a4e.../launch
{"file": "Table Name VPW Mod.vpx"}
```

`file` is optional and names one of the game's tables (`GET .../tables` lists them);
leave it out for the game's default. A name that isn't in the game's own folder is refused,
so this can't be talked into running something else.

Every refusal happens before anything starts, and comes back synchronously:

| Status | Code | Means |
|--------|------|-------|
| 404 | `not_found` | no game with that id |
| 400 | `invalid_request` | the named `file` isn't one of this game's tables |
| 409 | `conflict` | something is already playing — two VPX processes would fight over the same hardware |
| 501 | `feature_unavailable` | this machine can't launch at all, e.g. no `vpxbinpath` configured |

The endpoint carries `launch:invoke`, which is deliberately not `games:write`: reading the
library, changing it, and making the machine do something are three different permissions.

Discovery declares a `launch` capability separately from `play`, because reading what's
playing works on a machine that can't start anything. Check it before offering a Play button
rather than finding out from a 501.

This is the same launch the wheel and the Remote Control page use. That matters more than it
sounds — it means a launch from the API counts as a play, updates Last Played, reads the
score back out of NVRAM, and hands the peripherals over before VPX starts, because all of
that lives in the one path rather than in whichever caller remembered it.

## Event stream

`GET /api/v1/events` is the internal bus (`common/events.py`) on the wire, as Server-Sent
Events. Anything that wants to know what's happening subscribes instead of polling for it.

```js
const stream = new EventSource("/api/v1/events?events=play.state_changed");
stream.addEventListener("play.state_changed", (message) => {
  const { launching, table_name } = JSON.parse(message.data).state;
});
```

Each event is a named SSE frame whose `data` is the payload; the `event` field is the bus
event name, so a client listens for what it cares about rather than filtering a stream of
generic messages. `?events=` is a comma-separated filter — leave it off for everything. An
unknown name is an `invalid_request`, not a silently empty stream.

What's on it, each alongside the `install_id` described below:

| Event | Payload |
|-------|---------|
| `game.launching` / `game.launched` / `game.exited` / `game.selected` | `{"game": {"id", "name", "links"}}`, or `{"game": null}` when the launch didn't come from the wheel |
| `play.state_changed` | `{"state": {"launching", "table_name", "source"}}` |
| `job.progress` | `{"job_id", "pct", "message"}` |
| `job.done` | `{"job_id"}` |
| `job.failed` | `{"job_id", "error"}` |

Every payload also carries `install_id` — which install the event happened on. On a
single-machine install it is always the same value and can be ignored; a client watching
more than one is how it tells them apart. It is absent, not empty, when the install has no
id yet, so "didn't say" is distinguishable from an id that is the empty string.

What is deliberately *not* there is which surface asked. That names one user's browser tab
and means nothing to anyone else on the stream. Which install something happened on is the
provenance a subscriber can act on; who asked is private.

A game on the stream is a *reference*, not a resource: an id, a name to show, and
`links.self` to fetch the rest. Events stay small and there is one answer to what a game
looks like, at `GET /api/v1/games/{id}`. A game that hasn't been assigned an id yet carries
an empty one and no link rather than a broken one.

The bus carries more than that per event — `game.launching` hands its handlers the whole
`Game` object and the ini config, because its handlers are in-process. The stream projects
each event into the shape above instead of forwarding what was published, which is what makes
the wire shape a contract rather than a consequence: adding a keyword argument at a publisher
doesn't change what subscribers receive, and nothing internal leaks onto a socket. Streaming a
new event means adding it to `STREAMED_EVENTS` with the shape it takes.

The stream is always a subscriber and never a hook. A hook can stop the operation it's part
of, and nothing on the far end of a socket may do that.

### Connecting, and reconnecting

`play.state_changed` carries a `source` of `frontend`, `remote` or `api` — who asked for the
launch. The frontend uses it to ignore its own; everything else can treat the state as a fact
about the machine regardless of who caused it.

On connect the stream sends a `stream.hello` frame, then the current value of any
state-carrying event it's declared for — today `play.state_changed`. So a client that
connects mid-launch knows it, without a separate call to `/play/state` and without waiting
for the launch to end. An event whose payload doesn't describe the whole state has no
snapshot; there's nothing honest to send.

Every real event carries an `id`, and browsers replay it as `Last-Event-ID` when they
reconnect. Events since that point are replayed from a bounded buffer, and `stream.hello`
reports whether that worked:

```
event: stream.hello
data: {"seq": 118, "resumed": false}
```

`resumed: false` means the gap was too long, or the instance restarted — treat what you hold
as stale and resync. A resumed client isn't sent snapshots, because it has them already. That
distinction is why the buffer exists: `play.state_changed` carries the whole state and
corrects itself on the next event, but `job.done` doesn't happen twice.

A client is a bounded queue. One that falls further behind than the queue holds is sent what
was already queued and then disconnected, rather than being allowed to grow memory or slow a
publisher down — the bus runs its handlers on the thread that published, and a launch is one
of the things publishing. EventSource reconnects on its own, so a client that briefly stalls
recovers by itself.

## Collections

Two kinds behind one resource. A **manual** collection stores an explicit list of game
ids; a **filter** collection stores criteria and resolves to whatever matches when you ask.
`type` says which, and `table_count` is null for a filter collection because there is no
stored list to count — ask `/collections/{name}/games`, which answers the same question
for both kinds and applies the collection's own ordering.

Editing membership only makes sense for the manual kind, so `PUT`/`DELETE` on a filter
collection's games is a `409` rather than a silent no-op. Adding a game that is already a
member is a success: the caller wanted it in there, and it is.

Membership is the game's own id, not its VPS id — a game with no VPSdb match still
belongs to collections, which is why membership moved off the VPS id. The key on disk is
still `vpsids` for files written before that migration, and `type` is still `vpsid` there;
the wire uses the honest names.

Collection names are the identity, so they are URL-encoded in paths (`Last%20Played`).
`Last Played` itself is maintained automatically as you play.

`GET /library/filters` says what a filter collection can filter on: every axis with its
`scope`, `kind`, a one-line `summary`, and the `values` this library actually holds — so a
client offers a manufacturer somebody owns rather than every manufacturer that ever
existed. The axes are projected from the registry the resolver matches on, so the two
cannot disagree, and an axis added there appears here without a second edit.

A `rating` axis carries `values: null` rather than a list. It is 0–5 on every install, and
enumerating the ratings currently in use would offer a different scale to two libraries
and a shrinking one as ratings change.

## Jobs

Work that takes minutes is a job: you ask for the work, get `202` and a job resource back,
and follow it on the event stream. `POST /library/scan` is the first one — a metadata
rebuild across every game folder, which is why it sits under `/library` rather than
`/games/{id}`; it isn't an operation on a game.

The job resource exists because the stream isn't the only way in. A client that connected
late, missed `job.done`, or simply wants to know what is running asks `GET /jobs` or
`GET /jobs/{id}` — `pct` and `message` hold the last progress reported, so a late reader is
correct without having seen a single event. Finished jobs stay answerable for a while
(bounded — this is a courtesy for the client that missed the last event, not a history
feature).

Starting work is never a `POST /jobs`. The permission to run something is the permission of
the thing itself, so a scan is `games:write` because that is what a scan does. `jobs:read`
covers only asking; the right to watch is not the right to cause.

**One job of a kind at a time**, and the rule is shared with the rest of the app rather than
being an API-only guard: the Manager UI's own Scan button goes through the same registry, so
two library scans can't rewrite the same `.info` files at once, and a scan started from the
UI shows up on the stream exactly like one started here. A second request gets `409 conflict`
rather than being queued — queueing would mean a double-click costs two full scans.

## Game identity

Games are addressed by an opaque local id — `common/games/game_identity.py`, stored per game in
its `.info` under `vpinfe.game_id`:

```
GET /api/v1/games/tuF3WogthK
```

The id is minted once and then stays put. It survives renames, VPSdb re-matches, and table
updates, which is what an id in a URL, an event, or a job has to do.

`VPSId` is not that id, and can't be. It's empty for any game VPSdb hasn't matched, it isn't
guaranteed unique, and the effective id used elsewhere (`vpinfe.alt_vpsid or Info.VPSId`) is
deliberately cleared when the .vpx file changes — so updating a game would silently change
its identity. `vpsId` is still exposed on the game resource, because correlating with VPSdb,
VPinPlay, and other outside services is exactly what it's good for. It's an attribute, not
the key.

Two consequences worth knowing:

- Copying a game folder copies its id. The duplicate is spotted and re-minted the next time
  ids are checked across the library, so an id always addresses one game.
- Deleting a game's `.info` loses its id, the same way it loses that game's rating and play
  counts. A new one is minted; anything holding the old id won't resolve.

Existing games get an id on their next metadata rebuild, or on demand. Reading a game never
mints one — a scan is a read path and stays one.

In Manager UI game rows the field is `vpinfe_id`, pairing with `vpsid` so each name says who
issued the id. The API exposes it as the resource's `id`.

### Schema version

The `vpinfe` section of a game's `.info` carries a `schema` number, bumped when the shape of
the file changes. `Info` and `User` are the interop contract other frontends read and write, so
they stay shape-driven and tolerant; the sections we own carry the version.

A file with no `schema` at all was written by 2.x. It is migrated on read and, on the first
write after that, the original is kept alongside it as `<Game>.info.vpinfe-<timestamp>`.

Migration runs on read, in memory, and never writes — the stamp reaches disk on the next real
write. A section written by a *newer* VPinFE is left exactly as it is: downgrading someone's
data because they ran an older build once is worse than not understanding it. A version we
don't recognize is never a reason to refuse to read a file.

## Adding routes

Build an `APIRouter`, include it in `create_api_app()`, and let the envelope handle failures:

```python
from fastapi import APIRouter
from httpapi.errors import NotFoundError

router = APIRouter(prefix="/games", tags=["games"])

@router.get("/{game_id}")
def get_game(game_id: str) -> dict:
    game = game_repository.find(game_id)
    if game is None:
        raise NotFoundError(f"No game with id {game_id}")
    return game
```

Routes stay thin. The logic already lives in the service layer (`common/`,
`managerui/services/`), and the API is another adapter over it — the same services back the
Manager UI and the WebSocket bridge. If a route is growing logic, that logic belongs in a
service where the other callers can reach it too.

## Testing

`create_api_app()` builds the API standalone, so it's testable without NiceGUI:

```python
from starlette.testclient import TestClient
import httpapi

client = TestClient(httpapi.create_api_app())
assert client.get("/health").json() == {"status": "ok"}
```

See `tests/api/test_http_api.py`.
