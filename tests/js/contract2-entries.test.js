// Reading contract 2: an entry list instead of a row array.
//
// Contract 2 wraps the list, an entry is a table with its game attached, and media is a
// set of kind names rather than a filesystem path per kind. Nothing published declares
// it, so this is the only thing exercising the shape at all.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { newCore, fixture } from "./support/load-core.js";

const PAYLOAD = fixture("theme_payload.json").contract2;

const BRIDGE_DEFAULTS = {
  get_theme_assets_port: 8000,
  get_initial_game_index: 0,
  get_theme_config: {},
  get_keymapping: {},
  get_joymaping: {},
  get_mainmenu_config: {},
  get_monitors: [],
  get_collections: [],
};

// The payload comes from the fixture Python captures, so this cannot drift from what the
// builder actually produces.
async function coreWithEntries(payload = PAYLOAD) {
  const { vpin, browser } = newCore({ windowName: "table" });
  vpin.call = (method) => {
    if (method === "get_theme_contract") return Promise.resolve(2);
    if (method === "get_games") return Promise.resolve(JSON.stringify(payload));
    return Promise.resolve(BRIDGE_DEFAULTS[method]);
  };
  vpin.init();
  await browser.WebSocket.instances.at(-1).onopen();
  return vpin;
}

describe("the envelope is unwrapped into a list", () => {
  test("entries is the array a theme iterates", async () => {
    const vpin = await coreWithEntries();

    assert.ok(Array.isArray(vpin.entries));
    assert.equal(vpin.entries.length, PAYLOAD.count);
    assert.equal(vpin.getGameCount(), PAYLOAD.count,
      "the ordinal helpers count entries, not games");
  });

  test("the view the list belongs to travels with it", async () => {
    const vpin = await coreWithEntries({ ...PAYLOAD, collection: "Friday Night",
                                         expanded: true });

    assert.equal(vpin.collection, "Friday Night");
    assert.equal(vpin.expanded, true);
  });

  test("contract 1's array still loads", async () => {
    const rows = fixture("theme_payload.json").contract1;
    const { vpin, browser } = newCore();
    vpin.call = (method) => {
      if (method === "get_theme_contract") return Promise.resolve(1);
      if (method === "get_games") return Promise.resolve(JSON.stringify(rows));
      return Promise.resolve(BRIDGE_DEFAULTS[method]);
    };
    vpin.init();
    await browser.WebSocket.instances.at(-1).onopen();

    assert.equal(vpin.gameData.length, rows.length);
  });
});

describe("an entry is a table with its game attached", () => {
  test("it carries both identities", async () => {
    const entry = (await coreWithEntries()).entries[0];

    assert.ok(entry.game.id, "the game it belongs to");
    assert.ok(entry.table.id, "the table it is");
    assert.ok(entry.table.filename);
  });

  test("it carries the play stats a theme would show", async () => {
    const entry = (await coreWithEntries()).entries[0];

    for (const field of ["rating", "favorite", "tags", "last_played",
                         "play_count", "play_time_seconds"]) {
      assert.ok(field in entry.game.user, `game.user.${field} is missing`);
    }
    assert.ok("play_count" in entry.table.user, "the table keeps its own counters");
  });
});

describe("media is named, and the URL follows from the name", () => {
  test("a kind the entry has resolves to the media route", async () => {
    const vpin = await coreWithEntries();
    const entry = vpin.entries[0];
    const kind = entry.media.find((name) => name === "wheel") || entry.media[0];

    const url = vpin.getImageURL(0, kind);

    assert.ok(url.includes(`/media/${entry.table.id}/${kind}`),
      `expected the media route, got ${url}`);
    assert.ok(!url.includes("/tables/"), "no filesystem path reaches a contract-2 theme");
  });

  test("a kind the entry lacks answers missing, not undefined", async () => {
    const vpin = await coreWithEntries();

    assert.equal(vpin.getMedia(0, "topper").kind, "missing");
  });

  test("image versus video is still the user's preference", async () => {
    const vpin = await coreWithEntries();
    const entry = vpin.entries[0];
    if (!entry.media.includes("playfield_video")) return;   // fixture has no video

    assert.equal(vpin.getMedia(0, "playfield").kind, "video", "video by default");

    vpin.mediaPriorities = { ...vpin.mediaPriorities, playfield: "image" };
    assert.equal(vpin.getMedia(0, "playfield").kind, "image");
  });

  test("nothing hands a contract-2 theme a path", async () => {
    const vpin = await coreWithEntries();

    assert.equal(vpin.getMedia(0, "wheel").path, null,
      "the payload names kinds; it does not locate files");
  });

  test("a folder no metadata build has touched still addresses its media", async () => {
    // No tables section yet, so no table id - but it has art and it is in the wheel.
    // The route takes the game id in that case rather than building /media//wheel.
    const vpin = await coreWithEntries();
    const index = vpin.entries.findIndex((e) => !e.table.id && e.media.length);
    if (index < 0) return;                       // fixture has no such game with media

    const url = vpin.getImageURL(index, vpin.entries[index].media[0]);

    assert.ok(!url.includes("/media//"), `an empty id would break the route: ${url}`);
  });

  test("the manufacturer logo comes off the game", async () => {
    const vpin = await coreWithEntries();
    // Null in the fixture - no logo pack is installed - but it must not throw or
    // reach for contract 1's key.
    assert.doesNotThrow(() => vpin.getManufacturerLogoURL(0));
  });
});

describe("selection is something you can follow", () => {
  test("a listener runs when the wheel moves", async () => {
    const vpin = await coreWithEntries();
    const seen = [];
    vpin.onSelection((index) => seen.push(index));

    vpin.sendMessageToAllWindows({ type: "GameIndexUpdate", index: 2 });

    assert.deepEqual(seen, [2], "the listener gets the index it moved to");
  });

  test("unsubscribing stops it", async () => {
    const vpin = await coreWithEntries();
    let calls = 0;
    const off = vpin.onSelection(() => { calls += 1; });

    vpin.sendMessageToAllWindows({ type: "GameIndexUpdate", index: 1 });
    off();
    vpin.sendMessageToAllWindows({ type: "GameIndexUpdate", index: 2 });

    assert.equal(calls, 1);
  });

  test("one listener throwing does not stop the others", async () => {
    const vpin = await coreWithEntries();
    let reached = false;
    vpin.onSelection(() => { throw new Error("bad listener"); });
    vpin.onSelection(() => { reached = true; });

    vpin.sendMessageToAllWindows({ type: "GameIndexUpdate", index: 1 });

    assert.ok(reached, "the rating fetch must not be lost to a theme's bad handler");
  });

  test("a message that is not a selection change does not fire it", async () => {
    const vpin = await coreWithEntries();
    let calls = 0;
    vpin.onSelection(() => { calls += 1; });

    vpin.sendMessageToAllWindows({ type: "SomeThemeMessage", index: 4 });

    assert.equal(calls, 0);
  });
});
