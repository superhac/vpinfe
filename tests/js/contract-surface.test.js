// One declaration, the whole surface.
//
// Before this, `contract` governed the payload and nothing else: the vpin.* aliases, the
// media kind spellings and the dual-spelling window messages were unconditional, so none
// of them could ever be retired - nothing signalled that a theme had stopped needing them
// (THEME.local.md P1). A theme already says what it was written against; now that answer
// selects everything.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { newCore } from "./support/load-core.js";

// What the bridge answers during init. Only the shapes that would otherwise throw - the
// rest of the sequence tolerates undefined on purpose.
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

// Drives the real path: init() opens the (stubbed) socket, and opening it runs the same
// bridge-ready sequence a browser would. Faking the switch instead would test the test.
async function coreAtContract(level, answers = {}) {
  const { vpin, browser } = newCore({ windowName: "table" });
  const sent = [];
  vpin.call = (method, ...args) => {
    sent.push([method, ...args]);
    if (method === "get_theme_contract") {
      if (level === "unsupported") return Promise.reject(new Error("Method not allowed"));
      return Promise.resolve(level);
    }
    if (method in answers) return Promise.resolve(answers[method]);
    return Promise.resolve(BRIDGE_DEFAULTS[method]);
  };
  vpin.init();
  await browser.WebSocket.instances.at(-1).onopen();
  return { vpin, sent };
}

describe("a theme declaring nothing keeps every 2.x name", () => {
  test("the contract is 1 before the bridge has answered", () => {
    const { vpin } = newCore();

    assert.equal(vpin.contract, 1,
      "a theme touching vpin.* before the bridge is up must still find its names");
    assert.notEqual(vpin.tableData, undefined);
  });

  test("contract 1 keeps the aliases after the bridge answers", async () => {
    const { vpin } = await coreAtContract(1);

    assert.equal(vpin.contract, 1);
    for (const oldName of ["tableData", "getTableMeta", "launchTable"]) {
      assert.notEqual(vpin[oldName], undefined, `${oldName} must still answer`);
    }
  });

  test("a build too old to answer is treated as contract 1", async () => {
    const { vpin } = await coreAtContract("unsupported");

    assert.equal(vpin.contract, 1);
    assert.notEqual(vpin.tableData, undefined,
      "an unknown method must not cost a theme its names");
  });

  test("legacy media kinds resolve", async () => {
    const { vpin } = await coreAtContract(1, { get_theme_assets_port: 8000 });
    vpin.gameData = [{ TableImagePath: "/lib/Game (M 1990)/medias/table.png" }];

    assert.notEqual(vpin.getImageURL(0, "table"), null);
  });
});

describe("a theme declaring contract 2 gets the current surface only", () => {
  test("the 2.x vpin.* names are gone, not merely discouraged", async () => {
    const { vpin } = await coreAtContract(2);

    assert.equal(vpin.contract, 2);
    for (const oldName of ["tableData", "getTableMeta", "launchTable", "getTableCount"]) {
      assert.equal(vpin[oldName], undefined,
        `${oldName} must not answer at contract 2, or a theme can work by accident`);
    }
  });

  test("the current names still answer", async () => {
    const { vpin } = await coreAtContract(2);

    assert.notEqual(vpin.gameData, undefined);
    assert.equal(typeof vpin.getGameMeta, "function");
  });

  test("a legacy media kind stops resolving", async () => {
    const { vpin } = await coreAtContract(2, { get_theme_assets_port: 8000 });
    vpin.gameData = [{ game: { id: "g1" }, table: { id: "t1" }, media: ["playfield"] }];

    assert.ok(vpin.getImageURL(0, "playfield").includes("/media/t1/playfield"),
      "the canonical kind resolves");
    // An unknown kind answers with the missing-media placeholder rather than null, which
    // is the same thing a theme sees for art it does not have.
    assert.equal(vpin.getImageURL(0, "table"), "/web/images/file_missing.png",
      "`table` is contract 1's spelling and is not honoured at 2");
  });

  test("the reader is chosen by declaration, not by sniffing the payload", async () => {
    // A contract-1 row handed to a contract-2 theme used to fall through to the old
    // reader because the shape was inspected. It does not now: the theme said 2, so 2
    // is what it gets, and a mismatched payload fails visibly instead of half-working.
    const { vpin } = await coreAtContract(2, { get_theme_assets_port: 8000 });
    vpin.gameData = [{ PlayfieldImagePath: "/lib/G (M 1990)/medias/table.png" }];

    assert.equal(vpin.getImageURL(0, "playfield"), "/web/images/file_missing.png");
  });

  test("window messages go out once, under the current name only", async () => {
    const { vpin, sent } = await coreAtContract(2);
    sent.length = 0;
    vpin.sendMessageToAllWindows({ type: "GameIndexUpdate", index: 3 });

    const broadcasts = sent.filter(([m]) => m === "send_event_all_windows");
    assert.equal(broadcasts.length, 1, "no duplicate under the 2.x spelling");
    assert.equal(broadcasts[0][1].type, "GameIndexUpdate");
  });

  test("contract 1 still gets both spellings", async () => {
    const { vpin, sent } = await coreAtContract(1);
    sent.length = 0;
    vpin.sendMessageToAllWindows({ type: "GameIndexUpdate", index: 3 });

    const types = sent.filter(([m]) => m === "send_event_all_windows").map(([, msg]) => msg.type);
    assert.deepEqual(types.sort(), ["GameIndexUpdate", "TableIndexUpdate"]);
  });
});

describe("what the contract is for", () => {
  test("a theme can read which surface it is being served", async () => {
    const { vpin } = await coreAtContract(2);

    assert.equal(vpin.contract, 2);
  });

  test("a contract newer than this build serves the newest it has", async () => {
    const { vpin } = await coreAtContract(99);

    assert.equal(vpin.contract, 2, "clamped, not obeyed");
  });
});

describe("theme.json turns capabilities on and off", () => {
  test("core audio is off unless the theme asks for it", async () => {
    const { vpin } = await coreAtContract(1);

    assert.equal(vpin.isCoreAudioEnabled(), false);
  });

  test("the declared key switches it on", async () => {
    const { vpin } = await coreAtContract(1, { get_theme_config: { use_core_audio: true } });

    assert.equal(vpin.isCoreAudioEnabled(), true);
  });

  test("a nested key works too", async () => {
    const { vpin } = await coreAtContract(1,
      { get_theme_config: { audio: { enabled: true } } });

    assert.equal(vpin.isCoreAudioEnabled(), true);
  });

  test("the camelCase spellings earlier builds accepted still work", async () => {
    const { vpin } = await coreAtContract(1, { get_theme_config: { useCoreAudio: true } });

    assert.equal(vpin.isCoreAudioEnabled(), true,
      "themes are using these; they stay until contract 1 goes");
  });
});

describe("the controller window comes from the theme's list", () => {
  test("a theme that declares nothing keeps table as the controller", async () => {
    const { vpin } = await coreAtContract(1);

    assert.deepEqual([...vpin.windows], ["table", "bg", "dmd"]);
    assert.equal(vpin.isController(), true, "?window=table is the controller");
  });

  test("a secondary window is not the controller", async () => {
    const { vpin, browser } = newCore({ windowName: "bg" });
    vpin.call = (method) => Promise.resolve(
      method === "get_theme_contract" ? 1
      : method === "get_games" ? "[]" : BRIDGE_DEFAULTS[method]);
    vpin.init();
    await browser.WebSocket.instances.at(-1).onopen();

    assert.equal(vpin.isController(), false);
  });

  test("at contract 2 the controller is the playfield window", async () => {
    const { vpin, browser } = newCore({ windowName: "playfield" });
    vpin.call = (method) => Promise.resolve(
      method === "get_theme_contract" ? 2
      : method === "get_theme_windows" ? ["playfield", "bg", "dmd"]
      : method === "get_games" ? JSON.stringify({ entries: [], count: 0 })
      : BRIDGE_DEFAULTS[method]);
    vpin.init();
    await browser.WebSocket.instances.at(-1).onopen();

    assert.equal(vpin.isController(), true);
  });

  test("a theme can declare a window VPinFE never had", async () => {
    const { vpin, browser } = newCore({ windowName: "topper" });
    vpin.call = (method) => Promise.resolve(
      method === "get_theme_contract" ? 2
      : method === "get_theme_windows" ? ["playfield", "bg", "dmd", "topper"]
      : method === "get_games" ? JSON.stringify({ entries: [], count: 0 })
      : BRIDGE_DEFAULTS[method]);
    vpin.init();
    await browser.WebSocket.instances.at(-1).onopen();

    assert.ok(vpin.windows.includes("topper"));
    assert.equal(vpin.isController(), false, "it is a display, not the controller");
    assert.equal(browser.document.title, "VPinFE Topper", "titled from its own name");
  });

  test("a build too old to report windows keeps the 2.x three", async () => {
    const { vpin, browser } = newCore();
    vpin.call = (method) => {
      if (method === "get_theme_windows") return Promise.reject(new Error("Method not allowed"));
      return Promise.resolve(method === "get_theme_contract" ? 1
                             : method === "get_games" ? "[]" : BRIDGE_DEFAULTS[method]);
    };
    vpin.init();
    await browser.WebSocket.instances.at(-1).onopen();

    assert.deepEqual([...vpin.windows], ["table", "bg", "dmd"]);
    assert.equal(vpin.isController(), true);
  });
});
