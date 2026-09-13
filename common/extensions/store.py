"""What core knows about an extension, and where that extension keeps its own settings.

Two homes, because there are two owners. Whether an extension is switched off is core's
record about it - core has to know before it loads anything, and reading a file per
extension to answer "what am I not loading" is worse than reading one. What an extension
is configured with is nobody's business but its own, so it gets a file.

A file each rather than a namespace inside one, and the reason is the same one that keeps
these out of `vpinfe.ini`: a namespace in somebody else's file is a weaker form of "own"
than a file. One bad write took every extension's settings with it, and the switched-off
ones came back on.

Follows `common/games/locations.py`: small JSON, written whole and atomically, carrying
its own schema version.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path

from common.atomic_write import write_atomic
from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.common.extensions.store")

# Core's own record of what is installed here.
EXTENSIONS_PATH = CONFIG_DIR / "extensions.json"
# One file per extension, named for it. Not beside its code: an extension the build
# ships has no directory here at all, so settings need a home that does not depend on
# where the code came from.
SETTINGS_DIR = CONFIG_DIR / "extension_settings"

SCHEMA = 1
SCHEMA_KEY = "schema"
EXTENSIONS_KEY = "extensions"
ENABLED_KEY = "enabled"
SETTINGS_KEY = "settings"
MIGRATIONS_KEY = "migrations"

# The one-time move of settings out of the shared file and into a file each.
SETTINGS_SPLIT = "settings-split"

# The name is already restricted to this by the manifest. Checked again here because
# this one builds a path out of it, and a name that could contain a separator would be
# a way to write outside the directory.
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class ExtensionStore:
    def __init__(self, path: Path | str | None = None,
                 settings_dir: Path | str | None = None):
        self.path = Path(path) if path is not None else EXTENSIONS_PATH
        # Beside the registry, not at the default, unless told otherwise. The two homes
        # are one store: a caller that relocates the registry and silently leaves the
        # settings pointing at this machine's own is not isolated at all, which is a
        # thing to find out here rather than in whatever it was writing into.
        self.settings_dir = (
            Path(settings_dir) if settings_dir is not None
            else (SETTINGS_DIR if path is None
                  else self.path.parent / SETTINGS_DIR.name))
        self._lock = threading.RLock()

    # -- what core knows -----------------------------------------------------

    def enabled(self, name: str) -> bool:
        """An extension nobody has said anything about is on: installing one is the act
        of asking for it."""
        with self._lock:
            self._split_once()
            return bool(self._entry(name).get(ENABLED_KEY, True))

    def set_enabled(self, name: str, on: bool) -> None:
        with self._lock:
            self._split_once()
            held = self._registry()
            held[name] = {**dict(held.get(name) or {}), ENABLED_KEY: bool(on)}
            self._write_registry(held)

    # -- what the extension knows --------------------------------------------

    def settings(self, name: str) -> dict[str, str]:
        with self._lock:
            self._split_once()
            raw = self._read_settings(name)
        return {str(key): str(value) for key, value in raw.items()}

    def set_setting(self, name: str, key: str, value: str) -> None:
        wanted = str(key or "").strip()
        if not wanted:
            return
        with self._lock:
            self._split_once()
            held = self._read_settings(name)
            held[wanted] = str(value)
            self._write_settings(name, held)

    def forget(self, name: str) -> None:
        """Drop everything about an extension that has been removed. Its settings are a
        file, so this is a delete rather than an edit of something shared."""
        with self._lock:
            held = self._registry()
            if held.pop(name, None) is not None:
                self._write_registry(held)
            path = self._settings_path(name)
            if path is not None:
                path.unlink(missing_ok=True)

    # -- the files -----------------------------------------------------------

    def _entry(self, name: str) -> dict:
        found = self._registry().get(str(name or "").strip())
        return found if isinstance(found, dict) else {}

    def _payload(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as handle:
                return json.load(handle) or {}
        except FileNotFoundError:
            return {}
        except Exception:
            logger.exception("Could not read %s; treating it as empty", self.path)
            return {}

    def _registry(self) -> dict:
        held = self._payload().get(EXTENSIONS_KEY)
        return dict(held) if isinstance(held, dict) else {}

    def _write_registry(self, held: dict, migrations: list[str] | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            SCHEMA_KEY: SCHEMA,
            MIGRATIONS_KEY: (self._migrations() if migrations is None else migrations),
            EXTENSIONS_KEY: held,
        }
        write_atomic(self.path, lambda handle: json.dump(payload, handle, indent=2))

    def migrations(self) -> list[str]:
        """Which one-time conversions have already run against this install."""
        with self._lock:
            return self._migrations()

    def mark_migration(self, name: str) -> None:
        """Note that one has run, so it never runs twice."""
        wanted = str(name or "").strip()
        with self._lock:
            held = self._migrations()
            if wanted and wanted not in held:
                self._write_registry(self._registry(), migrations=[*held, wanted])

    def _migrations(self) -> list[str]:
        return [str(one) for one in self._payload().get(MIGRATIONS_KEY) or []]

    def _settings_path(self, name: str) -> Path | None:
        wanted = str(name or "").strip()
        if not _NAME.match(wanted):
            logger.error("Refusing settings for %r, which is not an extension name",
                         name)
            return None
        return self.settings_dir / f"{wanted}.json"

    def _read_settings(self, name: str) -> dict:
        path = self._settings_path(name)
        if path is None:
            return {}
        try:
            with open(path, encoding="utf-8") as handle:
                held = json.load(handle) or {}
        except FileNotFoundError:
            return {}
        except Exception:
            # One extension's file, so one extension's settings. This is the whole
            # reason they are not in one file together.
            logger.exception("Could not read %s; treating it as empty", path)
            return {}
        return dict(held) if isinstance(held, dict) else {}

    def _write_settings(self, name: str, held: dict) -> None:
        path = self._settings_path(name)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, lambda handle: json.dump(held, handle, indent=2))

    def _split_once(self) -> None:
        """Move settings out of the shared file into a file each, once.

        An install that ran a build where they lived together keeps them; the marker is
        what stops this looking at every read forever.
        """
        if SETTINGS_SPLIT in self._migrations():
            return
        held = self._registry()
        moved = 0
        kept: dict[str, dict] = {}
        for name, entry in held.items():
            if not isinstance(entry, dict):
                continue
            settings = entry.get(SETTINGS_KEY)
            if isinstance(settings, dict) and settings:
                self._write_settings(name, dict(settings))
                moved += 1
            kept[name] = {ENABLED_KEY: bool(entry.get(ENABLED_KEY, True))}
        self._write_registry(kept, migrations=[*self._migrations(), SETTINGS_SPLIT])
        if moved:
            logger.info("Moved settings for %d extension(s) into %s", moved,
                        self.settings_dir)


_store: ExtensionStore | None = None


def get_extension_store() -> ExtensionStore:
    """This install's extension settings. One per process, the way the launchers are."""
    global _store
    if _store is None:
        _store = ExtensionStore()
    return _store
