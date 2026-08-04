// The 2.x names a published theme still calls, and the window identity it reads.
//
// Every one of these is a compatibility shim with no expiry: nothing declares that a
// theme has stopped needing them (THEME.local.md P1). Until a contract governs the whole
// surface, these assertions are what stops one being dropped by accident.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { newCore } from "./support/load-core.js";

describe("the vpin.* names 2.x themes read still answer", () => {
  // PAR-23. The payload behind each is identical; only the spelling moved.
  const RENAMED = [
    ["tableData", "gameData"],
    ["tableRotation", "playfieldRotation"],
    ["tableOrientation", "playfieldOrientation"],
    ["getTableMeta", "getGameMeta"],
    ["getTableData", "getGameData"],
    ["getTableCount", "getGameCount"],
    ["getCurrentTableIndex", "getCurrentGameIndex"],
    ["playTableAudio", "playGameAudio"],
    ["stopTableAudio", "stopGameAudio"],
    ["launchTable", "launchGame"],
  ];

  for (const [oldName, newName] of RENAMED) {
    test(`vpin.${oldName} reaches ${newName}`, () => {
      const { vpin } = newCore();

      assert.notEqual(vpin[oldName], undefined,
        `${oldName} is a published name; dropping it breaks every 2.x theme`);
      if (typeof vpin[newName] === "function") {
        assert.equal(typeof vpin[oldName], "function");
      }
    });
  }

  test("a legacy read returns the current value, not a stale copy", () => {
    const { vpin } = newCore();
    vpin.gameData = [{ tableDirName: "example" }];

    assert.deepEqual(vpin.tableData, vpin.gameData);
  });

  test("a legacy write lands on the current member", () => {
    const { vpin } = newCore();
    vpin.tableData = [{ tableDirName: "written through the old name" }];

    assert.equal(vpin.gameData[0].tableDirName, "written through the old name");
  });

  test("getAllTables/getAllGames is a phantom - neither name has ever existed", () => {
    // Left deliberately failing-if-fixed rather than deleted, because three places
    // claim otherwise: the rename map lists it, docs/theme.md documents
    // vpin.getAllGames(), and PAR-23 says every old name still works. Nothing on
    // master defines getAllTables either, so this is a stale claim rather than a
    // regression - but a theme following the docs gets a TypeError.
    const { vpin } = newCore();

    assert.equal(typeof vpin.getAllGames, "undefined",
      "if getAllGames now exists, drop this test and the phantom note with it");
    assert.equal(vpin.getAllTables, undefined,
      "the alias forwards to a method that does not exist");
  });

  test("using a legacy name is reported, so the log can answer who still needs it", () => {
    const { vpin } = newCore();
    const reported = [];
    vpin.call = (method, ...args) => { reported.push([method, ...args]); return Promise.resolve(); };

    void vpin.tableData;

    assert.ok(reported.some(([method]) => method === "report_deprecated_use"),
      "a shim nobody can observe is a shim nobody can ever retire");
  });
});

describe("window identity", () => {
  for (const [name, title] of [["table", "VPinFE Table"], ["bg", "VPinFE BG"],
                               ["dmd", "VPinFE DMD"]]) {
    test(`?window=${name} is detected and titles the window`, () => {
      const { vpin, browser } = newCore({ windowName: name });

      assert.equal(vpin._windowName, name);
      assert.equal(browser.window.name, name);
      assert.equal(browser.document.title, title);
    });
  }

  test("an unknown window is named rather than left undefined", () => {
    const { vpin } = newCore({ search: "" });

    assert.equal(vpin._windowName, "unknown");
  });

  test("the controller window is the one that owns audio and selection", () => {
    // Six comparisons against the literal "table" decide this today. When windows are
    // declared by the theme they collapse into one controller test, and this assertion
    // is what should survive that change unchanged.
    const controller = newCore({ windowName: "table" }).vpin;
    const secondary = newCore({ windowName: "bg" }).vpin;

    assert.equal(controller._windowName, "table");
    assert.notEqual(secondary._windowName, "table");
  });
});

describe("core behaviors have defaults, and they disagree", () => {
  // Recorded rather than endorsed: THEME.local.md §13.2. Core paging is opt-out and core
  // audio is opt-in, neither is stated anywhere an author would look, and the audio
  // default contradicts itself between the constructor and init(). These assertions pin
  // today's answers so the capability registry can change them deliberately.
  test("core paging is on before a theme says anything", () => {
    const { vpin } = newCore();

    assert.equal(vpin.isCorePagingEnabled(), true);
  });

  test("core audio reads true at construction, though init() makes it opt-in", () => {
    const { vpin } = newCore();

    assert.equal(vpin.isCoreAudioEnabled(), true,
      "the constructor says true and init() says false - one registry entry with one "
      + "stated default is what fixes this");
  });

  test("a theme can turn each of them off", () => {
    const { vpin } = newCore();
    vpin.enableCorePaging(false);
    vpin.enableCoreAudio(false);

    assert.equal(vpin.isCorePagingEnabled(), false);
    assert.equal(vpin.isCoreAudioEnabled(), false);
  });
});
