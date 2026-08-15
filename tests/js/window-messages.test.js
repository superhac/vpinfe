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

// The five message types, in the one spelling that exists. They named a row all along,
// and a row is a table, so the 3.0 Game* spellings were withdrawn along with the alias
// that carried them - see PAR-24.
const MESSAGES = ["TableIndexUpdate", "TableDataChange", "TableLaunching",
                  "TableRunning", "TableLaunchComplete"];

describe("every window message has exactly one spelling", () => {
  test("nothing is aliased, so nothing can arrive under a second name", () => {
    assert.deepEqual(Object.keys(ALIASES), [],
      "an entry here means a message is broadcast twice; the map is empty on purpose");
  });

  test("a message type normalizes to itself", () => {
    for (const name of MESSAGES) {
      assert.equal(canonical(name), name);
    }
  });

  test("an unrelated message type passes through untouched", () => {
    assert.equal(canonical("SomeThemeSpecificMessage"), "SomeThemeSpecificMessage");
  });
});

describe("the Python side broadcasts what the docs promise", () => {
  // The half that was missing once. Asserted against the source because the broadcast
  // crosses a socket this harness does not stand up. With no alias to fall back on, a
  // spelling that drifts here reaches a theme as silence rather than as a second copy.
  const LAUNCH_TRIO = ["TableLaunching", "TableRunning", "TableLaunchComplete"];

  test("play_events emits the spelling the JS side recognizes", () => {
    const events = readFileSync(
      path.join(REPO_ROOT, "frontend", "play_events.py"), "utf8");

    for (const name of LAUNCH_TRIO) {
      assert.ok(events.includes(name),
        `play_events.py does not emit ${name}, so a theme listening for it gets no `
        + "launch events");
    }
  });

  test("the theme doc names what the code emits", () => {
    const doc = readFileSync(path.join(REPO_ROOT, "docs", "theme.md"), "utf8");

    for (const name of MESSAGES) {
      assert.ok(doc.includes(name), `${name} is emitted but not documented`);
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
    vpin.call = (method) => Promise.resolve(method === "get_tables" ? payload : null);
    await vpin.getTableData();
    await vpin.handleEvent({ type: "TableIndexUpdate", index: at });

    payload = after;
    const message = index === undefined ? { type: spelling } : { type: spelling, index };
    await vpin.handleEvent(message);
    return { message, vpin };
  };

  test("TableDataChange follows its game when the refresh reorders", async () => {
    const { message, vpin } = await refreshWith(
      "TableDataChange", rows("Alpha", "Beta", "Gamma"), rows("Gamma", "Alpha", "Beta"),
      { at: 1 });

    assert.equal(message.index, 2, "Beta moved to the end, and the wheel went with it");
    assert.equal(vpin.getCurrentTableIndex(), 2);
  });

  test("TableDataChange with an index keeps the one it was sent", async () => {
    // A collection or filter change originates in the browser and knows its own index.
    const { message } = await refreshWith(
      "TableDataChange", rows("Alpha", "Beta"), rows("Alpha", "Beta"), { index: 1, at: 0 });

    assert.equal(message.index, 1);
  });

  test("a game that left the list leaves the wheel where it was", async () => {
    const { message } = await refreshWith(
      "TableDataChange", rows("Alpha", "Beta", "Gamma"), rows("Alpha", "Gamma"), { at: 1 });

    assert.equal(message.index, 1);
  });

  test("an unrelated message is left alone", async () => {
    const { vpin } = newCore({ windowName: "table" });
    vpin.call = () => Promise.resolve("[]");
    const message = { type: "TableLaunchComplete" };

    await vpin.handleEvent(message);

    assert.equal(message.index, undefined);
  });
});
