"""Dropping files onto the Console, and what happens between the drop and the import.

The engine underneath is not this surface's: analysing what arrived, working out where
each file would go and copying it there all live in the install and are reachable over
the API. What is here is the gesture and the conversation - where you can let go, what
you are shown before anything is written, and how a target is named by where you let go
rather than by a control you had to find first.

**The gesture is the declaration.** Letting go on a game's row names that game; on a
media cell it names the slot as well. Nothing is inferred from a filename, because a
person who dropped a file on a row has already said what they meant more clearly than a
name ever does.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from nicegui import context, run, ui

logger = logging.getLogger("vpinfe.console.uploads")

# What a drop lands on, and therefore what it means.
TARGET_LIBRARY = "library"
TARGET_GAME = "game"
TARGET_SLOT = "slot"


@dataclass(frozen=True)
class Drop:
    """Where a drop landed, read off the DOM rather than guessed at."""

    target: str = TARGET_LIBRARY
    # The row's id, which for both grids is the id of the thing the row is about.
    row_id: str = ""
    # The media kind, where it landed on a cell that names one.
    media_kind: str = ""
    upload_id: str = ""
    name: str = ""


# Adapted from the drag-and-drop the Manager UI already ships, with one simplification
# that only this surface can make: its rows and cells needed markup added to carry the
# drop target, and AG Grid already puts `row-id` on every row and `col-id` on every cell.
# So a grid here is a drop target without any change to how its rows are built.
#
# Inline rather than a served file: the Console has no static assets of its own, and the
# served version needs a cache-busting query or a browser keeps the old script - whose
# own guard then blocks the new one. Nothing to bust if there is nothing cached.
_DND_SCRIPT = r"""
if (!window.__consoleDnd) {
  window.__consoleDnd = true;

  const emit = (payload) => {
    if (typeof emitEvent === 'function') emitEvent('console_dnd', payload);
  };

  const readEntries = (reader) =>
    new Promise((resolve, reject) => reader.readEntries(resolve, reject));
  const fileOf = (entry) =>
    new Promise((resolve, reject) => entry.file(resolve, reject));

  async function walk(entry, collected) {
    if (entry.isFile) {
      const file = await fileOf(entry);
      collected.push({relpath: entry.fullPath.replace(/^\/+/, ''), file: file});
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      // readEntries answers at most ~100 at a time, so loop until it answers none.
      while (true) {
        const batch = await readEntries(reader);
        if (!batch.length) break;
        for (const child of batch) await walk(child, collected);
      }
    }
  }

  async function collect(transfer) {
    const entries = [];
    for (const item of Array.from(transfer.items || [])) {
      const entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
      if (entry) entries.push(entry);
    }
    const collected = [];
    if (entries.length) {
      for (const entry of entries) await walk(entry, collected);
    } else {
      for (const file of Array.from(transfer.files || [])) {
        collected.push({relpath: file.name, file: file});
      }
    }
    return collected;
  }

  async function upload(files) {
    const begin = await fetch('/api/v1/uploads', {method: 'POST'});
    const uploadId = (await begin.json()).id;
    let done = 0;
    for (const item of files) {
      const form = new FormData();
      form.append('relpath', item.relpath);
      form.append('file', item.file, item.file.name);
      const said = await fetch(`/api/v1/uploads/${uploadId}/files`,
                               {method: 'POST', body: form});
      if (!said.ok) {
        let message = 'Upload failed';
        try { message = (await said.json()).error.message || message; } catch (e) {}
        await fetch(`/api/v1/uploads/${uploadId}`, {method: 'DELETE'});
        throw new Error(message);
      }
      done += 1;
      emit({status: 'progress', done: done, total: files.length, name: item.relpath});
    }
    return uploadId;
  }

  function named(files) {
    if (files.length === 1) return files[0].relpath;
    const first = files[0].relpath;
    const cut = first.indexOf('/');
    return cut > 0 ? first.slice(0, cut) : files.length + ' files';
  }

  // Where the pointer is decides the target, and it beats any checked selection: a
  // person who let go on a row meant that row.
  function landed(target) {
    const cell = target.closest ? target.closest('.ag-cell') : null;
    const row = target.closest ? target.closest('.ag-row') : null;
    if (!row) return {target: 'library'};
    const rowId = row.getAttribute('row-id') || '';
    const colId = cell ? (cell.getAttribute('col-id') || '') : '';
    if (colId.indexOf('media_') === 0 || colId.indexOf('thumb_') === 0) {
      return {target: 'slot', row_id: rowId,
              media_kind: colId.replace(/^(media_|thumb_)/, '')};
    }
    return {target: 'game', row_id: rowId};
  }

  const lit = (el, on) => { if (el) el.classList.toggle('console-drop-lit', on); };
  let hot = null;

  function highlight(where, event) {
    const el = where.target === 'library' ? null
      : (event.target.closest(where.target === 'slot' ? '.ag-cell' : '.ag-row'));
    if (el !== hot) { lit(hot, false); hot = el; lit(hot, true); }
  }

  function clear() { lit(hot, false); hot = null; }

  document.addEventListener('dragover', (event) => {
    if (!event.dataTransfer || !Array.from(event.dataTransfer.types || [])
        .includes('Files')) return;
    event.preventDefault();
    document.body.classList.add('console-dropping');
    highlight(landed(event.target), event);
  });
  document.addEventListener('dragleave', (event) => {
    if (event.relatedTarget) return;
    document.body.classList.remove('console-dropping');
    clear();
  });
  document.addEventListener('drop', async (event) => {
    if (!event.dataTransfer) return;
    event.preventDefault();
    document.body.classList.remove('console-dropping');
    const where = landed(event.target);
    clear();
    try {
      const files = await collect(event.dataTransfer);
      if (!files.length) {
        emit({status: 'error', message: 'Nothing in that drop'});
        return;
      }
      emit({status: 'progress', done: 0, total: files.length, name: ''});
      const uploadId = await upload(files);
      emit({status: 'done', upload_id: uploadId, name: named(files), ...where});
    } catch (err) {
      emit({status: 'error', message: String((err && err.message) || err)});
    }
  });
}
"""


def install(on_drop: Callable[[Drop], Any]) -> None:
    """Make the whole page a drop target, and say what to do when something lands.

    The document rather than a zone element: every grid in the Console is a place a file
    could sensibly be dropped, and a zone would be one more region to find and aim at.
    Where the pointer was still decides what the drop meant.
    """
    ui.run_javascript(_DND_SCRIPT)
    state: dict[str, Any] = {"busy": False, "client": context.client, "note": None}

    def said(event: Any) -> None:
        payload = event.args or {}
        status = payload.get("status")
        if status == "progress":
            total = int(payload.get("total") or 0)
            done = int(payload.get("done") or 0)
            if total > 1:
                _progress(state, f"Reading {done} of {total}…")
            elif total:
                _progress(state, "Reading…")
        elif status == "error":
            _clear(state)
            ui.notify(str(payload.get("message") or "That did not work"),
                      type="negative")
        elif status == "done":
            _clear(state)
            if state["busy"]:
                # One at a time. A second import landing while the first is still being
                # decided would have two dialogs answering for two different sessions.
                ui.notify("Finish the one already open first", type="warning")
                return
            asyncio.create_task(_handle(state, payload, on_drop))

    ui.on("console_dnd", said)


def _progress(state: dict[str, Any], text: str) -> None:
    if state.get("note") is None:
        state["note"] = ui.notification(text, spinner=True, timeout=None)
    else:
        state["note"].message = text


def _clear(state: dict[str, Any]) -> None:
    if state.get("note") is not None:
        state["note"].dismiss()
        state["note"] = None


async def _handle(state: dict[str, Any], payload: dict[str, Any],
                  on_drop: Callable[[Drop], Any]) -> None:
    state["busy"] = True
    # Bound to the client that asked. `asyncio.create_task` leaves the slot context the
    # event handler was running in, and anything drawn outside one belongs to no page
    # and is silently never shown - which made a drop that did everything right look
    # like a drop that did nothing.
    client = state["client"]
    try:
        found = Drop(target=str(payload.get("target") or TARGET_LIBRARY),
                     row_id=str(payload.get("row_id") or ""),
                     media_kind=str(payload.get("media_kind") or ""),
                     upload_id=str(payload.get("upload_id") or ""),
                     name=str(payload.get("name") or ""))
        with client:
            answer = on_drop(found)
            if asyncio.iscoroutine(answer):
                await answer
    except Exception:
        logger.exception("console: a drop could not be handled")
        with client:
            ui.notify("That drop could not be read", type="negative")
    finally:
        state["busy"] = False


async def analysis_of(library: Any, upload_id: str) -> dict[str, Any]:
    """What the install makes of what arrived."""
    return await run.io_bound(library.upload_analysis, upload_id)


def token() -> str:
    """A per-page id, for anything that has to tell two drops apart."""
    return uuid4().hex[:12]
