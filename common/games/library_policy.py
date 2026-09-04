"""What this library collects, which belongs to the library and not to a machine.

Which media kinds and asset kinds are worth having, and which online catalogs are
searched for artwork: three answers about one library, shared by every device reading
it. They lived in each install's config file, which is one answer per machine - so two
devices on one library had two answers, and only the hub's did anything.

Follows `common/games/collection_store.py`: a small JSON file, written whole and
atomically, carrying its own schema version. Hub-owned, like the library itself.

Empty means everything, in all three. A kind or a source added in a later version
arrives switched on rather than silently absent, which is what an install upgrading
into a longer registry needs.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from common.atomic_write import write_atomic
from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.common.games.library_policy")

LIBRARY_POLICY_PATH = CONFIG_DIR / "library.json"
SCHEMA = 1
SCHEMA_KEY = "schema"

# key -> where it was read from before, so an install that has one keeps it. The config
# entries stay declared and internal: a value still in a file has to keep resolving, and
# a setting nobody may set is not a setting.
MIGRATES_FROM: dict[str, tuple[str, str]] = {
    "hidden_media_kinds": ("general", "hidden_media_kinds"),
    "hidden_asset_kinds": ("general", "hidden_asset_kinds"),
    "asset_sources": ("media", "asset_sources"),
}

KEYS = tuple(MIGRATES_FROM)


def _as_list(raw: Any) -> list[str]:
    """However the value was stored - a JSON list, or the comma string an ini held."""
    if isinstance(raw, str):
        raw = raw.split(",")
    return [str(item).strip() for item in (raw or []) if str(item).strip()]


class LibraryPolicy:
    """What one library collects, read and written whole."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else LIBRARY_POLICY_PATH
        self._lock = threading.RLock()

    def _load(self) -> dict[str, list[str]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except Exception:
            # An unreadable file is an empty policy, never an error: empty means
            # everything, so the library keeps working while somebody fixes the file.
            logger.warning("%s is unreadable; treating it as empty", self.path)
            return {}
        return {key: _as_list(payload.get(key)) for key in KEYS}

    def values(self) -> dict[str, list[str]]:
        with self._lock:
            found = self._load()
            return {key: found.get(key, []) for key in KEYS}

    def get(self, key: str) -> list[str]:
        return self.values().get(key, [])

    def set(self, key: str, value: Any) -> list[str]:
        if key not in KEYS:
            raise ValueError(f"not a library policy: {key}")
        with self._lock:
            found = self.values()
            found[key] = _as_list(value)
            self._save(found)
            return found[key]

    def _save(self, values: dict[str, list[str]]) -> None:
        payload = {SCHEMA_KEY: SCHEMA, **{key: values.get(key, []) for key in KEYS}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(self.path, lambda handle: json.dump(payload, handle, indent=2))

    def adopt_from_config(self, config) -> bool:
        """Take what an install's config holds, once, and answer whether anything moved.

        Only where this file does not exist: after that the library owns these, and
        re-reading a config that still carries the old values would undo every change
        made since. The config entries are left alone rather than cleared - a device
        downgrading to a build that reads them still finds what it had.
        """
        from common.config_access import cfg_get, cfg_list

        with self._lock:
            if self.path.exists():
                return False
            found: dict[str, list[str]] = {}
            for key, (section, name) in MIGRATES_FROM.items():
                try:
                    found[key] = [str(v).strip() for v in cfg_list(config, section, name)
                                  if str(v).strip()]
                except Exception:
                    found[key] = _as_list(cfg_get(config, section, name, ""))
            self._save(found)
            if any(found.values()):
                logger.info("Library policy adopted from the config file: %s",
                            {k: v for k, v in found.items() if v})
            return True


_policy: LibraryPolicy | None = None


def get_library_policy() -> LibraryPolicy:
    global _policy
    if _policy is None:
        _policy = LibraryPolicy()
    return _policy


def reset_for_tests(path: Path | str | None = None) -> LibraryPolicy:
    global _policy
    _policy = LibraryPolicy(path)
    return _policy
