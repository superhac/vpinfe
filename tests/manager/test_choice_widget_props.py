"""No choice widget tells Quasar to emit a value NiceGUI is not expecting back.

`ui.select` with named options sends Quasar `[{label, value: <index>}]` and expects the
whole option object back: `_event_args_to_value` reads `e.args['value']`. Adding
`emit-value` makes Quasar return the option's value instead, which is that index, and an
int reaches none of the branches that method handles.

Four controls carried `emit-value map-options` and raised
`TypeError: 'int' object is not subscriptable` the moment anyone picked a value -
rotation, orientation, paging type and media priority. Rendering was correct throughout,
so nothing caught it until a user changed a setting.

The reason this is a test and not a fixed list: on a `multiple` select the same mistake
does not raise. That branch falls back to the raw argument and then filters it out, so
the selection is silently dropped - no traceback, no log line. The loud version is the
one we happened to make.

Props are read through variables as well as literals, because a shared props string is
exactly where this would hide.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

MANAGER_UI = Path(__file__).resolve().parents[2] / "managerui"

# The NiceGUI elements built on ChoiceElement, which is what maps options to indices.
CHOICE_WIDGETS = {"select", "radio", "toggle"}

# Options shapes whose values NiceGUI maps by index. A list literal is mapped the same
# way, so it is no safer - it is here only because every one we ship is opaque or a dict.
MAPPED_OPTIONS = ("dict", "name:", "call:", "Subscript", "list", "?")


def _link_parents(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node        # type: ignore[attr-defined]


def _string_constants(tree: ast.AST) -> dict[str, str]:
    """Module-and-function-level `name = "..."` assignments, for props passed by name."""
    values: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                values[target.id] = node.value.value
    return values


def _props_applied(node: ast.AST, constants: dict[str, str]) -> str:
    """Every .props(...) argument applied to this call's result, resolved where named."""
    parts: list[str] = []
    current: ast.AST | None = node
    while current is not None:
        parent = getattr(current, "_parent", None)
        if isinstance(parent, ast.Attribute) and parent.attr == "props":
            call = getattr(parent, "_parent", None)
            if isinstance(call, ast.Call):
                for arg in call.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        parts.append(arg.value)
                    elif isinstance(arg, ast.Name):
                        parts.append(constants.get(arg.id, ""))
        current = parent
    return " ".join(parts)


def _options_shape(call: ast.Call) -> str:
    candidates = [kw.value for kw in call.keywords if kw.arg == "options"]
    if not candidates and call.args:
        candidates = [call.args[0]]
    if not candidates:
        return "?"
    value = candidates[0]
    if isinstance(value, ast.Dict):
        return "dict"
    if isinstance(value, (ast.List, ast.ListComp)):
        return "list"
    if isinstance(value, ast.Name):
        return f"name:{value.id}"
    if isinstance(value, ast.Call):
        return f"call:{getattr(value.func, 'attr', getattr(value.func, 'id', '?'))}()"
    return type(value).__name__


def _choice_widgets():
    """(path, line, widget, options shape, props) for every ui.select/radio/toggle."""
    for path in sorted(MANAGER_UI.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        _link_parents(tree)
        constants = _string_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr not in CHOICE_WIDGETS:
                continue
            if getattr(func.value, "id", None) != "ui":
                continue
            yield (path.relative_to(MANAGER_UI), node.lineno, f"ui.{func.attr}",
                   _options_shape(node), _props_applied(node, constants))


class ChoiceWidgetPropTests(unittest.TestCase):
    def test_no_mapped_options_widget_sets_emit_value(self) -> None:
        offenders = [
            f"{path}:{line} {widget} options={shape} props={props!r}"
            for path, line, widget, shape, props in _choice_widgets()
            if "emit-value" in props and shape.startswith(MAPPED_OPTIONS)
        ]
        self.assertEqual(offenders, [], "\n".join([
            "emit-value makes Quasar return the option index, which NiceGUI's handler "
            "cannot read. Remove it - NiceGUI maps the options itself:", *offenders]))

    def test_the_audit_still_sees_the_widgets(self) -> None:
        """A rename that stops this finding anything would make it pass by accident."""
        self.assertGreater(len(list(_choice_widgets())), 20)


if __name__ == "__main__":
    unittest.main()
