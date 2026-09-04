"""This install's own log, as records rather than lines.

A traceback is one thing that happened. Split into fourteen rows it buries the message
that caused it, and a level filter drops the half carrying the reason - so a record keeps
its continuation lines and a filter applies to the whole of it.

Answered by the install holding the file. A fleet surface reads another machine's log
through that machine, which is the only party that has it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from common import log_setup

from . import models, scopes
from .auth import requires

logger = logging.getLogger("vpinfe.httpapi.logs")

router = APIRouter(prefix="/logs", tags=["logs"])

# Enough to see what led to something without handing over the whole file. A reader that
# wants more of it has the path.
MAX_RECORDS = 1000


@router.get("", summary="Recent log records from this install",
            dependencies=[requires(scopes.SYSTEM_READ)])
def get_log(limit: int = Query(200, ge=1, le=MAX_RECORDS),
            level: str = "", contains: str = "") -> models.LogRecords:
    """The tail, oldest first, optionally filtered by level or by text. `path` is served
    so a person can go and read the rest of it."""
    found = log_setup.read_log(limit=limit, level=level, contains=contains)
    where = log_setup.log_file()
    return {"count": len(found), "records": found,
            "path": str(where) if where else ""}
