// Window message types, which shipped half-written once already.
//
// `92dfaa7` and `eaf6662` taught vpinfe-core.js to broadcast both spellings and the
// Python half was never written, so docs/theme.md told themes to listen for names the
// backend did not emit. It reached the cabinet looking healthy because installed themes
// used the 2.x spellings. PAR-24.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";

import { loadCore, newCore, REPO_ROOT } from "./support/load-core.js";

const { context } = loadCore();
const ALIASES = context.MESSAGE_TYPE_ALIASES;
const canonical = context.canonicalMessageType;

describe("both spellings of every window message are carried", () => {
  test("every current name maps to its 2.x spelling", () => {
    assert.ok(Object.keys(ALIASES).length >= 5, "PAR-24 lists five message types");

    for (const [current, legacy] of Object.entries(ALIASES)) {
      assert.notEqual(current, legacy);
      assert.match(legacy, /^Table/,
        `${legacy} should be the pre-3.0 spelling of ${current}`);
    }
  });

  test("an inbound legacy name normalizes to the current one", () => {
    for (const [current, legacy] of Object.entries(ALIASES)) {
      assert.equal(canonical(legacy), current,
        `a theme posting ${legacy} must still be understood`);
    }
  });

  test("a current name normalizes to itself", () => {
    for (const current of Object.keys(ALIASES)) {
      assert.equal(canonical(current), current);
    }
  });

  test("an unrelated message type passes through untouched", () => {
    assert.equal(canonical("SomeThemeSpecificMessage"), "SomeThemeSpecificMessage");
  });
});

describe("the Python side broadcasts what the docs promise", () => {
  // The half that was missing. Asserted against the source because the broadcast crosses
  // a socket this harness does not stand up.
  const LAUNCH_TRIO = /^(Game|Table)(Launching|Running|LaunchComplete)$/;

  test("play_events emits a spelling the JS side recognizes", () => {
    const events = readFileSync(
      path.join(REPO_ROOT, "frontend", "play_events.py"), "utf8");

    const launchPairs = Object.entries(ALIASES)
      .filter(([current]) => LAUNCH_TRIO.test(current));
    assert.ok(launchPairs.length === 3, "the launch trio should be three messages");

    for (const [current, legacy] of launchPairs) {
      assert.ok(events.includes(current) || events.includes(legacy),
        `play_events.py emits neither ${current} nor ${legacy}, so a theme listening `
        + "for either gets no launch events");
    }
  });
});

describe("a data change the backend raised carries the wheel position", () => {
  // The backend has no index to send - the wheel lives in the browser. Every shipped
  // theme assigns message.index to its wheel on this message, so an undefined there
  // sends the player back to nowhere the moment a finished game refreshes the payload.
  //
  // And the number alone is not enough. The refresh re-derives order and membership, so
  // a session that just ended moves its game up a LastRun wheel: what has to survive is
  // the game the player was standing on, not the slot it happened to be in.
  const rows = (...names) => JSON.stringify(names.map(name => ({ gameDirName: name })));

  /** A core holding `before`, handed `after` by the refresh this message triggers. */
  const refreshWith = async (spelling, before, after, { index, at = 0 } = {}) => {
    const { vpin } = newCore({ windowName: "table" });
    let payload = before;
    vpin.call = (method) => Promise.resolve(method === "get_games" ? payload : null);
    await vpin.getGameData();
    await vpin.handleEvent({ type: "GameIndexUpdate", index: at });

    payload = after;
    const message = index === undefined ? { type: spelling } : { type: spelling, index };
    await vpin.handleEvent(message);
    return { message, vpin };
  };

  for (const spelling of ["GameDataChange", "TableDataChange"]) {
    test(`${spelling} follows its game when the refresh reorders`, async () => {
      const { message, vpin } = await refreshWith(
        spelling, rows("Alpha", "Beta", "Gamma"), rows("Gamma", "Alpha", "Beta"), { at: 1 });

      assert.equal(message.index, 2, "Beta moved to the end, and the wheel went with it");
      assert.equal(vpin.getCurrentGameIndex(), 2);
    });

    test(`${spelling} with an index keeps the one it was sent`, async () => {
      // A collection or filter change originates in the browser and knows its own index.
      const { message } = await refreshWith(
        spelling, rows("Alpha", "Beta"), rows("Alpha", "Beta"), { index: 1, at: 0 });

      assert.equal(message.index, 1);
    });
  }

  test("a game that left the list leaves the wheel where it was", async () => {
    const { message } = await refreshWith(
      "GameDataChange", rows("Alpha", "Beta", "Gamma"), rows("Alpha", "Gamma"), { at: 1 });

    assert.equal(message.index, 1);
  });

  test("an unrelated message is left alone", async () => {
    const { vpin } = newCore({ windowName: "table" });
    vpin.call = () => Promise.resolve("[]");
    const message = { type: "GameLaunchComplete" };

    await vpin.handleEvent(message);

    assert.equal(message.index, undefined);
  });
});
