
"""Files arriving in the Console, and what happens between their arrival and the import.

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

from common.i18n import t
from console import import_dialog, offload

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
    asset_kind: str = ""
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

  async function upload(files, say) {
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
        let message = '';
        try { message = (await said.json()).error.message || message; } catch (e) {}
        await fetch(`/api/v1/uploads/${uploadId}`, {method: 'DELETE'});
        throw new Error(message);
      }
      done += 1;
      say({status: 'progress', done: done, total: files.length, name: item.relpath});
    }
    return uploadId;
  }

  // Every way in ends here. `gathering` is already under way when it arrives, because a
  // drop's files can only be read while the drop is still being handled.
  async function send(gathering, say, where) {
    try {
      const files = await gathering;
      if (!files.length) {
        say({status: 'error', empty: true});
        return;
      }
      say({status: 'progress', done: 0, total: files.length, name: ''});
      const uploadId = await upload(files, say);
      say({status: 'done', upload_id: uploadId, name: named(files), ...where});
    } catch (err) {
      say({status: 'error', message: String((err && err.message) || err)});
    }
  }

  function named(files) {
    if (files.length === 1) return files[0].relpath;
    const first = files[0].relpath;
    const cut = first.indexOf('/');
    return cut > 0 ? first.slice(0, cut) : files.length + ' files';
  }

  // Where the pointer is decides the target, and it beats any checked selection: a
  // person who let go on a row meant that row. Null inside a dialog, which covers the
  // page: a dialog that takes a drop takes it itself.
  function landed(target) {
    if (target.closest && target.closest('.q-dialog')) return null;
    const cell = target.closest ? target.closest('.ag-cell') : null;
    const row = target.closest ? target.closest('.ag-row') : null;
    if (!row) return {target: 'library'};
    const rowId = row.getAttribute('row-id') || '';
    const colId = cell ? (cell.getAttribute('col-id') || '') : '';
    if (colId.indexOf('media_') === 0 || colId.indexOf('thumb_') === 0) {
      return {target: 'slot', row_id: rowId,
              media_kind: colId.replace(/^(media_|thumb_)/, '')};
    }
    if (colId.indexOf('asset_') === 0) {
      return {target: 'game', row_id: rowId, asset_kind: colId.slice(6)};
    }
    return {target: 'game', row_id: rowId};
  }

  const lit = (el, on) => { if (el) el.classList.toggle('console-drop-lit', on); };
  let hot = null;

  function highlight(where, event) {
    const el = where.target === 'library' ? null
      : (event.target.closest(where.target === 'slot' || where.asset_kind
                              ? '.ag-cell' : '.ag-row'));
    if (el !== hot) { lit(hot, false); hot = el; lit(hot, true); }
  }

  function clear() { lit(hot, false); hot = null; }

  // A dialog's own ways in. `say` is the emit of the control that asked, so what
  // happens next is heard by that dialog and not by the page behind it.
  window.__consoleDrop = (transfer, say) => send(collect(transfer), say, {});

  window.__consoleChoose = (folder, say) => {
    const input = document.createElement('input');
    input.type = 'file';
    if (folder) input.webkitdirectory = true;
    else input.multiple = true;
    input.onchange = () => send(Promise.resolve(Array.from(input.files || []).map(
      file => ({relpath: file.webkitRelativePath || file.name, file}))), say, {});
    input.click();
  };

  document.addEventListener('dragover', (event) => {
    if (!event.dataTransfer || !Array.from(event.dataTransfer.types || [])
        .includes('Files')) return;
    // Refused rather than ignored: a drop nothing takes opens the file in place of the
    // Console.
    event.preventDefault();
    const where = landed(event.target);
    if (!where) {
      event.dataTransfer.dropEffect = 'none';
      document.body.classList.remove('console-dropping');
      clear();
      return;
    }
    document.body.classList.add('console-dropping');
    highlight(where, event);
  });
  document.addEventListener('dragleave', (event) => {
    if (event.relatedTarget) return;
    document.body.classList.remove('console-dropping');
    clear();
  });
  document.addEventListener('drop', (event) => {
    if (!event.dataTransfer) return;
    event.preventDefault();
    document.body.classList.remove('console-dropping');
    const where = landed(event.target);
    clear();
    if (where) send(collect(event.dataTransfer), emit, where);
  });
}
"""


def install(on_drop: Callable[[Drop], Any]) -> Callable[[Any], None]:
    """Make the whole page a drop target, and return what the page listens to
    `console_dnd` with.

    The document rather than a zone element: every grid in the Console is a place a file
    could sensibly be dropped, and a zone would be one more region to find and aim at.
    Where the pointer was still decides what the drop meant.
    """
    ui.run_javascript(_DND_SCRIPT)
    return listener(on_drop)


def listener(on_arrival: Callable[[Drop], Any]) -> Callable[[Any], None]:
    """What hears one place's uploads, from the first file read to the finished session.

    One per place that starts them: the page for its drop, and a dialog for its own drop
    and pickers, whose controls hand the script their `emit` so the answer comes back to
    them.
    """
    state: dict[str, Any] = {"busy": False, "client": context.client, "note": None}

    def said(event: Any) -> None:
        payload = event.args or {}
        status = payload.get("status")
        if status == "progress":
            total = int(payload.get("total") or 0)
            done = int(payload.get("done") or 0)
            if total > 1:
                _progress(state, t("console.uploads.reading_2", done=(done), total=(total)))
            elif total:
                _progress(state, t("console.uploads.reading"))
        elif status == "error":
            _clear(state)
            if payload.get("empty"):
                ui.notify(t("console.uploads.nothing_to_upload"), type="warning")
            else:
                ui.notify(str(payload.get("message") or t("console.uploads.not_work")),
                          type="negative")
        elif status == "done":
            _clear(state)
            if state["busy"]:
                # One at a time. A second import landing while the first is still being
                # decided would have two dialogs answering for two different sessions.
                ui.notify(t("console.uploads.finish_one_already_open"), type="warning")
                return
            asyncio.create_task(_handle(state, payload, on_arrival))

    return said


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
                     asset_kind=str(payload.get("asset_kind") or ""),
                     upload_id=str(payload.get("upload_id") or ""),
                     name=str(payload.get("name") or ""))
        with client:
            answer = on_drop(found)
            if asyncio.iscoroutine(answer):
                await answer
    except Exception:
        logger.exception("console: a drop could not be handled")
        with client:
            ui.notify(t("console.uploads.not_work"), type="negative")
    finally:
        state["busy"] = False


async def analyzed(library: Any, upload_id: str) -> dict[str, Any] | None:
    """What the install makes of what arrived, or None once it has said why not and let
    the files go."""
    try:
        analysis = await offload.io(library.upload_analysis, upload_id)
    except Exception as exc:  # noqa: BLE001
        analysis = {"error": exc}
    if analysis.get("error"):
        ui.notify(t("console.uploads.could_not_read", exc=analysis["error"]), type="negative")
        await run.io_bound(library.abort_upload, upload_id)
        return None
    return analysis


async def confirmed_import(library: Any, upload_id: str, analysis: dict[str, Any], *,
                           source: str, on_done: Callable[[], Any], game_id: str = "",
                           game_dir: str = "", allow_new_game: bool = False,
                           media_kind: str = "", location_id: str = "",
                           asset_kind: str = "") -> None:
    """From staged files to the import confirmation, and what follows a yes.

    `on_done` runs only after an import, once the library has been read again. Declined,
    blocked or empty, the staged files are let go and nothing else happens.
    """
    try:
        plan = await offload.io(library.upload_plan, upload_id, game_dir=game_dir,
                                allow_new_game=allow_new_game, media_kind=media_kind,
                                location_id=location_id, asset_kind=asset_kind)
    except Exception as exc:  # noqa: BLE001
        ui.notify(t("console.uploads.could_not_work_where", exc=exc), type="negative")
        await run.io_bound(library.abort_upload, upload_id)
        return
    if not plan.get("items"):
        reasons = sorted({str(one.get("reason") or "")
                          for one in plan.get("blocked") or ()})
        ui.notify("; ".join(one for one in reasons if one)
                  or t("console.uploads.nothing_import"), type="warning")
        await run.io_bound(library.abort_upload, upload_id)
        return

    async def done(_report: Any) -> None:
        if game_id:
            library.forget_media(game_id)
        await run.io_bound(library.refresh_after_import)
        answer = on_done()
        if asyncio.iscoroutine(answer):
            await answer

    await import_dialog.open_for(
        library, upload_id, plan, source=source, game_dir=game_dir,
        allow_new_game=allow_new_game, media_kind=media_kind, location_id=location_id,
        asset_kind=asset_kind, declared=_declared(analysis, game_id), on_done=done)


def _declared(analysis: dict[str, Any], game_id: str) -> dict[str, Any]:
    """What choosing a game said the files are: that game's, on the user's word."""
    if not game_id:
        return {}
    names = {str(entry.get("path") or "").rsplit("/", 1)[-1]
             for asset in analysis.get("assets") or ()
             for entry in asset.get("entries") or ()}
    return {name: {"game_id": game_id, "host": "user", "confirmed_by": "user"}
            for name in names if name}


def token() -> str:
    """A per-page id, for anything that has to tell two drops apart."""
    return uuid4().hex[:12]
