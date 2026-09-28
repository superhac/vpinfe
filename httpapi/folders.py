"""This device's folders and files, for a path field's Browse button.

`common/folder_browse.py` decides what is listed and how far it may look.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from common import folder_browse
from common.i18n import t

from . import models, scopes
from .auth import ForbiddenError, caller_is_local, requires

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("", summary="This device's folders and files under a path",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def list_folders(request: Request, path: str = Query(""), kind: str = Query("dir"),
                 suffix: list[str] = Query(default=[])) -> models.FolderListing:
    if not caller_is_local(request):
        raise ForbiddenError(t("error.folders.this_device_only"))
    return models.FolderListing.model_validate(
        folder_browse.listing(path, kind, tuple(suffix)))
