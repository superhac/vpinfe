// The browser surface vpinfe-core.js needs, and nothing more.
//
// The file touches five globals - window, document, WebSocket, fetch, navigator - so a
// stub is small enough to read in one sitting. Anything a test does not exercise throws
// rather than returning undefined, because a silent undefined is how a test passes while
// the real thing is broken.

function unimplemented(name) {
  return () => {
    throw new Error(`${name} is not stubbed; add it to tests/js/support/browser.js`);
  };
}

// Records what was sent so a test can assert on it, and answers calls with whatever the
// test queued up. No timers, no reconnect: the socket is a spy, not a simulation.
class FakeWebSocket {
  constructor(url) {
    this.url = url;
    this.sent = [];
    this.readyState = FakeWebSocket.OPEN;
    FakeWebSocket.instances.push(this);
  }

  send(raw) {
    this.sent.push(JSON.parse(raw));
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
  }

  // Deliver a message as the bridge would.
  receive(message) {
    if (this.onmessage) this.onmessage({ data: JSON.stringify(message) });
  }
}
FakeWebSocket.OPEN = 1;
FakeWebSocket.CLOSED = 3;
FakeWebSocket.instances = [];

// Records every src it was given. Preloading is judged by how many requests it makes,
// so the count is the assertion.
class FakeImage {
  constructor() {
    this.decoding = "";
    this._src = "";
  }
  set src(value) { this._src = value; FakeImage.requested.push(value); }
  get src() { return this._src; }
}
FakeImage.requested = [];

class FakeAudio {
  constructor() {
    this.loop = false;
    this.muted = false;
    this.volume = 1;
    this.src = "";
    this.paused = true;
  }
  play() { this.paused = false; return Promise.resolve(); }
  pause() { this.paused = true; }
  addEventListener() {}
  removeEventListener() {}
}

// `search` is what #detectWindowName reads first, so a test picks its window by URL the
// same way a real window does.
export function makeBrowser({ windowName = "table", search = null, pathname = "/",
                              innerWidth = 1920, innerHeight = 1080 } = {}) {
  const query = search === null ? `?window=${windowName}` : search;

  // Just enough DOM for the overlays: an element that can hold a class and children,
  // and iframes that record what they were posted. Not a browser - a place for the
  // overlay logic to leave evidence.
  function element(id = "") {
    const el = {
      id,
      src: "",
      style: {},
      children: [],
      classes: new Set(),
      posted: [],
      attributes: {},
      classList: {
        add: (name) => el.classes.add(name),
        remove: (name) => el.classes.delete(name),
        contains: (name) => el.classes.has(name),
      },
      setAttribute(name, value) { el.attributes[name] = value; },
      appendChild(child) { el.children.push(child); documentStub._byId[child.id] = child; },
      contentWindow: { postMessage: (message) => el.posted.push(message) },
    };
    return el;
  }

  const rootStub = {
    dataset: {},
    style: { _props: {}, setProperty(name, value) { rootStub.style._props[name] = value; } },
  };

  const documentStub = {
    documentElement: rootStub,
    title: "",
    addEventListener() {},
    removeEventListener() {},
    querySelector: unimplemented("document.querySelector"),
    readyState: "complete",
    _byId: { "overlay-root": element("overlay-root") },
    getElementById(id) { return documentStub._byId[id] || null; },
    createElement() { return element(); },
    body: { appendChild: unimplemented("document.body.appendChild") },
  };

  const windowStub = {
    name: "",
    // A real window has a size, and #resolveLayout measures it for any window the ini
    // does not describe. Left undefined, `h > w` is false and every test would read
    // "landscape" whether or not the code worked.
    innerWidth,
    innerHeight,
    location: { search: query, pathname, href: `http://127.0.0.1:8000${pathname}${query}` },
    addEventListener() {},
    removeEventListener() {},
    postMessage() {},
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: (id) => clearTimeout(id),
    requestAnimationFrame: (fn) => setTimeout(() => fn(Date.now()), 0),
  };

  FakeWebSocket.instances = [];
  FakeImage.requested = [];

  return {
    window: windowStub,
    document: documentStub,
    navigator: { getGamepads: () => [] },
    WebSocket: FakeWebSocket,
    Audio: FakeAudio,
    Image: FakeImage,
    fetch: unimplemented("fetch"),
    // The remote-launch stream. It only ever has listeners attached.
    EventSource: function EventSource() {
      return { addEventListener() {}, removeEventListener() {}, close() {} };
    },
    URLSearchParams,
    Promise,
    Map,
    Set,
    Date,
    Math,
    JSON,
    Object,
    Array,
    String,
    Number,
    Boolean,
    Error,
    setTimeout,
    clearTimeout,
    // A no-op rather than a real frame: the gamepad poll re-arms itself every frame, so
    // scheduling it for real would spin a test forever. Nothing here asserts on gamepads.
    requestAnimationFrame: () => 0,
    cancelAnimationFrame: () => {},
    setInterval,
    clearInterval,
    console,
  };
}

export { FakeWebSocket, FakeAudio, FakeImage };
