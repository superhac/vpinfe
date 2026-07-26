"""Asks libpinmame about ROM sets. Run as a subprocess, never imported into the app.

The library spins an emulator core with global state and its struct layout can
drift between the versions VPX ships; in a worker a mismatch is a dead subprocess
reported as "audit unavailable", not a dead VPinFE. Same isolation reasoning as
dof_service_worker.

Usage: python -m common.host.pinmame_worker <libpath> <roms_dir> <set> [<set>...]
Prints one JSON object keyed by set name.
"""

from __future__ import annotations

import ctypes
import json
import sys
import tempfile

PINMAME_MAX_PATH = 512
FILE_TYPE_ROMS = 0
STATUS_OK = 0


class PinmameGame(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("clone_of", ctypes.c_char_p),
        ("description", ctypes.c_char_p),
        ("year", ctypes.c_char_p),
        ("manufacturer", ctypes.c_char_p),
        ("flags", ctypes.c_uint32),
        ("found", ctypes.c_int32),
    ]


class PinmameConfig(ctypes.Structure):
    # audioFormat, sampleRate, vpmPath, then twelve callback pointers we leave
    # null - catalog reads never start the machine.
    _fields_ = ([("audioFormat", ctypes.c_int), ("sampleRate", ctypes.c_int),
                 ("vpmPath", ctypes.c_char * PINMAME_MAX_PATH)]
                + [(f"cb{i}", ctypes.c_void_p) for i in range(12)])


def lookup(lib_path: str, roms_dir: str, names: list[str]) -> dict:
    lib = ctypes.CDLL(lib_path)
    game_callback = ctypes.CFUNCTYPE(None, ctypes.POINTER(PinmameGame), ctypes.c_void_p)

    config = PinmameConfig()
    ctypes.memset(ctypes.byref(config), 0, ctypes.sizeof(config))
    # The library insists on a writable vpm home even for catalog reads.
    vpm_home = tempfile.mkdtemp(prefix="vpinfe-pinmame-").encode()
    ctypes.memmove(config.vpmPath, vpm_home, min(len(vpm_home), PINMAME_MAX_PATH - 1))
    lib.PinmameSetConfig(ctypes.byref(config))
    lib.PinmameSetPath(FILE_TYPE_ROMS, roms_dir.encode())

    hit: list[dict] = []

    def on_game(game_ptr, _user):
        game = game_ptr.contents
        hit.append({
            "clone_of": (game.clone_of or b"").decode() or None,
            "description": (game.description or b"").decode(),
            "year": (game.year or b"").decode(),
            "manufacturer": (game.manufacturer or b"").decode(),
            "found": bool(game.found),
        })

    callback = game_callback(on_game)
    result = {}
    for name in names:
        hit.clear()
        status = lib.PinmameGetGame(name.encode(), callback, None)
        if status == STATUS_OK and hit:
            result[name] = {"catalog": True, **hit[0]}
        else:
            result[name] = {"catalog": False}
    return result


def main() -> int:
    if len(sys.argv) < 4:
        print(json.dumps({"error": "usage: pinmame_worker <lib> <roms_dir> <set>..."}))
        return 2
    try:
        print(json.dumps(lookup(sys.argv[1], sys.argv[2], sys.argv[3:])))
        return 0
    except Exception as exc:  # the whole point of the worker: die informatively
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
