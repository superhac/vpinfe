// What a theme gets when it asks for media.
//
// This is the surface a rename broke on the way to the cabinet: MEDIA_PATH_FIELDS maps a
// kind to a payload key, and when the payload key moved the map still pointed at the old
// one. Six gates and 745 Python tests were green. These assertions are the ones that
// would not have been.

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import { newCore, fixture } from "./support/load-core.js";

const PAYLOAD = fixture("theme_payload.json");
const ROWS = PAYLOAD.contract1;

const byFolder = (name) => ROWS.findIndex((row) => row.tableDirName === name);
const AFM = byFolder("Attack from Mars (Bally 1995)");
const CONGO = byFolder("Congo (Williams 1995)");
const MM = byFolder("Medieval Madness (Williams 1997)");
const BARE = byFolder("Bare Table (Gottlieb 1980)");

function coreWithLibrary() {
  const { vpin } = newCore({ windowName: "table" });
  vpin.gameData = ROWS;
  vpin.themeAssetsPort = 8000;
  return vpin;
}

describe("media kinds resolve to URLs", () => {
  test("every kind the payload resolved has a reachable URL", () => {
    const vpin = coreWithLibrary();

    for (const [kind, expected] of [
      ["wheel", "wheel.png"],
      ["bg", "bg.png"],
      ["dmd", "dmd.png"],
    ]) {
      const url = vpin.getImageURL(AFM, kind);
      assert.ok(url.startsWith("http://127.0.0.1:8000/"),
        `${kind} should resolve to a served URL, got ${url}`);
      assert.ok(url.endsWith(expected), `${kind} should end in ${expected}, got ${url}`);
    }
  });

  test("a kind with no file resolves to the missing placeholder, never undefined", () => {
    const vpin = coreWithLibrary();
    const media = vpin.getMedia(BARE, "wheel");

    assert.equal(media.kind, "missing");
    assert.equal(media.path, null);
    assert.ok(media.url.length > 0, "a missing kind still needs something to put in src");
  });

  test("an unknown kind does not throw", () => {
    const vpin = coreWithLibrary();
    // A theme asking for a kind this build does not have is a version skew, not a crash.
    assert.doesNotThrow(() => vpin.getMedia(AFM, "no_such_kind"));
  });
});

describe("the URL builder handles every layout the scan produces", () => {
  test("media under medias/ is served from the game folder", () => {
    const vpin = coreWithLibrary();
    const url = vpin.getImageURL(AFM, "wheel");

    assert.match(url, /\/tables\/Attack%20from%20Mars%20\(Bally%201995\)\/medias\/wheel\.png$/);
  });

  test("media at the folder root is served too", () => {
    const vpin = coreWithLibrary();
    const url = vpin.getImageURL(CONGO, "wheel");

    assert.ok(url.startsWith("http://127.0.0.1:8000/"));
    assert.ok(url.endsWith("wheel.png"));
    assert.ok(!url.includes("/medias/"), `root media should not gain a medias segment: ${url}`);
  });

  test("a wheel set keeps every segment below medias/", () => {
    // The case that needed its own branch: the file sits deeper than medias/, so taking
    // the parent of the filename would address the wrong folder.
    const vpin = coreWithLibrary();
    const url = vpin.getImageURL(MM, "wheel");

    assert.match(url, /\/medias\/wheels\/monochrome\/wheel\.png$/);
  });

  test("folder names with spaces and brackets are encoded", () => {
    const vpin = coreWithLibrary();
    const url = vpin.getImageURL(AFM, "wheel");

    assert.ok(!url.includes(" "), `a raw space would break the request: ${url}`);
  });
});

describe("image versus video is the user's preference, and it is honoured", () => {
  test("video wins by default when both exist", () => {
    const vpin = coreWithLibrary();
    const media = vpin.getMedia(AFM, "playfield");

    assert.equal(media.kind, "video");
    assert.ok(media.url.endsWith(".mp4"));
  });

  test("image wins when the priority says so", () => {
    const vpin = coreWithLibrary();
    vpin.mediaPriorities = { ...vpin.mediaPriorities, playfield: "image" };
    const media = vpin.getMedia(AFM, "playfield");

    assert.equal(media.kind, "image");
    assert.ok(media.url.endsWith(".png"));
  });

  test("the preference falls back rather than showing nothing", () => {
    // Congo has neither playfield image nor video; bg exists only as an image.
    const vpin = coreWithLibrary();
    vpin.mediaPriorities = { ...vpin.mediaPriorities, bg: "video" };
    const media = vpin.getMedia(MM, "bg");

    assert.equal(media.kind, "image", "a missing video must fall back to the image");
  });
});

describe("realdmd is one kind with two frames", () => {
  test("color is preferred by default", () => {
    const vpin = coreWithLibrary();
    const media = vpin.getMedia(AFM, "realdmd");

    assert.ok(media.url.endsWith("realdmd-color.png"), `got ${media.url}`);
  });

  test("both spellings of the color kind reach the same place", () => {
    const vpin = coreWithLibrary();

    assert.equal(vpin.getMedia(AFM, "realdmd-color").url,
                 vpin.getMedia(AFM, "realdmd_color").url);
  });
});

describe("the kind names earlier builds used still answer", () => {
  test("table, table_video and fss reach their renamed kinds", () => {
    const vpin = coreWithLibrary();

    assert.equal(vpin.getMedia(AFM, "table").url, vpin.getMedia(AFM, "playfield").url);
    assert.equal(vpin.getImageURL(MM, "fss"), vpin.getImageURL(MM, "playfield_fss"));
  });

  test("a theme naming the playfield by its old key still gets the playfield", () => {
    // The single most common call in any theme, and the one a rename would break
    // most visibly.
    const vpin = coreWithLibrary();

    assert.notEqual(vpin.getMedia(AFM, "table").kind, "missing");
  });
});
