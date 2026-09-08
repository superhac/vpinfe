"""Slow work as a job: start it, watch it on the bus, ask about it later.

A job is the answer to "this takes minutes and someone wants to watch". The event
shape is the one common/events.py documents, and it does not vary with who started
the work - a scan begun in the Manager UI looks the same on the stream as one begun
over the API, because both come through here.

Two entry points, one registry behind them. `submit` runs the work on its own thread
and hands back immediately, which is what an HTTP caller needs. `track` wraps work
already running on the caller's thread, which is what the Manager UI needs: its
dialog keeps its own callbacks and its own return value, and gains the event stream
and the busy check for free.

Kinds are exclusive. Two library scans at once would interleave writes to the same
.info files, so the second caller is refused rather than queued - a queue would mean
a user who clicked twice waits through two full scans.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from common import events

logger = logging.getLogger("vpinfe.common.jobs")

ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]

RUNNING = "running"
DONE = "done"
FAILED = "failed"

# Well-known kinds. Named here because both the Manager UI and the API start this
# work and the exclusivity rule only means anything if they agree on the name.
KIND_LIBRARY_SCAN = "library.scan"
# Its own kind, not the scan's: this only reads, so it may run beside anything.
KIND_VPS_ROLLUP = "library.vps_rollup"

# Finished jobs a client can still ask about. Small on purpose: this is a courtesy
# for the caller who missed the last event, not a history feature.
_HISTORY_LIMIT = 20


class JobBusyError(RuntimeError):
    """Work of this kind is already running."""


@dataclass
class JobReporter:
    """The reporting surface a long operation writes to.

    Predates the registry and is still what services accept, so a service needs no
    knowledge of jobs to be run as one.
    """

    logger: logging.Logger
    progress_cb: ProgressCallback | None = None
    log_cb: LogCallback | None = None

    def log(self, message: str) -> None:
        self.logger.info(message)
        if self.log_cb:
            self.log_cb(message)

    def progress(self, current: int, total: int, message: str) -> None:
        if not self.progress_cb:
            return
        try:
            self.progress_cb(current, total, message)
        except Exception:
            self.logger.debug("Progress callback failed", exc_info=True)


@dataclass
class Job:
    """One run of one kind of work.

    `progress`/`log` both publish and chain: whatever callbacks the starter passed
    still fire, so an existing caller keeps its own progress bar while the bus gets
    the same information.
    """

    id: str
    kind: str
    state: str = RUNNING
    pct: int = 0
    message: str = ""
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    progress_cb: ProgressCallback | None = None
    log_cb: LogCallback | None = None

    def progress(self, current: int, total: int, message: str) -> None:
        self.pct = int(100 * current / total) if total else 0
        self.message = message
        if self.progress_cb:
            try:
                self.progress_cb(current, total, message)
            except Exception:
                logger.debug("Progress callback failed", exc_info=True)
        events.emit(events.JOB_PROGRESS, job_id=self.id, pct=self.pct, message=message)

    def log(self, message: str) -> None:
        logger.info(message)
        if self.log_cb:
            try:
                self.log_cb(message)
            except Exception:
                logger.debug("Log callback failed", exc_info=True)

    def reporter(self) -> JobReporter:
        """This job as the surface services already accept."""
        return JobReporter(logger, progress_cb=self.progress, log_cb=self.log)

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "state": self.state,
            "pct": self.pct,
            "message": self.message,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


_lock = threading.RLock()
_active: dict[str, Job] = {}
_history: list[Job] = []


def _finish(job: Job, error: BaseException | None) -> None:
    with _lock:
        _active.pop(job.kind, None)
        job.finished_at = time.time()
        if error is None:
            job.state = DONE
            job.pct = 100
        else:
            job.state = FAILED
            job.error = str(error) or error.__class__.__name__
        _history.append(job)
        del _history[:-_HISTORY_LIMIT]
    if error is None:
        events.emit(events.JOB_DONE, job_id=job.id)
    else:
        events.emit(events.JOB_FAILED, job_id=job.id, error=job.error)


@contextmanager
def track(kind: str, *, progress_cb: ProgressCallback | None = None,
          log_cb: LogCallback | None = None) -> Iterator[Job]:
    """Run work on the caller's thread as a job. Raises JobBusyError if one is running."""
    job = Job(id=uuid.uuid4().hex, kind=kind, progress_cb=progress_cb, log_cb=log_cb)
    with _lock:
        if kind in _active:
            raise JobBusyError(f"{kind} is already running")
        _active[kind] = job
    try:
        yield job
    except BaseException as exc:
        _finish(job, exc)
        raise
    else:
        _finish(job, None)


def submit(kind: str, work: Callable[[Job], object], *,
           progress_cb: ProgressCallback | None = None,
           log_cb: LogCallback | None = None) -> Job:
    """Start work on its own thread and return its job immediately."""
    job = Job(id=uuid.uuid4().hex, kind=kind, progress_cb=progress_cb, log_cb=log_cb)
    with _lock:
        if kind in _active:
            raise JobBusyError(f"{kind} is already running")
        _active[kind] = job

    def _run() -> None:
        try:
            work(job)
        except BaseException as exc:  # noqa: BLE001 - the thread's job is to record it
            logger.exception("Job %s (%s) failed", job.id, job.kind)
            _finish(job, exc)
        else:
            _finish(job, None)

    threading.Thread(target=_run, daemon=True, name=f"job-{kind}").start()
    return job


def get(job_id: str) -> Job | None:
    with _lock:
        for job in _active.values():
            if job.id == job_id:
                return job
        for job in reversed(_history):
            if job.id == job_id:
                return job
    return None


def active(kind: str | None = None) -> list[Job]:
    with _lock:
        jobs = list(_active.values())
    return [job for job in jobs if kind is None or job.kind == kind]


def recent(limit: int = _HISTORY_LIMIT) -> list[Job]:
    """Running jobs first, then the most recently finished."""
    with _lock:
        return list(_active.values()) + list(reversed(_history))[:limit]


def reset_for_tests() -> None:
    with _lock:
        _active.clear()
        _history.clear()
