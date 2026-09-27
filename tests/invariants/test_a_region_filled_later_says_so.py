"""A region the Console fills after the page is drawn says so while it waits.

Its first draw is deferred through `console.busy.fill`, which marks it busy at once,
never through a one-shot `ui.timer` of its own. A one-shot timer that fills no region is
listed below with what it does instead.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tests.support import trees

ROOT = Path(__file__).resolve().parents[2]
CONSOLE = ROOT / "console"
HELPER = "busy.py"

# (file under console/, enclosing function) -> why it is not a region's first draw.
NOT_A_REGION: dict[tuple[str, str], str] = {
    ("page.py", "console_page"):
        "Puts the update count on the Devices entry once the devices have answered: "
        "a badge in the nav, not a region's content.",
    ("settings.py", "build_device_page.rerender"):
        "Schedules a rebuild, and the rebuild draws through the section build that "
        "holds its own region.",
    ("about.py", "_show_to_copy"):
        "Selects the text in a dialog once the dialog has focused itself. Draws nothing.",
    ("games.py", "view_control.wire"):
        "Applies a saved view to a grid already drawn. Draws nothing.",
    ("input_watch.py", "strip"):
        "Starts the readout's script once its element is in the document. Draws nothing.",
}


def _one_shot(node: ast.Call) -> bool:
    return (isinstance(node.func, ast.Attribute)
            and node.func.attr == "timer" and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "ui"
            and any(one.arg == "once"
                    and not (isinstance(one.value, ast.Constant) and one.value.value is False)
                    for one in node.keywords))


def one_shot_timers(tree: ast.AST) -> list[tuple[int, str]]:
    """(line, enclosing function as `outer.inner`) of every one-shot `ui.timer`."""
    found: list[tuple[int, str]] = []

    def visit(node: ast.AST, where: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(child, (*where, child.name))
                continue
            if isinstance(child, ast.Call) and _one_shot(child):
                found.append((child.lineno, ".".join(where)))
            visit(child, where)

    visit(tree, ())
    return found


def _console() -> dict[str, list[tuple[int, str]]]:
    return {str(path.relative_to(CONSOLE)): one_shot_timers(trees.tree_for(path))
            for path in sorted(CONSOLE.rglob("*.py"))}


class ARegionFilledLaterSaysSo(unittest.TestCase):
    def test_a_one_shot_timer_is_the_helper_s_or_listed_with_its_reason(self) -> None:
        stray = [f"console/{name}:{line} in {where or 'the module'}"
                 for name, found in _console().items() if name != HELPER
                 for line, where in found if (name, where) not in NOT_A_REGION]

        self.assertEqual([], stray,
                         "Fill the region through `busy.fill(region, work)`, which marks "
                         "it busy until the work ends. A timer that fills no region goes "
                         "in NOT_A_REGION with the reason.")

    def test_every_listed_timer_is_still_there(self) -> None:
        present = {(name, where) for name, found in _console().items()
                   for _line, where in found}

        self.assertEqual([], sorted(set(NOT_A_REGION) - present))

    def test_the_helper_s_own_is_found(self) -> None:
        self.assertEqual(["fill"], [where for _line, where in _console()[HELPER]])

    def test_only_a_one_shot_timer_is_counted(self) -> None:
        tree = trees.parse_snippet(
            "def page():\n"
            "    ui.timer(0.01, load, once=True)\n"
            "    ui.timer(2.0, tick)\n"
            "    ui.timer(2.0, tick, once=False)\n"
            "    def later():\n"
            "        ui.timer(0, draw, once=True)\n")

        self.assertEqual([(2, "page"), (6, "page.later")], one_shot_timers(tree))


if __name__ == "__main__":
    unittest.main()
