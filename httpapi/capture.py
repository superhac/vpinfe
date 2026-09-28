"""Recording this device's own screens into its tables' media."""

from __future__ import annotations

from fastapi import APIRouter

from common.capture import preflight

from . import models, scopes
from .auth import requires

router = APIRouter(prefix="/capture", tags=["capture"])


@router.get("", summary="What this device can record, and why not",
            dependencies=[requires(scopes.PLAY_READ)])
def get_capture() -> models.CaptureReport:
    return models.CaptureReport.model_validate(preflight.report())
