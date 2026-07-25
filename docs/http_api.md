# HTTP API

VPinFE serves a versioned HTTP API at `/api/v1`, on the same port as the Manager UI
(`manageruiport`, default 8001).

> **Unstable.** The API is under active development and may change without notice until v1
> is declared stable. Nothing outside this repo should depend on it yet.

## Structure

- `httpapi/__init__.py`: the app factory (`create_api_app()`) and the mount (`register(app)`).
- `httpapi/errors.py`: the error envelope — `ApiError` and the handlers that shape it.
- `httpapi/meta.py`: discovery and health.
- `httpapi/capabilities.py`: the capability registry discovery reads from.

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
| GET | `/api/v1/play/state` | What this play host is doing. Every change also goes out as `play.state_changed`, so the poll retires once there is a stream to subscribe to |
| GET | `/api/v1/tables` | List tables (`q`, `limit`, `offset`) |
| GET | `/api/v1/tables/{id}` | One table |
| GET | `/api/v1/tables/{id}/files` | The table's game files |
| GET | `/api/v1/tables/{id}/archive` | Download the table folder as `.vpxz` |
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
  "api_version": "v1",
  "app_version": "2.5.0",
  "capabilities": [],
  "extensions": [],
  "links": {
    "self": "/api/v1",
    "health": "/api/v1/health",
    "openapi": "/api/v1/openapi.json",
    "docs": "/api/v1/docs",
    "events": null
  }
}
```

Links are relative so they stay correct behind a reverse proxy. A link that is present but
`null` is a known part of the contract that this instance doesn't offer — clients should
branch on that rather than on its absence.

## Conventions

Field names are `snake_case` (see `docs/conventions.md`), matching Python's own convention (PEP 8) so nothing has to be
translated on the way out, and matching the repo's existing JSON. Plenty of JSON APIs use
snake_case for the same reason — GitHub's and Stripe's among them.

A table resource carries `id` (this install's id) and `vps_id` (correlation with VPSdb and
friends). Sub-resources are linked from `links` rather than assembled by the client.

## Errors

Every failure under `/api/v1` comes back in one shape, with a real HTTP status:

```json
{"error": {"code": "not_found", "message": "No such table", "details": null}}
```

`code` is the contract. Branch on it; don't parse `message`, which is meant for humans and
may be reworded. `details` is optional structured context — for a validation failure it
carries the offending fields.

Raise, don't build responses by hand:

```python
from httpapi.errors import NotFoundError, InvalidRequestError, FeatureUnavailableError

raise NotFoundError(f"No table with id {table_id}")
raise InvalidRequestError("sort must be one of: name, year", details={"got": sort})
raise FeatureUnavailableError("DOF is not configured on this instance")
```

For anything else, `ApiError(code, message, status_code=..., details=...)`. Uncaught
exceptions become a logged `internal_error` with no detail in the response — put anything the
user needs into an explicit `ApiError`.

Codes defined so far: `not_found`, `invalid_request`, `method_not_allowed`,
`feature_unavailable`, `internal_error`, plus `unauthorized` and `forbidden` reserved for the
authorization boundary. Add new codes to `httpapi/errors.py` rather than inventing them at a call site.

## Authorization

Every request into `/api/v1` passes one middleware that stamps an identity on it, and every
route declares the scope it needs:

```python
@router.get("/tables", dependencies=[requires(scopes.TABLES_READ)])
```

**The policy is dormant.** Today whoever can reach the instance is granted every scope, which
is exactly how the app has always behaved — this changes nothing for anyone. What exists now
is the mechanism, so tightening later is a policy change rather than a retrofit across every
endpoint. Replacing `LocalTrustPolicy` is the whole of it.

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
    name="feedback_hardware",
    residency=capabilities.RESIDENCY_PLAY_HOST,
    description="DOF and real-DMD output",
    is_available=lambda: (dof_configured(), "DOF is not configured"),
))
```

`is_available` runs per request, not once at import, so the answer stays honest after the
user changes a setting. Return `(False, reason)` rather than a bare `False` — the reason is
shown to users, so say what's missing and how to fix it.

`residency` records where a capability has to run: `catalog` for things that only need the
library (location-independent, cacheable) and `play_host` for things tied to the machine
where tables launch and hardware lives.

## Table identity

Tables are addressed by an opaque local id — `common/table_identity.py`, stored per table in
its `.info` under `VPinFE.id`:

```
GET /api/v1/tables/6f1c9a4e8b7d4f02a1c35e9d7b204c88
```

The id is minted once and then stays put. It survives renames, VPSdb re-matches, and table
updates, which is what an id in a URL, an event, or a job has to do.

`VPSId` is not that id, and can't be. It's empty for any table VPSdb hasn't matched, it isn't
guaranteed unique, and the effective id used elsewhere (`VPinFE.altvpsid or Info.VPSId`) is
deliberately cleared when the .vpx file changes — so updating a table would silently change
its identity. `vpsId` is still exposed on the table resource, because correlating with VPSdb,
VPinPlay, and other outside services is exactly what it's good for. It's an attribute, not
the key.

Two consequences worth knowing:

- Copying a table folder copies its id. The duplicate is spotted and re-minted the next time
  ids are checked across the library, so an id always addresses one table.
- Deleting a table's `.info` loses its id, the same way it loses that table's rating and play
  counts. A new one is minted; anything holding the old id won't resolve.

Existing tables get an id on their next metadata rebuild, or on demand. Reading a table never
mints one — a scan is a read path and stays one.

In Manager UI table rows the field is `vpinfe_id`, pairing with `vpsid` so each name says who
issued the id. The API exposes it as the resource's `id`.

### Schema version

The `VPinFE` section of a table's `.info` carries a `schema` number, bumped when the shape of
that section changes. It is scoped to that section deliberately: VPinFE owns those keys
outright, so their shape can be reasoned about from a version. `Info` and `VPXFile` are derived
from VPSdb and the vpx file, and the `.info` is a file other tools read and write, so those
sections stay shape-driven and tolerant.

Migration runs on read, in memory, and never writes — the stamp reaches disk on the next real
write. A section written by a *newer* VPinFE is left exactly as it is: downgrading someone's
data because they ran an older build once is worse than not understanding it. A version we
don't recognize is never a reason to refuse to read a file.

## Adding routes

Build an `APIRouter`, include it in `create_api_app()`, and let the envelope handle failures:

```python
from fastapi import APIRouter
from httpapi.errors import NotFoundError

router = APIRouter(prefix="/tables", tags=["tables"])

@router.get("/{table_id}")
def get_table(table_id: str) -> dict:
    table = table_repository.find(table_id)
    if table is None:
        raise NotFoundError(f"No table with id {table_id}")
    return table
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

See `tests/test_http_api.py`.
