// The theme documentation, checked against the code it documents.
//
// docs/theme.md is what a theme author builds against, and it drifted: doing this by hand
// once found four documented keys nothing serves and thirteen served keys nobody
// documented. A doc that names a method core does not have is worse than no doc, because
// the author writes the call and gets `undefined` at runtime.
//
// The examples are fragments, not programs - they reference `vpin`, `document` and a
// `currentGameIndex` that only exists in the surrounding prose - so running them is not
// the check. Three things are, and each one is a way the doc goes wrong:
//
//   1. every example parses, so a typo in the docs is a red build
//   2. every `vpin.<name>` the doc calls exists on the class
//   3. every payload path the doc reads exists in the captured payload
//
// The reverse direction - what we serve and never documented - is reported rather than
// failed, because "not written about yet" is a judgement and this file should not be the
// one making it.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";

import { REPO_ROOT, loadCore } from "./support/load-core.js";

const DOC = path.join(REPO_ROOT, "docs", "theme.md");
const DOC_CONTRACT_1 = path.join(REPO_ROOT, "docs", "theme-contract-1.md");
const PAYLOAD = path.join(REPO_ROOT, "tests", "fixtures", "theme_payload.json");

const doc = readFileSync(DOC, "utf8");
const docContract1 = readFileSync(DOC_CONTRACT_1, "utf8");

// Named exemptions, each with the reason, because a blanket allowance would hide the
// drift this file exists to catch.
//
// `someNewMethod` is the feature-detection example: the doc's whole point there is that
// the method may not exist, so requiring it to would invert the lesson.
const NOT_REAL_METHODS = new Set(["someNewMethod"]);
// `vpinplay` is attached to an entry after a rating is fetched (vpinfe-core.js), so it is
// absent from a captured payload by construction rather than by omission.
const ATTACHED_AT_RUNTIME = new Set(["vpinplay"]);
const payload = JSON.parse(readFileSync(PAYLOAD, "utf8"));

/** Every fenced JavaScript block, with the file and line so a failure is findable. */
function jsBlocks(text = doc, name = "docs/theme.md") {
  const blocks = [];
  const pattern = /^```(js|javascript)\n([\s\S]*?)^```/gm;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    const line = text.slice(0, match.index).split("\n").length;
    blocks.push({ where: `${name}:${line}`, source: match[2] });
  }
  return blocks;
}

/** Both theme docs: contract 2 is current, contract 1 is what 2.x themes still read. */
function allJsBlocks() {
  return [...jsBlocks(),
          ...jsBlocks(docContract1, "docs/theme-contract-1.md")];
}

test("docs/theme.md still has examples to check", () => {
  // A regex that quietly matches nothing would make every test below vacuous.
  assert.ok(jsBlocks().length > 15, `only found ${jsBlocks().length} javascript blocks`);
});

test("every javascript example parses", () => {
  const broken = [];
  for (const { where, source } of allJsBlocks()) {
    try {
      // Wrapped in a function so top-level `return` and `await` in a fragment are legal,
      // and compiled rather than run: these reference a `vpin` that does not exist here.
      new vm.Script(`(async function () {\n${source}\n})`);
    } catch (error) {
      broken.push(`${where} ${error.message}`);
    }
  }
  assert.deepEqual(broken, [], `examples that do not parse:\n  ${broken.join("\n  ")}`);
});

test("every vpin method the docs call exists on core", () => {
  const { VPinFECore } = loadCore();
  const surface = new Set();
  for (let proto = VPinFECore.prototype; proto && proto !== Object.prototype;
       proto = Object.getPrototypeOf(proto)) {
    for (const name of Object.getOwnPropertyNames(proto)) surface.add(name);
  }
  // Properties assigned in the constructor are not on the prototype.
  for (const name of Object.getOwnPropertyNames(new VPinFECore())) surface.add(name);

  const called = new Set();
  for (const { source } of allJsBlocks()) {
    for (const m of source.matchAll(/\bvpin\.([A-Za-z_$][\w$]*)/g)) called.add(m[1]);
  }

  const missing = [...called]
    .filter((name) => !surface.has(name) && !NOT_REAL_METHODS.has(name))
    .sort();
  assert.deepEqual(missing, [],
    `the theme docs call vpin members core does not have:\n  ${missing.join("\n  ")}`);
});

test("every payload path the docs read is in the payload we serve", () => {
  const entry = (payload.contract2.entries || [])[0];
  assert.ok(entry, "the captured contract 2 payload has no entries to check against");

  // `entry`, `table` and `media` are the names the doc gives the same objects.
  const roots = { entry, table: entry.table, media: entry.media, game: entry.game };

  const missing = [];
  for (const { where, source } of jsBlocks()) {
    for (const m of source.matchAll(/\b(entry|table|game)((?:\.[A-Za-z_$][\w$]*)+)/g)) {
      const [root, ...steps] = [m[1], ...m[2].slice(1).split(".")];
      let node = roots[root];
      const walked = [root];
      if (steps.some((step) => ATTACHED_AT_RUNTIME.has(step))) continue;
      for (const step of steps) {
        if (node === undefined || node === null || !(step in node)) {
          missing.push(`${where} reads ${walked.join(".")}.${step}`);
          break;
        }
        node = node[step];
        walked.push(step);
      }
    }
  }
  assert.deepEqual(missing, [],
    `documented payload keys nothing serves:\n  ${missing.join("\n  ")}`);
});

test("what we serve and never documented is reported, not failed", () => {
  // The other half of the drift, and the half that is a judgement call: a key nobody has
  // written about yet is a gap, not a defect. Printed so it stays visible.
  const entry = (payload.contract2.entries || [])[0];
  const undocumented = [];
  for (const [group, object] of [["entry", entry], ["entry.game", entry.game],
                                 ["entry.table", entry.table]]) {
    for (const key of Object.keys(object || {})) {
      if (!doc.includes(key)) undocumented.push(`${group}.${key}`);
    }
  }
  if (undocumented.length) {
    console.log(`  served but undocumented: ${undocumented.join(", ")}`);
  }
  assert.ok(true);
});
