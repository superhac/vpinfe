"""Where an extension meets the API: the gate, and who is blamed when one throws.

An extension declares the actions it gates its own routes on; core mints the scope from
its name and attaches it here. Nothing an extension can write reaches a route without a
gate, because the extension does not attach one.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import quote

import anyio
from fastapi import APIRouter, Depends, FastAPI, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from common import extensions
from common.extensions import accounts
from common.i18n import t

from . import models, scopes
from .auth import requires
from .errors import CODE_INTERNAL_ERROR, ApiError, FeatureUnavailableError, NotFoundError

logger = logging.getLogger("vpinfe.httpapi.extensions")

PREFIX = "/ext"

router = APIRouter(prefix="/extensions", tags=["extensions"])


@router.get("", summary="What this install has loaded",
            dependencies=[requires(scopes.INSTANCE_READ)])
def list_extensions() -> dict:
    """Every extension this install looked at, running or not."""
    return {"extensions": [record.as_dict() for record in extensions.records()]}


@router.put("/{name}/enabled", summary="Switch an extension on or off",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def put_extension_enabled(name: str, body: models.ExtensionSwitch) -> dict:
    record = extensions.switch(name, body.enabled)
    if record is None:
        raise NotFoundError(t("error.extensions.no_extension_named", name=name))
    return record.as_dict()


def _running(name: str) -> Any:
    """Refuse on an extension's own routes while it is not running.

    Its scopes are revoked as well, so this is not the only thing in the way. It is the
    one that says which extension and why, which a 403 would not.
    """
    async def check() -> None:
        record = extensions.registry().get(name)
        if record is None or not record.running:
            reason = (record.reason if record is not None
                      else t("extension.reason.not_installed"))
            display = record.display_name if record is not None else name
            raise FeatureUnavailableError(t("error.extensions.extension_not_running",
                    display=(display),
                    value=(reason or t("extension.reason.none_recorded"))))

    return Depends(check)


def mount(api: FastAPI) -> None:
    """Mount every router an extension registered, gated on the scope it declared.

    Once, at startup, whatever becomes of the extension after. A disabled one keeps its
    paths and refuses on them, where a 404 would read as a typo.
    """
    for record, ext_router, scope in extensions.mounted():
        manifest = record.manifest
        unknown = sorted(one for one in (manifest.scopes if manifest else ())
                         if not scopes.is_known(one))
        if unknown:
            extensions.refuse(record.name, "extension.reason.unknown_scopes",
                              scopes=", ".join(unknown))
        for route in getattr(ext_router, "routes", []):
            # On each route rather than on the inclusion: the startup check that refuses
            # an ungated route reads what a route itself declares, and a gate it cannot
            # see is one nothing would notice the loss of.
            route.dependencies.extend([_running(record.name), requires(scope)])
        api.include_router(ext_router, prefix=f"{PREFIX}/{record.name}")
        logger.debug("Mounted %s/%s gated on %s", PREFIX, record.name, scope)


def _answering_for_an_extension(scope: Scope) -> bool:
    path = str(scope.get("path") or "")
    return path[len(str(scope.get("root_path") or "")):].startswith(f"{PREFIX}/")


class SecretsStayHere:
    """Takes the value out of every secret field an extension's route answers with."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _answering_for_an_extension(scope):
            await self.app(scope, receive, send)
            return
        started: list[Message] = []
        body: list[bytes] = []

        async def hold(message: Message) -> None:
            if message["type"] == "http.response.start" and _is_json(message):
                started.append(message)
                return
            if message["type"] != "http.response.body" or not started:
                await send(message)
                return
            body.append(message.get("body", b""))
            if message.get("more_body"):
                return
            kept = accounts.scrubbed_json(b"".join(body))
            headers = [(name, value) for name, value in started[0].get("headers", [])
                       if name.lower() != b"content-length"]
            await send({**started[0],
                        "headers": [*headers, (b"content-length", str(len(kept)).encode())]})
            await send({"type": "http.response.body", "body": kept})

        await self.app(scope, receive, hold)


def _is_json(message: Message) -> bool:
    return any(name.lower() == b"content-type" and b"json" in value.lower()
               for name, value in message.get("headers", []))


async def ask(request: Request, extension: str, method: str, path: str,
              body: Any = None) -> Any:
    """What one of an extension's own routes answers, asked in-process through the whole
    API app, as the caller. An answer that is an error is raised as that error."""
    root = str(request.scope.get("root_path") or "")
    where = f"{root}{PREFIX}/{quote(extension, safe='')}{path}"
    raw = b"" if body is None else json.dumps(body).encode("utf-8")
    finished = anyio.Event()
    asked = False

    async def receive() -> Message:
        nonlocal asked
        if not asked:
            asked = True
            return {"type": "http.request", "body": raw, "more_body": False}
        await finished.wait()
        return {"type": "http.disconnect"}

    status, chunks = [500], []

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            status[0] = int(message["status"])
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                finished.set()

    headers = [(name, value) for name, value in request.scope.get("headers", [])
               if name.lower() not in (b"content-length", b"content-type",
                                       b"transfer-encoding")]
    scope: Scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": request.scope.get("scheme", "http"),
        "path": where, "raw_path": where.encode("utf-8"), "root_path": root,
        "query_string": b"", "client": request.scope.get("client"),
        "server": request.scope.get("server"),
        "headers": [*headers, (b"content-type", b"application/json"),
                    (b"content-length", str(len(raw)).encode())],
    }
    try:
        await request.app(scope, receive, send)
    except Exception:
        # An error nobody expected is answered with a 500 first and raised after; the
        # answer is what counts, and the extension has already been blamed for it.
        logger.debug("%s %s raised after answering", method, where, exc_info=True)
    return _answered(status[0], b"".join(chunks))


def _answered(status: int, body: bytes) -> Any:
    try:
        said = json.loads(body) if body else None
    except ValueError:
        said = None
    if status < 400:
        return said
    error = (said or {}).get("error") if isinstance(said, dict) else None
    if isinstance(error, dict):
        raise ApiError(str(error.get("code") or CODE_INTERNAL_ERROR),
                       str(error.get("message") or ""), status_code=status,
                       details=error.get("details"))
    raise ApiError(CODE_INTERNAL_ERROR, t("error.envelope.internal_server_error"),
                   status_code=status)


def blame(request: Request) -> None:
    """Disable the extension a failing request belonged to, if it belonged to one.

    Called from the envelope's unhandled-error handler. An extension raising an ApiError
    is answering rather than failing, and never arrives there.
    """
    path = request.url.path
    marker = f"{PREFIX}/"
    if marker not in path:
        return
    name = path.split(marker, 1)[1].split("/", 1)[0]
    if extensions.registry().get(name) is not None:
        extensions.disable(name, "extension.reason.failed_serving", path=path)
