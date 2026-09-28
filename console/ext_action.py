"""What core draws when somebody presses an action an extension offers.

The extension describes what to ask and what to call; this binds its three calls -
`GET {base}`, `POST {base}/check` and `POST {base}/run` - and hands them to the shared
wizard control (`console/wizard.py`), which does the drawing. Nothing about the
treatment comes from the extension, so every action looks like the Console rather than
like whoever wrote it, and it keeps working if that extension later runs somewhere else.
"""

from __future__ import annotations

from typing import Any

from console import offload, wizard
from console.api import ApiClient
from console.on_page import on_page


@on_page
async def open_action(extension: str, action: dict) -> None:
    """Run one action: ask what it asks, in as many steps as it asks it, then do it."""
    client = ApiClient()
    base = f"/ext/{extension}{action.get('base') or ''}"

    async def first() -> dict:
        return await offload.io(client.ext_get, base)

    async def check(values: dict[str, Any], step: str) -> dict:
        return await offload.io(client.ext_post, f"{base}/check",
                                 {"values": values, "step": step})

    async def run(values: dict[str, Any]) -> dict:
        return await offload.io(client.ext_post, f"{base}/run", {"values": values})

    async def job(job_id: str) -> dict:
        return await offload.io(client.job, job_id)

    await wizard.open_dialog(
        label=str(action.get("label") or ""),
        calls=wizard.Calls(first, check, run, job),
        under=f"ext.{extension}.action.{action.get('key')}")
