"""What an importer reader notes is bound, kept and returned by whatever calls it."""

from __future__ import annotations

import ast
import pathlib
import unittest

from tests.support import trees

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
IMPORTER = REPO / "extensions" / "library_importer"

FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
SCOPES = (*FUNCTIONS, ast.Lambda, ast.ClassDef)
CARRIES = {"append", "extend", "insert"}

PLANTED = '''
from .source import Note

def read() -> tuple[list, list[Note]]:
    return [], []

def dropped():
    found, _notes = read()
    return found

def replaced():
    found, notes = read()
    notes = []
    return found, notes

def indexed():
    return read()[0]

def ignored():
    read()

def unreturned():
    found, notes = read()
    print(notes)
    return found

def kept():
    found, notes = read()
    notes = [*notes, "more"]
    notes.append("more")
    return found, tuple(notes)

def extended():
    everything = []
    found, said = read()
    everything.extend(said)
    return {"found": found, "notes": everything}

def handed_on():
    return read()
'''


def _mentions_note(node: ast.AST) -> bool:
    return any(isinstance(one, ast.Name) and one.id == "Note" for one in ast.walk(node))


def _readers(parsed: dict[str, ast.Module]) -> dict[tuple[str, str], tuple[int, set[int]]]:
    """(module, function) -> the length of the tuple it answers, and where its notes are."""
    found = {}
    for module, tree in parsed.items():
        for node in tree.body:
            if not isinstance(node, FUNCTIONS):
                continue
            said = node.returns
            if isinstance(said, ast.Subscript) and isinstance(said.value, ast.Name) \
               and said.value.id == "tuple" and isinstance(said.slice, ast.Tuple):
                at = {i for i, one in enumerate(said.slice.elts) if _mentions_note(one)}
                if at:
                    found[(module, node.name)] = (len(said.slice.elts), at)
    return found


def _names(module: str, tree: ast.Module, modules: set[str]) -> tuple[dict, dict]:
    """What a bare name and a module alias stand for, in this module."""
    local = {node.name: (module, node.name) for node in tree.body
             if isinstance(node, FUNCTIONS)}
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            for one in node.names:
                if node.module is None and one.name in modules:
                    aliases[one.asname or one.name] = one.name
                elif node.module in modules:
                    local[one.asname or one.name] = (node.module, one.name)
    return local, aliases


def _own(function: ast.AST) -> list[ast.AST]:
    """The nodes of one function, without those of a function defined inside it."""
    out, stack = [], list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        out.append(node)
        if not isinstance(node, SCOPES):
            stack.extend(ast.iter_child_nodes(node))
    return out


def _loaded(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    return {one.id for one in ast.walk(node)
            if isinstance(one, ast.Name) and isinstance(one.ctx, ast.Load)}


def _returned(nodes: list[ast.AST]) -> set[str]:
    """Every name whose value reaches a return, through what carries it there."""
    reach = set().union(*(_loaded(one.value) for one in nodes if isinstance(one, ast.Return)))
    while True:
        more = set(reach)
        for node in nodes:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
               and node.func.attr in CARRIES and isinstance(node.func.value, ast.Name) \
               and node.func.value.id in reach:
                more |= set().union(*(_loaded(one) for one in node.args))
            elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) \
                    and node.target.id in reach:
                more |= _loaded(node.value)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(one.id in reach for target in targets for one in ast.walk(target)
                       if isinstance(one, ast.Name)):
                    more |= _loaded(node.value)
        if more == reach:
            return reach
        reach = more


def _bound(nodes: list[ast.AST], name: str) -> list[tuple[ast.stmt, ast.AST | None]]:
    """Every statement in the function that binds this name, with the value it binds."""
    out: list[tuple[ast.stmt, ast.AST | None]] = []
    for node in nodes:
        value: ast.AST | None = None
        targets: list[ast.AST]
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            targets = [node.target]
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            targets = [one.optional_vars for one in node.items if one.optional_vars]
        else:
            continue
        if any(isinstance(one, ast.Name) and one.id == name and isinstance(one.ctx, ast.Store)
               for target in targets for one in ast.walk(target)):
            out.append((node, value))
    return out


def _offenders(parsed: dict[str, ast.Module]) -> tuple[list[str], int]:
    """Every call to a reader that loses its notes, and how many calls were looked at."""
    readers = _readers(parsed)
    found, looked = [], 0
    for module, tree in parsed.items():
        local, aliases = _names(module, tree, set(parsed))
        for function in ast.walk(tree):
            if not isinstance(function, FUNCTIONS):
                continue
            nodes = _own(function)
            parents = {child: node for node in nodes for child in ast.iter_child_nodes(node)}
            for call in nodes:
                if not isinstance(call, ast.Call):
                    continue
                if isinstance(call.func, ast.Name):
                    target = local.get(call.func.id)
                elif isinstance(call.func, ast.Attribute) \
                        and isinstance(call.func.value, ast.Name) \
                        and call.func.value.id in aliases:
                    target = (aliases[call.func.value.id], call.func.attr)
                else:
                    target = None
                if target not in readers:
                    continue
                looked += 1
                size, at = readers[target]
                where = f"{module}:{call.lineno} {function.name}: {target[0]}.{target[1]}"
                parent = parents.get(call)
                if isinstance(parent, ast.Return):
                    continue
                if not (isinstance(parent, ast.Assign) and len(parent.targets) == 1
                        and isinstance(parent.targets[0], ast.Tuple)
                        and len(parent.targets[0].elts) == size):
                    found.append(f"{where} is not unpacked, so its notes are not kept")
                    continue
                reach = _returned(nodes)
                for i in sorted(at):
                    held = parent.targets[0].elts[i]
                    if not isinstance(held, ast.Name) or held.id.startswith("_"):
                        found.append(f"{where} binds its notes to {ast.unparse(held)}, "
                                     "which nothing keeps")
                        continue
                    for again, value in _bound(nodes, held.id):
                        if again is not parent and again.lineno > parent.lineno \
                           and held.id not in _loaded(value):
                            found.append(f"{where} binds its notes to {held.id}, which "
                                         f"line {again.lineno} replaces")
                            break
                    else:
                        if held.id not in reach:
                            found.append(f"{where} binds its notes to {held.id}, which "
                                         "never reaches a return")
    return found, looked


def _importer() -> dict[str, pathlib.Path]:
    return {path.stem: path for path in sorted(IMPORTER.glob("*.py"))}


class AnImporterNoteReachesWhatItReturns(unittest.TestCase):
    def test_the_check_sees_every_planted_drop(self) -> None:
        found, looked = _offenders({"planted": trees.parse_snippet(PLANTED)})

        self.assertEqual(looked, 8)
        self.assertEqual(sorted(one.split(":")[1].split(" ")[1] for one in found),
                         ["dropped", "ignored", "indexed", "replaced", "unreturned"])

    def test_it_finds_the_readers(self) -> None:
        parsed = {module: trees.tree_for(path) for module, path in _importer().items()}

        self.assertLessEqual({("pinballx", "read_database"), ("pinballx", "read_config"),
                              ("pinballx", "_database_text"), ("gamestats", "read"),
                              ("gamestats", "_text"), ("registry", "read"),
                              ("registry", "read_text")},
                             set(_readers(parsed)))

    def test_no_reader_in_the_importer_loses_its_notes(self) -> None:
        parsed = {module: trees.tree_for(path) for module, path in _importer().items()}
        found, looked = _offenders(parsed)

        self.assertGreaterEqual(looked, 6)
        self.assertEqual(found, [], "a reader's notes are bound, kept and returned, so "
                                    "the summary says everything the importer noticed")


if __name__ == "__main__":
    unittest.main()
