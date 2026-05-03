//console methods for overriding
const originalConsole = {
  log: console.log,
  info: console.info,
  warn: console.warn,
  error: console.error,
  debug: console.debug,
};

const MEDIA_PATH_FIELDS = {
  table: "TableImagePath",
  fss: "FSSImagePath",
  bg: "BGImagePath",
  dmd: "DMDImagePath",
  wheel: "WheelImagePath",
  cab: "CabImagePath",
  realdmd: "realDMDImagePath",
  "realdmd-color": "realDMDColorImagePath",
  realdmd_color: "realDMDColorImagePath",
  flyer: "FlyerImagePath",
};


class VPinFECore {
  constructor() {
    this.tableData = {};
    this.monitors = [];
    this._resolveReady = null;
    this.ready = new Promise(resolve => this._resolveReady = resolve);
    this.inputHandlers = []; // gamepad and joystick input handlers for theme
    this.inputHandlerMenu = []; // gamepad and joystick input handlers for menu
    this.inputHandlerCollectionMenu = []; // gamepad and joystick input handlers for collection menu
    this.inputHandlerTutorial = []; // gamepad and joystick input handlers for tutorial overlay

    // Gamepad mapping
    this.joyButtonMap = {}
    this.keyActionMap = {
      joyleft: ['arrowleft', 'shiftleft'],
      joyright: ['arrowright', 'shiftright'],
      joyup: ['arrowup'],
      joydown: ['arrowdown'],
      joypageup: ['pageup'],
      joypagedown: ['pagedown'],
      joyselect: ['enter'],
      joymenu: ['m'],
      joyback: [],
      joytutorial: ['t'],
      joyexit: ['escape', 'q'],
      joycollectionmenu: ['c'],
    };
    this.previousButtonStates = {};
    this.gamepadEnabled = true;

    // menu is up?
    this.menuUP = false;
    this.collectionMenuUP = false;
    this.tutorialUP = false;

    // Event handling
    this.eventHandlers = {}; // Custom event handlers registered by themes

    // Network config
    this.themeAssetsPort = 8000; // default, will be updated from config
    this.managerUiPort = 8001; // default manager UI port
    this.wsPort = 8002; // default WebSocket bridge port
    this.vpinplayEndpoint = '';

    // Display config
    this.tableOrientation = 'landscape'; // default, will be updated from config
    this.tableRotation = 0; // default, will be updated from config

    // Remote launch state tracking
    this.remoteLaunchActive = false;

    // Theme config and centralized audio state
    this.themeConfig = {};
    this._currentTableIndex = 0;
    this._coreAudioEnabled = true;
    this._audioMuted = false;
    this._audio = Object.assign(new Audio(), { loop: true });
    this._audioFadeId = null;
    this._audioFadeDuration = 500;
    this._audioMaxVolume = 0.8;
    this._audioCurrentUrl = null;
    this._audioRetries = 0;
    this._lastFrontendDofIndex = null;
    this._vpinplayRatingCache = new Map();
    this._vpinplayRatingRequests = new Map();

    // WebSocket bridge
    this._ws = null;
    this._pendingCalls = {}; // {callId: {resolve, reject}}
    this._callIdCounter = 0;
    this._windowName = this.#detectWindowName();
    this.#applyWindowIdentity();

  }

  #detectWindowName() {
    const queryWindow = new URLSearchParams(window.location.search).get('window');
    if (queryWindow) return queryWindow;

    const match = window.location.pathname.match(/^\/app\/(bg|dmd|table)\/?$/);
    if (match) return match[1];

    return 'unknown';
  }

  // ***********************************
  // Public api
  // ***********************************

  init() {
    this.#applyWindowIdentity();
    window.__vpinCoreResumeAudio = () => this.#audioResumePlay();

    // Set up keyboard listener
    window.addEventListener('keydown', (e) => this.#onKeyDown(e));

    // Connect to WebSocket bridge
    this.#connectWebSocket();
  }

  // theme register for Input events - Only for the table screen!
  async registerInputHandler(handler) {
    windowName = await this.call("get_my_window_name");
    if (typeof handler === 'function' && windowName == "table") {
      this.call("console_out", "registered gamepad handler");
      this.inputHandlers.push(handler);
    }
  }

  // Menu register for Input events
  async registerInputHandlerMenu(handler) {
    if (typeof handler === 'function') {
      this.call("console_out", "registered gamepad handler");
      this.inputHandlerMenu.push(handler);
    }
  }

  // Collection Menu register for Input events
  async registerInputHandlerCollectionMenu(handler) {
    if (typeof handler === 'function') {
      this.call("console_out", "registered collection menu gamepad handler");
      this.inputHandlerCollectionMenu.push(handler);
    }
  }

  async registerInputHandlerTutorial(handler) {
    if (typeof handler === 'function') {
      this.call("console_out", "registered tutorial gamepad handler");
      this.inputHandlerTutorial.push(handler);
    }
  }

  async call(method, ...args) {
    if (!this._ws || this._ws.readyState !== WebSocket.OPEN) {
      throw new Error(`WebSocket not connected, cannot call ${method}`);
    }
    const callId = String(++this._callIdCounter);
    return new Promise((resolve, reject) => {
      this._pendingCalls[callId] = { resolve, reject };
      this._ws.send(JSON.stringify({
        type: 'api_call',
        id: callId,
        method: method,
        args: args
      }));
    });
  }

  // get table image url paths
  getImageURL(index, type) {
    const table = this.tableData[index];
    if (!table) return null;
    const field = MEDIA_PATH_FIELDS[type];
    return field ? this.#convertPathToURL(table[field]) : null;
  }

  // get table audio url path (returns null if no audio exists)
  getAudioURL(index) {
    const table = this.tableData[index];
    if (!table) return null;
    if (!table.AudioPath) return null;
    return this.#convertPathToURL(table.AudioPath);
  }

  enableCoreAudio(enabled = true) {
    this._coreAudioEnabled = !!enabled;
    if (!this._coreAudioEnabled) this.stopTableAudio({ immediate: true });
  }

  isCoreAudioEnabled() {
    return !!this._coreAudioEnabled;
  }

  setAudioMuted(muted = true) {
    this._audioMuted = !!muted;
    if (this._audio) this._audio.muted = this._audioMuted;
    if (this._audioMuted) {
      this.stopTableAudio({ immediate: true });
      return;
    }
    if (this._coreAudioEnabled && this._windowName === "table") {
      this.playTableAudio(this._currentTableIndex);
    }
  }

  isAudioMuted() {
    return !!this._audioMuted;
  }

  setAudioOptions(options = {}) {
    if (typeof options !== 'object' || options === null) return;

    const fadeMs = this.#coerceNumber(
      options.fadeDuration,
      options.fade_duration_ms,
      options.fadeMs
    );
    if (fadeMs !== null) this._audioFadeDuration = Math.max(0, fadeMs);

    const volume = this.#coerceNumber(
      options.maxVolume,
      options.max_volume,
      options.volume
    );
    if (volume !== null) this._audioMaxVolume = Math.min(1, Math.max(0, volume));

    if (typeof options.loop === 'boolean') this._audio.loop = options.loop;
  }

  playTableAudio(indexOrUrl = this._currentTableIndex, retries = 3) {
    if (!this._coreAudioEnabled || this._audioMuted || this._windowName !== "table") return;
    const url = this.#resolveTableAudioUrl(indexOrUrl);
    if (!url) {
      this.stopTableAudio();
      return;
    }
    if (this._audioCurrentUrl === url && !this._audio.paused) return;

    clearInterval(this._audioFadeId);
    this._audio.pause();
    this._audio.volume = 0;
    this._audio.src = url;
    this._audioCurrentUrl = url;

    this._audio.play().then(() => {
      if (this._audioCurrentUrl === url) this.#fadeAudio(0, this._audioMaxVolume);
    }).catch((e) => {
      if (e && e.name === "NotAllowedError") {
        this._audioRetries = retries;
        this.#audioTriggerWhenReady(url);
      } else if (retries > 0 && this._audioCurrentUrl === url) {
        setTimeout(() => this.playTableAudio(url, retries - 1), 1000);
      }
    });
  }

  stopTableAudio(options = {}) {
    const immediate = !!(options && options.immediate);
    if (!this._audio || this._audio.paused) {
      clearInterval(this._audioFadeId);
      this._audioCurrentUrl = null;
      return;
    }
    if (immediate) {
      clearInterval(this._audioFadeId);
      this._audio.volume = 0;
      this._audio.pause();
      this._audioCurrentUrl = null;
      return;
    }
    this.#fadeAudio(this._audio.volume, 0, () => {
      this._audio.pause();
      this._audioCurrentUrl = null;
    });
  }

  // get table video url paths
  getVideoURL(index, type) {
    const table = this.tableData[index];
    if (type == "table") {
      return this.#convertPathToURL(table.TableVideoPath);
    }
    else if (type == "bg") {
      return this.#convertPathToURL(table.BGVideoPath);
    }
    else if (type == "dmd") {
      return this.#convertPathToURL(table.DMDVideoPath);
    }
  }

  getTableMeta(index) {
    return this.tableData[index];
  }

  getTableCount() {
    return this.tableData.length;
  }

  getCurrentTableIndex() {
    return this._currentTableIndex;
  }

  getCachedVPinPlayRating(index = this._currentTableIndex) {
    const table = this.#getTableByIndex(index);
    if (!table) return null;

    const vpsId = this.#getTableVPinPlayVpsId(table);
    if (!vpsId) return null;

    const cached = this._vpinplayRatingCache.get(vpsId);
    return cached && cached.data ? cached.data : null;
  }

  async getVPinPlayRating(index = this._currentTableIndex, options = {}) {
    return this.#loadVPinPlayRating(index, !!(options && options.forceRefresh));
  }

  async refreshVPinPlayRating(index = this._currentTableIndex) {
    return this.#loadVPinPlayRating(index, true);
  }

  // send a message to all windows except "self"
  sendMessageToAllWindows(message) {
    this.#syncLocalIndexFromOutgoingMessage(message);
    this.#syncFrontendDofFromMessage(message);
    this.call("send_event_all_windows", message);
  }

  // send a message to all windows including "self"
  sendMessageToAllWindowsIncSelf(message) {
    this.#syncLocalIndexFromOutgoingMessage(message);
    this.#syncFrontendDofFromMessage(message);
    this.call("send_event_all_windows_incself", message);
  }

  // Toggle collection menu (public method callable from collection menu)
  toggleCollectionMenu() {
    this.#showcollectionmenu();
  }

  // Toggle main menu (public method callable from main menu)
  toggleMenu() {
    this.#showmenu();
  }

  toggleTutorial() {
    this.#showtutorial();
  }

  // launch a table
  async launchTable(index) {
    this.gamepadEnabled = false;
    try {
      await this.call("launch_table", index);
    } catch (e) {
      // The call will timeout after 30s while VPX is still running - that's expected
      this.call("console_out", `launch_table call ended: ${e.message}`);
    } finally {
      this.gamepadEnabled = true;
    }
  }

  async getTableData(reset=false) {
    this.tableData = JSON.parse(await this.call("get_tables", reset));
    this.#attachCachedVPinPlayRatings();
    if (this._windowName === "table") {
      const maxIndex = Math.max(0, this.tableData.length - 1);
      if (this._currentTableIndex > maxIndex) this._currentTableIndex = maxIndex;
      if (this.tableData.length > 0) {
        this.getVPinPlayRating(this._currentTableIndex).catch(() => {});
        this.#updateFrontendDofForCurrentTable().catch(() => {});
      } else {
        this._lastFrontendDofIndex = null;
      }
    }
  }

  // Register an event handler for a specific event type
  // eventType: string (e.g., "TableIndexUpdate", "TableDataChange", etc.)
  // handler: function to call when event is received
  registerEventHandler(eventType, handler) {
    if (typeof handler === 'function') {
      if (!this.eventHandlers[eventType]) {
        this.eventHandlers[eventType] = [];
      }
      this.eventHandlers[eventType].push(handler);
      this.call("console_out", `Registered event handler for ${eventType}`);
    }
  }

  // Handle incoming events from window.receiveEvent
  // This should be called from the theme's receiveEvent function
  async handleEvent(message) {
    if (typeof message.index === "number") this._currentTableIndex = message.index;
    if (message.type === "AudioMuteChanged") {
      this.setAudioMuted(!!message.muted);
      return;
    }

    // Default handling for TableDataChange
    if (message.type === "TableDataChange") {
      if (this._windowName === "table") this._lastFrontendDofIndex = null;
      await this.#handleTableDataChange(message);
    }
    this.#syncFrontendDofFromMessage(message);
    await this.#handleCoreAudioEvent(message);

    // Call any custom handlers registered by the theme
    if (this.eventHandlers[message.type]) {
      for (const handler of this.eventHandlers[message.type]) {
        await handler(message);
      }
    }
  }

  #applyWindowIdentity() {
    const windowName = this._windowName;
    const windowLabel = this.#getWindowLabel(windowName);

    window.name = windowName;
    document.title = `VPinFE ${windowLabel}`;
  }

  #getWindowLabel(windowName) {
    if (windowName === 'bg') {
      return 'BG';
    }
    if (windowName === 'dmd') {
      return 'DMD';
    }
    if (windowName === 'table') {
      return 'Table';
    }
    return 'Window';
  }

  // Default handler for TableDataChange events
  async #handleTableDataChange(message) {
    // Check if a collection filter was applied
    if (message.collection) {
      // if collection is "None" then reset to all tables, otherwise set to the selected collection.
      if (message.collection === "None") {
        await this.getTableData(true);
      } else {
        await this.call("set_tables_by_collection", message.collection);
        await this.getTableData();
      }
    } else if (message.filters) {
      // VPSdb filters - apply them to this window's API instance
      await this.call("apply_filters",
        message.filters.letter,
        message.filters.theme,
        message.filters.type,
        message.filters.manufacturer,
        message.filters.year,
        message.filters.rating,
        message.filters.rating_or_higher
      );
      // If a sort order is also specified, apply it after filters
      if (message.sort) {
        await this.call("apply_sort", message.sort, message.order);
      }
      await this.getTableData();
    } else if (message.sort) {
      // Sort order change - apply it to this window's API instance
      await this.call("apply_sort", message.sort, message.order);
      await this.getTableData();
    } else {
      // No filters specified - just refresh table data
      await this.getTableData();
    }
  }

  async #handleCoreAudioEvent(message) {
    if (!this._coreAudioEnabled || this._windowName !== "table") return;

    if (message.type === "TableIndexUpdate") {
      this.playTableAudio(this._currentTableIndex);
      return;
    }
    if (message.type === "TableLaunching" || message.type === "RemoteLaunching") {
      this.stopTableAudio();
      return;
    }
    if (message.type === "TableLaunchComplete" || message.type === "RemoteLaunchComplete") {
      this.playTableAudio(this._currentTableIndex);
      return;
    }
    if (message.type === "TableDataChange" && typeof message.index === "number") {
      this.playTableAudio(this._currentTableIndex);
    }
  }

  #resolveTableAudioUrl(indexOrUrl) {
    if (typeof indexOrUrl === "number" && Number.isFinite(indexOrUrl)) {
      this._currentTableIndex = indexOrUrl;
      return this.getAudioURL(indexOrUrl);
    }
    if (typeof indexOrUrl === "string") return indexOrUrl;
    return null;
  }

  #syncLocalIndexFromOutgoingMessage(message) {
    if (!message || typeof message !== "object") return;
    if (typeof message.index !== "number" || !Number.isFinite(message.index)) return;
    if (message.index < 0) return;
    if (message.type === "TableIndexUpdate" || message.type === "TableDataChange") {
      this._currentTableIndex = Math.floor(message.index);
    }
  }

  #syncFrontendDofFromMessage(message) {
    if (!message || typeof message !== "object") return;
    if (this._windowName !== "table") return;

    if (message.type === "TableIndexUpdate") {
      this.getVPinPlayRating(this._currentTableIndex).catch(() => {});
      this.#updateFrontendDofForCurrentTable().catch(() => {});
      return;
    }
    if (message.type === "TableLaunchComplete" || message.type === "RemoteLaunchComplete") {
      this._lastFrontendDofIndex = null;
      this.getVPinPlayRating(this._currentTableIndex).catch(() => {});
      this.#updateFrontendDofForCurrentTable().catch(() => {});
    }
  }

  async #updateFrontendDofForCurrentTable() {
    if (this._windowName !== "table") return;
    if (!Array.isArray(this.tableData) || this.tableData.length === 0) return;

    const index = Math.floor(this._currentTableIndex);
    if (!Number.isFinite(index) || index < 0 || index >= this.tableData.length) return;
    if (this._lastFrontendDofIndex === index) return;

    this._lastFrontendDofIndex = index;
    try {
      await this.call("update_frontend_dof_for_table", index);
    } catch (e) {
      this._lastFrontendDofIndex = null;
      this.call("console_out", `update_frontend_dof_for_table failed: ${e.message}`);
    }
  }

  #coerceNumber(...values) {
    for (const value of values) {
      if (value === undefined || value === null || value === "") continue;
      const numeric = Number(value);
      if (!Number.isNaN(numeric) && Number.isFinite(numeric)) return numeric;
    }
    return null;
  }

  #getTableByIndex(index) {
    const numeric = Number(index);
    if (!Number.isFinite(numeric)) return null;
    const normalized = Math.floor(numeric);
    if (!Array.isArray(this.tableData) || normalized < 0 || normalized >= this.tableData.length) return null;
    return this.tableData[normalized];
  }

  #getTableVPinPlayVpsId(table) {
    if (!table || typeof table !== "object") return "";
    const meta = (table.meta && typeof table.meta === "object") ? table.meta : {};
    const info = (meta.Info && typeof meta.Info === "object") ? meta.Info : {};
    return String(info.VPSId || "").trim();
  }

  #getVPinPlayUrl(vpsId) {
    const endpoint = String(this.vpinplayEndpoint || "").trim().replace(/\/+$/, "");
    if (!endpoint || !vpsId) return "";
    return `${endpoint}/api/v1/tables/${encodeURIComponent(vpsId)}/cumulative-rating`;
  }

  #normalizeVPinPlayRatingPayload(vpsId, payload) {
    if (!payload || typeof payload !== "object") return null;

    const resolvedVpsId = String(payload.vpsId || vpsId || "").trim();
    const cumulativeRating = this.#coerceNumber(payload.cumulativeRating);
    const ratingCount = this.#coerceNumber(payload.ratingCount);
    const vpsdb = (payload.vpsdb && typeof payload.vpsdb === "object") ? payload.vpsdb : {};
    const normalizedYear = this.#coerceNumber(vpsdb.year, vpsdb.year === "" ? null : vpsdb.year);

    return {
      vpsId: resolvedVpsId,
      cumulativeRating: cumulativeRating === null ? null : cumulativeRating,
      ratingCount: ratingCount === null ? 0 : Math.max(0, Math.floor(ratingCount)),
      vpsdb: {
        name: typeof vpsdb.name === "string" ? vpsdb.name : "",
        authors: Array.isArray(vpsdb.authors) ? vpsdb.authors : [],
        manufacturer: typeof vpsdb.manufacturer === "string" ? vpsdb.manufacturer : "",
        year: normalizedYear !== null ? normalizedYear : (vpsdb.year || ""),
      },
      fetchedAt: new Date().toISOString(),
    };
  }

  #setTableVPinPlayRating(table, payload) {
    if (!table || typeof table !== "object") return;
    table.vpinplay = payload ? { ...payload } : null;
  }

  #setCachedVPinPlayRatingForCurrentTables(vpsId, payload) {
    if (!Array.isArray(this.tableData)) return;
    this.tableData.forEach((table) => {
      if (this.#getTableVPinPlayVpsId(table) === vpsId) {
        this.#setTableVPinPlayRating(table, payload);
      }
    });
  }

  #attachCachedVPinPlayRatings() {
    if (!Array.isArray(this.tableData)) return;
    this.tableData.forEach((table) => {
      const vpsId = this.#getTableVPinPlayVpsId(table);
      if (!vpsId) {
        this.#setTableVPinPlayRating(table, null);
        return;
      }
      const cached = this._vpinplayRatingCache.get(vpsId);
      this.#setTableVPinPlayRating(table, cached && cached.data ? cached.data : null);
    });
  }

  async #loadVPinPlayRating(index, forceRefresh = false) {
    const table = this.#getTableByIndex(index);
    if (!table) return null;

    const vpsId = this.#getTableVPinPlayVpsId(table);
    if (!vpsId) {
      this.#setTableVPinPlayRating(table, null);
      return null;
    }

    const cached = this._vpinplayRatingCache.get(vpsId);
    if (!forceRefresh && cached && cached.data) {
      this.#setTableVPinPlayRating(table, cached.data);
      return cached.data;
    }

    const existingRequest = this._vpinplayRatingRequests.get(vpsId);
    if (!forceRefresh && existingRequest) {
      return existingRequest;
    }

    if (!this.vpinplayEndpoint) {
      this.#setTableVPinPlayRating(table, null);
      return null;
    }

    const request = this.#fetchVPinPlayRating(vpsId)
      .then((payload) => {
        const data = this.#normalizeVPinPlayRatingPayload(vpsId, payload);
        if (!data) {
          this._vpinplayRatingCache.delete(vpsId);
          this.#setCachedVPinPlayRatingForCurrentTables(vpsId, null);
          return null;
        }
        this._vpinplayRatingCache.set(vpsId, { data });
        this.#setCachedVPinPlayRatingForCurrentTables(vpsId, data);
        return data;
      })
      .catch((error) => {
        this.call("console_out", `VPinPlay rating fetch failed for ${vpsId}: ${error.message}`).catch(() => {});
        this.#setCachedVPinPlayRatingForCurrentTables(vpsId, null);
        return null;
      })
      .finally(() => {
        this._vpinplayRatingRequests.delete(vpsId);
      });

    this._vpinplayRatingRequests.set(vpsId, request);
    return request;
  }

  async #fetchVPinPlayRating(vpsId) {
    const url = this.#getVPinPlayUrl(vpsId);
    if (!url) return null;

    const response = await fetch(url, {
      method: "GET",
      headers: { "Accept": "application/json" },
    });

    if (response.status === 404) return null;
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return response.json();
  }

  #fadeAudio(from, to, onComplete) {
    clearInterval(this._audioFadeId);
    if (!this._audio) {
      if (onComplete) onComplete();
      return;
    }
    this._audio.volume = from;
    if (this._audioFadeDuration <= 0 || from === to) {
      this._audio.volume = to;
      if (onComplete) onComplete();
      return;
    }
    const steps = this._audioFadeDuration / 20;
    const delta = (to - from) / steps;
    this._audioFadeId = setInterval(() => {
      const next = this._audio.volume + delta;
      if ((delta > 0 && next >= to) || (delta < 0 && next <= to) || delta === 0) {
        this._audio.volume = to;
        clearInterval(this._audioFadeId);
        if (onComplete) onComplete();
      } else {
        this._audio.volume = next;
      }
    }, 20);
  }

  #audioTriggerWhenReady(url) {
    if (this._audioCurrentUrl !== url) return;
    if (this._audio.readyState >= 2) {
      this.call("trigger_audio_play").catch(() => {});
    } else {
      this._audio.addEventListener("canplay", () => {
        if (this._audioCurrentUrl === url) this.call("trigger_audio_play").catch(() => {});
      }, { once: true });
    }
  }

  #audioResumePlay() {
    if (this._audioMuted) return;
    const url = this._audioCurrentUrl;
    const retries = this._audioRetries || 0;
    if (!url) return;
    this._audio.play().then(() => {
      if (this._audioCurrentUrl === url) this.#fadeAudio(0, this._audioMaxVolume);
    }).catch(() => {
      if (retries > 0 && this._audioCurrentUrl === url) {
        this._audioRetries = retries - 1;
        setTimeout(() => this.#audioTriggerWhenReady(url), 500);
      }
    });
  }

  // **********************************************
  // private functions
  // **********************************************

  #connectWebSocket() {
    const wsUrl = `ws://127.0.0.1:${this.wsPort}?window=${this._windowName}`;
    console.log(`[WS] Connecting to ${wsUrl}`);
    this._ws = new WebSocket(wsUrl);

    this._ws.onopen = async () => {
      console.log("[WS] Connected to bridge");
      await this.#onBridgeReady();
      this._resolveReady();
    };

    this._ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'api_response') {
        const pending = this._pendingCalls[data.id];
        if (pending) {
          delete this._pendingCalls[data.id];
          if (data.error) {
            pending.reject(new Error(data.error));
          } else {
            pending.resolve(data.result);
          }
        }
      } else if (data.type === 'event') {
        // Handle pushed events from Python
        if (typeof window.receiveEvent === 'function') {
          window.receiveEvent(data.message);
        }
        // Forward to iframes if requested
        if (data.forward_iframe) {
          const iframes = document.querySelectorAll('iframe');
          iframes.forEach(iframe => {
            try {
              iframe.contentWindow.postMessage({ vpinfeEvent: data.message }, '*');
            } catch (e) { /* cross-origin, ignore */ }
          });
        }
      }
    };

    this._ws.onclose = () => {
      console.log("[WS] Disconnected from bridge");
    };

    this._ws.onerror = (err) => {
      console.error("[WS] WebSocket error:", err);
    };
  }

  async #onBridgeReady() {
    console.log("WebSocket bridge is ready!");
    try {
      this.setAudioMuted(await this.call("get_audio_muted"));
    } catch (_e) {
      this.setAudioMuted(false);
    }
    try {
      this.themeConfig = await this.call("get_theme_config");
    } catch (e) {
      this.themeConfig = {};
    }
    if (!this.themeConfig || typeof this.themeConfig !== "object") {
      this.themeConfig = {};
    }

    const audioCfg = (this.themeConfig && typeof this.themeConfig.audio === "object")
      ? this.themeConfig.audio
      : {};
    const enabledOpt = [
      this.themeConfig.use_core_audio,
      this.themeConfig.useCoreAudio,
      audioCfg.use_core_audio,
      audioCfg.useCoreAudio,
      audioCfg.enabled
    ].find(v => v !== undefined);
    // Opt-in by default: themes must explicitly enable core audio.
    this.enableCoreAudio(enabledOpt === undefined ? false : !!enabledOpt);
    this.setAudioOptions(audioCfg);

    // Load network config
    this.themeAssetsPort = await this.call("get_theme_assets_port");
    try {
      this.vpinplayEndpoint = await this.call("get_vpinplay_endpoint");
    } catch (_e) {
      this.vpinplayEndpoint = "";
    }
    // Load display config
    this.tableOrientation = await this.call("get_table_orientation");
    this.tableRotation = await this.call("get_table_rotation");
    await this.#loadMonitors();
    await this.getTableData();
   //this.#overrideConsole(); //disabled for now...

    // only run on the table window.. Its the master controller for all screens/windows
    if (this._windowName == "table") {
      await this.#initKeyboardMapping();
      await this.#initGamepadMapping();
      this.#setupGamepadListeners();
      this.#updateGamepads();           // No await needed here — runs loop
      this.#pollRemoteLaunch();         // Poll for remote launch events
    }
  }

  #setupGamepadListeners() {
    // Listen for gamepad connection events
    window.addEventListener("gamepadconnected", (e) => {
      this.call("console_out", `Gamepad connected: ${e.gamepad.id} (index ${e.gamepad.index})`);
      // Reset button states for this gamepad
      this.previousButtonStates[e.gamepad.index] = new Array(e.gamepad.buttons.length).fill(false);
    });

    window.addEventListener("gamepaddisconnected", (e) => {
      this.call("console_out", `Gamepad disconnected: ${e.gamepad.id} (index ${e.gamepad.index})`);
      delete this.previousButtonStates[e.gamepad.index];
    });

    // Check if gamepad is already connected (may have been connected before page load)
    this.#waitForGamepad();
  }

  #waitForGamepad(attempts = 0, maxAttempts = 30) {
    const gamepads = navigator.getGamepads();
    const hasGamepad = Array.from(gamepads).some(gp => gp !== null);

    if (hasGamepad) {
      this.call("console_out", "Gamepad detected and ready");
      return;
    }

    if (attempts < maxAttempts) {
      // Retry every 500ms for up to 15 seconds
      setTimeout(() => this.#waitForGamepad(attempts + 1, maxAttempts), 500);
    } else {
      this.call("console_out", "No gamepad detected after waiting. Will detect when connected.");
    }
  }

  async #triggerInputAction(action) {
    if(this.tutorialUP) {
      this.inputHandlerTutorial.forEach(handler => handler(action));
    }
    else if(this.collectionMenuUP) {
      // Collection menu is up, route to its handler
      this.inputHandlerCollectionMenu.forEach(handler => handler(action));
    }
    else if(this.menuUP) {
      // Menu is up route to its handler
      this.inputHandlerMenu.forEach(handler => handler(action));
    }
    else {
      // No menu is up, route to theme handler
      this.inputHandlers.forEach(handler => handler(action));
    }
  }

  #normalizeKeyboardToken(token) {
    const normalized = String(token || '').trim().toLowerCase();
    const aliases = {
      esc: 'escape',
      return: 'enter',
      ' ': 'space',
      spacebar: 'space',
    };
    return aliases[normalized] || normalized;
  }

  #parseKeyboardBinding(value) {
    if (typeof value !== 'string') return [];
    return value
      .split(',')
      .map(token => this.#normalizeKeyboardToken(token))
      .filter(Boolean);
  }

  #eventKeyboardTokens(e) {
    return new Set([
      this.#normalizeKeyboardToken(e.key),
      this.#normalizeKeyboardToken(e.code),
    ].filter(Boolean));
  }

  #actionForKeyboardEvent(e) {
    const eventTokens = this.#eventKeyboardTokens(e);
    for (const [action, bindings] of Object.entries(this.keyActionMap)) {
      if (bindings.some(binding => eventTokens.has(binding))) {
        return action;
      }
    }
    return null;
  }

  // Keybaord input processing to handlers
  async #onKeyDown(e) {
    if (this._windowName == "table") {
      const action = this.#actionForKeyboardEvent(e);
      if (!action) return;

      if (action === "joyexit") this.call("close_app");
      else if (action === "joymenu") this.#showmenu();
      else if (action === "joycollectionmenu") this.#showcollectionmenu();
      else if (action === "joytutorial") this.#showtutorial();
      else this.#triggerInputAction(action);
    }
  }

  async #loadMonitors() {
    this.monitors = await this.call("get_monitors");
  }

  // Gamepad handling
 async #initKeyboardMapping() {
  const keymap = await this.call("get_keymapping");
  const actionMap = {
    keyleft: 'joyleft',
    keyright: 'joyright',
    keyup: 'joyup',
    keydown: 'joydown',
    keypageup: 'joypageup',
    keypagedown: 'joypagedown',
    keyselect: 'joyselect',
    keymenu: 'joymenu',
    keyback: 'joyback',
    keytutorial: 'joytutorial',
    keyexit: 'joyexit',
    keycollectionmenu: 'joycollectionmenu',
  };

  for (const [configKey, action] of Object.entries(actionMap)) {
    this.keyActionMap[action] = this.#parseKeyboardBinding(keymap[configKey] || '');
  }
}

 async #initGamepadMapping() {
  const joymap = await this.call("get_joymaping");

  // Collect multiple actions per button. sometimes the same button has two mappings
  this.joyButtonMap = {};
  for (const [action, button] of Object.entries(joymap)) {
    if (!this.joyButtonMap[button]) {
      this.joyButtonMap[button] = [];
    }
    this.joyButtonMap[button].push(action);
  }

  //this.call("console_out", "Gamepad mapping loaded: " + JSON.stringify(this.joyButtonMap));
}

async #onButtonPressed(buttonIndex, gamepadIndex) {
  const actions = this.joyButtonMap[buttonIndex.toString()];
  if (!actions) return;

  // Handle all actions mapped to this button
  for (const action of actions) {
    //this.call("console_out", `Button action: ${action}, windowName: ${this._windowName}`);
    if (action === "joyexit" && this._windowName == "table") {
      this.call("close_app");
    }
    else if (action === "joymenu" && this._windowName == "table") {
      this.#showmenu();
    }
    else if (action === "joycollectionmenu" && this._windowName == "table") {
      this.call("console_out", "Triggering collection menu");
      this.#showcollectionmenu();
    }
    else if (action === "joytutorial" && this._windowName == "table") {
      this.#showtutorial();
    }
    else {
      this.#triggerInputAction(action);
    }
  }
}

  #updateGamepads() {
    if (this.gamepadEnabled) {
      const gamepads = navigator.getGamepads();
      for (let i = 0; i < gamepads.length; i++) {
        const gp = gamepads[i];
        if (!gp) continue;

        if (!this.previousButtonStates[i]) {
          this.previousButtonStates[i] = new Array(gp.buttons.length).fill(false);
        }

        gp.buttons.forEach((button, index) => {
          const wasPressed = this.previousButtonStates[i][index];
          const isPressed = button.pressed;

          if (isPressed && !wasPressed) {
            //this.call("console_out", "Button: " + index);
            this.#onButtonPressed(index, i); // new press
          }
          this.previousButtonStates[i][index] = isPressed;
        });
      }
    }
    requestAnimationFrame(() => this.#updateGamepads());
  }

  // convert the hard full local path to the web servers url map
  #convertPathToURL(localPath) {
    if (!localPath || typeof localPath !== 'string') {
      return "/web/images/file_missing.png";  // fallback default
    }
    // Normalize Windows backslashes to forward slashes
    const normalized = localPath.replace(/\\/g, '/');
    const parts = normalized.split('/');
    const file = parts[parts.length - 1];    // last part = filename
    const port = this.themeAssetsPort;

    // Check if the path includes a medias/ subfolder
    if (parts.length >= 3 && parts[parts.length - 2] === 'medias') {
      const tableDir = parts[parts.length - 3];  // table folder is 3rd from end
      return `http://127.0.0.1:${port}/tables/${encodeURIComponent(tableDir)}/medias/${encodeURIComponent(file)}`;
    }

    // Fallback: image is directly in table folder
    const dir = parts[parts.length - 2];     // second-to-last part = folder
    return `http://127.0.0.1:${port}/tables/${encodeURIComponent(dir)}/${encodeURIComponent(file)}`;
  }

  async #showmenu() {
    const overlayRoot = document.getElementById('overlay-root');
    let iframe = document.getElementById("menu-frame");

    // Close collection menu if it's open
    if (this.collectionMenuUP) {
      await this.#showcollectionmenu();
    }
    if (this.tutorialUP) {
      await this.#showtutorial();
    }

    if (!this.menuUP) {
      this.menuUP = true;
      overlayRoot.classList.add("active"); // fade in

      if (!iframe) {
        iframe = document.createElement("iframe");
        iframe.src = "/web/mainmenu/mainmenu.html";
        iframe.id = "menu-frame";
        iframe.setAttribute("allowTransparency", "true");
        iframe.style.display = "none"; // start hidden to prevent flash
        overlayRoot.appendChild(iframe);
        await new Promise(resolve => setTimeout(resolve, 10)); // tiny delay to allow DOM update
      }

      iframe.style.display = "block"; // show iframe
      if (iframe && iframe.contentWindow) {
        iframe.contentWindow.postMessage({
          event: "menu_open",
          table_index: this._currentTableIndex
        }, "*");
      }
    } else {
      this.menuUP = false;
      overlayRoot.classList.remove("active"); // fade out

      if (iframe) {
        iframe.style.display = "none"; // just hide, don't remove
        iframe.contentWindow.postMessage({ event: "reset state" }, "*");
      }
      //this.#deregisterAllInputHandlersMenu();  // only need this when we destory it.
    }
  }

  async #showcollectionmenu() {
    const overlayRoot = document.getElementById('overlay-root');
    let iframe = document.getElementById("collection-menu-frame");

    // Close main menu if it's open
    if (this.menuUP) {
      await this.#showmenu();
    }
    if (this.tutorialUP) {
      await this.#showtutorial();
    }

    if (!this.collectionMenuUP) {
      this.collectionMenuUP = true;
      overlayRoot.classList.add("active"); // fade in

      if (!iframe) {
        iframe = document.createElement("iframe");
        iframe.src = "/web/collectionmenu/collectionmenu.html";
        iframe.id = "collection-menu-frame";
        iframe.setAttribute("allowTransparency", "true");
        iframe.style.display = "none"; // start hidden to prevent flash
        overlayRoot.appendChild(iframe);
        await new Promise(resolve => setTimeout(resolve, 10)); // tiny delay to allow DOM update
      }

      iframe.style.display = "block"; // show iframe
    } else {
      this.collectionMenuUP = false;
      overlayRoot.classList.remove("active"); // fade out

      if (iframe) {
        iframe.style.display = "none"; // just hide, don't remove
        iframe.contentWindow.postMessage({ event: "reset state" }, "*");
      }
    }
  }

  #getCurrentPinballPrimerTutorialUrl() {
    const index = Math.floor(this._currentTableIndex);
    if (!Array.isArray(this.tableData) || index < 0 || index >= this.tableData.length) {
      return "";
    }

    const table = this.tableData[index];
    const meta = (table && typeof table === "object") ? table.meta : null;
    const info = (meta && typeof meta === "object" && meta.Info && typeof meta.Info === "object")
      ? meta.Info
      : null;
    const tutorialUrl = info ? info.PinballPrimerTut : "";
    return (typeof tutorialUrl === "string") ? tutorialUrl.trim() : "";
  }

  #buildTutorialProxyUrl(tutorialUrl) {
    if (!tutorialUrl) return "";
    return `/proxy/pinballprimer?url=${encodeURIComponent(tutorialUrl)}`;
  }

  async #showtutorial() {
    const overlayRoot = document.getElementById('overlay-root');
    let iframe = document.getElementById("tutorial-frame");

    if (!this.tutorialUP) {
      const tutorialUrl = this.#getCurrentPinballPrimerTutorialUrl();
      if (!tutorialUrl) {
        return;
      }

      if (this.menuUP) {
        await this.#showmenu();
      }
      if (this.collectionMenuUP) {
        await this.#showcollectionmenu();
      }

      this.tutorialUP = true;
      overlayRoot.classList.add("active");

      if (!iframe) {
        iframe = document.createElement("iframe");
        iframe.src = "/web/tutorial/tutorial.html";
        iframe.id = "tutorial-frame";
        iframe.setAttribute("allowTransparency", "true");
        iframe.style.display = "none";
        overlayRoot.appendChild(iframe);
        await new Promise(resolve => setTimeout(resolve, 10));
      }

      iframe.style.display = "block";
      if (iframe && iframe.contentWindow) {
        iframe.contentWindow.postMessage({
          event: "tutorial_open",
          tutorial_url: tutorialUrl,
          tutorial_proxy_url: this.#buildTutorialProxyUrl(tutorialUrl),
          table_rotation: this.tableRotation,
        }, "*");
      }
    } else {
      this.tutorialUP = false;
      overlayRoot.classList.remove("active");

      if (iframe) {
        iframe.style.display = "none";
        iframe.contentWindow.postMessage({ event: "reset state" }, "*");
      }
    }
  }

  // Menu deregister for Input Events
  async #deregisterAllInputHandlersMenu() {
    this.inputHandlerMenu = [];
    this.call("console_out", "cleared the menu gamepad handler. aka menu closed");
  }

  // Poll the manager UI for remote launch events
  #pollRemoteLaunch() {
    // Don't poll from file:// origin - CORS blocks it on Chromium/QWebEngine.
    // Polling will start correctly once the theme page loads over http://.
    if (window.location.protocol === 'file:') return;

    const pollInterval = 1000; // Poll every 1 second
    const managerUrl = `http://127.0.0.1:${this.managerUiPort}/api/remote-launch`;

    console.log("[RemoteLaunch] Starting poll to:", managerUrl);

    const poll = async () => {
      try {
        const response = await fetch(managerUrl);
        if (response.ok) {
          const data = await response.json();

          // Check if launch state changed
          if (data.launching && !this.remoteLaunchActive) {
            // Remote launch started
            this.remoteLaunchActive = true;
            console.log("[RemoteLaunch] Launch detected:", data.table_name);
            this.call("console_out", `Remote launching: ${data.table_name}`);
            // Send TableLaunching event to all windows with the table name
            this.sendMessageToAllWindowsIncSelf({
              type: "RemoteLaunching",
              table_name: data.table_name
            });
          } else if (!data.launching && this.remoteLaunchActive) {
            // Remote launch completed
            this.remoteLaunchActive = false;
            console.log("[RemoteLaunch] Launch completed");
            this.call("console_out", "Remote launch completed");
            // Send completion event
            this.sendMessageToAllWindowsIncSelf({
              type: "RemoteLaunchComplete"
            });
          }
        }
      } catch (e) {
        // Manager UI might not be running, that's OK - silently ignore
        // But log first few failures for debugging
        console.log("[RemoteLaunch] Poll error (manager UI may not be running):", e.message);
      }

      // Continue polling
      setTimeout(poll, pollInterval);
    };

    // Start polling
    poll();
  }

  // override console and send them to the python console instead
  #overrideConsole() {
    Object.keys(originalConsole).forEach(method => {
      console[method] = function (...args) {
        // Call original method
        originalConsole[method].apply(console, args);
        // Append to page
        vpin.call("console_out", method + ':' + args);
      };
    });
  }

}
