// Which window the splash page plays its video in, run from the page's own script.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import vm from "node:vm";

import { loadCore, REPO_ROOT } from "./support/load-core.js";

const PAGE = path.join(REPO_ROOT, "frontend", "static", "splash.html");
const SCRIPT = [...readFileSync(PAGE, "utf8").matchAll(/<script>([\s\S]*?)<\/script>/g)]
  .map((match) => match[1]).join("\n");

const WINDOWS = { 1: ["table", "bg", "dmd"], 2: ["playfield", "backglass", "scoreview"] };

function element(id, hidden) {
  const classes = new Set(hidden ? ["hidden"] : []);
  return {
    id, style: {}, played: false, classes,
    classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name) },
    load() {},
    async play() { this.played = true; },
    addEventListener() {},
  };
}

async function splashIn(contract, windowName) {
  const { VPinFECore, context, browser } = loadCore({ windowName });
  const video = element("splash", false);
  const image = element("splash-image", true);
  Object.assign(browser.document._byId, {
    "splash-root": element("splash-root"), splash: video,
    "splash-source": element("splash-source"), "splash-image": image,
  });
  const bridge = {
    get_theme_contract: contract, get_theme_windows: WINDOWS[contract],
    get_splashscreen_enabled: "true",
    get_cab_mode: false, get_playfield_rotation: 0, get_theme_assets_port: 8000,
    get_tables: JSON.stringify([]), get_theme_config: {}, get_monitors: [],
  };
  VPinFECore.prototype.call = (method) => Promise.resolve(bridge[method]);

  vm.runInContext(SCRIPT, context, { filename: PAGE });
  await browser.WebSocket.instances.at(-1).onopen();
  await new Promise((resolve) => setTimeout(resolve, 10));
  return { video, image };
}

for (const contract of [1, 2]) {
  const [controller, ...others] = WINDOWS[contract];

  test(`at contract ${contract} the video plays in ${controller}, the controller`, async () => {
    const { video, image } = await splashIn(contract, controller);

    assert.equal(video.played, true);
    assert.ok(image.classes.has("hidden"));
  });

  for (const windowName of others) {
    test(`at contract ${contract} ${windowName} shows the still`, async () => {
      const { video, image } = await splashIn(contract, windowName);

      assert.equal(video.played, false);
      assert.ok(!image.classes.has("hidden"));
    });
  }
}
