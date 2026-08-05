//console methods for overriding
const originalConsole = {
  log: console.log,
  info: console.info,
  warn: console.warn,
  error: console.error,
  debug: console.debug,
};

// A media kind to the payload field that carries it. Kind names are snake_case, the
// same strings /api/v1 and vpin.getMedia() take.
const MEDIA_PATH_FIELDS = {
  playfield: "PlayfieldImagePath",
  playfield_fss: "FSSImagePath",
  bg: "BGImagePath",
  dmd: "DMDImagePath",
  wheel: "WheelImagePath",
  cab: "CabImagePath",
  real_dmd: "realDMDImagePath",
  real_dmd_color: "realDMDColorImagePath",
  flyer: "FlyerImagePath",
  instruction_card: "InstructionCardImagePath",
  topper: "TopperPath",
  logo: "LogoImagePath",
};

const MEDIA_VIDEO_PATH_FIELDS = {
  playfield: "PlayfieldVideoPath",
  bg: "BGVideoPath",
  dmd: "DMDVideoPath",
  loading: "LoadingVideoPath",
};

const DEFAULT_MEDIA_PRIORITIES = {
  playfield: "video",
  bg: "video",
  dmd: "video",
  real_dmd: "color",
};


// What core does on a theme's behalf. One entry per behavior, with its default stated
// here rather than implied by a constructor - the audio default used to be `true` at
// construction and `false` after init, and nothing said which was meant.
//
// `config` names the theme.json keys that turn it on or off, most specific first. The
// extra spellings are contract 1's: they accumulated because nothing declared the real
// one, and they stay only for themes already using them.
const CAPABILITIES = {
  core_paging: {
    default: true,
    config: [],
    describe: "Core handles page-up and page-down itself.",
  },
  core_audio: {
    default: false,
    config: ["use_core_audio", "audio.use_core_audio", "audio.enabled"],
    legacyConfig: ["useCoreAudio", "audio.useCoreAudio"],
    describe: "Core plays, fades and mutes per-game audio.",
  },
  // Off by default: every published theme preloads for itself, so turning this on
  // without deleting the theme's own loop just doubles the requests.
  core_preload: {
    default: false,
    // One spelling. A capability's settings live in a block named after it, and
    // `enabled` is one of them - which is also the only shape `kinds` can travel in.
    config: ["preload.enabled"],
    describe: "Core fetches the media on either side of the selection once it settles.",
  },
};

// Read a possibly-dotted key out of a theme's config.
function configValue(config, key) {
  return key.split(".").reduce((at, part) =>
    (at && typeof at === "object") ? at[part] : undefined, config);
}

const MISSING_MEDIA_URL = "/web/images/file_missing.png";

// The contract a theme declares in its manifest. 1 is what declaring nothing gets, and
// what this file assumes until the bridge answers: the compatibility layer below is
// installed up front and taken away again at contract 2, so a theme that touches vpin.*
// before the bridge is up still finds its names.
const OLDEST_CONTRACT = 1;
const CURRENT_CONTRACT = 2;


// How to read one item of the payload at contract 2. An entry is a table with its game
// attached: it names the media kinds it has rather than locating them, so a URL is the
// table's id and the kind.
class ContractTwoReader {
  constructor(core) { this.core = core; }

  has(entry, kind) { return Array.isArray(entry.media) && entry.media.includes(kind); }

  url(entry, kind) {
    if (!this.has(entry, kind)) return null;
    // A folder no metadata build has touched has no table id yet, but it still has art
    // and still appears in the wheel. The route accepts either id.
    const id = String(entry.table?.id || entry.game?.id || "");
    if (!id) return null;
    return `http://127.0.0.1:${this.core.themeAssetsPort}/media/${encodeURIComponent(id)}/${kind}`;
  }

  imageURL(entry, kind) { return this.url(entry, kind) || MISSING_MEDIA_URL; }
  // Contract 2 names kinds; it never locates files, so there is no path to hand back.
  path()                { return null; }
  videoURL(entry, kind) { return this.url(entry, VIDEO_KIND[kind] || kind); }
  audioURL(entry)       { return this.url(entry, "audio"); }
  logo(entry)           { return entry.game?.manufacturer_logo || null; }
  vpsId(entry)          { return String(entry.game?.vps_id || "").trim(); }

  imageVideo(entry, kind, priority) {
    const order = priority === "image" ? ["image", "video"] : ["video", "image"];
    for (const want of order) {
      const url = want === "video"
        ? this.url(entry, VIDEO_KIND[kind] || `${kind}_video`)
        // The playfield falls back to its own FSS variant, which is why the two are
        // named as a pair rather than as unrelated kinds.
        : (this.url(entry, kind)
           || (kind === "playfield" ? this.url(entry, "playfield_fss") : null));
      if (url) return { url, kind: want, priority, path: null };
    }
    return { url: MISSING_MEDIA_URL, kind: "missing", priority, path: null };
  }

  realDmd(entry, priority) {
    const order = priority === "standard"
      ? [["standard", "real_dmd"], ["color", "real_dmd_color"]]
      : [["color", "real_dmd_color"], ["standard", "real_dmd"]];
    for (const [variant, kind] of order) {
      const url = this.url(entry, kind);
      if (url) return { url, kind: "image", priority, variant, path: null };
    }
    return { url: MISSING_MEDIA_URL, kind: "missing", priority, variant: "missing", path: null };
  }
}

const VIDEO_KIND = { playfield: "playfield_video", bg: "bg_video", dmd: "dmd_video",
                     topper: "topper_video", loading: "loading" };


// ─────────────────────────────────────────────────────────────────────────────
//  CONTRACT 1 COMPATIBILITY
//
//  Everything a theme written before 3.0 depends on, in one place: the vpin.*
//  names it reads, the media kinds it asks for, the payload keys it expects and
//  the window messages it listens for. All of it is keyed on the 2.x spellings,
//  so a theme author arriving from 2.x finds their name here.
//
//  None of it is reachable at contract 2 - #applyContract takes it away. When
//  contract 1 is retired, this whole block goes with it and nothing else moves.
// ─────────────────────────────────────────────────────────────────────────────

// Pre-3.0 themes read these names. Aliased rather than removed: the payload behind each
// is identical, so a theme written against any earlier build keeps working. The contract
// projects the payload, never this surface, so aliasing is the only mechanism there is.
// PAR-23.
const VPINFE_RENAMED_MEMBERS = {
  tableData: 'gameData',
  tableRotation: 'playfieldRotation',
  tableOrientation: 'playfieldOrientation',
  getTableMeta: 'getGameMeta',
  getTableData: 'getGameData',
  getTableCount: 'getGameCount',
  getCurrentTableIndex: 'getCurrentGameIndex',
  playTableAudio: 'playGameAudio',
  stopTableAudio: 'stopGameAudio',
  launchTable: 'launchGame',
};

// Kind names earlier builds accepted, against the canonical snake_case set.
// real_dmd_color is the odd one: at contract 1 both frames collapse onto real_dmd, the
// way 2.x addressed them, while contract 2 keeps it separately addressable.
const MEDIA_KIND_ALIASES = {
  table: "playfield",
  table_video: "playfield_video",
  fss: "playfield_fss",
  realdmd: "real_dmd",
  "realdmd-color": "real_dmd",
  realdmd_color: "real_dmd",
  real_dmd_color: "real_dmd",
  rulecard: "instruction_card",
  audiolaunch: "audio_launch",
  rulesheet: "rule_sheet",
};

// This file is served to themes of every contract, so it cannot assume which spelling
// the payload carries: contract 1 receives TableImagePath, contract 2 PlayfieldImagePath.
// Look up the current key, fall back to the one the projection sends. PAR-22.
const MEDIA_FIELD_FALLBACK = {
  PlayfieldImagePath: "TableImagePath",
  PlayfieldVideoPath: "TableVideoPath",
};

// Window message types are a theme-facing contract: a theme both listens for these and
// posts them. Pre-3.0 themes use the Table* spelling, so at contract 1 every broadcast
// goes out under both names. Receipts are normalized at either contract - a theme
// posting an old name has to be understood regardless. PAR-24.
const MESSAGE_TYPE_ALIASES = {
  GameIndexUpdate: "TableIndexUpdate",
  GameDataChange: "TableDataChange",
  GameLaunching: "TableLaunching",
  GameRunning: "TableRunning",
  GameLaunchComplete: "TableLaunchComplete",
};

const MESSAGE_TYPE_CANONICAL = Object.fromEntries(
  Object.entries(MESSAGE_TYPE_ALIASES).map(([current, legacy]) => [legacy, current]),
);

function canonicalMessageType(type) {
  return MESSAGE_TYPE_CANONICAL[type] || type;
}

// Say it once per name, not once per access - a wheel reads gameData every frame. The
// backend keeps the same list in common/deprecations.py and logs there; a theme runs in
// the browser, so this is the only place its use of an old name is visible.
const announcedLegacy = new Set();
function announceLegacy(target, oldName, newName) {
  if (announcedLegacy.has(oldName)) return;
  announcedLegacy.add(oldName);
  console.info(`vpinfe: deprecated theme JavaScript '${oldName}' is in use; the current name is ${newName} (PAR-23)`);
  // Also tell the backend, so the log on the machine can answer "is anything still
  // on the old name". A console line is invisible on a cabinet. Best effort: this is
  // reporting, and it must never be the reason a theme fails.
  // call() is async, so a rejection has to be caught on the promise as well as around
  // the invocation - the bridge may not be connected yet, and an unhandled rejection in
  // a property getter is a poor trade for a log line.
  try {
    Promise.resolve(target.call("report_deprecated_use", "vpin-members", oldName))
      .catch(() => {});
  } catch (err) {
    /* nothing to do; the console line already went out */
  }
}

function installLegacyAliases(target) {
  for (const [oldName, newName] of Object.entries(VPINFE_RENAMED_MEMBERS)) {
    if (oldName in target) continue;
    Object.defineProperty(target, oldName, {
      get() {
        announceLegacy(this, oldName, newName);
        const value = this[newName];
        return typeof value === 'function' ? value.bind(this) : value;
      },
      set(value) { announceLegacy(this, oldName, newName); this[newName] = value; },
      configurable: true,
    });
  }
}

function removeLegacyAliases(target) {
  for (const oldName of Object.keys(VPINFE_RENAMED_MEMBERS)) {
    if (Object.getOwnPropertyDescriptor(target, oldName)) delete target[oldName];
  }
}


// How to read one item of the payload at contract 1. A game carries a filesystem path
// per media kind, so every URL here is built by taking that path apart - which is the
// reason contract 2 stopped serving paths at all.
class ContractOneReader {
  constructor(core) { this.core = core; }

  // The current key, falling back to the spelling the projection sends. PAR-22.
  field(game, name) {
    if (!name) return null;
    if (game[name] != null) return game[name];
    const legacy = MEDIA_FIELD_FALLBACK[name];
    return legacy ? game[legacy] : null;
  }

  has(game, kind)      { return !!this.field(game, MEDIA_PATH_FIELDS[kind]); }
  path(game, kind)     { return this.field(game, MEDIA_PATH_FIELDS[kind]) || null; }
  imageURL(game, kind) { return this.pathToURL(this.field(game, MEDIA_PATH_FIELDS[kind])); }
  videoURL(game, kind) { return this.pathToURL(this.field(game, MEDIA_VIDEO_PATH_FIELDS[kind])); }
  audioURL(game)       { return game.AudioPath ? this.pathToURL(game.AudioPath) : null; }
  logo(game)           { return game.ManufacturerLogoPath || null; }
  vpsId(game)          { return String(game?.meta?.Info?.VPSId || "").trim(); }

  imageVideo(game, kind, priority) {
    const image = this.field(game, MEDIA_PATH_FIELDS[kind]);
    const video = this.field(game, MEDIA_VIDEO_PATH_FIELDS[kind]);
    const imagePath = kind === "playfield" ? (image || game.FSSImagePath) : image;
    const candidates = priority === "image"
      ? [{ kind: "image", path: imagePath }, { kind: "video", path: video }]
      : [{ kind: "video", path: video }, { kind: "image", path: imagePath }];
    const picked = candidates.find(c => !!c.path) || { kind: "missing", path: null };
    return { url: this.pathOrMissing(picked.path), kind: picked.kind, priority,
             path: picked.path || null };
  }

  realDmd(game, priority) {
    const candidates = priority === "standard"
      ? [{ variant: "standard", path: game.realDMDImagePath },
         { variant: "color", path: game.realDMDColorImagePath }]
      : [{ variant: "color", path: game.realDMDColorImagePath },
         { variant: "standard", path: game.realDMDImagePath }];
    const picked = candidates.find(c => !!c.path) || { variant: "missing", path: null };
    return { url: this.pathOrMissing(picked.path),
             kind: picked.variant === "missing" ? "missing" : "image",
             priority, variant: picked.variant, path: picked.path || null };
  }

  pathOrMissing(localPath) { return localPath ? this.pathToURL(localPath) : MISSING_MEDIA_URL; }

  pathToURL(localPath) {
    if (!localPath || typeof localPath !== 'string') return MISSING_MEDIA_URL;
    const normalized = localPath.replace(/\\/g, '/');       // Windows separators
    const parts = normalized.split('/');
    const file = parts[parts.length - 1];
    const port = this.core.themeAssetsPort;
    // The file may sit deeper than medias/ itself - wheel sets live in
    // medias/wheels/<set>/ - so keep everything from medias/ down.
    const mediasIndex = parts.lastIndexOf('medias');
    if (mediasIndex > 0) {
      const gameDir = parts[mediasIndex - 1];
      const rest = parts.slice(mediasIndex).map(encodeURIComponent).join('/');
      return `http://127.0.0.1:${port}/tables/${encodeURIComponent(gameDir)}/${rest}`;
    }
    const dir = parts[parts.length - 2];        // media sitting in the game folder
    return `http://127.0.0.1:${port}/tables/${encodeURIComponent(dir)}/${encodeURIComponent(file)}`;
  }
}

// ─────────────────────────── end contract 1 ──────────────────────────────────


class VPinFECore {
  constructor() {
    this.gameData = {};
    // What the running theme declared. Contract 1 until the bridge says otherwise.
    this.contract = OLDEST_CONTRACT;
    // The theme's windows, controller first. Replaced once the bridge answers; until
    // then the three VPinFE has always opened, under contract 1's names.
    this.windows = ["table", "bg", "dmd"];
    // The view the entry list came from. Seeded so a theme reading either before the
    // first payload gets the documented type rather than undefined.
    this.collection = "";
    this.expanded = false;
    this._reader = new ContractOneReader(this);
    installLegacyAliases(this);
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
    // A held key repeats at whatever rate the OS is set to - often 30 a second - and
    // every one of those used to become a full wheel move. Deliberate presses are never
    // throttled; only the automatic repeat is.
    this.minRepeatIntervalMs = 150;
    this._lastRepeatAt = 0;
    this.gamepadEnabled = true;
    this.frontendInputEnabled = true;
    this._launchInputSuppressedByLifecycle = false;

    // What core is doing on the theme's behalf, seeded from CAPABILITIES so the
    // default is stated in one place.
    this._capabilities = Object.fromEntries(
      Object.entries(CAPABILITIES).map(([name, spec]) => [name, spec.default]));
    this._pagingInFlight = false;

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
    this.playfieldOrientation = 'landscape'; // default, will be updated from config
    this.playfieldRotation = 0; // default, will be updated from config
    // Whether this is a cabinet. A property like the two above it, because a theme
    // deciding its layout wants all three at the same moment.
    this.cabMode = false;

    // Remote launch state tracking
    this.remoteLaunchActive = false;

    // Theme config and centralized audio state
    this.themeConfig = {};
    this.mediaPriorities = Object.assign({}, DEFAULT_MEDIA_PRIORITIES);
    this._currentGameIndex = 0;
    this._initialGameRestored = false;
    this._audioMuted = false;
    this._audio = Object.assign(new Audio(), { loop: true });
    this._audioFadeId = null;
    this._audioFadeDuration = 500;
    this._audioMaxVolume = 0.8;
    this._audioCurrentUrl = null;
    this._audioRetries = 0;
    this._lastSelectedIndex = null;
    // Preloading waits for the wheel to stop. Fetching on every step is what made a
    // two-second hold ask for hundreds of images that were obsolete before they decoded;
    // the settle delay is the whole mechanism, not a nicety.
    this._preloadSettleMs = 180;
    this._preloadKinds = ["playfield", "bg", "wheel"];
    this._preloadTimer = null;
    this._preloaded = new Set();

    this._onSelection = [];
    this.onSelection(() => this.getVPinPlayRating(this._currentGameIndex).catch(() => {}));
    this.onSelection(() => this.#notifySelectedGame().catch(() => {}));
    this.onSelection(() => this.#schedulePreload());
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

    // Any window name, not a fixed three: a theme declares its own, and the bootstrap is
    // served at /app/<name> for whatever it declared. Same character class the server
    // accepts there.
    const match = window.location.pathname.match(/^\/app\/([A-Za-z0-9_-]+)\/?$/);
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

  // Input goes to the controller window only. The round trip stays because it also
  // sets the global a theme's own example reads; the decision comes from the window
  // list, not from a name.
  //
  // `window.windowName`, not a bare assignment: a class body is strict mode, so writing
  // an undeclared name throws. Every published theme opens with `windowName = ""` and
  // hid that - a theme reading vpin.windowName instead has no reason to, and crashed
  // here on the first call.
  async registerInputHandler(handler) {
    window.windowName = await this.call("get_my_window_name");
    if (typeof handler === 'function' && this.isController()) {
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

  getImageURL(index, kind) {
    const item = this.gameData[index];
    return item ? this._reader.imageURL(item, this.#normalizeMediaType(kind)) : null;
  }

  getMediaURL(index, type) {
    return this.getMedia(index, type).url;
  }

  // URL of the game manufacturer's logo, or null when none is installed
  getManufacturerLogoURL(index) {
    const item = this.gameData[index];
    const path = item ? this._reader.logo(item) : null;
    return path ? `http://127.0.0.1:${this.themeAssetsPort}${path}` : null;
  }

  getPreferredMediaURL(index, type) {
    return this.getMediaURL(index, type);
  }

  getMedia(index, type) {
    const item = this.gameData[index];
    if (!item) return { url: null, kind: null, priority: null, path: null };

    const normalizedType = this.#normalizeMediaType(type);
    if (normalizedType === "real_dmd") {
      return this.#resolveRealDmdMedia(item);
    }
    if (["playfield", "bg", "dmd"].includes(normalizedType)) {
      return this.#resolveImageVideoMedia(item, normalizedType);
    }

    // Every other kind is a single image, whichever contract it came from.
    const url = this._reader.imageURL(item, normalizedType);
    const has = this._reader.has(item, normalizedType);
    return {
      url,
      kind: has ? "image" : "missing",
      priority: null,
      path: this._reader.path(item, normalizedType),
    };
  }

  // The URL of a game's audio, or null when it has none
  getAudioURL(index) {
    const item = this.gameData[index];
    return item ? this._reader.audioURL(item) : null;
  }

  // Core handles joypageup/joypagedown by default: it asks the backend for the
  // target index ([Input] pagingtype/pagingsize + current sort) and broadcasts a
  // GameIndexUpdate. Themes that implement their own paging call
  /**
   * What this build does on your behalf, and whether each is on right now. A name that
   * is absent is a behavior this build does not have - check before using it.
   */
  get capabilities() {
    return { ...this._capabilities };
  }

  enabled(name) {
    return !!this._capabilities[name];
  }

  #setCapability(name, on) {
    if (!(name in CAPABILITIES)) return;
    this._capabilities[name] = !!on;
  }

  // Whatever the theme's config says, against the keys each capability declares.
  #applyCapabilityConfig() {
    const config = this.themeConfig || {};
    for (const [name, spec] of Object.entries(CAPABILITIES)) {
      const keys = [...(spec.config || []), ...(spec.legacyConfig || [])];
      const stated = keys.map((key) => configValue(config, key))
                         .find((value) => value !== undefined);
      this.#setCapability(name, stated === undefined ? spec.default : !!stated);
    }
    if (!this.enabled("core_audio")) this.stopGameAudio({ immediate: true });

    // A theme that shows a cab shot, or shows no wheel, preloads a different set. The
    // names go through the same normalization as everywhere else, so a contract 1 theme
    // can still say `table` and mean the playfield.
    const kinds = configValue(config, "preload.kinds");
    if (Array.isArray(kinds) && kinds.length) {
      this._preloadKinds = kinds.map((kind) => this.#normalizeMediaType(kind));
    }
  }

  // enableCorePaging(false) and receive the actions in handleInput instead.
  enableCorePaging(enabled = true) {
    this.#setCapability("core_paging", enabled);
  }

  isCorePagingEnabled() {
    return this.enabled("core_paging");
  }

  // Ask the backend where a page next/prev press should land. Available to
  // themes doing their own paging animation.
  async getPageIndex(direction = "next", index = this._currentGameIndex) {
    return await this.call("get_page_index", index, direction);
  }

  enableCoreAudio(enabled = true) {
    this.#setCapability("core_audio", enabled);
    if (!this.enabled("core_audio")) this.stopGameAudio({ immediate: true });
  }

  isCoreAudioEnabled() {
    return this.enabled("core_audio");
  }

  setAudioMuted(muted = true) {
    this._audioMuted = !!muted;
    if (this._audio) this._audio.muted = this._audioMuted;
    if (this._audioMuted) {
      this.stopGameAudio({ immediate: true });
      return;
    }
    if (this.enabled("core_audio") && this.isController()) {
      this.playGameAudio(this._currentGameIndex);
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

  playGameAudio(indexOrUrl = this._currentGameIndex, retries = 3) {
    if (!this.enabled("core_audio") || this._audioMuted || !this.isController()) return;
    const url = this.#resolveAudioUrl(indexOrUrl);
    if (!url) {
      this.stopGameAudio();
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
        setTimeout(() => this.playGameAudio(url, retries - 1), 1000);
      }
    });
  }

  stopGameAudio(options = {}) {
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

  // The URL of a game's video, by media kind
  getVideoURL(index, kind) {
    const item = this.gameData[index];
    return item ? this._reader.videoURL(item, this.#normalizeMediaType(kind)) : null;
  }

  // The list, under the name that describes what is in it. At contract 2 the items are
  // entries - a table with its game attached - so `entries` is what a theme iterates.
  get entries() {
    return this.gameData;
  }

  getGameMeta(index) {
    return this.gameData[index];
  }

  getGameCount() {
    return this.gameData.length;
  }

  getCurrentGameIndex() {
    return this._currentGameIndex;
  }

  getCachedVPinPlayRating(index = this._currentGameIndex) {
    const item = this.#itemByIndex(index);
    if (!item) return null;

    const vpsId = this.#vpsIdOf(item);
    if (!vpsId) return null;

    const cached = this._vpinplayRatingCache.get(vpsId);
    return cached && cached.data ? cached.data : null;
  }

  async getVPinPlayRating(index = this._currentGameIndex, options = {}) {
    return this.#loadVPinPlayRating(index, !!(options && options.forceRefresh));
  }

  async refreshVPinPlayRating(index = this._currentGameIndex) {
    return this.#loadVPinPlayRating(index, true);
  }

  // The legacy copy goes out by the SAME delivery as the message it mirrors. Sending it
  // without _incself once reached bg and dmd but never came back to the playfield
  // window, so paging updated the backglass and DMD while the wheel sat still. Both
  // spellings leave from here, so they cannot disagree about how again.
  #broadcast(method, message) {
    this.#syncLocalIndexFromOutgoingMessage(message);
    this.#syncSelectionFromMessage(message);
    this.call(method, message);
    const legacy = this.#servesLegacyNames() && MESSAGE_TYPE_ALIASES[message.type];
    if (legacy) this.call(method, { ...message, type: legacy });
  }

  // send a message to all windows except "self"
  sendMessageToAllWindows(message) {
    this.#broadcast("send_event_all_windows", message);
  }

  // send a message to all windows including "self"
  sendMessageToAllWindowsIncSelf(message) {
    this.#broadcast("send_event_all_windows_incself", message);
  }

  // Toggle collection menu (public method callable from collection menu)
  toggleCollectionMenu() {
    return this.#showcollectionmenu();
  }

  // Toggle main menu (public method callable from main menu)
  toggleMenu() {
    return this.#showmenu();
  }

  toggleTutorial() {
    return this.#showtutorial();
  }

  // Launch a game
  async launchGame(index) {
    this.#setFrontendInputEnabled(false);
    try {
      await this.call("launch_game", index);
    } catch (e) {
      // The call will timeout after 30s while VPX is still running - that's expected
      this.call("console_out", `launch_game call ended: ${e.message}`);
    } finally {
      if (!this._launchInputSuppressedByLifecycle && !this.remoteLaunchActive) {
        this.#setFrontendInputEnabled(true);
      }
    }
  }

  async getGameData(reset=false) {
    const payload = JSON.parse(await this.call("get_games", reset));
    if (Array.isArray(payload)) {
      this.gameData = payload;                       // contract 1: a row per game
    } else {
      // Contract 2 wraps the list so the view it belongs to travels with it.
      this.gameData = payload.entries || [];
      this.collection = payload.collection || "";
      this.expanded = !!payload.expanded;
    }
    this.#attachCachedVPinPlayRatings();
    if (this.isController()) {
      const maxIndex = Math.max(0, this.gameData.length - 1);
      if (this._currentGameIndex > maxIndex) this._currentGameIndex = maxIndex;
      if (this.gameData.length > 0) {
        if (!this._initialGameRestored) {
          this._initialGameRestored = true;
          await this.#restoreInitialGame();
        }
        this.#selectionChanged();
      } else {
        this._lastSelectedIndex = null;
      }
    }
  }

  // On the first game-data load, ask the backend for the last-launched game's
  // index and, if it isn't already first, move the wheel there. Sending a
  // GameIndexUpdate (inc self) drives the theme through the same path its own
  // input uses, so no theme changes are needed to honor the restored position.
  async #restoreInitialGame() {
    try {
      const index = await this.call("get_initial_game_index");
      if (typeof index === "number" && index > 0 && index < this.gameData.length) {
        this._currentGameIndex = index;
        // Themes register window.receiveEvent at varying points in their startup
        // (some only after a couple of awaits inside vpin.ready.then). Wait for it
        // so the restore broadcast isn't dropped by the guard in #connectWebSocket.
        await this.#waitForReceiveEvent();
        this.sendMessageToAllWindowsIncSelf({ type: "GameIndexUpdate", index });
      }
    } catch (e) {
      this.call("console_out", `restoreInitialTable failed: ${e.message}`);
    }
  }

  // Resolve once window.receiveEvent is a function, or after the timeout so a
  // theme that never registers one can't hang startup.
  async #waitForReceiveEvent(timeoutMs = 2000, intervalMs = 25) {
    const deadline = Date.now() + timeoutMs;
    while (typeof window.receiveEvent !== "function" && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, intervalMs));
    }
    return typeof window.receiveEvent === "function";
  }

  // Register an event handler for a specific event type
  // eventType: string (e.g., "GameIndexUpdate", "GameDataChange", etc.)
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
    // A theme may post the pre-3.0 spelling; normalize before anything matches on it.
    if (message && MESSAGE_TYPE_CANONICAL[message.type]) {
      message = { ...message, type: canonicalMessageType(message.type) };
    }
    if (typeof message.index === "number") this._currentGameIndex = message.index;
    if (message.type === "AudioMuteChanged") {
      this.setAudioMuted(!!message.muted);
      return;
    }
    this.#handleFrontendInputLifecycleEvent(message);

    // Default handling for GameDataChange
    if (message.type === "GameDataChange") {
      if (this.isController()) this._lastSelectedIndex = null;
      await this.#handleGameDataChange(message);
    }
    this.#syncSelectionFromMessage(message);
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
    // Only the ones a title-cased name gets wrong. Everything else - table, playfield,
    // a declared topper - reads correctly from the name itself. Kept in step with
    // theme_windows.TITLES, which does the same job for the bootstrap page.
    const known = { bg: "BG", dmd: "DMD" };
    if (known[windowName]) return known[windowName];
    if (!windowName || windowName === "unknown") return "Window";
    return windowName.charAt(0).toUpperCase() + windowName.slice(1);
  }


  // Default handler for GameDataChange events
  // The three overlays differ in four things: which flag says they are up, which iframe
  // they own, what they load, and what they are told when opened. Everything else - the
  // fade class, creating the frame once, the ten-millisecond wait so it does not flash,
  // hiding rather than destroying - was written out three times and drifted.
  static OVERLAYS = {
    menu: {
      flag: "menuUP",
      frameId: "menu-frame",
      src: "/web/mainmenu/mainmenu.html",
      // table_index is mainmenu.js's own key, not ours to rename.
      opened: (core) => ({ event: "menu_open", table_index: core._currentGameIndex }),
    },
    collectionMenu: {
      flag: "collectionMenuUP",
      frameId: "collection-menu-frame",
      src: "/web/collectionmenu/collectionmenu.html",
    },
    tutorial: {
      flag: "tutorialUP",
      frameId: "tutorial-frame",
      src: "/web/tutorial/tutorial.html",
      // There is nothing to show without a URL, and this runs before anything is
      // closed - a missing tutorial must leave whatever is open alone.
      prepare: (core) => core.getCurrentTutorialUrl() || null,
      opened: (core, url) => ({
        event: "tutorial_open",
        tutorial_url: url,
        tutorial_proxy_url: core.buildTutorialProxyUrl(url),
        table_rotation: core.playfieldRotation,
      }),
    },
  };

  async #toggleOverlay(name) {
    const spec = VPinFECore.OVERLAYS[name];
    const overlayRoot = document.getElementById("overlay-root");
    let iframe = document.getElementById(spec.frameId);

    if (this[spec.flag]) {
      this[spec.flag] = false;
      overlayRoot.classList.remove("active");          // fade out
      if (iframe) {
        iframe.style.display = "none";                 // hide, never destroy
        if (iframe.contentWindow) {
          iframe.contentWindow.postMessage({ event: "reset state" }, "*");
        }
      }
      return;
    }

    const context = spec.prepare ? spec.prepare(this) : undefined;
    if (spec.prepare && context === null) return;

    for (const [other, otherSpec] of Object.entries(VPinFECore.OVERLAYS)) {
      if (other !== name && this[otherSpec.flag]) await this.#toggleOverlay(other);
    }

    this[spec.flag] = true;
    overlayRoot.classList.add("active");               // fade in
    if (!iframe) {
      iframe = document.createElement("iframe");
      iframe.src = spec.src;
      iframe.id = spec.frameId;
      iframe.setAttribute("allowTransparency", "true");
      iframe.style.display = "none";                   // start hidden to prevent a flash
      overlayRoot.appendChild(iframe);
      await new Promise(resolve => setTimeout(resolve, 10));   // let the DOM catch up
    }

    iframe.style.display = "block";
    const message = spec.opened && spec.opened(this, context);
    if (message && iframe.contentWindow) iframe.contentWindow.postMessage(message, "*");
  }

  #showmenu()           { return this.#toggleOverlay("menu"); }
  #showcollectionmenu() { return this.#toggleOverlay("collectionMenu"); }
  #showtutorial()       { return this.#toggleOverlay("tutorial"); }

  async #handleGameDataChange(message) {
    // Check if a collection filter was applied
    if (message.collection) {
      // if collection is "None" then reset to all tables, otherwise set to the selected collection.
      if (message.collection === "None") {
        await this.getGameData(true);
      } else {
        await this.call("set_games_by_collection", message.collection);
        await this.getGameData();
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
      await this.getGameData();
    } else if (message.sort) {
      // Sort order change - apply it to this window's API instance
      await this.call("apply_sort", message.sort, message.order);
      await this.getGameData();
    } else {
      // No filters specified - just refresh the game data
      await this.getGameData();
    }
  }

  async #handleCoreAudioEvent(message) {
    if (!this.enabled("core_audio") || !this.isController()) return;

    if (message.type === "GameIndexUpdate") {
      this.playGameAudio(this._currentGameIndex);
      return;
    }
    if (message.type === "GameLaunching" || message.type === "RemoteLaunching") {
      this.stopGameAudio();
      return;
    }
    if (message.type === "GameLaunchComplete" || message.type === "RemoteLaunchComplete") {
      this.playGameAudio(this._currentGameIndex);
      return;
    }
    if (message.type === "GameDataChange" && typeof message.index === "number") {
      this.playGameAudio(this._currentGameIndex);
    }
  }

  #resolveAudioUrl(indexOrUrl) {
    if (typeof indexOrUrl === "number" && Number.isFinite(indexOrUrl)) {
      this._currentGameIndex = indexOrUrl;
      return this.getAudioURL(indexOrUrl);
    }
    if (typeof indexOrUrl === "string") return indexOrUrl;
    return null;
  }

  #syncLocalIndexFromOutgoingMessage(message) {
    if (!message || typeof message !== "object") return;
    if (typeof message.index !== "number" || !Number.isFinite(message.index)) return;
    if (message.index < 0) return;
    if (message.type === "GameIndexUpdate" || message.type === "GameDataChange") {
      this._currentGameIndex = Math.floor(message.index);
    }
  }

  // Which messages mean "the wheel is now on something else". GameIndexUpdate is an
  // ordinary step; the other two mean the list or the game underneath may have changed,
  // so the notify has to fire again even when the index did not move.
  static SELECTION_MESSAGES = new Set([
    "GameIndexUpdate", "GameDataChange", "GameLaunchComplete", "RemoteLaunchComplete",
  ]);

  // How many preloaded URLs to remember. Generous enough to cover a page of the wheel
  // in both directions; small enough that forgetting all of them costs one page.
  static PRELOAD_MEMORY = 300;

  #syncSelectionFromMessage(message) {
    if (!message || typeof message !== "object") return;
    if (!this.isController()) return;
    if (!VPinFECore.SELECTION_MESSAGES.has(message.type)) return;
    if (message.type !== "GameIndexUpdate") this._lastSelectedIndex = null;
    this.#selectionChanged();
  }

  /**
   * Run something whenever the selection changes. This is how anything that follows the
   * wheel attaches - the rating fetch and the backend notify already do, and preloading
   * will - rather than being added to a list of message types by hand.
   */
  onSelection(listener) {
    if (typeof listener !== "function") return () => {};
    this._onSelection.push(listener);
    return () => {
      const at = this._onSelection.indexOf(listener);
      if (at >= 0) this._onSelection.splice(at, 1);
    };
  }

  #selectionChanged() {
    for (const listener of this._onSelection) {
      // One listener throwing must not stop the others, the same rule the backend's
      // event bus follows.
      try {
        listener(this._currentGameIndex);
      } catch (err) {
        console.warn("vpinfe: a selection listener failed", err);
      }
    }
  }

  // Neighbors only, and only once the wheel has stopped moving.
  #schedulePreload() {
    if (!this.enabled("core_preload")) return;
    clearTimeout(this._preloadTimer);
    this._preloadTimer = setTimeout(() => this.#preloadNeighbors(), this._preloadSettleMs);
  }

  #preloadNeighbors() {
    this._preloadTimer = null;
    const at = this._currentGameIndex;
    for (const index of [at - 1, at, at + 1]) {
      if (index < 0 || index >= this.gameData.length) continue;
      for (const kind of this._preloadKinds) this.#preload(this.getImageURL(index, kind));
    }
  }

  #preload(url) {
    if (!url || url === MISSING_MEDIA_URL || this._preloaded.has(url)) return;
    // Emptied wholesale rather than evicted one at a time. It exists to stop a re-fetch
    // on the way back through the wheel, and a large library would otherwise grow it
    // without limit.
    if (this._preloaded.size >= VPinFECore.PRELOAD_MEMORY) this._preloaded.clear();
    this._preloaded.add(url);
    Object.assign(new Image(), { decoding: "async", src: url });
  }

  async #notifySelectedGame() {
    if (!this.isController()) return;
    if (!Array.isArray(this.gameData) || this.gameData.length === 0) return;

    const index = Math.floor(this._currentGameIndex);
    if (!Number.isFinite(index) || index < 0 || index >= this.gameData.length) return;
    if (this._lastSelectedIndex === index) return;

    this._lastSelectedIndex = index;
    try {
      await this.call("notify_game_selected", index);
    } catch (e) {
      this._lastSelectedIndex = null;
      this.call("console_out", `notify_game_selected failed: ${e.message}`);
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

  #itemByIndex(index) {
    const numeric = Number(index);
    if (!Number.isFinite(numeric)) return null;
    const normalized = Math.floor(numeric);
    if (!Array.isArray(this.gameData) || normalized < 0 || normalized >= this.gameData.length) return null;
    return this.gameData[normalized];
  }

  #vpsIdOf(item) {
    return item && typeof item === "object" ? this._reader.vpsId(item) : "";
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

  #setGameVPinPlayRating(item, payload) {
    if (!item || typeof item !== "object") return;
    item.vpinplay = payload ? { ...payload } : null;
  }

  #applyCachedRatingToList(vpsId, payload) {
    if (!Array.isArray(this.gameData)) return;
    this.gameData.forEach((item) => {
      if (this.#vpsIdOf(item) === vpsId) {
        this.#setGameVPinPlayRating(item, payload);
      }
    });
  }

  #attachCachedVPinPlayRatings() {
    if (!Array.isArray(this.gameData)) return;
    this.gameData.forEach((item) => {
      const vpsId = this.#vpsIdOf(item);
      if (!vpsId) {
        this.#setGameVPinPlayRating(item, null);
        return;
      }
      const cached = this._vpinplayRatingCache.get(vpsId);
      this.#setGameVPinPlayRating(item, cached && cached.data ? cached.data : null);
    });
  }

  async #loadVPinPlayRating(index, forceRefresh = false) {
    const item = this.#itemByIndex(index);
    if (!item) return null;

    const vpsId = this.#vpsIdOf(item);
    if (!vpsId) {
      this.#setGameVPinPlayRating(item, null);
      return null;
    }

    const cached = this._vpinplayRatingCache.get(vpsId);
    if (!forceRefresh && cached && cached.data) {
      this.#setGameVPinPlayRating(item, cached.data);
      return cached.data;
    }

    const existingRequest = this._vpinplayRatingRequests.get(vpsId);
    if (!forceRefresh && existingRequest) {
      return existingRequest;
    }

    if (!this.vpinplayEndpoint) {
      this.#setGameVPinPlayRating(item, null);
      return null;
    }

    const request = this.#fetchVPinPlayRating(vpsId)
      .then((payload) => {
        const data = this.#normalizeVPinPlayRatingPayload(vpsId, payload);
        if (!data) {
          this._vpinplayRatingCache.delete(vpsId);
          this.#applyCachedRatingToList(vpsId, null);
          return null;
        }
        this._vpinplayRatingCache.set(vpsId, { data });
        this.#applyCachedRatingToList(vpsId, data);
        return data;
      })
      .catch((error) => {
        this.call("console_out", `VPinPlay rating fetch failed for ${vpsId}: ${error.message}`).catch(() => {});
        this.#applyCachedRatingToList(vpsId, null);
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
        this.#handleFrontendInputLifecycleEvent(data.message);
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
      this.#applyContract(await this.call("get_theme_contract"));
    } catch (_e) {
      this.#applyContract(OLDEST_CONTRACT);   // an older build cannot answer; assume 1
    }
    try {
      const windows = await this.call("get_theme_windows");
      if (Array.isArray(windows) && windows.length) this.windows = windows;
    } catch (_e) {
      /* an older build cannot answer; the default below already covers it */
    }
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
    this.#applyCapabilityConfig();
    this.setAudioOptions(audioCfg);

    // Load network config
    this.themeAssetsPort = await this.call("get_theme_assets_port");
    try {
      this.mediaPriorities = this.#normalizeMediaPriorities(await this.call("get_media_priorities"));
    } catch (_e) {
      this.mediaPriorities = Object.assign({}, DEFAULT_MEDIA_PRIORITIES);
    }
    try {
      this.vpinplayEndpoint = await this.call("get_vpinplay_endpoint");
    } catch (_e) {
      this.vpinplayEndpoint = "";
    }
    // Load display config
    this.playfieldOrientation = await this.call("get_playfield_orientation");
    this.playfieldRotation = await this.call("get_playfield_rotation");
    this.cabMode = !!await this.call("get_cab_mode");
    await this.#loadMonitors();
    await this.getGameData();
   //this.#overrideConsole(); //disabled for now...

    // only run on the table window.. Its the master controller for all screens/windows
    if (this.isController()) {
      await this.#initKeyboardMapping();
      await this.#initGamepadMapping();
      this.#setupGamepadListeners();
      this.#updateGamepads();           // No await needed here — runs loop
      this.#watchPlayState();           // Subscribe to remote launch events
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

  #setFrontendInputEnabled(enabled) {
    this.frontendInputEnabled = !!enabled;
    this.gamepadEnabled = this.frontendInputEnabled;
  }

  #handleFrontendInputLifecycleEvent(message) {
    if (!message || typeof message !== "object") return;

    if (message.type === "GameLaunching" || message.type === "RemoteLaunching") {
      this._launchInputSuppressedByLifecycle = true;
      this.#setFrontendInputEnabled(false);
    } else if (message.type === "GameLaunchComplete" || message.type === "RemoteLaunchComplete") {
      this._launchInputSuppressedByLifecycle = false;
      this.#setFrontendInputEnabled(true);
    }
  }

  // True when core should consume a paging action itself: paging enabled, table
  // window, and no overlay up (overlays keep receiving the raw action).
  #shouldHandleCorePaging(action) {
    if (action !== "joypageup" && action !== "joypagedown") return false;
    if (!this.enabled("core_paging")) return false;
    if (!this.isController()) return false;
    if (this.menuUP || this.collectionMenuUP || this.tutorialUP) return false;
    return true;
  }

  async #handleCorePaging(action) {
    // One page request in flight at a time; presses during the round trip are
    // dropped rather than queued against a stale index.
    if (this._pagingInFlight) return;
    this._pagingInFlight = true;
    try {
      // pageup advances (next letter / forward), pagedown goes back.
      const direction = action === "joypageup" ? "next" : "prev";
      const index = await this.call("get_page_index", this._currentGameIndex, direction);
      if (typeof index === "number" && index >= 0 && index !== this._currentGameIndex) {
        // Same path restorelasttable uses: themes move their wheel on the
        // incoming GameIndexUpdate, so no theme changes are needed.
        this.sendMessageToAllWindowsIncSelf({ type: "GameIndexUpdate", index });
      }
    } catch (e) {
      this.call("console_out", `Core paging failed: ${e.message}`);
    } finally {
      this._pagingInFlight = false;
    }
  }

  async #triggerInputAction(action) {
    if (!this.frontendInputEnabled) return;

    let handlers;
    if (this.tutorialUP) handlers = this.inputHandlerTutorial;
    else if (this.collectionMenuUP) handlers = this.inputHandlerCollectionMenu;
    else if (this.menuUP) handlers = this.inputHandlerMenu;
    else handlers = this.inputHandlers;   // no menu is up: the theme's own handler

    // Handlers are async and their result was dropped, so a theme that threw did it
    // in silence - and a theme guarding itself with an "is animating" flag never
    // cleared it, which is what left the wheel dead until a restart.
    for (const handler of handlers) {
      try {
        const result = handler(action);
        if (result && typeof result.catch === "function") {
          result.catch(e => this.call("console_out",
            `Theme input handler failed on ${action}: ${e && e.message}`));
        }
      } catch (e) {
        this.call("console_out", `Theme input handler threw on ${action}: ${e && e.message}`);
      }
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
    if (!this.frontendInputEnabled) return;
    if (e.repeat) {
      const now = Date.now();
      if (now - this._lastRepeatAt < this.minRepeatIntervalMs) return;
      this._lastRepeatAt = now;
    }

    if (this.isController()) {
      const action = this.#actionForKeyboardEvent(e);
      if (!action) return;

      if (action === "joyexit") this.call("close_app");
      else if (action === "joymenu") this.#showmenu();
      else if (action === "joycollectionmenu") this.#showcollectionmenu();
      else if (action === "joytutorial") this.#showtutorial();
      else if (this.#shouldHandleCorePaging(action)) this.#handleCorePaging(action);
      else this.#triggerInputAction(action);
    }
  }

  async #loadMonitors() {
    this.monitors = await this.call("get_monitors");
  }

  // One branch, once, for the whole surface. A theme declares what it was written
  // against and gets that and nothing else, which is what makes the legacy layer
  // removable as a unit instead of one alias at a time.
  #applyContract(level) {
    const declared = Number(level) || OLDEST_CONTRACT;
    this.contract = Math.min(Math.max(declared, OLDEST_CONTRACT), CURRENT_CONTRACT);
    this._reader = this.contract > OLDEST_CONTRACT
      ? new ContractTwoReader(this)
      : new ContractOneReader(this);
    if (this.contract > OLDEST_CONTRACT) removeLegacyAliases(this);
    console.info(`vpinfe: serving theme contract ${this.contract}`);
  }

  /**
   * This window's name - which page it loaded, and its media kind when it has one.
   *
   * Known before the socket opens. Every published theme asks the backend for it instead,
   * because until now there was nothing else to ask.
   */
  get windowName() {
    return this._windowName;
  }

  /**
   * Whether this window is the one that owns input, audio and the selection. It is the
   * first window the theme declared - `table` for a theme that declares nothing, and
   * `playfield` at contract 2 - so nothing here has to know a name.
   */
  isController() {
    return this._windowName === (this.windows[0] || "table");
  }

  #servesLegacyNames() {
    return this.contract <= OLDEST_CONTRACT;
  }

  #normalizeMediaType(type) {
    const value = String(type || "").trim().toLowerCase();
    if (!this.#servesLegacyNames()) return value;
    return MEDIA_KIND_ALIASES[value] || value;
  }

  #normalizeMediaPriorities(priorities) {
    const normalized = Object.assign({}, DEFAULT_MEDIA_PRIORITIES);
    if (!priorities || typeof priorities !== "object") return normalized;

    for (const key of ["playfield", "bg", "dmd"]) {
      const value = String(priorities[key] || "").trim().toLowerCase();
      if (value === "image" || value === "video") normalized[key] = value;
    }

    const realDmd = String(priorities.real_dmd || "").trim().toLowerCase();
    if (["standard", "color"].includes(realDmd)) normalized.real_dmd = realDmd;
    return normalized;
  }

  #resolveImageVideoMedia(item, kind) {
    const priority = this.mediaPriorities[kind] || DEFAULT_MEDIA_PRIORITIES[kind] || "video";
    return this._reader.imageVideo(item, kind, priority);
  }

  #resolveRealDmdMedia(item) {
    return this._reader.realDmd(item, this.mediaPriorities.real_dmd
                                     || DEFAULT_MEDIA_PRIORITIES.real_dmd);
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
  if (!this.frontendInputEnabled) return;

  const actions = this.joyButtonMap[buttonIndex.toString()];
  if (!actions) return;

  // Handle all actions mapped to this button
  for (const action of actions) {
    //this.call("console_out", `Button action: ${action}, windowName: ${this._windowName}`);
    if (action === "joyexit" && this.isController()) {
      this.call("close_app");
    }
    else if (action === "joymenu" && this.isController()) {
      this.#showmenu();
    }
    else if (action === "joycollectionmenu" && this.isController()) {
      this.call("console_out", "Triggering collection menu");
      this.#showcollectionmenu();
    }
    else if (action === "joytutorial" && this.isController()) {
      this.#showtutorial();
    }
    else if (this.#shouldHandleCorePaging(action)) {
      this.#handleCorePaging(action);
    }
    else {
      this.#triggerInputAction(action);
    }
  }
}

  #updateGamepads() {
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

        if (this.frontendInputEnabled && isPressed && !wasPressed) {
          //this.call("console_out", "Button: " + index);
          this.#onButtonPressed(index, i); // new press
        }
        this.previousButtonStates[i][index] = isPressed;
      });
    }
    requestAnimationFrame(() => this.#updateGamepads());
  }

  // convert the hard full local path to the web servers url map
  getCurrentTutorialUrl() {
    const index = Math.floor(this._currentGameIndex);
    if (!Array.isArray(this.gameData) || index < 0 || index >= this.gameData.length) {
      return "";
    }

    const item = this.gameData[index];
    const meta = (item && typeof item === "object") ? item.meta : null;
    const info = (meta && typeof meta === "object" && meta.Info && typeof meta.Info === "object")
      ? meta.Info
      : null;
    const tutorialUrl = info ? info.PinballPrimerTut : "";
    return (typeof tutorialUrl === "string") ? tutorialUrl.trim() : "";
  }

  buildTutorialProxyUrl(tutorialUrl) {
    if (!tutorialUrl) return "";
    return `/proxy/pinballprimer?url=${encodeURIComponent(tutorialUrl)}`;
  }

  // Menu deregister for Input Events
  async #deregisterAllInputHandlersMenu() {
    this.inputHandlerMenu = [];
    this.call("console_out", "cleared the menu gamepad handler. aka menu closed");
  }

  // Subscribe to play state on the manager UI's event stream
  #watchPlayState() {
    // Don't subscribe from a file:// origin - CORS blocks it on Chromium/QWebEngine.
    // The theme page loads over http://, where this works.
    if (window.location.protocol === 'file:') return;

    const streamUrl = `http://127.0.0.1:${this.managerUiPort}/api/v1/events?events=play.state_changed`;
    console.log("[RemoteLaunch] Subscribing to:", streamUrl);

    const source = new EventSource(streamUrl);
    let reportedOffline = false;

    source.addEventListener("play.state_changed", (message) => {
      reportedOffline = false;
      const state = JSON.parse(message.data).state || {};

      // Our own launches arrive as GameLaunching over the bridge. Acting on them
      // here as well would raise the remote overlay on a launch from the wheel.
      if (state.source === "frontend") return;

      if (state.launching && !this.remoteLaunchActive) {
        this.remoteLaunchActive = true;
        console.log("[RemoteLaunch] Launch detected:", state.table_name);
        this.call("console_out", `Remote launching: ${state.table_name}`);
        this.sendMessageToAllWindowsIncSelf({
          type: "RemoteLaunching",
          table_name: state.table_name
        });
      } else if (!state.launching && this.remoteLaunchActive) {
        this.remoteLaunchActive = false;
        console.log("[RemoteLaunch] Launch completed");
        this.call("console_out", "Remote launch completed");
        this.sendMessageToAllWindowsIncSelf({
          type: "RemoteLaunchComplete"
        });
      }
    });

    // EventSource reconnects on its own, and the stream sends the current state on
    // connect, so a manager UI that is down or restarting needs nothing here beyond
    // not filling the log with it.
    source.onerror = () => {
      if (reportedOffline) return;
      reportedOffline = true;
      console.log("[RemoteLaunch] Event stream unavailable (manager UI may not be running)");
    };
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
