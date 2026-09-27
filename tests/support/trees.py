"""One parsed tree per source file, shared by every checker that reads it.

A checker asks `tree_for` for a path's tree instead of parsing it directly. A checker's
own literal snippet - never a real file on disk - goes through `parse_snippet` instead,
and is not cached. A tree handed out is never mutated; a checker that needs a changed
tree builds its own copy.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Literal, overload

_cache: dict[Path, ast.Module] = {}


def tree_for(path: Path | str) -> ast.Module:
    """The parsed tree for `path`, parsed once and shared with every later caller."""
    resolved = Path(path).resolve()
    tree = _cache.get(resolved)
    if tree is None:
        source = resolved.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(resolved))
        _cache[resolved] = tree
    return tree


@overload
def parse_snippet(source: str, *, filename: str = ...,
                  mode: Literal["exec"] = "exec") -> ast.Module: ...
@overload
def parse_snippet(source: str, *, filename: str = ..., mode: Literal["eval"]) -> ast.Expression: ...
@overload
def parse_snippet(source: str, *, filename: str = ...,
                  mode: Literal["single"]) -> ast.Interactive: ...


def parse_snippet(source: str, *, filename: str = "<snippet>", mode: str = "exec") -> ast.AST:
    """Parse a checker's own literal fixture. Not a real file, and never cached."""
    return ast.parse(source, filename=filename, mode=mode)


def cached() -> dict[Path, ast.Module]:
    """Every path cached so far, keyed by its resolved path."""
    return dict(_cache)


def reparsed(path: Path) -> ast.Module:
    """A fresh parse of `path`, independent of the cache.

    Used only by the test that confirms a cached tree was not mutated in place - it
    would defeat that check to hand back the same cached object.
    """
    resolved = Path(path).resolve()
    source = resolved.read_text(encoding="utf-8", errors="ignore")
    return ast.parse(source, filename=str(resolved))
