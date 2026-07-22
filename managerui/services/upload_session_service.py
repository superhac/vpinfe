from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


logger = logging.getLogger("vpinfe.manager.upload_session")

MAX_TOTAL_BYTES = 20 * 1024 ** 3      # 20 GiB per session (PUP packs are large)
SESSION_TTL_SECONDS = 3600
_CHUNK = 1024 * 1024


class UnknownSession(ValueError):
    pass


class UnsafePath(ValueError):
    pass


class UploadTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class UploadSession:
    upload_id: str
    directory: str
    created: float


_sessions: dict[str, dict] = {}     # upload_id -> {"dir": str, "created": float, "bytes": int}
_lock = threading.Lock()


def _safe_join(base: Path, relative: str) -> Path:
    rel = PurePosixPath(relative.replace("\\", "/"))
    drive_letter = len(relative) >= 2 and relative[1] == ":"
    if not relative or rel.is_absolute() or ".." in rel.parts or drive_letter:
        raise UnsafePath(f"Unsafe upload path: {relative}")
    dest = (base / Path(*rel.parts)).resolve()
    try:
        dest.relative_to(base.resolve())
    except ValueError as exc:
        raise UnsafePath(f"Unsafe upload path: {relative}") from exc
    return dest


def _sweep() -> None:
    now = time.time()
    with _lock:
        stale = [uid for uid, rec in _sessions.items() if now - rec["created"] > SESSION_TTL_SECONDS]
        records = [_sessions.pop(uid) for uid in stale]
    for rec in records:
        shutil.rmtree(rec["dir"], ignore_errors=True)


def begin_session() -> UploadSession:
    """Create a fresh upload session backed by a temp directory (sweeping expired ones first)."""
    _sweep()
    upload_id = uuid.uuid4().hex
    directory = tempfile.mkdtemp(prefix="vpinfe_upload_")
    created = time.time()
    with _lock:
        _sessions[upload_id] = {"dir": directory, "created": created, "bytes": 0}
    return UploadSession(upload_id, directory, created)


def _record(upload_id: str) -> dict:
    with _lock:
        rec = _sessions.get(upload_id)
    if rec is None:
        raise UnknownSession("Unknown upload session")
    return rec


def store_file(upload_id: str, relpath: str, stream) -> int:
    """Stream a single uploaded file into the session directory at its relative path."""
    rec = _record(upload_id)
    dest = _safe_join(Path(rec["dir"]), relpath)
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(dest, "wb") as out:
        while True:
            chunk = stream.read(_CHUNK)
            if not chunk:
                break
            written += len(chunk)
            with _lock:
                rec["bytes"] += len(chunk)
                total = rec["bytes"]
            if total > MAX_TOTAL_BYTES:
                raise UploadTooLarge("Upload exceeds the maximum allowed size")
            out.write(chunk)
    return written


def get_session_dir(upload_id: str) -> Path:
    return Path(_record(upload_id)["dir"])


def finish_session(upload_id: str) -> dict:
    directory = get_session_dir(upload_id)
    files = [p for p in directory.rglob("*") if p.is_file()]
    return {"file_count": len(files), "total_bytes": sum(p.stat().st_size for p in files)}


def cleanup_session(upload_id: str) -> None:
    with _lock:
        rec = _sessions.pop(upload_id, None)
    if rec is not None:
        shutil.rmtree(rec["dir"], ignore_errors=True)
