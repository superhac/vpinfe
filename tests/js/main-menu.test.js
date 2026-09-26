// What the main menu's metadata build says when it stops.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import vm from "node:vm";

import { REPO_ROOT } from "./support/load-core.js";

const MENU = path.join(REPO_ROOT, "frontend", "static", "mainmenu", "mainmenu.js");
const WORDS = JSON.parse(readFileSync(
  path.join(REPO_ROOT, "common", "i18n", "catalogs", "en.json"), "utf8"));

function menuPage() {
  const elements = {};
  const element = (id) => (elements[id] ||= { id, textContent: "", style: {} });
  const window = {
    __vpinWords: WORDS,
    parent: { vpin: { registerOverlayHandler() {} } },
    addEventListener() {},
  };
  const context = vm.createContext({ window, document: { getElementById: element } });
  vm.runInContext(readFileSync(MENU, "utf8"), context, { filename: MENU });
  return { window, element };
}

test("a build that stops says the reason it was given, and nothing before it", () => {
  const { window, element } = menuPage();

  window.receiveEvent({ type: "buildmeta_error",
                        error: WORDS["frontend.buildmeta.library_busy"] });

  assert.equal(element("progress-text").textContent,
               "The library is busy - try again when it finishes");
});
