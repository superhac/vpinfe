// Keyboard input: one dispatch, and it does not quit the app from inside a menu.
//
// These started as throwaway checks that asserted the defects existed (INPUT.local.md
// §4, input-tools/). They are inverted here: each one now pins the fixed behavior, so
// the same evidence that found the bugs is the net that keeps them fixed.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { loadCore } from "./support/load-core.js";

// A controller-window core with the keydown listener core installs captured, so a test
// can fire a key the way the browser would. Overlay flags are set directly: what is
// under test is what a keypress does while one is up, not how it got there.
function controller() {
  const { VPinFECore, browser } = loadCore({ windowName: "table" });
  const listeners = {};
  browser.window.addEventListener = (type, fn) => { (listeners[type] ||= []).push(fn); };
  const vpin = new VPinFECore();
  vpin.init();
  const socket = browser.WebSocket.instances[0];
  vpin.isController = () => true;
  vpin.frontendInputEnabled = true;

  // The listener is async, so a handler runs on a microtask - a synchronous assert
  // would look at the list before anything reached it.
  const press = async (key, { code = key, repeat = false, target = null } = {}) => {
    const event = { key, code, repeat, target, prevented: false,
                    preventDefault() { event.prevented = true; } };
    await Promise.all((listeners.keydown || []).map(fn => fn(event)));
    return event;
  };
  const calls = () => socket.sent.filter(m => m.type === "api_call").map(m => m.method);
  return { vpin, press, calls };
}

describe("exit never quits VPinFE from inside an overlay", () => {
  // Escape and q are both bound to exit by default, and an overlay's own Escape
  // handler never runs because nothing focuses the iframe - so this used to be a
  // one-key exit from any menu.
  for (const [name, flag] of [["main menu", "menuUP"],
                              ["collection menu", "collectionMenuUP"],
                              ["tutorial", "tutorialUP"]]) {
    for (const key of ["Escape", "q"]) {
      test(`${key} with the ${name} up closes it instead of the app`, async () => {
        const { vpin, press, calls } = controller();
        vpin[flag] = true;

        await press(key);

        assert.equal(calls().includes("close_app"), false,
          "close_app must not be reachable while an overlay is up");
        assert.equal(vpin[flag], false, "the overlay should have closed");
      });
    }
  }

  test("exit still quits when no overlay is up", async () => {
    const { press, calls } = controller();

    await press("Escape");

    assert.equal(calls().includes("close_app"), true,
      "exit has to keep working where it was always meant to");
  });
});

describe("a bound key belongs to core", () => {
  test("a matched action prevents the browser default", async () => {
    const { press } = controller();

    assert.equal((await press("ArrowLeft")).prevented, true,
      "without this the arrows also scroll the theme's page");
  });

  test("an unbound key is left alone", async () => {
    const { press } = controller();

    assert.equal((await press("F9")).prevented, false,
      "core must not swallow keys it has no binding for");
  });
});

describe("the auto-repeat throttle is per action", () => {
  test("a repeating right is not swallowed by a repeating left", async () => {
    const { vpin, press } = controller();
    // Contract 2, so the names below are core's own rather than the translated ones a
    // contract 1 theme is handed. What is under test is the throttle, not the naming.
    vpin.contract = 2;
    const seen = [];
    // Pushed directly: registerInputHandler awaits a bridge round-trip before it
    // registers anything, and what is under test here is dispatch.
    vpin.inputHandlers.push((action) => { seen.push(action); });

    await press("ArrowLeft", { repeat: true });
    await press("ArrowRight", { repeat: true });

    assert.deepEqual(seen, ["previous", "next"],
      "one shared timestamp read a direction change as the same key repeating");
  });

  test("the same action repeating is still throttled", async () => {
    const { vpin, press } = controller();
    // Contract 2, so the names below are core's own rather than the translated ones a
    // contract 1 theme is handed. What is under test is the throttle, not the naming.
    vpin.contract = 2;
    const seen = [];
    // Pushed directly: registerInputHandler awaits a bridge round-trip before it
    // registers anything, and what is under test here is dispatch.
    vpin.inputHandlers.push((action) => { seen.push(action); });

    await press("ArrowLeft", { repeat: true });
    await press("ArrowLeft", { repeat: true });

    assert.deepEqual(seen, ["previous"],
      "the throttle is what keeps a held key from flooding the wheel");
  });
});

describe("defaults agree across the boundary", () => {
  test("back is bound in the JavaScript fallback too", () => {
    const { vpin } = controller();

    assert.deepEqual([...vpin.keyActionMap.back], ["b"],
      "Python ships b for back; an empty fallback meant back did nothing until the "
      + "bridge answered");
  });
});

describe("one dispatch, wherever focus is", () => {
  // Key events go to the focused document, so a touch or click inside an overlay used
  // to take them away from the window listener - which is why each overlay carried its
  // own hardcoded map. Core listens on the overlay's window too now, so the configured
  // bindings apply either way and those three maps could go.
  test("core listens on an overlay's own window when it opens", async () => {
    const { VPinFECore, browser } = loadCore({ windowName: "table" });
    browser.window.addEventListener = () => {};
    const framed = [];
    const original = browser.document.createElement;
    browser.document.createElement = (tag) => {
      const el = original.call(browser.document, tag);
      if (tag === "iframe") {
        el.contentWindow = {
          addEventListener: (type) => framed.push(type),
          postMessage: () => {},
        };
      }
      return el;
    };
    const vpin = new VPinFECore();
    vpin.init();
    vpin.call = () => Promise.resolve(undefined);

    await vpin.toggleMenu();

    assert.equal(framed.includes("keydown"), true,
      "without this, keys do nothing once focus is inside the overlay");
  });
});

describe("typing is typing, not input actions", () => {
  // b, c, m, q and t are bound by default, and core listens inside overlays now - so
  // without this guard the collection menu's save-filter box could not accept them,
  // and Enter would fire select instead of reaching the field.
  const field = (type = "text") => ({ tagName: "INPUT", type });

  for (const key of ["b", "c", "m", "q", "t", "Enter", "Escape"]) {
    test(`${key} typed into a text field is left to the field`, async () => {
      const { vpin, press, calls } = controller();
      const seen = [];
      vpin.inputHandlers.push((action) => { seen.push(action); });

      const event = await press(key, { target: field() });

      assert.deepEqual(seen, [], `${key} must reach the field, not the wheel`);
      assert.equal(event.prevented, false, "the field needs the browser default");
      assert.equal(calls().includes("close_app"), false);
    });
  }

  test("a checkbox is not a text field, so bindings still work", async () => {
    const { vpin, press } = controller();
    vpin.contract = 2;
    const seen = [];
    vpin.inputHandlers.push((action) => { seen.push(action); });

    await press("ArrowLeft", { target: field("checkbox") });

    assert.deepEqual(seen, ["previous"]);
  });
});

describe("a theme is handed the action names its contract published", () => {
  // Twelve registry themes switch on `case "joyleft"`. Core dispatches `previous` now,
  // so contract 1 gets translated at the theme boundary and nothing else does.
  const themeSees = (contract) => {
    const { vpin, press } = controller();
    vpin.contract = contract;
    const seen = [];
    vpin.inputHandlers.push((action) => { seen.push(action); });
    return { seen, press };
  };

  test("contract 1 still receives joyleft", async () => {
    const { seen, press } = themeSees(1);
    await press("ArrowLeft");
    assert.deepEqual(seen, ["joyleft"], "every published theme switches on this");
  });

  test("contract 2 receives previous", async () => {
    const { seen, press } = themeSees(2);
    await press("ArrowLeft");
    assert.deepEqual(seen, ["previous"]);
  });

  test("up merged into paging, which core consumes by default", async () => {
    // joyup and joypageup were the same intent under two names, so ArrowUp is a paging
    // action now - and core_paging is on, so core answers it and no theme sees it.
    // That is the merge working: carousel-desktop's dead page-jump cases were dead
    // precisely because core already owned the paging actions.
    const { seen, press } = themeSees(1);

    await press("ArrowUp");

    assert.deepEqual(seen, [], "core handles paging; the theme is not asked");
  });
});
