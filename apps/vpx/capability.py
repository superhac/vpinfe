"""What a given Visual Pinball install can do, established by looking at it.

Never by comparing version numbers. 10.8.0 is the only release in the 10.8 line and
every 10.8.1 tag is a prerelease, so builds eighteen months apart both answer "10.8.1"
while differing by everything we would be gating on.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from common.apps.contract import Availability

PROGRAM = "program"
PLUGINS = "plugins"
PER_TABLE_SETTINGS = "per_table_settings"


def _program_dir(bin_path: str) -> Path | None:
    binary = Path(str(bin_path or "").strip())
    if not binary.name:
        return None
    # A macOS pick is `VPinballX.app`, a directory, and the plugins sit beside the
    # bundle rather than beside the executable inside it.
    for candidate in (binary, *binary.parents):
        if candidate.suffix.lower() == ".app":
            return candidate.parent
    return binary.parent


class VPXCapability:
    def probe(self, settings: Mapping[str, Any]) -> Mapping[str, Availability]:
        bin_path = str(settings.get("bin_path") or "").strip()
        program = Path(bin_path).exists() if bin_path else False

        if not bin_path:
            program_state = Availability(False, "This launcher has no program set.")
        elif not program:
            program_state = Availability(
                False, f"Nothing is at the program this launcher names: {bin_path}")
        else:
            program_state = Availability(True)

        return {
            PROGRAM: program_state,
            PLUGINS: self._plugins(bin_path, settings) if program else Availability(
                False, "The program has to be found before its plugins can be."),
            # Read by 10.8.0 and by master alike, so there is nothing to gate on.
            PER_TABLE_SETTINGS: Availability(True),
        }

    def _plugins(self, bin_path: str, settings: Mapping[str, Any]) -> Availability:
        """The plugin architecture postdates 10.8.0, where B2S is built in and there are
        no plugin sections at all. Evidence is a `plugins/` directory beside the program,
        or the ini already carrying one."""
        directory = _program_dir(bin_path)
        if directory is not None and (directory / "plugins").is_dir():
            return Availability(True)

        ini_path = str(settings.get("ini_path") or "").strip()
        if ini_path and _declares_a_plugin(Path(ini_path)):
            return Availability(True)

        return Availability(False, "This build has no plugins beside it.")


def _declares_a_plugin(ini_path: Path) -> bool:
    try:
        with ini_path.open(encoding="utf-8", errors="replace") as handle:
            return any(line.lstrip().startswith("[Plugin.") for line in handle)
    except OSError:
        return False
