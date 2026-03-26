let rotationAngle = 0;
let selectedIndex = 0;
let items = [];
let dialogState = null; // 'options' | 'progress' | 'rating' | null
let dialogSelectedIndex = 0;
let dialogItems = [];
let ratingDraft = 0;
let ratingTableIndex = 0;
let currentTableIndex = 0;
let ratingLabelRequestSeq = 0;
let audioMuted = false;

window.parent.vpin.registerInputHandlerMenu(handleInput);

window.addEventListener('keydown', (e) => {
  if (e.code === 'ShiftLeft' || e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    handleInput('joyleft');
    e.preventDefault();
  } else if (e.code === 'ShiftRight' || e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    handleInput('joyright');
    e.preventDefault();
  } else if (e.key === 'Enter') {
    handleInput('joyselect');
    e.preventDefault();
  } else if (e.key === 'Escape') {
    handleInput('joyback');
    e.preventDefault();
  }
});

window.addEventListener('message', (event) => {
  const message = event.data;
  if (!message) return;

  if (message.event === 'menu_open') {
    if (typeof message.table_index === 'number' && Number.isFinite(message.table_index) && message.table_index >= 0) {
      currentTableIndex = Math.floor(message.table_index);
    } else {
      currentTableIndex = resolveCurrentTableIndex();
    }
    selectedIndex = 0;
    updateMenu();
    refreshRatingMenuLabel(currentTableIndex);
    refreshAudioMenuLabel();
    return;
  }

  if (message.event === 'reset state') {
    selectedIndex = 0;
    updateMenu();
    refreshRatingMenuLabel(resolveCurrentTableIndex());
    refreshAudioMenuLabel();
    return;
  }

  if (message.vpinfeEvent) {
    const ev = message.vpinfeEvent;
    if (
      (ev.type === 'TableIndexUpdate' || ev.type === 'TableDataChange') &&
      typeof ev.index === 'number' &&
      Number.isFinite(ev.index) &&
      ev.index >= 0
    ) {
      currentTableIndex = Math.floor(ev.index);
      refreshRatingMenuLabel(currentTableIndex);
    }
  }
});

window.addEventListener('DOMContentLoaded', () => {
  rotateMenu(rotationAngle);
});

function rotateMenu(degrees) {
  rotationAngle = degrees;
  document.getElementById('menu-container').style.transform = `rotate(${rotationAngle}deg)`;
}

function resolveCurrentTableIndex() {
  try {
    const evalIndex = Number(window.parent.eval('typeof currentTableIndex !== "undefined" ? currentTableIndex : undefined'));
    if (Number.isFinite(evalIndex) && evalIndex >= 0) {
      currentTableIndex = Math.floor(evalIndex);
      return currentTableIndex;
    }
  } catch (_e) {}

  try {
    const evalSelected = Number(window.parent.eval('typeof selectedIndex !== "undefined" ? selectedIndex : undefined'));
    if (Number.isFinite(evalSelected) && evalSelected >= 0) {
      currentTableIndex = Math.floor(evalSelected);
      return currentTableIndex;
    }
  } catch (_e) {}

  try {
    const themeIndex = Number(window.parent.currentTableIndex);
    if (Number.isFinite(themeIndex) && themeIndex >= 0) {
      currentTableIndex = Math.floor(themeIndex);
      return currentTableIndex;
    }
  } catch (_e) {}

  try {
    const parentIndex = Number(window.parent.vpin.getCurrentTableIndex());
    if (Number.isFinite(parentIndex) && parentIndex >= 0) {
      currentTableIndex = Math.floor(parentIndex);
    }
  } catch (_e) {}

  return currentTableIndex;
}

function normalizeRating(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(5, Math.floor(numeric)));
}

function ratingStarsText(rating) {
  const normalized = normalizeRating(rating);
  return `${'★'.repeat(normalized)}${'☆'.repeat(5 - normalized)}`;
}

function syncMenuWidthFromLongestLabel() {
  const menu = document.getElementById('menu');
  const container = document.getElementById('menu-container');
  if (!menu) return;
  if (!container) return;

  const menuItems = Array.from(menu.querySelectorAll('.menu-item'));
  if (menuItems.length === 0) return;

  // Reserve left/right "cap" space in the button image so labels stay centered.
  const sideInsetPx = Math.max(32, Math.round(container.clientHeight * 0.09));
  const edgeBufferPx = Math.max(5, Math.round(container.clientHeight * 0.01));
  menu.style.setProperty('--menu-item-side-inset', `${sideInsetPx}px`);

  const styleProbe = getComputedStyle(menuItems[0]);
  const ruler = document.createElement('span');
  ruler.style.position = 'absolute';
  ruler.style.visibility = 'hidden';
  ruler.style.whiteSpace = 'pre';
  ruler.style.pointerEvents = 'none';
  ruler.style.font = styleProbe.font;
  ruler.style.fontSize = styleProbe.fontSize;
  ruler.style.fontWeight = styleProbe.fontWeight;
  ruler.style.fontFamily = styleProbe.fontFamily;
  ruler.style.letterSpacing = styleProbe.letterSpacing;
  ruler.style.textTransform = styleProbe.textTransform;
  document.body.appendChild(ruler);

  let maxLabelWidth = 0;
  menuItems.forEach((item) => {
    ruler.textContent = item.textContent || '';
    maxLabelWidth = Math.max(maxLabelWidth, Math.ceil(ruler.getBoundingClientRect().width));
  });
  ruler.remove();

  const computedContainer = getComputedStyle(container);
  const containerInnerWidth =
    container.clientWidth
    - parseFloat(computedContainer.paddingLeft || '0')
    - parseFloat(computedContainer.paddingRight || '0');
  const labelWidthWithExtra = Math.ceil(maxLabelWidth * 1.4);
  const rawTargetWidth = Math.ceil(labelWidthWithExtra + sideInsetPx * 2 + edgeBufferPx * 2);
  const targetWidth = Math.max(180, Math.min(rawTargetWidth, Math.floor(containerInnerWidth)));
  menu.style.width = `${targetWidth}px`;

  menuItems.forEach((item) => {
    item.style.whiteSpace = 'nowrap';
    item.style.width = '100%';
  });
}

async function refreshRatingMenuLabel(indexHint = null) {
  const ratingItem = document.getElementById('rating-item');
  if (!ratingItem) return;

  const requestSeq = ++ratingLabelRequestSeq;
  try {
    let idx = Number(indexHint);
    if (!Number.isFinite(idx) || idx < 0) {
      idx = resolveCurrentTableIndex();
    } else {
      idx = Math.floor(idx);
      currentTableIndex = idx;
    }

    const savedRating = await window.parent.vpin.call('get_table_rating', idx);
    if (requestSeq !== ratingLabelRequestSeq) return;
    ratingItem.innerHTML = `Rating (<span style="color:#ffd84d;">${ratingStarsText(savedRating)}</span>)`;
    syncMenuWidthFromLongestLabel();
  } catch (_e) {
    if (requestSeq !== ratingLabelRequestSeq) return;
    ratingItem.textContent = 'Rating';
    syncMenuWidthFromLongestLabel();
  }
}

function handleInput(input) {
  if (dialogState === 'options' || dialogState === 'rating') {
    handleDialogInput(input);
    return;
  }

  if (dialogState === 'progress') {
    if (input === 'joyback' || input === 'joyselect') {
      const closeBtn = document.getElementById('buildmeta-close');
      if (closeBtn.style.display !== 'none') {
        hideBuildMetaDialog();
      }
    }
    return;
  }

  switch (input) {
    case 'joyup':
    case 'joyleft':
      selectedIndex = (selectedIndex - 1 + items.length) % items.length;
      break;
    case 'joydown':
    case 'joyright':
      selectedIndex = (selectedIndex + 1) % items.length;
      break;
    case 'joyselect': {
      const selectedItem = items[selectedIndex];
      if (selectedItem.id === 'quit-item') {
        window.parent.vpin.call('close_app');
      } else if (selectedItem.id === 'shutdown-item') {
        window.parent.vpin.call('shutdown_system');
      } else if (selectedItem.id === 'rating-item') {
        showRatingDialog();
      } else if (selectedItem.id === 'audio-item') {
        toggleAudioMute();
      } else if (selectedItem.id === 'buildmeta-item') {
        showBuildMetaDialog();
      }
      break;
    }
    case 'joyback':
      window.parent.vpin.toggleMenu();
      break;
  }
  updateMenu();
}

function handleDialogInput(input) {
  switch (input) {
    case 'joyup':
    case 'joyleft':
      dialogSelectedIndex = (dialogSelectedIndex - 1 + dialogItems.length) % dialogItems.length;
      updateDialogSelection();
      break;
    case 'joydown':
    case 'joyright':
      dialogSelectedIndex = (dialogSelectedIndex + 1) % dialogItems.length;
      updateDialogSelection();
      break;
    case 'joyselect': {
      const selectedElement = dialogItems[dialogSelectedIndex];
      if (selectedElement.type === 'checkbox') {
        selectedElement.checked = !selectedElement.checked;
      } else if (selectedElement.tagName === 'BUTTON') {
        selectedElement.click();
      }
      break;
    }
    case 'joyback':
      closeActiveDialog();
      break;
  }
}

function closeActiveDialog() {
  if (dialogState === 'options' || dialogState === 'progress') {
    hideBuildMetaDialog();
  } else if (dialogState === 'rating') {
    hideRatingDialog();
  }
}

function updateDialogSelection() {
  dialogItems.forEach((item, i) => {
    if (item.tagName === 'BUTTON') {
      if (i === dialogSelectedIndex) {
        item.style.outline = '3px solid #2196F3';
        item.style.outlineOffset = '2px';
      } else {
        item.style.outline = 'none';
      }
    } else if (item.parentElement && item.parentElement.tagName === 'LABEL') {
      if (i === dialogSelectedIndex) {
        item.parentElement.style.outline = '3px solid #2196F3';
        item.parentElement.style.outlineOffset = '2px';
      } else {
        item.parentElement.style.outline = 'none';
      }
    }
  });
}

function showBuildMetaDialog() {
  document.getElementById('buildmeta-overlay').style.display = 'block';
  document.getElementById('buildmeta-options').style.display = 'block';
  document.getElementById('buildmeta-progress').style.display = 'none';
  dialogState = 'options';
  dialogSelectedIndex = 0;
  dialogItems = [
    document.getElementById('update-all-check'),
    document.getElementById('download-media-check'),
    document.getElementById('buildmeta-cancel'),
    document.getElementById('buildmeta-start'),
  ];
  updateDialogSelection();
}

function hideBuildMetaDialog() {
  document.getElementById('buildmeta-overlay').style.display = 'none';
  dialogState = null;
  dialogItems = [];
  dialogSelectedIndex = 0;
}

function renderRatingStars() {
  const stars = Array.from(document.querySelectorAll('.rating-star'));
  stars.forEach((btn) => {
    const starValue = Number(btn.dataset.rating || '0');
    if (starValue <= ratingDraft) {
      btn.textContent = '★';
      btn.style.color = '#ffd84d';
      btn.style.textShadow = '0 0 1.2vh rgba(255,216,77,0.55)';
    } else {
      btn.textContent = '☆';
      btn.style.color = '#666';
      btn.style.textShadow = 'none';
    }
  });

  const filled = '★'.repeat(ratingDraft);
  const empty = '☆'.repeat(5 - ratingDraft);
  document.getElementById('rating-current-text').innerHTML =
    `Current: <span style="color:#ffd84d;">${filled}</span><span style="color:#777;">${empty}</span> (${ratingDraft}/5)`;
}

async function showRatingDialog() {
  try {
    ratingTableIndex = resolveCurrentTableIndex();
    const savedRating = await window.parent.vpin.call('get_table_rating', ratingTableIndex);
    ratingDraft = normalizeRating(savedRating);
  } catch (_e) {
    ratingTableIndex = resolveCurrentTableIndex();
    ratingDraft = 0;
  }

  renderRatingStars();
  document.getElementById('rating-overlay').style.display = 'block';
  dialogState = 'rating';
  dialogSelectedIndex = 0;
  dialogItems = [
    ...Array.from(document.querySelectorAll('.rating-star')),
    document.getElementById('rating-clear'),
    document.getElementById('rating-cancel'),
    document.getElementById('rating-save'),
  ];
  updateDialogSelection();
}

function hideRatingDialog() {
  document.getElementById('rating-overlay').style.display = 'none';
  dialogState = null;
  dialogItems = [];
  dialogSelectedIndex = 0;
}

async function saveRatingDialog() {
  try {
    await window.parent.vpin.call('set_table_rating', ratingTableIndex, ratingDraft);
    window.parent.vpin.sendMessageToAllWindowsIncSelf({
      type: 'TableDataChange',
      index: ratingTableIndex,
    });
    await refreshRatingMenuLabel(ratingTableIndex);
  } catch (_e) {}
  hideRatingDialog();
}

function startBuildMeta() {
  const updateAll = document.getElementById('update-all-check').checked;
  const downloadMedia = document.getElementById('download-media-check').checked;

  document.getElementById('buildmeta-options').style.display = 'none';
  document.getElementById('buildmeta-progress').style.display = 'block';
  document.getElementById('log-container').innerHTML = '';
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('progress-text').textContent = 'Starting...';
  document.getElementById('buildmeta-close').style.display = 'none';

  dialogState = 'progress';
  dialogItems = [];
  dialogSelectedIndex = 0;

  window.parent.vpin.call('build_metadata', downloadMedia, updateAll);
}

window.receiveEvent = function(event) {
  if (event.type === 'buildmeta_progress') {
    const percent = event.total > 0 ? Math.round((event.current / event.total) * 100) : 0;
    document.getElementById('progress-bar').style.width = `${percent}%`;
    document.getElementById('progress-text').textContent = `${event.message} — ${percent}%`;
  } else if (event.type === 'buildmeta_log') {
    const logContainer = document.getElementById('log-container');
    const logLine = document.createElement('div');
    logLine.textContent = event.message;
    logLine.style.marginBottom = '0.3vh';
    logContainer.appendChild(logLine);
    logContainer.scrollTop = logContainer.scrollHeight;
  } else if (event.type === 'buildmeta_complete') {
    document.getElementById('progress-bar').style.width = '100%';
    document.getElementById('progress-text').textContent =
      `Complete! ${event.result.found} tables scanned, ${event.result.not_found} not found in VPSdb`;
    document.getElementById('buildmeta-close').style.display = 'block';
  } else if (event.type === 'buildmeta_error') {
    document.getElementById('progress-text').textContent = `Error: ${event.error}`;
    document.getElementById('progress-text').style.color = '#f44336';
    document.getElementById('buildmeta-close').style.display = 'block';
  }
};

function updateMenu() {
  items.forEach((item, i) => {
    item.classList.toggle('selected', i === selectedIndex);
  });
}

function audioMenuLabel(muted) {
  return `Frontend Audio: ${muted ? 'Off' : 'On'}`;
}

async function refreshAudioMenuLabel() {
  const audioItem = document.getElementById('audio-item');
  if (!audioItem) return;

  try {
    const muted = await window.parent.vpin.call('get_audio_muted');
    audioMuted = !!muted;
  } catch (_e) {
    audioMuted = false;
  }
  audioItem.textContent = audioMenuLabel(audioMuted);
  syncMenuWidthFromLongestLabel();
}

async function toggleAudioMute() {
  const nextMuted = !audioMuted;
  try {
    const savedMuted = await window.parent.vpin.call('set_audio_muted', nextMuted);
    audioMuted = !!savedMuted;
  } catch (_e) {
    audioMuted = nextMuted;
  }

  const audioItem = document.getElementById('audio-item');
  if (audioItem) {
    audioItem.textContent = audioMenuLabel(audioMuted);
    syncMenuWidthFromLongestLabel();
  }

  if (window.parent.vpin && typeof window.parent.vpin.setAudioMuted === 'function') {
    window.parent.vpin.setAudioMuted(audioMuted);
  }
}

window.onload = async () => {
  currentTableIndex = resolveCurrentTableIndex();
  items = Array.from(document.querySelectorAll('.menu-item'));
  syncMenuWidthFromLongestLabel();
  await refreshRatingMenuLabel(currentTableIndex);
  await refreshAudioMenuLabel();
  updateMenu();

  document.getElementById('buildmeta-cancel').addEventListener('click', hideBuildMetaDialog);
  document.getElementById('buildmeta-start').addEventListener('click', startBuildMeta);
  document.getElementById('buildmeta-close').addEventListener('click', hideBuildMetaDialog);

  const ratingStars = Array.from(document.querySelectorAll('.rating-star'));
  ratingStars.forEach((btn) => {
    btn.addEventListener('click', () => {
      ratingDraft = Math.max(1, Math.min(5, Number(btn.dataset.rating || '1')));
      renderRatingStars();
    });
  });
  document.getElementById('rating-clear').addEventListener('click', () => {
    ratingDraft = 0;
    renderRatingStars();
  });
  document.getElementById('rating-cancel').addEventListener('click', hideRatingDialog);
  document.getElementById('rating-save').addEventListener('click', saveRatingDialog);
};

window.addEventListener('resize', () => {
  syncMenuWidthFromLongestLabel();
});
