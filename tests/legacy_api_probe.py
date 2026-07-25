"""Drives the app's HTTP surface and prints the result as JSON.

Run as a subprocess by tests/test_legacy_api_contract.py, not directly. It needs a
private VPINFE_CONFIG_DIR set before any common/ import, which only a fresh
interpreter can guarantee.
"""

from __future__ import annotations

import json
import sys
import warnings

warnings.filterwarnings("ignore")


def probe() -> dict:
    import managerui.managerui  # registers the Manager UI routes on the nicegui app
    from nicegui import app as nicegui_app
    from starlette.testclient import TestClient

    import httpapi
    if not any(getattr(r, "path", "") == httpapi.API_PREFIX for r in nicegui_app.routes):
        httpapi.register(nicegui_app)

    client = TestClient(nicegui_app, raise_server_exceptions=False)
    result: dict = {}

    def record(name, response, *, body=True):
        entry = {
            "status": response.status_code,
            "cors": response.headers.get("access-control-allow-origin"),
            "content_type": (response.headers.get("content-type") or "").split(";")[0],
        }
        if body:
            try:
                entry["json"] = response.json()
            except Exception:
                entry["json"] = None
        result[name] = entry

    record("remote_launch", client.get("/api/remote-launch"))
    record("archive_missing", client.get("/api/download-table-vpxz?name=__no_such_table__"))
    record("archive_traversal", client.get("/api/download-table-vpxz?name=../../etc"))

    begin = client.post("/api/asset-upload/begin")
    record("upload_begin", begin)
    upload_id = (begin.json() or {}).get("upload_id", "")
    record("upload_abort", client.post("/api/asset-upload/abort", data={"upload_id": upload_id}))
    record("upload_unknown_session",
           client.post("/api/asset-upload/finish", data={"upload_id": "no-such-session"}))
    record("upload_analyze_unknown",
           client.post("/api/asset-upload/analyze", json={"upload_id": "no-such-session"}))
    record("vps_search", client.post("/api/asset-upload/vps-search", json={"q": "", "limit": 1}))

    return result


if __name__ == "__main__":
    try:
        print(json.dumps(probe()))
    except Exception as exc:  # surface the real cause to the parent test
        print(json.dumps({"__error__": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)
