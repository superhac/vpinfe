"""One error envelope for /api/v1: {"error": {code, message, details}}.

Routes raise; the handlers here do the shaping. See docs/http_api.md.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from common.i18n import t

logger = logging.getLogger("vpinfe.httpapi.errors")


# Part of the contract: clients branch on these, not on message text.
CODE_NOT_FOUND = "not_found"
CODE_INVALID_REQUEST = "invalid_request"
CODE_METHOD_NOT_ALLOWED = "method_not_allowed"
CODE_FEATURE_UNAVAILABLE = "feature_unavailable"
CODE_CONFLICT = "conflict"
CODE_INTERNAL_ERROR = "internal_error"
# Reserved for the authorization boundary; nothing raises these yet.
CODE_UNAUTHORIZED = "unauthorized"
CODE_FORBIDDEN = "forbidden"

# Statuses that map to a specific code when they arrive as a bare HTTPException
# (from routing, or from code that raises HTTPException directly).
_STATUS_CODES = {
    401: CODE_UNAUTHORIZED,
    403: CODE_FORBIDDEN,
    404: CODE_NOT_FOUND,
    405: CODE_METHOD_NOT_ALLOWED,
    409: CODE_CONFLICT,
    422: CODE_INVALID_REQUEST,
    501: CODE_FEATURE_UNAVAILABLE,
}


class ApiError(Exception):
    """An error to return to the client in the standard envelope."""

    def __init__(self, code: str, message: str, *, status_code: int = 400,
                 details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFoundError(ApiError):
    def __init__(self, message: str = "", *, details: Any = None) -> None:
        message = message or t("error.envelope.not_found")
        super().__init__(CODE_NOT_FOUND, message, status_code=404, details=details)


class InvalidRequestError(ApiError):
    def __init__(self, message: str = "", *, details: Any = None) -> None:
        message = message or t("error.envelope.invalid_request")
        super().__init__(CODE_INVALID_REQUEST, message, status_code=400, details=details)


class ConflictError(ApiError):
    """The request is fine, but the thing it asks for cannot happen right now -
    something is already using what it needs."""

    def __init__(self, message: str = "", *, details: Any = None) -> None:
        message = message or t("error.envelope.conflict")
        super().__init__(CODE_CONFLICT, message, status_code=409, details=details)


class FeatureUnavailableError(ApiError):
    """Exists, but not available here. The message is user-facing: say how to enable it."""

    def __init__(self, message: str = "", *, details: Any = None) -> None:
        message = message or t("error.envelope.feature_unavailable")
        super().__init__(CODE_FEATURE_UNAVAILABLE, message, status_code=501, details=details)


def error_response(status_code: int, code: str, message: str,
                   details: Any = None) -> JSONResponse:
    """Build an envelope response directly. Prefer raising ApiError."""
    error: dict[str, Any] = {"code": code, "message": message}
    error["details"] = jsonable_encoder(details) if details is not None else None
    return JSONResponse(status_code=status_code, content={"error": error})


def install_error_handlers(app, on_unhandled=None) -> None:
    """Attach the envelope handlers. Only ever the /api/v1 app - these would turn the
    Manager UI's HTML error pages into JSON.

    `on_unhandled` is told which request raised something nobody expected, so the
    extension seam can take the extension that did it out. Passed in rather than
    imported: this module is what the seam raises through.
    """

    @app.exception_handler(ApiError)
    async def _api_error(request, exc: ApiError):
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request, exc: StarletteHTTPException):
        code = _STATUS_CODES.get(exc.status_code)
        if code is None:
            code = CODE_INVALID_REQUEST if exc.status_code < 500 else CODE_INTERNAL_ERROR
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request, exc: RequestValidationError):
        return error_response(422, CODE_INVALID_REQUEST,
                              t("error.envelope.validation_failed"), exc.errors())

    @app.exception_handler(Exception)
    async def _unhandled(request, exc: Exception):
        # Log the cause; tell the client nothing beyond "we broke".
        logger.exception("Unhandled error serving %s %s", request.method, request.url.path)
        if on_unhandled is not None:
            try:
                on_unhandled(request)
            except Exception:
                logger.exception("Reporting the failure failed as well")
        return error_response(500, CODE_INTERNAL_ERROR, t("error.envelope.internal"))
