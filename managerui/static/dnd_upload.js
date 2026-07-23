// Reusable drag/drop target for the manager UI. Walks dropped files and folders,
// streams them to /api/asset-upload/* with their relative paths, and reports status
// back to Python via the NiceGUI global-event bridge (emitEvent -> ui.on).
(function () {
  if (window.vpinfeDnd) return;

  function emit(payload) {
    if (typeof emitEvent === 'function') {
      emitEvent('vpinfe_dnd', payload);
    }
  }

  function readEntries(reader) {
    return new Promise((resolve, reject) => reader.readEntries(resolve, reject));
  }

  function fileFromEntry(entry) {
    return new Promise((resolve, reject) => entry.file(resolve, reject));
  }

  async function walkEntry(entry, collected) {
    if (entry.isFile) {
      const file = await fileFromEntry(entry);
      collected.push({ relpath: entry.fullPath.replace(/^\/+/, ''), file: file });
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      // readEntries returns at most ~100 entries per call, so loop until empty.
      while (true) {
        const batch = await readEntries(reader);
        if (!batch.length) break;
        for (const child of batch) await walkEntry(child, collected);
      }
    }
  }

  async function collectFiles(dataTransfer) {
    const entries = [];
    const items = dataTransfer.items ? Array.from(dataTransfer.items) : [];
    for (const item of items) {
      const entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
      if (entry) entries.push(entry);
    }
    const collected = [];
    if (entries.length) {
      for (const entry of entries) await walkEntry(entry, collected);
    } else {
      for (const file of Array.from(dataTransfer.files || [])) {
        collected.push({ relpath: file.name, file: file });
      }
    }
    return collected;
  }

  async function uploadAll(token, files) {
    const begin = await fetch('/api/asset-upload/begin', { method: 'POST' });
    const uploadId = (await begin.json()).upload_id;
    let done = 0;
    for (const item of files) {
      const form = new FormData();
      form.append('upload_id', uploadId);
      form.append('relpath', item.relpath);
      form.append('file', item.file, item.file.name);
      const resp = await fetch('/api/asset-upload/file', { method: 'POST', body: form });
      if (!resp.ok) {
        let message = 'Upload failed';
        try { message = (await resp.json()).error || message; } catch (e) { /* ignore */ }
        await fetch('/api/asset-upload/abort', {
          method: 'POST',
          body: new URLSearchParams({ upload_id: uploadId }),
        });
        throw new Error(message);
      }
      done += 1;
      emit({ token: token, status: 'progress', done: done, total: files.length, name: item.relpath });
    }
    const finish = await fetch('/api/asset-upload/finish', {
      method: 'POST',
      body: new URLSearchParams({ upload_id: uploadId }),
    });
    return { uploadId: uploadId, info: await finish.json() };
  }

  function rootName(files) {
    if (files.length === 1) return files[0].relpath;
    const first = files[0].relpath;
    const slash = first.indexOf('/');
    return slash > 0 ? first.slice(0, slash) : files.length + ' files';
  }

  function tokenOf(el) {
    const cls = Array.from(el.classList).find((c) => c.indexOf('vpinfe-dnd-') === 0);
    return cls ? cls.slice('vpinfe-dnd-'.length) : null;
  }

  function attachEl(el) {
    if (!el || el.dataset.vpinfeDndBound) return;
    const token = tokenOf(el);
    if (!token) return;
    el.dataset.vpinfeDndBound = '1';
    const activate = (on) => el.classList.toggle('dnd-drop-zone--active', on);

    el.addEventListener('dragenter', (e) => { e.preventDefault(); activate(true); });
    el.addEventListener('dragover', (e) => { e.preventDefault(); activate(true); });
    el.addEventListener('dragleave', (e) => { if (e.target === el) activate(false); });
    el.addEventListener('drop', async (e) => {
      e.preventDefault();
      activate(false);
      try {
        const files = await collectFiles(e.dataTransfer);
        if (!files.length) {
          emit({ token: token, status: 'error', message: 'No files found in the drop' });
          return;
        }
        emit({ token: token, status: 'progress', done: 0, total: files.length, name: '' });
        const result = await uploadAll(token, files);
        emit({
          token: token, status: 'done', upload_id: result.uploadId,
          file_count: result.info.file_count, total_bytes: result.info.total_bytes,
          name: rootName(files),
        });
      } catch (err) {
        emit({ token: token, status: 'error', message: String((err && err.message) || err) });
      }
    });
  }

  function rowsTokenOf(el) {
    const cls = Array.from(el.classList).find((c) => c.indexOf('vpinfe-dnd-rows-') === 0);
    return cls ? cls.slice('vpinfe-dnd-rows-'.length) : null;
  }

  function attachRowContainer(el) {
    if (!el || el.dataset.vpinfeDndRowsBound) return;
    const token = rowsTokenOf(el);
    if (!token) return;
    el.dataset.vpinfeDndRowsBound = '1';

    const rowOf = (target) => {
      const row = target && target.closest ? target.closest('tr') : null;
      return row && row.querySelector('[data-drop-filename]') ? row : null;
    };
    const clearHighlight = () => {
      el.querySelectorAll('tr.dnd-row-active').forEach((r) => r.classList.remove('dnd-row-active'));
    };

    el.addEventListener('dragover', (e) => {
      const row = rowOf(e.target);
      if (!row) { clearHighlight(); return; }
      e.preventDefault();
      if (!row.classList.contains('dnd-row-active')) {
        clearHighlight();
        row.classList.add('dnd-row-active');
      }
    });
    el.addEventListener('dragleave', (e) => {
      if (e.target === el || !el.contains(e.relatedTarget)) clearHighlight();
    });
    el.addEventListener('drop', async (e) => {
      const row = rowOf(e.target);
      clearHighlight();
      if (!row) return;
      e.preventDefault();
      const rowKey = row.querySelector('[data-drop-filename]').getAttribute('data-drop-filename');
      try {
        const files = await collectFiles(e.dataTransfer);
        if (!files.length) {
          emit({ token: token, status: 'error', message: 'No files found in the drop' });
          return;
        }
        emit({ token: token, status: 'progress', done: 0, total: files.length, name: '' });
        const result = await uploadAll(token, files);
        emit({
          token: token, status: 'done', upload_id: result.uploadId, row_key: rowKey,
          file_count: result.info.file_count, total_bytes: result.info.total_bytes,
          name: rootName(files),
        });
      } catch (err) {
        emit({ token: token, status: 'error', message: String((err && err.message) || err) });
      }
    });
  }

  function cellsTokenOf(el) {
    const cls = Array.from(el.classList).find((c) => c.indexOf('vpinfe-dnd-cells-') === 0);
    return cls ? cls.slice('vpinfe-dnd-cells-'.length) : null;
  }

  function attachCellContainer(el) {
    if (!el || el.dataset.vpinfeDndCellsBound) return;
    const token = cellsTokenOf(el);
    if (!token) return;
    el.dataset.vpinfeDndCellsBound = '1';

    const cellOf = (target) =>
      target && target.closest ? target.closest('td[data-drop-media-key]') : null;
    const clearHighlight = () => {
      el.querySelectorAll('td.dnd-cell-active').forEach((c) => c.classList.remove('dnd-cell-active'));
    };

    el.addEventListener('dragover', (e) => {
      const cell = cellOf(e.target);
      if (!cell) { clearHighlight(); return; }
      e.preventDefault();
      if (!cell.classList.contains('dnd-cell-active')) {
        clearHighlight();
        cell.classList.add('dnd-cell-active');
      }
    });
    el.addEventListener('dragleave', (e) => {
      if (e.target === el || !el.contains(e.relatedTarget)) clearHighlight();
    });
    el.addEventListener('drop', async (e) => {
      const cell = cellOf(e.target);
      clearHighlight();
      if (!cell) return;
      e.preventDefault();
      const mediaKey = cell.getAttribute('data-drop-media-key');
      const rowKey = cell.getAttribute('data-drop-media-row');
      try {
        const files = await collectFiles(e.dataTransfer);
        if (!files.length) {
          emit({ token: token, status: 'error', message: 'No files found in the drop' });
          return;
        }
        emit({ token: token, status: 'progress', done: 0, total: files.length, name: '' });
        const result = await uploadAll(token, files);
        emit({
          token: token, status: 'done', upload_id: result.uploadId,
          cell_row: rowKey, cell_media_key: mediaKey,
          file_count: result.info.file_count, total_bytes: result.info.total_bytes,
          name: rootName(files),
        });
      } catch (err) {
        emit({ token: token, status: 'error', message: String((err && err.message) || err) });
      }
    });
  }

  // Auto-attach: bind any drop zone present now and whenever one is added to the DOM.
  // This survives NiceGUI re-renders and websocket reconnects without a server-side timer.
  function scan() {
    document.querySelectorAll('.dnd-drop-zone').forEach(attachEl);
    document.querySelectorAll('[class*="vpinfe-dnd-rows-"]').forEach(attachRowContainer);
    document.querySelectorAll('[class*="vpinfe-dnd-cells-"]').forEach(attachCellContainer);
  }

  scan();
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.addedNodes && mutation.addedNodes.length) {
        scan();
        return;
      }
    }
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  window.vpinfeDnd = { scan: scan, attach: attachEl };
})();
