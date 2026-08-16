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
// Keyed by canonical kind; the field names are contract 1's payload and are frozen.
const MEDIA_PATH_FIELDS = {
  playfield: "PlayfieldImagePath",
  playfield_fss: "FSSImagePath",
  backglass: "BGImagePath",
  scoreview: "DMDImagePath",
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
  backglass: "BGVideoPath",
  scoreview: "DMDVideoPath",
  loading: "LoadingVideoPath",
};

// Canonical kind names. Everything that reads this does so after normalization, so
// contract 1's `bg` and `dmd` arrive here already translated - keyed the old way, the
// lookup missed and the whole image-or-video preference was dead for those two.
const DEFAULT_MEDIA_PRIORITIES = {
  playfield: "video",
  backglass: "video",
  scoreview: "video",
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
    // Declarable, so a theme that pages for itself can say so. It had no key at all,
    // which left carousel-desktop's own page-jump cases losing to core with no way to
    // opt out short of calling enableCorePaging(false) in JavaScript.
    config: ["paging.enabled"],
    describe: "Core handles the paging actions itself.",
  },
  core_navigation: {
    // On only for a theme that says it needs 3.0. One that still runs on 2.x drives its
    // own cursor: Revolution, Trinidad and carousel-desktop use previous/next to move
    // their own collection list, and #dispatchAction reaches #shouldHandleCoreNavigation
    // before #triggerInputAction with an else-if between them - so core consumes the
    // press, the theme's handler never runs, and the broadcast behind it reads to those
    // themes as "the user picked a game". Their picker exits onto an unrelated game.
    //
    // `navigation.enabled: true` still turns it on for a theme that has not moved yet.
    default: false,
    defaultFromContract: 2,
    config: ["navigation.enabled"],
    describe: "Core moves the selection, wraps it, and announces where it went.",
  },
  core_audio: {
    default: false,
    config: ["use_core_audio", "audio.use_core_audio", "audio.enabled"],
    legacyConfig: ["useCoreAudio", "audio.useCoreAudio"],
    describe: "Core plays, fades and mutes per-game audio.",
  },
  // Off by default: every published theme preloads for itself, so turning this on
  // without deleting the theme's own loop just doubles the requests.
  // Off by default like the rest: a theme that already lays itself out must ask before
  // core starts setting attributes its CSS may fight.
  core_layout: {
    default: false,
    config: ["layout.enabled"],
    describe: "Core turns the UI and the playfield art to suit the cabinet.",
  },
  core_launch_dim: {
    // On by default. VPX is about to own every screen, so every window should step
    // aside - and a theme cannot do this for itself on more than one, because its
    // script only runs in the controller.
    default: true,
    config: ["launch_dim.enabled"],
    describe: "Core dims each window while a game is launching.",
  },
  core_media_window: {
    // On by default. A media kind is named after the display it captures, so a window
    // that is a display has exactly one obvious thing to show, and every theme wrote the
    // same few lines to show it. A theme that wants something else on a secondary window
    // sets `media_window.enabled` false, or simply omits the element core renders into.
    default: true,
    config: ["media_window.enabled"],
    describe: "Core shows each display window the media named for it.",
  },
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

const MISSING_MEDIA_URL = "/core/images/file_missing.png";

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
    return `${this.core.endpoints.assets}/media/${encodeURIComponent(id)}/${kind}`;
  }

  imageURL(entry, kind) { return this.url(entry, kind) || MISSING_MEDIA_URL; }
  // Contract 2 names kinds; it never locates files, so there is no path to hand back.
  path()                { return null; }
  videoURL(entry, kind) { return this.url(entry, VIDEO_KIND[kind] || kind); }
  audioURL(entry)       { return this.url(entry, "audio"); }
  logo(entry)           { return entry.game?.manufacturer_logo || null; }
  vpsId(entry)          { return String(entry.game?.vps_id || "").trim(); }
  // The table, not the game: a row is a table, and the collection chose which one.
  identity(entry)       { return String(entry.table?.id || entry.game?.id || ""); }

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

const VIDEO_KIND = { playfield: "playfield_video", backglass: "backglass_video",
                     scoreview: "scoreview_video", topper: "topper_video",
                     loading: "loading" };


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
// The action names a contract 1 theme's handleInput switches on. Core dispatches the
// current names; a theme that declared nothing is handed these instead, so every
// published `case "joyleft"` keeps matching. PAR-40.
const LEGACY_ACTION_NAMES = {
  previous: "joyleft",
  next: "joyright",
  page_previous: "joypageup",
  page_next: "joypagedown",
  select: "joyselect",
  back: "joyback",
  menu: "joymenu",
  collection_menu: "joycollectionmenu",
  tutorial: "joytutorial",
  exit: "joyexit",
};

// Only the screen pair is left. The selection members went back to the Table* spelling
// 2.x published, so there is nothing for them to forward to - and an entry mapping a
// name to itself would install an accessor that reads itself.
const VPINFE_RENAMED_MEMBERS = {
  tableRotation: 'playfieldRotation',
  tableOrientation: 'playfieldOrientation',
};

// Kind names earlier builds accepted, against the canonical snake_case set.
// real_dmd_color is the odd one: at contract 1 both frames collapse onto real_dmd, the
// way 2.x addressed them, while contract 2 keeps it separately addressable.
// Every media kind VPinFE serves, in common/media_specs.py order. Kept in step by
// tests/theming/test_media_kinds.py, because a name that drifts here fails silently:
// a lookup for a kind nobody serves returns nothing rather than complaining.
const MEDIA_KINDS = [
  "backglass", "scoreview", "playfield", "playfield_fss", "wheel", "cab",
  "real_dmd", "real_dmd_color", "flyer", "playfield_video", "backglass_video",
  "scoreview_video", "audio", "instruction_card", "topper", "topper_video",
  "loading", "audio_launch", "rule_sheet", "logo",
];

const MEDIA_KIND_ALIASES = {
  table: "playfield",
  table_video: "playfield_video",
  fss: "playfield_fss",
  bg: "backglass",
  bg_video: "backglass_video",
  dmd: "scoreview",
  dmd_video: "scoreview_video",
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
// Empty since the selection surface went back to the Table* spelling 2.x published:
// there is nothing left to translate. The machinery stays because it is what the next
// message rename uses - see VPINFE_RENAMED_MEMBERS, which is still carrying two.
const MESSAGE_TYPE_ALIASES = {};

const MESSAGE_TYPE_CANONICAL = Object.fromEntries(
  Object.entries(MESSAGE_TYPE_ALIASES).map(([current, legacy]) => [legacy, current]),
);

function canonicalMessageType(type) {
  return MESSAGE_TYPE_CANONICAL[type] || type;
}

// Say it once per name, not once per access - a wheel reads tableData every frame. The
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

// Core's own calls, refused by vpin.call(). These sort and filter the library for the
// collection-menu overlay, which core ships; no theme is expected to reach them, and core
// owns sorting outright once it owns the list the wheel steps through.
//
// This is a line, not a wall. A theme's iframe is same-origin and can reach whatever the
// overlays reach if it goes looking, so it does not stop a determined author - what it
// does is move these from documented and allowed to deliberately circumvented, which is
// the difference worth having before anyone builds on them.
const INTERNAL_METHODS = new Set([
  "apply_filters",
  "apply_sort",
  "get_current_filter_state",
  "get_current_sort_state",
  "get_current_order_state",
]);

// Same once-per-name reporting as announceLegacy, and for the same reason: without it the
// only evidence about who still calls these is a console nobody reads on a cabinet.
const announcedInternal = new Set();
function announceInternal(target, method) {
  if (announcedInternal.has(method)) return;
  announcedInternal.add(method);
  console.info(`vpinfe: '${method}' is not part of the theme API; the call was refused (PAR-84)`);
  try {
    Promise.resolve(target.callInternal("report_deprecated_use", "theme-internal-methods", method))
      .catch(() => {});
  } catch (err) {
    /* nothing to do; the console line already went out */
  }
}

// Contract 1's overlay surface, all nine names of it. Derived rather than forwarded: three
// booleans over one string, and six methods over two that take the overlay's name - so
// VPINFE_RENAMED_MEMBERS, which maps a name to a name, cannot express them.
const VPINFE_OVERLAY_ALIASES = {
  menuUP:           { overlay: "menu" },
  collectionMenuUP: { overlay: "collectionMenu" },
  tutorialUP:       { overlay: "tutorial" },
  toggleMenu:                         { overlay: "menu",           call: "toggleOverlay" },
  toggleCollectionMenu:               { overlay: "collectionMenu", call: "toggleOverlay" },
  toggleTutorial:                     { overlay: "tutorial",       call: "toggleOverlay" },
  registerInputHandlerMenu:           { overlay: "menu",           call: "registerOverlayHandler" },
  registerInputHandlerCollectionMenu: { overlay: "collectionMenu", call: "registerOverlayHandler" },
  registerInputHandlerTutorial:       { overlay: "tutorial",       call: "registerOverlayHandler" },
};

function installOverlayAliases(target) {
  for (const [oldName, spec] of Object.entries(VPINFE_OVERLAY_ALIASES)) {
    Object.defineProperty(target, oldName, {
      get() {
        announceLegacy(this, oldName, spec.call || "overlay");
        if (!spec.call) return this.overlay === spec.overlay;
        return (...args) => this[spec.call](spec.overlay, ...args);
      },
      // Nothing we ship writes these, but a theme could, and silently ignoring it would
      // be worse than acting on it: assigning false closes the overlay it names.
      set(value) {
        announceLegacy(this, oldName, "overlay");
        if (spec.call || !!value === (this.overlay === spec.overlay)) return;
        this.toggleOverlay(spec.overlay);
      },
      configurable: true,
    });
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
  for (const oldName of Object.keys(VPINFE_OVERLAY_ALIASES)) {
    if (Object.getOwnPropertyDescriptor(target, oldName)) delete target[oldName];
  }
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
  // Contract 1 is one row per game and carries no id, so the folder is the name it has.
  identity(game)       { return String(game.gameDirName || ""); }

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
    const assets = this.core.endpoints.assets;
    // The file may sit deeper than medias/ itself - wheel sets live in
    // medias/wheels/<set>/ - so keep everything from medias/ down.
    const mediasIndex = parts.lastIndexOf('medias');
    if (mediasIndex > 0) {
      const gameDir = parts[mediasIndex - 1];
      const rest = parts.slice(mediasIndex).map(encodeURIComponent).join('/');
      return `${assets}/tables/${encodeURIComponent(gameDir)}/${rest}`;
    }
    const dir = parts[parts.length - 2];        // media sitting in the game folder
    return `${assets}/tables/${encodeURIComponent(dir)}/${encodeURIComponent(file)}`;
  }
}

// ─────────────────────────── end contract 1 ──────────────────────────────────


class VPinFECore {
  // Resolves the confirm dialog when one is up, and is null when one is not - which is
  // also how the input handler knows whether it owns the next select or back.
  #pendingConfirm = null;

  // The notice currently on screen, so a second one replaces it rather than stacking.
  #lifecycleNotice = null;

  constructor() {
    this.tableData = {};
    // What the running theme declared. Contract 1 until the bridge says otherwise.
    this.contract = OLDEST_CONTRACT;
    // The theme's windows, controller first. Replaced once the bridge answers; until
    // then the three VPinFE has always opened, under contract 1's names.
    this.windows = ["table", "bg", "dmd"];
    // Which collection the entry list came from. Seeded so a theme reading it before
    // the first payload gets the documented type rather than undefined.
    this.collection = "";
    this._reader = new ContractOneReader(this);
    installLegacyAliases(this);
    installOverlayAliases(this);
    this.monitors = [];
    this._resolveReady = null;
    this.ready = new Promise(resolve => this._resolveReady = resolve);
    this.inputHandlers = []; // gamepad and joystick input handlers for theme
    // Input handlers per overlay, keyed by its name in OVERLAYS. One map rather than an
    // array per overlay, so adding a fourth is a registry entry and nothing else.
    this.overlayHandlers = {};

    // Gamepad mapping
    this.joyButtonMap = {}
    this.keyActionMap = {
      previous: ['arrowleft', 'shiftleft'],
      next: ['arrowright', 'shiftright'],
      page_previous: ['pageup', 'arrowup'],
      page_next: ['pagedown', 'arrowdown'],
      select: ['enter'],
      back: ['b'],
      menu: ['m'],
      collection_menu: ['c'],
      tutorial: ['t'],
      exit: ['escape', 'q'],
    };
    this.previousButtonStates = {};
    // A held key repeats at whatever rate the OS is set to - often 30 a second - and
    // every one of those used to become a full wheel move. Deliberate presses are never
    // throttled; only the automatic repeat is.
    this.minRepeatIntervalMs = 150;
    // Keyed by action: one timestamp for everything meant a fast direction change was
    // read as the same key repeating and got dropped.
    this._lastRepeatAt = {};
    this.gamepadEnabled = true;
    this.frontendInputEnabled = true;
    this._launchInputSuppressedByLifecycle = false;

    // What core is doing on the theme's behalf, seeded from CAPABILITIES so the
    // default is stated in one place.
    this._capabilities = Object.fromEntries(
      Object.entries(CAPABILITIES).map(([name, spec]) => [name, spec.default]));
    this._pagingInFlight = false;

    // menu is up?
    // The overlay that is open, or null. One-of by construction - #toggleOverlay closes
    // any other before opening one - so three booleans could only ever disagree.
    this.overlay = null;

    // Event handling
    this.eventHandlers = {}; // Custom event handlers registered by themes

    // Where the services are, resolved once before any theme code runs. Ports travel in
    // the url because the page cannot ask for them: asking needs the bridge, and finding
    // the bridge needs a port. Absent - an older launcher, a page opened by hand - these
    // fall back to what the frontend has always assumed.
    const params = new URLSearchParams(window.location.search);
    const port = (name, fallback) => Number(params.get(name)) || fallback;
    this.themeAssetsPort = port('themeAssetsPort', 8000);
    this.hubPort = port('hubPort', 8001);
    this.wsPort = port('wsPort', 8002);
    // Set only when the hub is another machine. The player's own services stay loopback:
    // this names where the library and its art are, not where this page is running.
    this.hubHost = params.get('hubHost') || '';
    // What this player serves on, which is not what a remote hub answers on - `hubPort`
    // carries the hub's when there is one, so the two cannot be the same number.
    this.playerPort = port('playerPort', this.hubPort);
    // The hub's asset server, when the hub is elsewhere. Its own port, not this
    // machine's: pairing a remote host with the local port addresses neither.
    this.hubAssetsPort = port('hubAssetsPort', this.themeAssetsPort);
    this.vpinplayEndpoint = '';

    // Display config, as the ini states it. Raw values - `layout` below is what a theme
    // should read.
    this.playfieldOrientation = 'landscape'; // default, will be updated from config
    this.playfieldRotation = 0; // default, will be updated from config

    // The three questions every theme was answering for itself, answered once. Seeded so
    // a theme laying out before the bridge answers gets the documented types.
    this.layout = { cabinet: false, uprightRotation: 0, surface: 'landscape' };
    // How far to turn playfield art. "auto" measures each image instead.
    this.playfieldMediaRotation = 'auto';

    // Remote launch state tracking
    this.remoteLaunchActive = false;

    // Theme config and centralized audio state
    this.themeConfig = {};
    this.mediaPriorities = Object.assign({}, DEFAULT_MEDIA_PRIORITIES);
    this._currentTableIndex = 0;
    this._initialGameRestored = false;
    this._audioMuted = false;
    this._audio = Object.assign(new Audio(), { loop: true });
    this._audioFadeId = null;
    this._audioFadeDuration = 500;
    this._audioMaxVolume = 0.8;
    this._audioCurrentUrl = null;
    this._lastSelectedIndex = null;
    // Preloading waits for the wheel to stop. Fetching on every step is what made a
    // two-second hold ask for hundreds of images that were obsolete before they decoded;
    // the settle delay is the whole mechanism, not a nicety.
    this._preloadSettleMs = 180;
    // Canonical names: a contract 1 theme has these translated for it on the way
    // out, while `bg` here would only ever have worked for contract 1.
    this._preloadKinds = ["playfield", "backglass", "wheel"];
    this._preloadTimer = null;
    this._preloaded = new Set();

    this._onSelection = [];
    // The base mode is never popped; overlays and dialogs push on top.
    this._inputModes = ['navigation'];
    this._lastMoveAt = 0;
    this.onSelection(() => this.getVPinPlayRating(this._currentTableIndex).catch(() => {}));
    this.onSelection(() => this.#notifySelectedGame().catch(() => {}));
    this.onSelection(() => this.#schedulePreload());
    this._vpinplayRatingCache = new Map();
    this._vpinplayRatingRequests = new Map();

    // WebSocket bridge
    this._ws = null;
    this._reconnectTimer = null;
    this._reconnectDelayMs = 0;
    this._shuttingDown = false;
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

  // An overlay page registers the handler that receives every action while it is open.
  // Not guarded on isController: an overlay only ever exists in the controller window.
  async registerOverlayHandler(name, handler) {
    if (!VPinFECore.OVERLAYS[name]) {
      console.warn(`[vpinfe] registerOverlayHandler("${name}") names no overlay`);
      return;
    }
    if (typeof handler !== 'function') return;
    this.call("console_out", `registered ${name} overlay handler`);
    (this.overlayHandlers[name] ||= []).push(handler);
  }

  async call(method, ...args) {
    if (INTERNAL_METHODS.has(method)) {
      announceInternal(this, method);
      throw new Error(`Method not allowed: ${method}`);
    }
    return this.callInternal(method, ...args);
  }

  // The door core's own overlays come in by. Not part of the theme surface - see
  // INTERNAL_METHODS for what that is worth and what it is not.
  async callInternal(method, ...args) {
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
    const item = this.tableData[index];
    return item ? this._reader.imageURL(item, this.#normalizeMediaType(kind)) : null;
  }

  getMediaURL(index, type) {
    return this.getMedia(index, type).url;
  }

  // URL of the game manufacturer's logo, or null when none is installed
  getManufacturerLogoURL(index) {
    const item = this.tableData[index];
    const path = item ? this._reader.logo(item) : null;
    return path ? `${this.endpoints.assets}${path}` : null;
  }

  getPreferredMediaURL(index, type) {
    return this.getMediaURL(index, type);
  }

  getMedia(index, type) {
    const item = this.tableData[index];
    if (!item) return { url: null, kind: null, priority: null, path: null };

    const normalizedType = this.#normalizeMediaType(type);
    if (normalizedType === "real_dmd") {
      return this.#resolveRealDmdMedia(item);
    }
    // Canonical, because normalizedType is. Written as `bg`/`dmd` this never matched,
    // so a backglass or scoreview video was never preferred over its still at either
    // contract - the branch below treated both as a plain image.
    if (["playfield", "backglass", "scoreview"].includes(normalizedType)) {
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
    const item = this.tableData[index];
    return item ? this._reader.audioURL(item) : null;
  }

  // Core handles joypageup/joypagedown by default: it asks the backend for the
  // target index ([Input] pagingtype/pagingsize + current sort) and broadcasts a
  // TableIndexUpdate. Themes that implement their own paging call
  /**
   * What this build does on your behalf, and whether each is on right now. A name that
   * is absent is a behavior this build does not have - check before using it.
   */
  get capabilities() {
    return { ...this._capabilities };
  }

  /**
   * Where the things this page talks to actually are. Build urls from these rather than
   * assuming a host or a port: the halves can be separate machines, and only this knows.
   *
   * Three are addresses you fetch from - take one, add a path, get an answer back:
   *   `hub`     the library and what is known about it: games, collections, uploads
   *   `player`  this machine: launching, play state, its hardware
   *   `assets`  the files themselves: theme packages, table media, shared art
   *
   * One is a line held open instead, so it takes no path:
   *   `frontend_channel`  how this page and VPinFE talk to each other, both ways
   *
   * `hub` and `player` are one address today because one `/api/v1` answers for both.
   * They are separate keys because they are separate questions, and a theme built
   * against them keeps working when the two are separate machines.
   *
   * Derived on read, so correcting a port after startup corrects every url built from it.
   * Hosts are loopback until bind configuration says otherwise, and deliberately not
   * taken from window.location: "wherever this page came from" is a different
   * one-machine assumption, and one that fails only for remote viewers - so it still
   * looks right on the machine it was written on.
   */
  get endpoints() {
    const host = '127.0.0.1';
    // The hub's services follow the hub. `player` and `frontend_channel` never do: they
    // are this machine's own, and a page dialling another host for them would be asking
    // a different player to answer for this one's windows.
    const hubHost = this.hubHost || host;
    return {
      hub: `http://${hubHost}:${this.hubPort}`,
      player: `http://${host}:${this.playerPort}`,
      assets: `http://${hubHost}:${this.hubHost ? this.hubAssetsPort : this.themeAssetsPort}`,
      frontend_channel: `ws://${host}:${this.wsPort}`,
    };
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
      // `defaultFromContract` reads ">= this contract", not "== it", so a contract 3
      // theme inherits the newer default rather than falling back to the older one.
      const fallback = spec.defaultFromContract === undefined
        ? spec.default
        : this.contract >= spec.defaultFromContract;
      this.#setCapability(name, stated === undefined ? fallback : !!stated);
    }
    if (!this.enabled("core_audio")) this.stopTableAudio({ immediate: true });

    // A theme that shows a cab shot, or shows no wheel, preloads a different set. The
    // names go through the same normalization as everywhere else, so a contract 1 theme
    // can still say `table` and mean the playfield.
    const kinds = configValue(config, "preload.kinds");
    if (Array.isArray(kinds) && kinds.length) {
      const asked = kinds.map((kind) => this.#normalizeMediaType(kind));
      const unknown = asked.filter((kind) => !MEDIA_KINDS.includes(kind));
      if (unknown.length) {
        console.warn(`[vpinfe] preload.kinds names ${unknown.join(", ")}, which `
          + `${unknown.length === 1 ? "is not a media kind" : "are not media kinds"}. `
          + `Nothing preloads for ${unknown.length === 1 ? "it" : "them"}.`);
      }
      this._preloadKinds = asked.filter((kind) => MEDIA_KINDS.includes(kind));
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
  async getPageIndex(direction = "next", index = this._currentTableIndex) {
    return await this.call("get_page_index", index, direction);
  }

  enableCoreAudio(enabled = true) {
    this.#setCapability("core_audio", enabled);
    if (!this.enabled("core_audio")) this.stopTableAudio({ immediate: true });
  }

  isCoreAudioEnabled() {
    return this.enabled("core_audio");
  }

  setAudioMuted(muted = true) {
    this._audioMuted = !!muted;
    if (this._audio) this._audio.muted = this._audioMuted;
    if (this._audioMuted) {
      this.stopTableAudio({ immediate: true });
      return;
    }
    if (this.enabled("core_audio") && this.isController()) {
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
    if (!this.enabled("core_audio") || this._audioMuted || !this.isController()) return;
    const url = this.#resolveAudioUrl(indexOrUrl);
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
      // Autoplay refused: nothing to retry against, the browser wants a gesture. The
      // frontend launches Chromium with --autoplay-policy=no-user-gesture-required, so
      // this is only reachable outside that launcher.
      if (e && e.name === "NotAllowedError") return;
      if (retries > 0 && this._audioCurrentUrl === url) {
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

  // The URL of a game's video, by media kind
  getVideoURL(index, kind) {
    const item = this.tableData[index];
    return item ? this._reader.videoURL(item, this.#normalizeMediaType(kind)) : null;
  }

  // The list, under the name that describes what is in it. At contract 2 the items are
  // entries - a table with its game attached - so `entries` is what a theme iterates.
  get entries() {
    return this.tableData;
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
    const item = this.#itemByIndex(index);
    if (!item) return null;

    const vpsId = this.#vpsIdOf(item);
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

  // Open the named overlay, or close it if it is the one that is open. Callable from an
  // overlay's own page, which is how each of them closes itself.
  toggleOverlay(name) {
    return this.#toggleOverlay(name);
  }

  // Launch a game
  async launchTable(index) {
    this.#setFrontendInputEnabled(false);
    try {
      await this.call("launch_table", index);
    } catch (e) {
      // The call will timeout after 30s while VPX is still running - that's expected
      this.call("console_out", `launch_table call ended: ${e.message}`);
    } finally {
      if (!this._launchInputSuppressedByLifecycle && !this.remoteLaunchActive) {
        this.#setFrontendInputEnabled(true);
      }
    }
  }

  async getTableData(reset=false) {
    const payload = JSON.parse(await this.call("get_tables", reset));
    if (Array.isArray(payload)) {
      this.tableData = payload;                       // contract 1: a row per game
    } else {
      // Contract 2 wraps the list so the collection it belongs to travels with it.
      this.tableData = payload.entries || [];
      this.collection = payload.collection || "";
    }
    this.#attachCachedVPinPlayRatings();
    if (this.isController()) {
      const maxIndex = Math.max(0, this.tableData.length - 1);
      if (this._currentTableIndex > maxIndex) this._currentTableIndex = maxIndex;
      if (this.tableData.length > 0) {
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
  // TableIndexUpdate (inc self) drives the theme through the same path its own
  // input uses, so no theme changes are needed to honor the restored position.
  async #restoreInitialGame() {
    try {
      const index = await this.call("get_initial_table_index");
      if (typeof index === "number" && index > 0 && index < this.tableData.length) {
        // Captured before moveTo assigns it, or `previous` reports the index we are
        // moving to. This used to assign _currentTableIndex here for the same reason
        // moveTo does it now.
        const previous = this._currentTableIndex;
        // Themes register window.receiveEvent at varying points in their startup
        // (some only after a couple of awaits inside vpin.ready.then). Wait for it
        // so the restore broadcast isn't dropped by the guard in #connectWebSocket.
        await this.#waitForReceiveEvent();
        this.moveTo(index, { previous, reason: "restore" });
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
    // A data change raised by the backend carries no index - the wheel position only
    // exists in the browser, and a theme assigns message.index straight to its wheel.
    // The game under the wheel is held rather than the number, because the refresh can
    // reorder: a finished session moves a game up a LastRun wheel, and a Manager UI edit
    // can filter it out of the list entirely.
    const raised = message && typeof message === "object"
      && typeof message.index !== "number"
      && canonicalMessageType(message.type) === "TableDataChange";
    const held = raised ? this.#identityAt(this._currentTableIndex) : null;
    // Set now as well as after the refresh, so the message carries a usable index even
    // if the held game is gone. `raw` is the object the theme itself will read: the
    // alias copy below is core's, and writing only to that would leave a theme matching
    // on the 2.x spelling with the index this had before the refresh.
    const raw = message;
    if (raised) message.index = this._currentTableIndex;
    // A theme may post the pre-3.0 spelling; normalize before anything matches on it.
    if (message && MESSAGE_TYPE_CANONICAL[message.type]) {
      message = { ...message, type: canonicalMessageType(message.type) };
    }
    if (typeof message.index === "number") this._currentTableIndex = message.index;
    if (message.type === "AudioMuteChanged") {
      this.setAudioMuted(!!message.muted);
      return;
    }
    if (message.type === "LifecycleActing") {
      this.#showLifecycleNotice(message);
      // Still offered to the theme below: a theme may want to say it in its own voice,
      // and core's notice is what happens when none does.
    }
    this.#handleFrontendInputLifecycleEvent(message);

    // Default handling for TableDataChange
    if (message.type === "TableDataChange") {
      if (this.isController()) this._lastSelectedIndex = null;
      await this.#handleTableDataChange(message);
      if (raised) {
        const index = this.#indexOfIdentity(held);
        this._currentTableIndex = index;
        raw.index = message.index = index;
      }
    }
    this.#syncSelectionFromMessage(message);
    this.#applyLaunchDim(message.type);
    if (VPinFECore.SELECTION_MESSAGES.has(message.type)) this.#renderWindowMedia();
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
    const known = { bg: "BG", dmd: "DMD", scoreview: "ScoreView" };
    if (known[windowName]) return known[windowName];
    if (!windowName || windowName === "unknown") return "Window";
    return windowName.charAt(0).toUpperCase() + windowName.slice(1);
  }


  // Default handler for TableDataChange events
  // The three overlays differ in four things: which flag says they are up, which iframe
  // they own, what they load, and what they are told when opened. Everything else - the
  // fade class, creating the frame once, the ten-millisecond wait so it does not flash,
  // hiding rather than destroying - was written out three times and drifted.
  static OVERLAYS = {
    menu: {
      frameId: "menu-frame",
      src: "/core/mainmenu/mainmenu.html",
      // table_index is mainmenu.js's own key, not ours to rename.
      opened: (core) => ({ event: "menu_open", table_index: core._currentTableIndex }),
    },
    collectionMenu: {
      frameId: "collection-menu-frame",
      src: "/core/collectionmenu/collectionmenu.html",
    },
    tutorial: {
      frameId: "tutorial-frame",
      src: "/core/tutorial/tutorial.html",
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

    if (this.overlay === name) {
      this.overlay = null;
      overlayRoot.classList.remove("active");          // fade out
      if (iframe) {
        iframe.style.display = "none";                 // hide, never destroy
        if (iframe.contentWindow) {
          iframe.contentWindow.postMessage({ event: "overlay_close", overlay: name }, "*");
          // What the three pages we ship have always matched on. PAR-24's shape: the
          // current spelling first, the older one behind it.
          iframe.contentWindow.postMessage({ event: "reset state" }, "*");
        }
      }
      return;
    }

    const context = spec.prepare ? spec.prepare(this) : undefined;
    if (spec.prepare && context === null) return;

    if (this.overlay) await this.#toggleOverlay(this.overlay);

    this.overlay = name;
    overlayRoot.classList.add("active");               // fade in
    if (!iframe) {
      iframe = document.createElement("iframe");
      iframe.src = spec.src;
      iframe.id = spec.frameId;
      iframe.className = "vpinfe-overlay-frame";
      iframe.setAttribute("allowTransparency", "true");
      iframe.style.display = "none";                   // start hidden to prevent a flash
      overlayRoot.appendChild(iframe);
      await new Promise(resolve => setTimeout(resolve, 10));   // let the DOM catch up
      this.#listenForKeysIn(iframe);
    }

    iframe.style.display = "block";
    if (!iframe.contentWindow) return;
    iframe.contentWindow.postMessage({ event: "overlay_open", overlay: name, context }, "*");
    const legacy = spec.opened && spec.opened(this, context);
    if (legacy) iframe.contentWindow.postMessage(legacy, "*");
  }

  /**
   * Start, stop or restart the frontend, VPinFE or the machine.
   *
   * Scope is "frontend", "app" or "system"; action is "start", "stop" or "restart".
   * Confirms first when the user asked to be asked, and resolves false when they say no
   * or the build cannot do it, so a caller can leave its menu open.
   */
  async requestLifecycle(scope, action, reason = "") {
    if (!await this.#confirmLifecycle(scope, action)) return false;
    return await this.call("lifecycle_request", scope, action, reason, true);
  }

  /**
   * Ask before starting, stopping or restarting something, if the user asked to be asked.
   *
   * A theme that draws its own is welcome to: it calls lifecycle_request with
   * confirmed:true and never reaches this. This is the fallback, so turning the setting
   * on works on every theme, including the ones written before it existed.
   *
   * Built from the input actions rather than window.confirm, because a cabinet has no
   * keyboard and no mouse - select confirms and back cancels, on the buttons already
   * bound to them.
   */
  async #confirmLifecycle(scope, action) {
    const asking = await this.call("lifecycle_needs_confirmation", scope, action);
    if (!asking || !asking.confirm) return true;

    // Built node by node rather than from innerHTML: the description is wording from
    // the bridge, and textContent cannot become markup.
    const root = document.createElement("div");
    root.className = "vpinfe-confirm";
    const card = document.createElement("div");
    card.className = "vpinfe-confirm-card";
    const question = document.createElement("p");
    question.className = "vpinfe-confirm-question";
    question.textContent = `${asking.description}?`;
    const hint = document.createElement("p");
    hint.className = "vpinfe-confirm-hint";
    hint.textContent = "Select to confirm, Back to cancel";
    card.appendChild(question);
    card.appendChild(hint);
    root.appendChild(card);
    document.body.appendChild(root);

    const releaseMode = this.pushInputMode("modal");
    try {
      return await new Promise(resolve => { this.#pendingConfirm = resolve; });
    } finally {
      this.#pendingConfirm = null;
      releaseMode?.();
      root.remove();
    }
  }

  /**
   * Say what is about to happen, on a window that did not ask for it.
   *
   * A notice, never a question: this window has no say, and the surface that asked has
   * already had one. It is not dismissible and does not take the input, because there
   * is nothing to answer and the app is usually about to go away underneath it.
   */
  #showLifecycleNotice(message) {
    const existing = this.#lifecycleNotice;
    if (existing) existing.remove();

    const root = document.createElement("div");
    root.className = "vpinfe-notice";
    const text = document.createElement("p");
    text.className = "vpinfe-notice-text";
    text.textContent = message.description || "";
    root.appendChild(text);
    document.body.appendChild(root);
    this.#lifecycleNotice = root;
  }


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
      await this.callInternal("apply_filters",
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
        await this.callInternal("apply_sort", message.sort, message.order);
      }
      await this.getTableData();
    } else if (message.sort) {
      // Sort order change - apply it to this window's API instance
      await this.callInternal("apply_sort", message.sort, message.order);
      await this.getTableData();
    } else {
      // No filters specified - just refresh the game data
      await this.getTableData();
    }
  }

  async #handleCoreAudioEvent(message) {
    if (!this.enabled("core_audio") || !this.isController()) return;

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

  #resolveAudioUrl(indexOrUrl) {
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

  // Which messages mean "the wheel is now on something else". TableIndexUpdate is an
  // ordinary step; the other two mean the list or the game underneath may have changed,
  // so the notify has to fire again even when the index did not move.
  // The longest we wait between reconnect attempts. A cabinet can sleep for hours, so
  // there is no point trying every half second for all of it.
  static RECONNECT_CEILING_MS = 10000;

  static SELECTION_MESSAGES = new Set([
    "TableIndexUpdate", "TableDataChange", "TableLaunchComplete", "RemoteLaunchComplete",
  ]);

  // How many preloaded URLs to remember. Generous enough to cover a page of the wheel
  // in both directions; small enough that forgetting all of them costs one page.
  static PRELOAD_MEMORY = 300;

  #syncSelectionFromMessage(message) {
    if (!message || typeof message !== "object") return;
    if (!this.isController()) return;
    if (!VPinFECore.SELECTION_MESSAGES.has(message.type)) return;
    if (message.type !== "TableIndexUpdate") this._lastSelectedIndex = null;
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
    this.#renderWindowMedia();
    for (const listener of this._onSelection) {
      // One listener throwing must not stop the others, the same rule the backend's
      // event bus follows.
      try {
        listener(this._currentTableIndex);
      } catch (err) {
        console.warn("vpinfe: a selection listener failed", err);
      }
    }
  }

  /**
   * Step this window aside while VPX has the screens.
   *
   * Set on the document element rather than the body, so it is there before a theme's
   * own stylesheet loads and a theme can key off it without guessing a class name.
   * TableLaunchComplete clears it - the same message that already tells every window the
   * game came back.
   */
  #applyLaunchDim(type) {
    if (!this.enabled("core_launch_dim")) return;
    const root = document.documentElement;
    if (!root) return;
    // dataset, like every other data-vpinfe-* this file sets.
    if (type === "TableLaunching") root.dataset.vpinfeLaunching = "true";
    else if (type === "TableLaunchComplete") delete root.dataset.vpinfeLaunching;
  }

  /**
   * Show this window the media named for it.
   *
   * Renders into the first `[data-vpin-media]` element on the page, so a theme opts in
   * with an attribute and opts out by leaving it off or setting `media_window.enabled`
   * false. Nothing is guessed: a window that is not a display, or a page with no target,
   * does nothing at all rather than picking somewhere to draw.
   */
  #renderWindowMedia() {
    if (!this.enabled("core_media_window")) return;
    const kind = this.windowMediaKind;
    if (!kind) return;
    const target = document.querySelector("[data-vpin-media]");
    if (!target) return;

    // Video first, then the still - the same order a theme would ask in, and the reason
    // the kinds are named in pairs.
    const index = this._currentTableIndex;
    const wanted = [`${kind}_video`, kind].find((name) => {
      if (!MEDIA_KINDS.includes(name)) return false;
      const media = this.getMedia(index, name);
      // `missing` still answers with the placeholder URL, so truthiness is not enough -
      // it would put the file-missing image on screen inside a <video>.
      return media.url && media.kind !== "missing";
    });
    if (!wanted) return target.replaceChildren();

    const isVideo = wanted.endsWith("_video");
    const node = document.createElement(isVideo ? "video" : "img");
    node.src = this.getMediaURL(index, wanted);
    node.alt = this.tableData[index]?.game?.name || "";
    if (isVideo) {
      Object.assign(node, { autoplay: true, loop: true, muted: true, playsInline: true });
    }
    target.replaceChildren(node);
  }

  // Neighbors only, and only once the wheel has stopped moving.
  #schedulePreload() {
    if (!this.enabled("core_preload")) return;
    clearTimeout(this._preloadTimer);
    this._preloadTimer = setTimeout(() => this.#preloadNeighbors(), this._preloadSettleMs);
  }

  #preloadNeighbors() {
    this._preloadTimer = null;
    const at = this._currentTableIndex;
    for (const index of [at - 1, at, at + 1]) {
      if (index < 0 || index >= this.tableData.length) continue;
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
    if (!Array.isArray(this.tableData) || this.tableData.length === 0) return;

    const index = Math.floor(this._currentTableIndex);
    if (!Number.isFinite(index) || index < 0 || index >= this.tableData.length) return;
    if (this._lastSelectedIndex === index) return;

    this._lastSelectedIndex = index;
    try {
      await this.call("notify_table_selected", index);
    } catch (e) {
      this._lastSelectedIndex = null;
      this.call("console_out", `notify_table_selected failed: ${e.message}`);
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
    if (!Array.isArray(this.tableData) || normalized < 0 || normalized >= this.tableData.length) return null;
    return this.tableData[normalized];
  }

  #vpsIdOf(item) {
    return item && typeof item === "object" ? this._reader.vpsId(item) : "";
  }

  /** What the wheel is standing on, in terms that survive the list being rebuilt. */
  #identityAt(index) {
    const item = this.#itemByIndex(index);
    return item && typeof item === "object" ? (this._reader.identity(item) || null) : null;
  }

  /**
   * Where a held game sits now, or the index we already had.
   *
   * A game can leave the list - an edit filters it out, a collection drops it - and
   * there is no good answer for where the player then is. Staying put is the least
   * surprising of the bad answers, and the clamp in getTableData keeps it in range.
   */
  #indexOfIdentity(held) {
    if (!held || !Array.isArray(this.tableData)) return this._currentTableIndex;
    const found = this.tableData.findIndex(item =>
      item && typeof item === "object" && this._reader.identity(item) === held);
    return found >= 0 ? found : this._currentTableIndex;
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
    if (!Array.isArray(this.tableData)) return;
    this.tableData.forEach((item) => {
      if (this.#vpsIdOf(item) === vpsId) {
        this.#setGameVPinPlayRating(item, payload);
      }
    });
  }

  #attachCachedVPinPlayRatings() {
    if (!Array.isArray(this.tableData)) return;
    this.tableData.forEach((item) => {
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

  #audioResumePlay() {
    if (this._audioMuted) return;
    const url = this._audioCurrentUrl;
    if (!url) return;
    this._audio.play().then(() => {
      if (this._audioCurrentUrl === url) this.#fadeAudio(0, this._audioMaxVolume);
    }).catch(() => {});
  }

  // **********************************************
  // private functions
  // **********************************************

  #connectWebSocket() {
    const wsUrl = `${this.endpoints.frontend_channel}?window=${this._windowName}`;
    console.log(`[WS] Connecting to ${wsUrl}`);
    this._ws = new WebSocket(wsUrl);

    this._ws.onopen = async () => {
      console.log("[WS] Connected to bridge");
      this._reconnectDelayMs = 0;
      await this.#onBridgeReady();
      // ready is a one-shot: a theme awaits it once at startup, and resolving an
      // already-resolved promise on every reconnect is a no-op rather than a second
      // startup.
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
        // Handle pushed events from Python. A theme's receiveEvent is expected to call
        // vpin.handleEvent itself, so calling both would handle the message twice.
        // With no theme script on the page there is nobody to call it - and a window
        // core draws by itself has no reason to carry one - so core pumps its own.
        if (typeof window.receiveEvent === 'function') {
          window.receiveEvent(data.message);
        } else {
          this.handleEvent(data.message);
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
      this.#scheduleReconnect();
    };

    this._ws.onerror = (err) => {
      console.error("[WS] WebSocket error:", err);
    };
  }

  /**
   * Come back after the bridge goes away.
   *
   * Without this a cabinet that sleeps wakes up dead: the sockets close with 1006, the
   * three windows stay on screen showing the last game, and nothing reconnects - so no
   * button reaches the backend and the frontend looks fine while doing nothing. The same
   * hole swallowed a backend restart under a running frontend.
   *
   * Backs off to a ceiling rather than hammering a bridge that may be gone for hours,
   * and reconnecting re-runs #onBridgeReady, so config, game data and this window's
   * media are all re-read rather than assumed to have survived.
   */
  #scheduleReconnect() {
    if (this._reconnectTimer || this._shuttingDown) return;
    this._reconnectDelayMs = Math.min((this._reconnectDelayMs || 500) * 2,
                                      VPinFECore.RECONNECT_CEILING_MS);
    const delay = this._reconnectDelayMs;
    console.log(`[WS] Reconnecting in ${delay}ms`);
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this.#connectWebSocket();
    }, delay);
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

    // Load network config. The url already carried these, so this now only corrects a
    // page opened without them - `endpoints` derives from the ports, so correcting one
    // corrects every url built from it.
    this.themeAssetsPort = await this.call("get_theme_assets_port");
    // Only this machine's. With a hub elsewhere its asset port came in the url and this
    // answer is about the wrong machine.
    if (!this.hubHost) this.hubAssetsPort = this.themeAssetsPort;
    try {
      const ownPort = await this.call("get_hub_port");
      // What this install serves on. It is the hub's port too, unless a hub elsewhere
      // said otherwise in the url - correcting that here would point the page back at
      // itself for the library.
      this.playerPort = ownPort;
      if (!this.hubHost) this.hubPort = ownPort;
    } catch (_e) {
      /* an older build cannot answer; the 8001 default already covers it */
    }
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
    this.layout = this.#resolveLayout(await this.call("get_cab_mode"));
    this.playfieldMediaRotation = await this.call("get_playfield_media_rotation");
    this.#publishLayout();
    await this.#loadMonitors();
    await this.getTableData();

    // Draw once now the games are here. Waiting for a selection message would leave a
    // display window blank on a fresh start: the controller only broadcasts a restore
    // when the remembered index is past the first game, so at index 0 nothing arrives
    // and nothing ever asked this window to paint.
    this.#renderWindowMedia();
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

    if (message.type === "TableLaunching" || message.type === "RemoteLaunching") {
      this._launchInputSuppressedByLifecycle = true;
      this.#setFrontendInputEnabled(false);
    } else if (message.type === "TableLaunchComplete" || message.type === "RemoteLaunchComplete") {
      this._launchInputSuppressedByLifecycle = false;
      this.#setFrontendInputEnabled(true);
    }
  }

  // True when core should consume a paging action itself: paging enabled, table
  // window, and no overlay up (overlays keep receiving the raw action).
  #shouldHandleCorePaging(action) {
    if (action !== "page_previous" && action !== "page_next") return false;
    if (!this.enabled("core_paging")) return false;
    if (!this.isController()) return false;
    if (this.overlay) return false;
    return true;
  }

  async #handleCorePaging(action) {
    // One page request in flight at a time; presses during the round trip are
    // dropped rather than queued against a stale index.
    if (this._pagingInFlight) return;
    this._pagingInFlight = true;
    try {
      const direction = action === "page_previous" ? "prev" : "next";
      const index = await this.call("get_page_index", this._currentTableIndex, direction);
      if (typeof index === "number" && index >= 0 && index !== this._currentTableIndex) {
        // Through moveTo like every other index path, so a page carries previous,
        // direction and reason rather than an index a theme cannot place.
        this.moveTo(index, {
          direction: direction === "prev" ? "previous" : "next",
          reason: "page",
        });
      }
    } catch (e) {
      this.call("console_out", `Core paging failed: ${e.message}`);
    } finally {
      this._pagingInFlight = false;
    }
  }

  async #triggerInputAction(action) {
    if (!this.frontendInputEnabled) return;

    let handlers, named = action;
    if (this.overlay) handlers = this.overlayHandlers[this.overlay] || [];
    else {
      handlers = this.inputHandlers;   // no menu is up: the theme's own handler
      // The theme's handler is the only one outside this repo, so it is the only one
      // that gets the name its contract published. Every `case "joyleft"` in the twelve
      // registry themes keeps matching; the overlays above take the current names.
      if (this.contract < 2) named = LEGACY_ACTION_NAMES[action] || action;
    }

    // Handlers are async and their result was dropped, so a theme that threw did it
    // in silence - and a theme guarding itself with an "is animating" flag never
    // cleared it, which is what left the wheel dead until a restart.
    for (const handler of handlers) {
      try {
        const result = handler(named);
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

  // Key events go to whichever document has focus, so once a touch or a click moves
  // focus into an overlay's iframe the window listener stops seeing them. Each overlay
  // used to carry its own hardcoded keyboard map for that case - three maps that only
  // ran sometimes, agreed with nothing, and could not be configured. Core listens on
  // the overlay's own window instead, so there is one dispatch and one set of bindings
  // wherever focus happens to be. Same origin, so this is allowed.
  #listenForKeysIn(iframe) {
    // Nothing here may throw: this runs while an overlay is opening, and the socket is
    // not necessarily up - so it cannot report a failure through the bridge either.
    try {
      const frameWindow = iframe && iframe.contentWindow;
      if (!frameWindow || typeof frameWindow.addEventListener !== "function") return;
      frameWindow.addEventListener("keydown", (e) => this.#onKeyDown(e));
    } catch {
      // Cross-origin, or a frame that went away while opening. The parent window's
      // listener still covers every case except focus being inside the frame.
    }
  }

  // ── Input modes ───────────────────────────────────────────────────────────
  // What a keypress means depends on what is on screen. There was no such notion, so
  // each overlay hand-rolled its own flag - and the collection menu's save dialog had
  // none at all, which is why arrows drove the menu behind it and Enter opened a
  // dropdown instead of saving.
  //
  //   navigation  the default; actions reach the theme or the top overlay
  //   modal       a dialog owns them; select activates, back dismisses
  //   text        keystrokes belong to the focused field; only back is intercepted
  pushInputMode(mode) {
    if (!["navigation", "modal", "text"].includes(mode)) return null;
    this._inputModes.push(mode);
    return () => this.popInputMode(mode);
  }

  popInputMode(mode) {
    const at = this._inputModes.lastIndexOf(mode);
    if (at > 0) this._inputModes.splice(at, 1);   // never pop the base mode
  }

  get inputMode() {
    return this._inputModes[this._inputModes.length - 1];
  }

  // Move the selection, wrap it, and tell everyone where it went. Every theme wrote
  // this, and two of the installed three broadcast an undefined index doing it.
  moveBy(delta) {
    const count = this.tableData.length;
    if (!count) return this._currentTableIndex;
    const previous = this._currentTableIndex;
    const next = ((previous + delta) % count + count) % count;   // wraps both ways
    return this.moveTo(next, { previous, direction: delta < 0 ? "previous" : "next" });
  }

  /**
   * Move the selection to `index` and announce it. Every index path goes through here,
   * so a theme is told the same things however the cursor moved.
   *
   * `reason` is how far and why - `step`, `page`, `restore`, and `jump` when a letter
   * jump lands. `source` is who: `user`, or `attract` once core advances on a timer.
   * Two fields rather than one because they are independent - a random attract advance
   * is a jump *and* not a person, and one enum cannot say both.
   */
  moveTo(index, { previous = this._currentTableIndex, direction = "",
                  reason = "step", source = "user" } = {}) {
    const count = this.tableData.length;
    if (!count) return this._currentTableIndex;
    const at = Math.max(0, Math.min(count - 1, Number(index) || 0));
    this._currentTableIndex = at;
    this.sendMessageToAllWindowsIncSelf({
      type: "TableIndexUpdate", index: at, previous, direction, reason, source,
      // True while the wheel is still settling - what a theme needs to decide whether
      // to load full art or wait. INPUT-PERFORMANCE's fast-scroll signal is this flag.
      // It cannot serve as the jump signal: it is time-based, so one distant jump
      // reports false.
      moving: this.#stillMoving(),
    });
    this.#selectionChanged();
    return at;
  }

  #stillMoving() {
    const now = Date.now();
    const moving = (now - (this._lastMoveAt || 0)) < this.minRepeatIntervalMs * 2;
    this._lastMoveAt = now;
    return moving;
  }

  // Which overlay is up, or null. Every overlay is in OVERLAYS, so nothing new has to
  // be added here when one is.

  // A key typed into a text field is text, never an action. This matters most inside an
  // overlay, where core now listens: b, c, m, q and t are bound by default, so without
  // this the collection menu's save-filter box could not accept half the alphabet, and
  // Enter would fire select instead of reaching the field.
  #isTextEntry(target) {
    if (!target) return false;
    const tag = String(target.tagName || "").toLowerCase();
    if (tag === "textarea" || target.isContentEditable) return true;
    if (tag !== "input") return false;
    const type = String(target.type || "text").toLowerCase();
    return !["button", "checkbox", "radio", "range", "submit", "reset", "file", "color",
             "image"].includes(type);
  }

  // Keyboard input processing to handlers
  async #onKeyDown(e) {
    if (!this.frontendInputEnabled) return;
    if (!this.isController()) return;
    if (this.#isTextEntry(e.target)) return;

    const action = this.#actionForKeyboardEvent(e);
    if (!action) return;

    // Per action, not one timestamp for all of them. A repeating ArrowRight straight
    // after a repeating ArrowLeft is a different intent, and a shared clock ate it.
    if (e.repeat) {
      const now = Date.now();
      if (now - (this._lastRepeatAt[action] || 0) < this.minRepeatIntervalMs) return;
      this._lastRepeatAt[action] = now;
    }

    // A bound key belongs to us. Without this the arrows also scroll the theme's page
    // and Space activates whatever the browser thinks is focused.
    e.preventDefault();

    this.#dispatchAction(action);
  }

  // What an action does, whichever device produced it. One place, so the keyboard and
  // the gamepad cannot drift apart again.
  #dispatchAction(action) {
    if (!this.isController() && action !== "select") return this.#triggerInputAction(action);

    // A field owns its keystrokes; only back is intercepted, so a dialog can still be
    // dismissed from a cabinet button while typing into it.
    if (this.inputMode === "text" && action !== "back") return;
    // A confirm owns every action while it is up. Answering it is the only thing the
    // buttons can do, so an unmapped press cannot dismiss it and cannot act behind it.
    if (this.#pendingConfirm) {
      if (action === "select") this.#pendingConfirm(true);
      else if (action === "back" || action === "exit") this.#pendingConfirm(false);
      return;
    }
    // A dialog owns the actions while it is up: nothing reaches the menu behind it, and
    // nothing opens an overlay on top of it.
    if (this.inputMode === "modal" && !["select", "back", "previous", "next"].includes(action)) {
      return;
    }
    const overlay = this.overlay;
    if (action === "exit") {
      // Escape and q default to exit, and an overlay's own Escape handler never runs -
      // nothing focuses the iframe - so this used to quit VPinFE from inside a menu.
      // Closing the overlay is what every overlay's own map already meant by it.
      if (overlay) this.#toggleOverlay(overlay);
      else this.requestLifecycle("app", "stop");
    }
    else if (action === "menu") this.#toggleOverlay("menu");
    else if (action === "collection_menu") this.#toggleOverlay("collectionMenu");
    else if (action === "tutorial") this.#toggleOverlay("tutorial");
    else if (this.#shouldHandleCorePaging(action)) this.#handleCorePaging(action);
    else if (this.#shouldHandleCoreNavigation(action)) {
      this.moveBy(action === "previous" ? -1 : 1);
    }
    else this.#triggerInputAction(action);
  }

  // True when core should move the selection itself: navigation enabled, the table
  // window, and nothing on top that owns the actions.
  #shouldHandleCoreNavigation(action) {
    if (action !== "previous" && action !== "next") return false;
    if (!this.enabled("core_navigation")) return false;
    if (!this.isController()) return false;
    if (this.inputMode !== "navigation") return false;
    return !this.overlay;
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
   * The three layout answers, from the ini and this window's identity.
   *
   * `surface` is the shape you design for, and on the controller it is the *mounting*,
   * not the window: a portrait playfield reads portrait whether the OS turned the screen
   * (window already portrait, no rotation) or VPinFE turns the UI itself (window
   * landscape, rotated a quarter). Collapsing those two cabinet setups into one design
   * target is the point of this object.
   *
   * Other windows have no mounting declared, and nothing rotates them, so they measure.
   */
  #resolveLayout(cabMode) {
    const declared = String(this.playfieldOrientation || "").trim().toLowerCase();
    const orientation = (declared === "portrait" || declared === "landscape")
      ? declared
      : this.#unusable("playfieldorientation", this.playfieldOrientation, "landscape");

    const degrees = Number(this.playfieldRotation);
    const turned = Number.isFinite(degrees) ? ((degrees % 360) + 360) % 360 : NaN;
    // A quarter turn or nothing. Anything else would need a theme to guess which way to
    // round it, and every theme would guess differently.
    const uprightRotation = [0, 90, 180, 270].includes(turned)
      ? turned
      : this.#unusable("playfieldrotation", this.playfieldRotation, 0);

    return {
      cabinet: !!cabMode,
      uprightRotation: this.isController() ? uprightRotation : 0,
      surface: this.isController() ? orientation : this.#measuredSurface(),
    };
  }

  /**
   * Publish the layout to CSS, for themes that asked core to handle it.
   *
   * Attributes and custom properties rather than inline styles: the rules live in
   * vpinfe-style.css, which every theme already links, so a theme opts in with a class
   * and writes no JavaScript.
   */
  #publishLayout() {
    const root = document.documentElement;
    if (!root || !this.enabled("core_layout")) return;

    root.dataset.vpinfeSurface = this.layout.surface;
    root.dataset.vpinfeUpright = String(this.layout.uprightRotation);
    if (this.layout.cabinet) root.dataset.vpinfeCabinet = "true";
    root.style.setProperty("--vpinfe-upright-rotation", `${this.layout.uprightRotation}deg`);
  }

  /**
   * Turn one playfield media element to fit the surface, once it knows its own size.
   *
   * The art is measured rather than assumed. There is no reliable authoring convention -
   * a library may be landscape desktop captures, portrait FSS renders, or a mix - and the
   * image itself carries the answer, so nothing has to be declared. `playfieldmediarotation`
   * overrides it for what measurement cannot see, like art that is upside down.
   */
  applyPlayfieldMediaRotation(element) {
    if (!element || !this.enabled("core_layout")) return;

    const measure = () => {
      const wide = (element.naturalWidth || element.videoWidth || 0)
                 > (element.naturalHeight || element.videoHeight || 0);
      const fits = wide === (this.layout.surface === "landscape");
      // The setting arrives as a string, so it is coerced before it is compared.
      const stated = String(this.playfieldMediaRotation ?? "auto").trim().toLowerCase();
      const turn = stated === "auto" ? (fits ? 0 : 90) : Number(stated) || 0;
      element.dataset.vpinfeTurned = String(turn === 90 || turn === 270);
      element.style.setProperty("--vpinfe-playfield-media-rotation", `${turn}deg`);
    };

    if (element.naturalWidth || element.videoWidth) measure();
    else element.addEventListener("load", measure, { once: true });
    element.addEventListener("loadedmetadata", measure, { once: true });
  }

  /** The window's own shape. Read before any transform, so it is the untouched box. */
  #measuredSurface() {
    return window.innerHeight > window.innerWidth ? "portrait" : "landscape";
  }

  #unusable(key, value, fallback) {
    console.warn(`vpinfe: [Displays] ${key} is ${JSON.stringify(value)}, `
      + `which is not a value this build understands - using ${JSON.stringify(fallback)}.`);
    return fallback;
  }

  /**
   * This window's name - which page it loaded, and its media kind when it has one.
   *
   * Known before the socket opens. Every published theme asks the backend for it instead,
   * because until now there was nothing else to ask.
   */
  /**
   * The media kind this window shows, or null when it is not a display we hold art for.
   *
   * A media kind is named after the display it captures, so a window that is a display
   * finds its artwork under its own name. The mapping lives here rather than in every
   * theme: a contract 1 window is translated the same way its media names are, and a
   * window a theme invented resolves to null instead of a lookup that finds nothing.
   */
  get windowMediaKind() {
    const kind = this.#normalizeMediaType(this._windowName);
    return MEDIA_KINDS.includes(kind) ? kind : null;
  }

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
  // One call, one shape: every action and what is bound to it. The keyboard map and the
  // gamepad map used to arrive separately, with a table translating key* to joy* - which
  // existed only because a stored value could not name its own device.
  const bindings = await this.call("get_bindings") || {};
  const keys = {}, buttons = {};
  for (const [action, list] of Object.entries(bindings)) {
    for (const binding of list || []) {
      if (typeof binding !== "string") continue;
      if (binding.startsWith("key:")) {
        (keys[action] ||= []).push(binding.slice(4).trim().toLowerCase());
      } else if (binding.startsWith("pad:") && binding.includes("/button:")
                 && !binding.includes("@") && !binding.includes("chord(")) {
        // Richer selectors - chord, hold, axis - are stored and round-tripped, and
        // dispatching them is the binding grammar's phase, not this one.
        (buttons[binding.split("/button:").pop().trim()] ||= []).push(action);
      }
    }
  }
  if (Object.keys(keys).length) this.keyActionMap = keys;
  this.joyButtonMap = buttons;
}

 async #initGamepadMapping() {
  // Nothing to fetch: gamepad buttons arrive in the same binding list the keyboard
  // does, so joyButtonMap is already built by the time this runs.
}

async #onButtonPressed(buttonIndex, gamepadIndex) {
    if (!this.frontendInputEnabled) return;

    // Every action bound to this button. The branching is #dispatchAction's, shared with
    // the keyboard - it used to be written out twice, and the two had already drifted:
    // only the keyboard guarded exit while an overlay was up.
    for (const action of this.joyButtonMap[buttonIndex.toString()] || []) {
      this.#dispatchAction(action);
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
    const index = Math.floor(this._currentTableIndex);
    if (!Array.isArray(this.tableData) || index < 0 || index >= this.tableData.length) {
      return "";
    }

    const item = this.tableData[index];
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


  // Subscribe to play state on the manager UI's event stream
  #watchPlayState() {
    // Don't subscribe from a file:// origin - CORS blocks it on Chromium/QWebEngine.
    // The theme page loads over http://, where this works.
    if (window.location.protocol === 'file:') return;

    const streamUrl = `${this.endpoints.player}/api/v1/events?events=play.state_changed`;
    console.log("[RemoteLaunch] Subscribing to:", streamUrl);

    const source = new EventSource(streamUrl);
    let reportedOffline = false;

    source.addEventListener("play.state_changed", (message) => {
      reportedOffline = false;
      const state = JSON.parse(message.data).state || {};

      // Our own launches arrive as TableLaunching over the bridge. Acting on them
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


// A window core draws needs no theme script, and this file only defines the class - a
// theme is what constructs core and opens its socket. So a page with no script would sit
// black forever waiting for someone to start it.
//
// Scoped to pages that asked: no `[data-vpin-media]`, no bootstrap. A theme builds its
// own `vpin` while its script runs, which is before this fires, so a page that has one is
// left alone and can never end up with two.
if (typeof document !== "undefined" && typeof window !== "undefined") {
  const bootstrapCoreOnlyWindow = () => {
    if (window.vpin || !document.querySelector("[data-vpin-media]")) return;
    window.vpin = new VPinFECore();
    window.vpin.init();
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrapCoreOnlyWindow);
  } else {
    bootstrapCoreOnlyWindow();
  }
}
