"""What the Manager UI has already told the user.

Not vpinfe.ini: that is configuration with a documented shape and a compatibility ledger.
Losing this file costs one notice being shown twice.
"""

from __future__ import annotations

import json
import logging

from managerui.paths import CONFIG_DIR

logger = logging.getLogger("vpinfe.manager.ui_state")

STATE_PATH = CONFIG_DIR / "manager-ui-state.json"


def _load() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        logger.warning("Could not read %s; treating it as empty", STATE_PATH)
        return {}


def get(key: str, default=None):
    return _load().get(key, default)


def set(key: str, value) -> None:      # noqa: A001 - reads as ui_state.set at the call site
    data = _load()
    data[key] = value
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        # Never break a page over this: the worst case is the notice returning.
        logger.warning("Could not write %s", STATE_PATH, exc_info=True)
