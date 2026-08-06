// A display window shows the media named for it, without the theme saying so.
//
// A media kind is named after the display it captures, so a window that is a display has
// exactly one obvious thing to show. Every theme wrote the same handful of lines to show
// it, and the Reference theme - written to demonstrate best practice - could not avoid
// them either. That is the signal a behavior belongs in core.
//
// The mapping is the part worth testing. A contract 1 window is called `bg` and its media
// is `backglass`; a window a theme invented is neither, and must resolve to nothing
// rather than to a lookup that quietly finds nothing.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { newCore, fixture } from "./support/load-core.js";

const ROWS = fixture("theme_payload.json").contract1;

const BRIDGE_DEFAULTS = {
  get_games: "[]",
  get_theme_assets_port: 8000,
  get_initial_game_index: 0,
  get_theme_config: {},
  get_keymapping: {},
  get_joymaping: {},
  get_mainmenu_config: {},
  get_monitors: [],
  get_collections: [],
};

/** A core on a named window, with a page that may or may not offer a render target. */
async function coreOn(windowName, { target = true, themeConfig = {} } = {}) {
  const { vpin, browser } = newCore({ windowName });
  vpin.call = (method) => Promise.resolve(
    method === "get_theme_config" ? themeConfig : BRIDGE_DEFAULTS[method]);
  vpin.init();
  await browser.WebSocket.instances.at(-1).onopen();

  const stage = { children: [], replaceChildren(...kids) { this.children = kids; } };
  if (target) browser.document._query["[data-vpin-media]"] = stage;

  vpin.gameData = ROWS;
  vpin.themeAssetsPort = 8000;
  return { vpin, stage, browser };
}

// The receive path, which is how a secondary window learns the wheel moved. It is not
// the controller, so the send path's selection hook never runs there.
const step = (vpin, index = 0) =>
  vpin.handleEvent({ type: "GameIndexUpdate", index });

describe("the media kind a window shows", () => {
  test("a contract 1 window resolves through its own spelling", async () => {
    const { vpin } = await coreOn("bg");
    assert.equal(vpin.windowMediaKind, "backglass");
  });

  test("a contract 2 window is already the kind", async () => {
    const { vpin } = await coreOn("backglass");
    assert.equal(vpin.windowMediaKind, "backglass");
  });

  test("a window a theme invented is not a media kind", async () => {
    const { vpin } = await coreOn("marquee");
    assert.equal(vpin.windowMediaKind, null);
  });

  test("the controller is not a display, so it renders nothing here", async () => {
    // `table` is contract 1's playfield, which IS a kind - so the guard that keeps core
    // off the controller cannot be the kind lookup. A controller opts out by having no
    // target element, which is what every controller page looks like.
    const { vpin, stage } = await coreOn("table", { target: false });
    step(vpin);
    assert.deepEqual(stage.children, []);
  });
});

describe("core rendering the window's media", () => {
  test("it draws into the element the page offers", async () => {
    const { vpin, stage } = await coreOn("backglass");
    step(vpin);
    assert.equal(stage.children.length, 1);
  });

  test("a page with no target is left alone", async () => {
    const { vpin, stage } = await coreOn("backglass", { target: false });
    step(vpin);
    assert.deepEqual(stage.children, []);
  });

  test("a theme can turn it off and keep the element", async () => {
    const { vpin, stage } = await coreOn("backglass",
      { themeConfig: { media_window: { enabled: false } } });
    step(vpin);
    assert.deepEqual(stage.children, []);
  });

  test("it is on without the theme asking", async () => {
    const { vpin } = await coreOn("backglass");
    assert.equal(vpin.enabled("core_media_window"), true);
  });

  test("it draws on startup, without waiting to be told the wheel moved", async () => {
    // The controller only broadcasts a restore when the remembered index is past the
    // first game. At index 0 nothing arrives, so a window that only drew on a selection
    // message stayed blank from launch - which is what the cabinet showed.
    const { vpin, browser } = newCore({ windowName: "backglass" });
    const stage = { children: [], replaceChildren(...kids) { this.children = kids; } };
    browser.document._query["[data-vpin-media]"] = stage;
    vpin.call = (method) => Promise.resolve(
      method === "get_games" ? JSON.stringify(ROWS) : BRIDGE_DEFAULTS[method]);

    vpin.init();
    await browser.WebSocket.instances.at(-1).onopen();

    assert.equal(stage.children.length, 1, "nothing moved the wheel, and it still drew");
  });

  test("a page with no theme script still receives events", async () => {
    // The default is only usable if a window core draws needs no script of its own, and
    // incoming events reach handleEvent through window.receiveEvent - which a page with
    // no theme.js does not define. Core pumps its own in that case.
    const { vpin, stage, browser } = await coreOn("backglass");
    const socket = vpin._ws;
    delete browser.window.receiveEvent;

    socket.onmessage({ data: JSON.stringify(
      { type: "event", message: { type: "GameIndexUpdate", index: 0 } }) });
    await new Promise((resolve) => setTimeout(resolve, 0));

    assert.equal(stage.children.length, 1, "no script on the page, and it still drew");
  });
});
