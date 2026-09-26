"""Why something failed, in words, for the line under a failure's message."""

from __future__ import annotations

import errno
import os
import socket
from datetime import datetime
from urllib.parse import urlsplit

import requests

from common.http_client import HostQuietError
from common.i18n import t

# errno: the key with no path, and the key naming the path.
_FILES: dict[int, tuple[str, str]] = {
    errno.EACCES: ("said.why.no_permission", "said.why.no_permission_at"),
    errno.EPERM: ("said.why.no_permission", "said.why.no_permission_at"),
    errno.ENOSPC: ("said.why.disk_full", "said.why.disk_full_at"),
    errno.EDQUOT: ("said.why.disk_full", "said.why.disk_full_at"),
    errno.EROFS: ("said.why.read_only", "said.why.read_only_at"),
    errno.ENOENT: ("said.why.nothing_there", "said.why.nothing_at"),
    errno.EEXIST: ("said.why.already_there", "said.why.already_at"),
    errno.ENOTDIR: ("said.why.not_folder", "said.why.not_folder_at"),
    errno.EISDIR: ("said.why.is_folder", "said.why.is_folder_at"),
    errno.EBUSY: ("said.why.in_use", "said.why.in_use_at"),
    errno.ETXTBSY: ("said.why.in_use", "said.why.in_use_at"),
    errno.ENAMETOOLONG: ("said.why.name_too_long", "said.why.name_too_long"),
}

_UNREACHABLE = {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EHOSTDOWN, errno.ENETDOWN}


def why(exc: BaseException) -> str:
    """The failure in words where it is one a person can act on, else the exception's text.

    Never empty, and never a sentence built around the exception: it is the whole line.
    """
    if isinstance(exc, HostQuietError):
        return t("said.why.asked_to_wait_at", host=exc.host,
                 time=datetime.fromtimestamp(exc.until).strftime("%H:%M"))
    if isinstance(exc, requests.RequestException):
        return _network(exc) or _raw(exc)
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return t("said.why.timed_out")
    if isinstance(exc, ConnectionRefusedError):
        return t("said.why.nothing_answers")
    if isinstance(exc, socket.gaierror):
        return t("said.why.unreachable")
    if isinstance(exc, OSError) and exc.errno in _UNREACHABLE:
        return t("said.why.unreachable")
    if isinstance(exc, OSError) and exc.errno in _FILES:
        bare, at = _FILES[exc.errno]
        path = _path(exc.filename)
        return t(at, path=path) if path else t(bare)
    return _raw(exc)


def _raw(exc: BaseException) -> str:
    return str(exc) or exc.__class__.__name__


def _path(filename: object) -> str:
    return os.fsdecode(filename) if isinstance(filename, (str, bytes, os.PathLike)) else ""


def _host(exc: requests.RequestException) -> str:
    url = getattr(exc.request, "url", None) or getattr(exc.response, "url", None)
    return (urlsplit(str(url)).hostname or "") if url else ""


def _wrapped(exc: BaseException) -> list[BaseException]:
    """The exception and what it wraps: requests keeps the socket's error in `args`."""
    found: list[BaseException] = []
    waiting: list[object] = [exc]
    while waiting:
        one = waiting.pop()
        if isinstance(one, BaseException) and not any(one is seen for seen in found):
            found.append(one)
            waiting += [one.__cause__, getattr(one, "reason", None), *one.args]
    return found


def _network(exc: requests.RequestException) -> str:
    host = _host(exc)
    if isinstance(exc, requests.Timeout):
        return t("said.why.timed_out_at", host=host) if host else t("said.why.timed_out")
    if isinstance(exc, requests.ConnectionError):
        if any(isinstance(one, ConnectionRefusedError) for one in _wrapped(exc)):
            return (t("said.why.nothing_answers_at", host=host) if host
                    else t("said.why.nothing_answers"))
        return t("said.why.unreachable_at", host=host) if host else t("said.why.unreachable")
    status = getattr(exc.response, "status_code", 0)
    if not host or not isinstance(exc, requests.HTTPError):
        return ""
    if status in (404, 410):
        return t("said.why.not_found_at", host=host)
    if status in (401, 403):
        return t("said.why.refused_at", host=host)
    if status >= 500:
        return t("said.why.in_trouble_at", host=host)
    return ""
