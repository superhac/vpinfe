"""How a user has arranged a UI, kept on the hub so it follows them between devices.

Deliberately not `managerui/services/ui_state.py`, whose contract is that losing it
costs one notice being shown twice. A column layout someone tuned is worth more than
that, so this is its own file with its own durability expectation, and it is not in
`revert_3x.CONFIG_FILES` - a state reset is about 3.0 data, not about throwing away
how somebody likes their tables.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

from common.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.ui_preferences")

PREFERENCES_PATH = CONFIG_DIR / "ui-preferences.json"
SCHEMA = 1


def _load() -> dict[str, Any]:
    try:
        data = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        logger.warning("Could not read %s; treating it as empty", PREFERENCES_PATH)
        return {}
    return data.get("scopes", {}) if isinstance(data, dict) else {}


def get(scope: str) -> dict[str, Any]:
    value = _load().get(scope)
    return value if isinstance(value, dict) else {}


def put(scope: str, value: dict[str, Any]) -> dict[str, Any]:
    scopes = _load()
    scopes[scope] = value
    payload = json.dumps({"schema": SCHEMA, "scopes": scopes}, indent=2)
    # Atomic: a half-written layout would be read as an empty one on next start, and
    # silently reset every table the user had arranged.
    PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(dir=PREFERENCES_PATH.parent,
                                         prefix=".vpinfe_write_", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(temp_path, PREFERENCES_PATH)
    except Exception:
        os.unlink(temp_path)
        raise
    return value
