"""A workbench coroutine reaches no blocking library read through a plain call.

A library read can end in a request to the Console's own server, which cannot answer
while the loop is waiting on it. A read handed to `offload.io` is an attribute
reference, not a call, so it is not what this looks for.

Plain calls are followed into the module's top-level functions. A lambda or a nested
function is left alone: it runs whenever something calls it, not where it is written.
"""

from __future__ import annotations

import ast
import pathlib
import unittest
from collections.abc import Iterator

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
WORKBENCH = REPO / "console" / "workbench.py"


def _methods(path: str, name: str) -> dict[str, ast.FunctionDef]:
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == name)
    return {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}


def _self_calls(method: ast.FunctionDef) -> set[str]:
    return {node.func.attr for node in ast.walk(method)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"}


def _closed(methods: dict[str, ast.FunctionDef], seed: set[str]) -> set[str]:
    """`seed`, and every method that reaches one of them through `self`."""
    reached = set(seed)
    calls = {name: _self_calls(method) for name, method in methods.items()}
    grew = True
    while grew:
        grew = False
        for name, callees in calls.items():
            if name not in reached and callees & reached:
                reached.add(name)
                grew = True
    return reached


def _blocking() -> set[str]:
    """Library methods that can end in a request, a cached one included: a cache is
    cold on a fresh page."""
    client = _methods("console/api.py", "ApiClient")
    sends = {name for name, method in client.items() if any(
        (isinstance(node, ast.Attribute) and node.attr == "_session")
        or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "_refuse_the_event_loop")
        for node in ast.walk(method))}
    sends = _closed(client, sends)
    library = _methods("console/data.py", "Library")
    asks = {name for name, method in library.items() if any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "_client" and node.func.attr in sends
        for node in ast.walk(method))}
    return _closed(library, asks)


def _is_library(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "library"
    return (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant)
            and node.slice.value == "library")


def _own(function: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.AST]:
    """The function's own nodes, not those of a lambda or a def inside it."""
    stack: list[ast.AST] = list(function.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _offenders(src: str, blocking: set[str]) -> list[str]:
    tree = ast.parse(src)
    top = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    found = []
    for coroutine in ast.walk(tree):
        if not isinstance(coroutine, ast.AsyncFunctionDef):
            continue
        seen: set[str] = set()
        stack: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, tuple[str, ...]]] = [
            (coroutine, (coroutine.name,))]
        while stack:
            function, trail = stack.pop()
            for node in _own(function):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Attribute) and node.func.attr in blocking \
                        and _is_library(node.func.value):
                    found.append(f"{' > '.join(trail)} > {node.func.attr} "
                                 f"(line {node.lineno})")
                elif isinstance(node.func, ast.Name) and node.func.id in top \
                        and node.func.id not in seen:
                    seen.add(node.func.id)
                    stack.append((top[node.func.id], trail + (node.func.id,)))
    return sorted(set(found))


class WorkbenchReadsOffTheLoop(unittest.TestCase):
    def test_the_check_sees_a_read_three_calls_down(self) -> None:
        blocking = _blocking()
        self.assertIn("vps_releases", blocking)
        chain = (
            "async def draw(context):\n"
            "    _slot(context)\n"
            "def _slot(context):\n"
            "    _match_line(context)\n"
            "def _match_line(context):\n"
            "    context['library'].vps_releases('x', 'wheelArtFiles')\n")
        self.assertEqual(_offenders(chain, blocking),
                         ["draw > _slot > _match_line > vps_releases (line 6)"])

    def test_the_check_passes_a_read_handed_to_a_worker(self) -> None:
        handed = (
            "async def draw(context):\n"
            "    library = context['library']\n"
            "    await offload.io(library.vps_releases, 'x', 'wheelArtFiles')\n"
            "    ui.button(on_click=lambda: library.vps_releases('x', 'y'))\n")
        self.assertEqual(_offenders(handed, _blocking()), [])

    def test_no_workbench_coroutine_reaches_one(self) -> None:
        found = _offenders(WORKBENCH.read_text(encoding="utf-8"), _blocking())
        self.assertEqual(found, [], "a library read from a coroutine goes through "
                                    "`offload.io` or `run.io_bound`")


if __name__ == "__main__":
    unittest.main()
