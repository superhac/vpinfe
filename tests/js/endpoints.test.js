// Where the page thinks the services are.
//
// Six places hardcoded 127.0.0.1 and read a port off the core, so "which machine answers
// this" was asserted six times and a seventh was easy to add. The block answers it once,
// keyed by role - hub and player, not by transport, because the window channel is one
// transport serving both and a transport-keyed block cannot express the split.
//
// Ports arrive in the url because the page cannot ask for them: asking needs the bridge,
// and finding the bridge needs a port.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { newCore, fixture } from "./support/load-core.js";

const ROWS = fixture("theme_payload.json").contract1;

const withPorts = (search) => newCore({ windowName: "table", search }).vpin;

describe("the endpoint block", () => {
  test("is resolved from the url before any theme code runs", () => {
    const vpin = withPorts("?window=table&wsPort=9002&themeAssetsPort=9000&managerUiPort=9001");

    assert.equal(vpin.endpoints.hub, "http://127.0.0.1:9000");
    assert.equal(vpin.endpoints.player, "http://127.0.0.1:9001");
    assert.equal(vpin.endpoints.bridge, "ws://127.0.0.1:9002");
  });

  test("falls back to what the frontend has always assumed", () => {
    // A page opened by hand, or an older launcher that sends no ports.
    const vpin = withPorts("?window=table");

    assert.equal(vpin.endpoints.hub, "http://127.0.0.1:8000");
    assert.equal(vpin.endpoints.player, "http://127.0.0.1:8001");
    assert.equal(vpin.endpoints.bridge, "ws://127.0.0.1:8002");
  });

  test("a port given in the url wins over the assumed one", () => {
    const vpin = withPorts("?window=table&themeAssetsPort=9000");

    assert.equal(vpin.endpoints.hub, "http://127.0.0.1:9000");
    assert.equal(vpin.endpoints.player, "http://127.0.0.1:8001", "the rest are untouched");
  });

  test("correcting a port after startup corrects the urls built from it", () => {
    // The bridge answers get_theme_assets_port during init and may correct a page that
    // opened without one. Resolved once at construction, that correction would land on
    // the port and never reach the urls, which fails silently on the default port.
    const vpin = withPorts("?window=table");

    vpin.themeAssetsPort = 9000;

    assert.equal(vpin.endpoints.hub, "http://127.0.0.1:9000");
  });
});

describe("every url the page builds comes from the block", () => {
  test("game media resolves against the hub", () => {
    const vpin = withPorts("?window=table&themeAssetsPort=9000");
    vpin.gameData = ROWS;
    const index = ROWS.findIndex((row) => row.tableDirName === "Attack from Mars (Bally 1995)");

    const url = vpin.getImageURL(index, "wheel");

    assert.ok(url.startsWith("http://127.0.0.1:9000/"), url);
  });

  test("the manufacturer logo resolves against the hub", () => {
    const vpin = withPorts("?window=table&themeAssetsPort=9000");
    vpin.gameData = [{}];
    vpin._reader = { logo: () => "/assets/manufacturers/default/bally.png" };

    assert.equal(vpin.getManufacturerLogoURL(0),
                 "http://127.0.0.1:9000/assets/manufacturers/default/bally.png");
  });

  test("the window channel is dialled at the bridge endpoint", () => {
    const { vpin, browser } = newCore({
      windowName: "table", search: "?window=table&wsPort=9002",
    });

    vpin.init();

    assert.equal(browser.WebSocket.instances.at(-1).url,
                 "ws://127.0.0.1:9002?window=table");
  });
});
