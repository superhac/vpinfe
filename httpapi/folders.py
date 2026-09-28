"""This device's folders, for a folder field's Browse button.

`common/folder_browse.py` decides what is listed and how far it may look.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from common import folder_browse

from . import models, scopes
from .auth import requires

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("", summary="This device's folders under a path",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def list_folders(path: str = Query("")) -> models.FolderListing:
    return models.FolderListing.model_validate(folder_browse.listing(path))
