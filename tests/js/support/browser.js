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
export function makeBrowser({ windowName = "table", search = null } = {}) {
  const query = search === null ? `?window=${windowName}` : search;

  const documentStub = {
    title: "",
    addEventListener() {},
    removeEventListener() {},
    querySelector: unimplemented("document.querySelector"),
    getElementById: unimplemented("document.getElementById"),
    createElement: unimplemented("document.createElement"),
    readyState: "complete",
    body: { appendChild: unimplemented("document.body.appendChild") },
  };

  const windowStub = {
    name: "",
    location: { search: query, pathname: "/", href: `http://127.0.0.1:8000/${query}` },
    addEventListener() {},
    removeEventListener() {},
    postMessage() {},
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: (id) => clearTimeout(id),
    requestAnimationFrame: (fn) => setTimeout(() => fn(Date.now()), 0),
  };

  FakeWebSocket.instances = [];

  return {
    window: windowStub,
    document: documentStub,
    navigator: { getGamepads: () => [] },
    WebSocket: FakeWebSocket,
    Audio: FakeAudio,
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

export { FakeWebSocket, FakeAudio };
