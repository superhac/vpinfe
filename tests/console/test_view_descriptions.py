"""Every built-in view says what it is for, including the ones built at render time."""

from __future__ import annotations

import ast
import pathlib
import unittest

from console import assets, collections, devices, games, launchers, locations, media
from console import views as views_module

REPO = pathlib.Path(__file__).resolve().parent.parent.parent

DECLARED = {
    "games": games.GAME_VIEWS,
    "tables": games.TABLE_VIEWS,
    "media": media.VIEWS,
    "assets": assets.VIEWS,
    "devices": devices.VIEWS,
    "collections": collections.COLLECTION_VIEWS,
    "locations": locations.LOCATION_VIEWS,
    "launchers": launchers.LAUNCHER_VIEWS,
}


class BuiltinViewsAreDescribed(unittest.TestCase):

    def test_every_declared_view_has_one(self):
        bare = [f"{grid}: {view.name!r} has no description"
                for grid, presets in DECLARED.items()
                for view in views_module.builtins(presets)
                if not view.help.strip()]
        self.assertEqual(bare, [], "\n" + "\n".join(bare))

    def test_it_found_the_views(self):
        """An empty sweep passes and measures nothing, which reads the same as clean."""
        seen = sum(len(views_module.builtins(p)) for p in DECLARED.values())
        self.assertGreater(seen, 15)

    def test_a_view_built_at_render_time_is_a_preset(self):
        """A view built from what the library holds is a `Preset`, not a plain list."""
        source = (REPO / "console/games.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        plain = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and getattr(node.targets[0], "id", "") == "presets"):
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            for key, value in zip(node.value.keys, node.value.values, strict=True):
                if key is None:
                    continue
                if not (isinstance(value, ast.Call)
                        and getattr(value.func, "attr", "") == "Preset"):
                    plain.append(f"console/games.py:{node.lineno}: a view built here "
                                 "is a plain list, so it has no description")
        self.assertEqual(plain, [], "\n" + "\n".join(plain))


if __name__ == "__main__":
    unittest.main()
