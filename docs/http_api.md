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

- The error envelope, CORS, and eventually the auth seam apply to `/api/v1` and to nothing
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
from httpapi.errors import NotFound, InvalidRequest, FeatureUnavailable

raise NotFound(f"No table with id {table_id}")
raise InvalidRequest("sort must be one of: name, year", details={"got": sort})
raise FeatureUnavailable("DOF is not configured on this instance")
```

For anything else, `ApiError(code, message, status_code=..., details=...)`. Uncaught
exceptions become a logged `internal_error` with no detail in the response — put anything the
user needs into an explicit `ApiError`.

Codes defined so far: `not_found`, `invalid_request`, `method_not_allowed`,
`feature_unavailable`, `internal_error`, plus `unauthorized` and `forbidden` reserved for the
auth seam. Add new codes to `httpapi/errors.py` rather than inventing them at a call site.

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

## Adding routes

Build an `APIRouter`, include it in `create_api_app()`, and let the envelope handle failures:

```python
from fastapi import APIRouter
from httpapi.errors import NotFound

router = APIRouter(prefix="/tables", tags=["tables"])

@router.get("/{table_id}")
def get_table(table_id: str) -> dict:
    table = table_repository.find(table_id)
    if table is None:
        raise NotFound(f"No table with id {table_id}")
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
