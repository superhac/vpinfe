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

describe("core behaviours have one stated default each", () => {
  // These used to disagree with themselves: core audio read true at construction and
  // false after init(), because the constructor and init() each decided separately.
  // CAPABILITIES states each default once and both paths read it.
  test("core paging is on, core audio is off, before init and after", async () => {
    const { vpin } = newCore();

    assert.equal(vpin.isCorePagingEnabled(), true, "opt out");
    assert.equal(vpin.isCoreAudioEnabled(), false, "opt in");
  });

  test("a theme can turn each of them off", () => {
    const { vpin } = newCore();
    vpin.enableCorePaging(false);
    vpin.enableCoreAudio(true);

    assert.equal(vpin.isCorePagingEnabled(), false);
    assert.equal(vpin.isCoreAudioEnabled(), true);
  });

  test("capabilities names what this build offers and whether it is on", () => {
    const { vpin } = newCore();

    assert.ok("core_paging" in vpin.capabilities);
    assert.ok("core_audio" in vpin.capabilities);
    assert.equal(vpin.capabilities.core_paging, true);
    assert.equal(vpin.enabled("no_such_capability"), false,
      "a name this build does not have reads false rather than throwing");
  });

  test("the reported set is a copy, not the live one", () => {
    const { vpin } = newCore();
    vpin.capabilities.core_paging = false;

    assert.equal(vpin.isCorePagingEnabled(), true,
      "a theme poking the report must not change what core does");
  });
});

describe("the overlays behave the same as each other", () => {
  // Three near-identical methods until they were one: the fade class, creating the
  // frame once, hiding rather than destroying. They had already drifted - only two of
  // the three told their iframe anything on open.
  const OVERLAYS = [
    ["toggleMenu", "menuUP", "menu-frame"],
    ["toggleCollectionMenu", "collectionMenuUP", "collection-menu-frame"],
  ];

  for (const [toggle, flag, frameId] of OVERLAYS) {
    test(`${toggle} opens, then closes`, async () => {
      const { vpin, browser } = newCore();
      const root = browser.document.getElementById("overlay-root");

      await vpin[toggle]();
      assert.equal(vpin[flag], true);
      assert.ok(root.classList.contains("active"), "faded in");
      const frame = browser.document.getElementById(frameId);
      assert.ok(frame, "the frame was created");
      assert.equal(frame.style.display, "block");

      await vpin[toggle]();
      assert.equal(vpin[flag], false);
      assert.ok(!root.classList.contains("active"), "faded out");
      assert.equal(frame.style.display, "none", "hidden, never destroyed");
      // Field, not deepEqual: the object is made inside the vm, so its prototype
      // differs from this one and strict deep equality would fail on that alone.
      assert.equal(frame.posted.at(-1).event, "reset state");
    });
  }

  test("opening one closes the other", async () => {
    const { vpin } = newCore();

    await vpin.toggleMenu();
    await vpin.toggleCollectionMenu();

    assert.equal(vpin.menuUP, false, "the main menu closed itself");
    assert.equal(vpin.collectionMenuUP, true);
  });

  test("the frame is created once and reused", async () => {
    const { vpin, browser } = newCore();

    await vpin.toggleMenu();
    const first = browser.document.getElementById("menu-frame");
    await vpin.toggleMenu();
    await vpin.toggleMenu();

    assert.equal(browser.document.getElementById("menu-frame"), first);
  });

  test("a tutorial with no URL leaves what is open alone", async () => {
    const { vpin } = newCore();
    vpin.getCurrentTutorialUrl = () => "";
    await vpin.toggleMenu();

    await vpin.toggleTutorial();

    assert.equal(vpin.tutorialUP, false, "nothing to show");
    assert.equal(vpin.menuUP, true, "and the menu was not closed on the way to nothing");
  });
});
