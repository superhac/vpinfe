// The five methods core's collection menu owns, and the door it comes in by.
//
// The allowlist in frontend/api.py used to be flat, so core had no way to have a private
// call and these were theme API by construction. vpin.call refusing them is what makes
// the split real: the names stay dispatchable because the overlay is an iframe with no
// other route in, and documenting them away would have changed nothing (PAR-84).
//
// It stops an accident, not an attacker - the overlay's door is on the same object.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { loadCore } from "./support/load-core.js";

// A core with an open socket, without running init() and its whole bridge sequence.
function coreOnASocket() {
  const { VPinFECore, context, browser } = loadCore({ windowName: "playfield" });
  const vpin = new VPinFECore();
  vpin._ws = new browser.WebSocket("ws://127.0.0.1:8002?window=playfield");
  return { vpin, socket: vpin._ws, internal: context.INTERNAL_METHODS };
}

describe("vpin.call refuses core's own methods", () => {
  test("the ones the collection menu owns are the refused set", () => {
    const { internal } = coreOnASocket();

    assert.deepEqual([...internal].sort(), [
      "apply_filters",
      "apply_sort",
      "get_current_filter_state",
      "get_current_order_state",
      "get_current_sort_state",
      "get_paging_state",
    ]);
  });

  for (const method of ["apply_sort", "apply_filters", "get_current_sort_state"]) {
    test(`call("${method}") rejects and never reaches the bridge`, async () => {
      const { vpin, socket } = coreOnASocket();

      await assert.rejects(() => vpin.call(method), /Method not allowed/);
      assert.equal(socket.sent.filter((m) => m.method === method).length, 0,
        "a refused call must not be sent - the backend would answer it");
    });
  }

  test("a published method still goes through", async () => {
    const { vpin, socket } = coreOnASocket();

    vpin.call("get_collections");

    assert.equal(socket.sent.at(-1).method, "get_collections");
  });
});

describe("the overlays keep working, and the refusal is reported", () => {
  test("callInternal sends what call refuses", async () => {
    const { vpin, socket } = coreOnASocket();

    vpin.callInternal("apply_sort", "Alpha", "Ascending");

    assert.deepEqual(socket.sent.at(-1).args, ["Alpha", "Ascending"]);
    assert.equal(socket.sent.at(-1).method, "apply_sort");
  });

  test("a refused call tells the machine's log, once per name", async () => {
    const { vpin, socket } = coreOnASocket();

    await assert.rejects(() => vpin.call("apply_sort"));
    await assert.rejects(() => vpin.call("apply_sort"));

    const reports = socket.sent.filter((m) => m.method === "report_deprecated_use");
    assert.equal(reports.length, 1, "a wheel could refuse this every frame");
    assert.deepEqual(reports[0].args, ["theme-internal-methods", "apply_sort"]);
  });
});
