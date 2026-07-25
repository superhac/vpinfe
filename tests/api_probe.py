"""Drives the app's HTTP surface and prints the result as JSON.

Run as a subprocess by tests/test_api_contract.py, not directly. It needs a
private VPINFE_CONFIG_DIR set before any common/ import, which only a fresh
interpreter can guarantee.
"""

from __future__ import annotations

import json
import sys
import warnings

warnings.filterwarnings("ignore")


def probe() -> dict:
    from nicegui import app as nicegui_app
    from starlette.testclient import TestClient

    # managerui.managerui is imported for the side effect of registering its routes.
    import httpapi
    import managerui.managerui  # noqa: F401
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

    # Tables, and the sub-resources that used to be /api/download-table-vpxz.
    listing = client.get("/api/v1/tables")
    record("tables_list", listing)
    tables = (listing.json() or {}).get("tables") or []
    table_id = tables[0]["id"] if tables else ""

    record("table_get", client.get(f"/api/v1/tables/{table_id}"))
    record("table_files", client.get(f"/api/v1/tables/{table_id}/files"))
    archive = client.get(f"/api/v1/tables/{table_id}/archive?download_token=abc123")
    result["table_archive"] = {
        "status": archive.status_code,
        "content_type": (archive.headers.get("content-type") or "").split(";")[0],
        "disposition": archive.headers.get("content-disposition"),
        "set_cookie": archive.headers.get("set-cookie"),
        "bytes": len(archive.content),
    }
    def files_for(name):
        hit = [t for t in tables if t["name"] == name]
        return client.get(f"/api/v1/tables/{hit[0]['id']}/files") if hit else None

    multi = files_for("Multi File")
    if multi is not None:
        record("multi_file_files", multi)
    mismatch = files_for("Mismatch")
    if mismatch is not None:
        record("mismatch_files", mismatch)

    record("table_unknown", client.get("/api/v1/tables/no-such-id"))
    record("archive_unknown", client.get("/api/v1/tables/no-such-id/archive"))
    record("legacy_archive_gone", client.get("/api/download-table-vpxz?name=whatever"))

    # Uploads now live under /api/v1. Walk the same sequence the drag-and-drop
    # client does, so a break in the client's flow shows up here.
    begin = client.post("/api/v1/uploads")
    record("upload_begin", begin)
    upload_id = (begin.json() or {}).get("id", "")

    form = {"relpath": "Example/Example.txt"}
    files = {"file": ("Example.txt", b"hello", "text/plain")}
    record("upload_add_file",
           client.post(f"/api/v1/uploads/{upload_id}/files", data=form, files=files))
    record("upload_summary", client.get(f"/api/v1/uploads/{upload_id}"))
    record("upload_delete", client.delete(f"/api/v1/uploads/{upload_id}"))

    record("upload_unknown_session", client.get("/api/v1/uploads/no-such-session"))
    record("upload_analysis_unknown", client.get("/api/v1/uploads/no-such-session/analysis"))
    record("vps_search", client.get("/api/v1/vps/search?q=&limit=1"))
    record("legacy_upload_gone", client.post("/api/asset-upload/begin"))

    return result


if __name__ == "__main__":
    try:
        print(json.dumps(probe()))
    except Exception as exc:  # surface the real cause to the parent test
        print(json.dumps({"__error__": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)
