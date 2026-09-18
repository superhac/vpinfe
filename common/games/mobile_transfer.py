"""Sending games to a device that runs VPX but not VPinFE.

A phone or tablet running VPX Mobile is not an install: it has no library, no API and
nothing to announce. What it has is a small web server, and this speaks to it.

    GET  /files                                    what is on it, top level
    POST /folder?q=<dir>                           make a folder
    POST /upload?q=<dir>&file=<n>&offset=&length=  one chunk of one file
    POST /delete?q=<path>                          remove a folder
    POST /command?cmd=refresh_tables               look again

**What goes in a transfer is not decided here.** `export_bundle` already answers "what
belongs in an export", and it answers it for the archive somebody downloads as well - so
a game sent to a device and the same game exported as a file hold the same things. Two
answers to that question is the defect this reuse exists to avoid; the plumbing differs
because a zip and a chunked upload are different transports, and that is all that
differs.

`http.client` rather than `urllib`, because urllib re-encodes a query string and the
device's server matches on the bytes it was given.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import quote, urlparse

from common.games.export_bundle import bundle_paths, prune_info

logger = logging.getLogger("vpinfe.common.games.mobile_transfer")

# A megabyte. Large enough that a table moves in a reasonable number of round trips,
# small enough that a lost connection costs one chunk rather than the file.
CHUNK_BYTES = 1024 * 1024

# Short for the questions, long for the uploads: asking what is on a device should fail
# quickly when it is not there, and a chunk of a table crossing a phone's wifi should
# not.
ASK_SECONDS = 10
SEND_SECONDS = 300

Progress = Callable[[int, int, str], None]


class DeviceUnreachableError(RuntimeError):
    """The device did not answer. Its own words where it gave any."""


def carried(host: str, port: int, *, timeout: float = ASK_SECONDS) -> list[str]:
    """The folder names the device holds, sorted.

    Folders only: a file at the top level is not a game, and reporting one as though it
    were would offer a delete that does nothing.
    """
    body = _ask(host, port, "GET", "/files", timeout=timeout)
    try:
        found = json.loads(body.decode("utf-8"))
    except ValueError as exc:
        raise DeviceUnreachableError(f"{host} answered something that is not a file list") from exc
    return sorted(str(one.get("name") or "") for one in found
                  if isinstance(one, dict) and one.get("isDir") and one.get("name"))


def send(game_dir: Path, host: str, port: int, *,
         chunk_bytes: int = CHUNK_BYTES,
         everything: bool = False,
         on_progress: Progress | None = None) -> int:
    """Put one game folder on the device, and say how many files it took.

    The folder is made first and every file is written under it, so a transfer that is
    interrupted leaves a partial game in a folder of its own rather than files loose at
    the top level where the device would try to read them.
    """
    contents = list(bundle_paths(game_dir, everything=everything))
    if not contents:
        raise ValueError(f"{game_dir.name} has nothing to send")

    name = game_dir.name
    _ask(host, port, "POST", f"/folder?q={quote(name, safe='')}", timeout=ASK_SECONDS)

    total = len(contents)
    for index, (path, arcname) in enumerate(_ordered(contents), start=1):
        if on_progress:
            on_progress(index - 1, total, f"{name}: {arcname}")
        _put(host, port, name, str(arcname).replace(os.sep, "/"), path,
             _content_of(path, arcname, contents, name), chunk_bytes)
    if on_progress:
        on_progress(total, total, f"{name}: sent")
    _refresh(host, port)
    return total


def remove(name: str, host: str, port: int) -> None:
    """Take one game off the device."""
    _ask(host, port, "POST", f"/delete?q={quote(name, safe='')}", timeout=ASK_SECONDS)
    _refresh(host, port)


def _ordered(contents: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
    """Files at the folder root first: a device reads a folder as soon as it appears,
    and the table and its metadata landing before the media is what makes it show up
    named rather than as an entry with nothing in it."""
    return sorted(contents, key=lambda pair: ("/" in str(pair[1]).replace(os.sep, "/"),
                                              str(pair[1])))


def _content_of(path: Path, arcname: str, contents: Iterable[tuple[Path, str]],
                name: str) -> bytes | None:
    """The bytes to send, or None to stream the file as it is on disk.

    Only the `.info` differs: what it describes has to match what the transfer actually
    carries, which is the same rule the downloadable archive follows and the same
    function that applies it.
    """
    if arcname != f"{name}.info":
        return None
    allowed = {str(one).replace(os.sep, "/") for _, one in contents}
    return prune_info(path.read_text(encoding="utf-8", errors="replace"),
                      allowed).encode("utf-8")


def _put(host: str, port: int, folder: str, arcname: str, path: Path,
         content: bytes | None, chunk_bytes: int) -> None:
    """One file, in chunks, at the offsets the device expects."""
    where = (f"/upload?q={quote(folder, safe='')}"
             f"&file={quote(arcname, safe='')}")
    if content is not None:
        _ask(host, port, "POST", f"{where}&offset=0&length={len(content)}",
             body=content, timeout=SEND_SECONDS)
        return
    size = path.stat().st_size
    if not size:
        # A zero-length file still has to exist on the far side, and a loop over an
        # empty file would never send anything.
        _ask(host, port, "POST", f"{where}&offset=0&length=0", timeout=SEND_SECONDS)
        return
    offset = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            _ask(host, port, "POST", f"{where}&offset={offset}&length={size}",
                 body=chunk, timeout=SEND_SECONDS)
            offset += len(chunk)


def _refresh(host: str, port: int) -> None:
    """Tell the device to look again. Best effort: the files are there either way, and
    a device that will not be told is still a device that was sent to."""
    try:
        _ask(host, port, "POST", "/command?cmd=refresh_tables", timeout=ASK_SECONDS)
    except Exception:
        logger.debug("%s would not reload its list", host, exc_info=True)


def _ask(host: str, port: int, method: str, path: str, *, body: bytes = b"",
         timeout: float = ASK_SECONDS, tries: int = 3) -> bytes:
    """One request, retried on a dropped connection.

    Retried rather than failed because a phone's wifi drops mid-transfer as a matter of
    course, and a whole game resent for one lost chunk is what a person notices.
    """
    where = urlparse(f"http://{host}:{int(port)}{path}")
    target = where.path + (f"?{where.query}" if where.query else "")
    last: Exception | None = None
    for attempt in range(tries):
        connection = http.client.HTTPConnection(host, int(port), timeout=timeout)
        try:
            connection.request(method, target, body=body,
                               headers={"Content-Length": str(len(body)),
                                        "Connection": "close"})
            answer = connection.getresponse()
            said = answer.read()
            if answer.status >= 400:
                raise DeviceUnreachableError(
                    f"{host} refused {method} {where.path}: {answer.status}")
            return said
        except DeviceUnreachableError:
            raise
        except Exception as exc:
            last = exc
            if attempt < tries - 1:
                time.sleep(2 * (attempt + 1))
        finally:
            connection.close()
    raise DeviceUnreachableError(f"{host} did not answer: {last}")
