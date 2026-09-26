"""No two settings a person can pick read the same.

Two places name every setting: Add a Setting at a table, and the Tables grid's Own
Settings column, where a setting is picked across every table. Both are composed here
from the labels VPX writes into its ini: `tests/fixtures/vpx_labels.json` is every
setting VPX 11bc68f7d declares in `src/core/Settings_properties.inl`, by section, less
the sections the settings never offer.
"""

from __future__ import annotations

import json
import unittest
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import ClassVar
from unittest.mock import patch

from apps.vpx import ini as vini
from apps.vpx.setting_types import REGISTERED
from common.games import launcher_ops, launchers
from console import app_settings, data, workbench

LABELS = Path(__file__).resolve().parents[1] / "fixtures" / "vpx_labels.json"


def _ini(where: Path) -> Path:
    sections: dict[str, dict[str, str]] = json.loads(LABELS.read_text(encoding="utf-8"))
    for qualified in REGISTERED:
        section, _key = vini.section_and_key(qualified)
        sections.setdefault(section, {"Enable": "Enable"})
    lines = []
    for section, keys in sections.items():
        lines.append(f"[{section}]")
        for key, label in keys.items():
            lines.extend((f"; {label}:" if label else ";", f"{key} = "))
        lines.append("")
    written = where / "VPinballX.ini"
    written.write_text("\n".join(lines), encoding="utf-8")
    return written


def _read_the_same(names: dict[str, str]) -> dict[str, list[str]]:
    by: dict[str, list[str]] = defaultdict(list)
    for key, name in names.items():
        by[" ".join(name.casefold().split())].append(key)
    return {name: keys for name, keys in sorted(by.items()) if len(keys) > 1}


class SettingsReadApartTests(unittest.TestCase):
    at_a_table: ClassVar[list]
    every: ClassVar[list]

    @classmethod
    def setUpClass(cls) -> None:
        tmp = TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        where = Path(tmp.name)
        game = where / "Some Table" / "Some Table.vpx"
        game.parent.mkdir()
        game.write_text("", encoding="utf-8")
        store = launchers.LauncherStore(str(where / "launchers.json"))
        store.put(launchers.Launcher("vpx", app="vpx", settings={
            "bin_path": "", "ini_path": str(_ini(where))}))
        with patch.object(launchers, "get_launcher_store", return_value=store), \
                patch.object(launcher_ops, "_game_file", return_value=str(game)):
            cls.at_a_table = data.config_groups(
                launcher_ops.app_config("vpx", "some-table", "entry"))
            cls.every = data.config_groups(launcher_ops.app_config("vpx", "", "launcher"))

    def _read_apart(self, names: dict[str, str]) -> None:
        if same := _read_the_same(names):
            self.fail("{} names shared by {} settings:\n{}".format(
                len(same), sum(map(len, same.values())),
                "\n".join(f"  {name!r}: {keys}" for name, keys in same.items())))

    def test_add_a_setting_at_a_table(self) -> None:
        offered = {field.key: str(field.label)
                   for field, _area in app_settings.addable(self.at_a_table, {}, ())}

        self.assertIn("Plugin.B2S.Enable", offered)
        self._read_apart(offered)

    def test_every_table_s_own_settings(self) -> None:
        names = workbench.setting_names(self.every)

        self.assertIn("Backglass.BackglassFSWidth", names)
        self._read_apart(names)


if __name__ == "__main__":
    unittest.main()
