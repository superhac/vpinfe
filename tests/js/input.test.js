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
  const press = async (key, { code = key, repeat = false } = {}) => {
    const event = { key, code, repeat, prevented: false,
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
    const seen = [];
    // Pushed directly: registerInputHandler awaits a bridge round-trip before it
    // registers anything, and what is under test here is dispatch.
    vpin.inputHandlers.push((action) => { seen.push(action); });

    await press("ArrowLeft", { repeat: true });
    await press("ArrowRight", { repeat: true });

    assert.deepEqual(seen, ["joyleft", "joyright"],
      "one shared timestamp read a direction change as the same key repeating");
  });

  test("the same action repeating is still throttled", async () => {
    const { vpin, press } = controller();
    const seen = [];
    // Pushed directly: registerInputHandler awaits a bridge round-trip before it
    // registers anything, and what is under test here is dispatch.
    vpin.inputHandlers.push((action) => { seen.push(action); });

    await press("ArrowLeft", { repeat: true });
    await press("ArrowLeft", { repeat: true });

    assert.deepEqual(seen, ["joyleft"],
      "the throttle is what keeps a held key from flooding the wheel");
  });
});

describe("defaults agree across the boundary", () => {
  test("back is bound in the JavaScript fallback too", () => {
    const { vpin } = controller();

    assert.deepEqual([...vpin.keyActionMap.joyback], ["b"],
      "Python ships keyback=b; an empty fallback meant back did nothing until the "
      + "bridge answered");
  });
});
