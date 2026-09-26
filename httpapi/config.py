"""Every setting this install has, and what it is currently set to.

`common/config_service.py` describes, reads and writes settings for every surface. This
is the HTTP half: a client renders a settings page from what the install says about
itself instead of from a list it carries.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from common import config_service
from common.failures import why
from common.i18n import t
from common.paths import get_ini_config
from frontend import theme_windows

from . import models, scopes
from .auth import requires
from .errors import ConflictError, InvalidRequestError

router = APIRouter(prefix="/config", tags=["config"])


def _windows() -> tuple[str, ...]:
    """The windows the active theme adds, which the schema cannot name in advance."""
    return theme_windows.own_windows(theme_windows.active(get_ini_config()))


@router.get("/schema", summary="Every setting this install has",
            dependencies=[requires(scopes.CONFIG_READ)])
def get_schema() -> models.ConfigSchema:
    """What a settings page is built from. Internal options are left out."""
    return models.ConfigSchema.model_validate(config_service.schema(_windows()))


@router.get("/paths", summary="Whether each path setting finds anything",
            dependencies=[requires(scopes.CONFIG_READ)])
def get_path_checks() -> models.ConfigPathChecks:
    """Every path setting, checked against this device's disk.

    The caller names no path. It asks about settings, and the install answers about the
    values it holds - so this cannot be used to ask whether a file exists somewhere a
    caller is not otherwise allowed to look.
    """
    return models.ConfigPathChecks.model_validate(config_service.path_states())


@router.get("", summary="What this install is set to",
            dependencies=[requires(scopes.CONFIG_READ)])
def get_values() -> models.ConfigValues:
    return models.ConfigValues.model_validate(config_service.values(_windows()))


@router.put("", summary="Change settings",
            dependencies=[requires(scopes.CONFIG_WRITE)])
def put_values(values: dict[str, dict[str, Any]] = Body(...)) -> models.ConfigValues:
    """A patch: only the sections and keys sent are written."""
    try:
        return models.ConfigValues.model_validate(
            config_service.set_values(values, _windows()))
    except config_service.UnknownSettingsError as exc:
        raise InvalidRequestError(
            t("error.config.no_such_settings",
              keys=", ".join(exc.keys))) from exc
    except config_service.ReadOnlySettingsError as exc:
        raise InvalidRequestError(
            t("error.config.read_http_theme_sources",
              keys=", ".join(exc.keys))) from exc
    except config_service.SettingsWriteError as exc:
        raise ConflictError(why(exc)) from exc
