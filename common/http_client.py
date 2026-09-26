"""Fetching over HTTP, with a timeout every time.

A thin wrapper over requests rather than a client: the point is that no call site can
forget the timeout and hang the app on a server that never answers, or ask a host again
before the time it said to wait.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

DEFAULT_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 60
QUIET_SECONDS = 60.0

# Set to refuse every host but this machine, as an offline machine would.
OFFLINE = "VPINFE_OFFLINE"

logger = logging.getLogger("vpinfe.common.http_client")

_quiet: dict[str, float] = {}
_quiet_lock = threading.Lock()


class HostQuietError(requests.RequestException):
    """A host that said wait, asked before the time it gave."""

    def __init__(self, host: str, until: float, **kwargs: Any) -> None:
        self.host = host
        self.until = until
        super().__init__(f"{host} asked to wait until {_clock(until)}", **kwargs)


class OfflineError(requests.ConnectionError):
    """A host outside this machine, asked while OFFLINE is set."""


def unreachable(log: logging.Logger, what: str, exc: requests.RequestException) -> None:
    refused = isinstance(exc, (HostQuietError, OfflineError))
    log.log(logging.DEBUG if refused else logging.WARNING, "%s: %s", what, exc)


def _clock(when: float) -> str:
    return datetime.fromtimestamp(when).strftime("%H:%M:%S")


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


def _loopback(url: str) -> bool:
    name = (urlsplit(url).hostname or "").lower()
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def _number(value: str | None) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _retry_after(value: str | None, now: float) -> float | None:
    if value is None:
        return None
    seconds = _number(value)
    if seconds is not None:
        return now + seconds
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError):
        return None


def _wait_until(response: requests.Response, now: float) -> float | None:
    """When the host said to ask again, or None when this answer is not a wait."""
    headers = response.headers
    remaining = headers.get("x-ratelimit-remaining")
    limited = remaining is not None or "retry-after" in headers
    if not (response.status_code == 429 or (response.status_code == 403 and limited)):
        return None
    said = _retry_after(headers.get("retry-after"), now)
    if said is None and _number(remaining) == 0:
        said = _number(headers.get("x-ratelimit-reset"))
    return said if said is not None and said > now else now + QUIET_SECONDS


def _asked(verb: Callable[..., requests.Response], url: str,
           **kwargs: Any) -> requests.Response:
    host = _host(url)
    if os.environ.get(OFFLINE, "").strip() and not _loopback(url):
        raise OfflineError(f"{host} is outside this machine and {OFFLINE} is set")
    now = time.time()
    with _quiet_lock:
        until = _quiet.get(host, 0.0)
    if until > now:
        raise HostQuietError(host, until)
    response = verb(url, **kwargs)
    wait = _wait_until(response, time.time())
    if wait is not None:
        with _quiet_lock:
            _quiet[host] = wait
        logger.warning("%s said to wait; not asking it again until %s", host, _clock(wait))
        response.close()
        raise HostQuietError(host, wait, response=response)
    return response


def get_json(
        url: str, *, timeout: int = DEFAULT_TIMEOUT, headers: dict[str, str] | None = None) -> Any:
    response = _asked(requests.get, url, timeout=timeout, headers=headers)
    response.raise_for_status()
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON returned from {url}") from exc


def put_json(url: str, payload: Any, *, timeout: int = DEFAULT_TIMEOUT,
             headers: dict[str, str] | None = None) -> Any:
    """PUT a JSON body and read the answer back. Same rule as the readers: a timeout
    every time, so no call site can hang the app on a server that never answers."""
    response = _asked(requests.put, url, json=payload, timeout=timeout, headers=headers)
    response.raise_for_status()
    try:
        return response.json()
    except json.JSONDecodeError:
        return None


def post_json(url: str, payload: Any = None, *, timeout: int = DEFAULT_TIMEOUT,
              headers: dict[str, str] | None = None) -> Any:
    """POST a JSON body and read the answer back.

    An empty answer is None rather than an error: a 202 that says a thing was started
    need not describe it, and one route here goes down as its own response is sent.
    """
    response = _asked(requests.post, url, json=payload, timeout=timeout, headers=headers)
    response.raise_for_status()
    try:
        return response.json()
    except json.JSONDecodeError:
        return None


def get_text(
        url: str, *, timeout: int = DEFAULT_TIMEOUT, headers: dict[str, str] | None = None) -> str:
    response = _asked(requests.get, url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.text


def get_bytes(url: str, *, timeout: int = DOWNLOAD_TIMEOUT,
              headers: dict[str, str] | None = None) -> bytes:
    response = _asked(requests.get, url, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.content


def download_file(
    url: str,
    dest: Path,
    *,
    timeout: int = DOWNLOAD_TIMEOUT,
    headers: dict[str, str] | None = None,
    chunk_size: int = 1024 * 1024,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with _asked(requests.get, url, timeout=timeout, headers=headers, stream=True) as response:
        response.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    fh.write(chunk)
