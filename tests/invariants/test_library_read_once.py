"""Reading the library once, checked two ways.

Constructing a `GameParser` loads every game, so a reload on the next line reads the
whole library a second time. It is invisible at runtime and cheap to reintroduce, which
is why one test watches the parser and the other watches the source for the pattern.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common.games.game_parser import GameParser
from tests.support import library_loader
from tests.support.library import TempTree, write_game

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _tableparser_target(node) -> str | None:
    """The variable name, if this statement is `x = GameParser(...)`."""
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    if not isinstance(node.value, ast.Call):
        return None
    func = node.value.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    if name != "GameParser":
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _is_reload_of(node, name: str) -> bool:
    """Whether this statement is `name.loadGames(...)`."""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "loadGames"
        and isinstance(func.value, ast.Name)
        and func.value.id == name
    )


class LibraryIsReadOnceTests(unittest.TestCase):
    def test_constructing_a_gameparser_reads_each_game_once(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("A Table (Bally 1990)", "B Table (Bally 1991)"):
                folder = root / name
                folder.mkdir()
                (folder / f"{name}.vpx").write_text("")

            real_build = GameParser._build_game
            calls = []

            def counting_build(self, game_dir, **kwargs):
                calls.append(game_dir)
                return real_build(self, game_dir, **kwargs)

            with mock.patch.object(GameParser, "_build_game", counting_build):
                parser = GameParser(root)
                games = parser.getAllGames()

            self.assertEqual(len(games), 2)
            self.assertEqual(len(calls), 2, "the library was read more than once")

    def test_no_caller_reloads_a_freshly_constructed_tableparser(self) -> None:
        """Constructing loads, so a reload on the next line reads the whole library twice.

        Cheap to reintroduce and invisible at runtime, so it is checked in the source
        rather than left to review.
        """
        offenders = []
        for path in sorted(REPO_ROOT.rglob("*.py")):
            if any(part in {".venv", "build", "third_party"} for part in path.parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                body = getattr(node, "body", None)
                if not isinstance(body, list):
                    continue
                for first, second in zip(body, body[1:], strict=False):
                    name = _tableparser_target(first)
                    if name and _is_reload_of(second, name):
                        offenders.append(f"{path.relative_to(REPO_ROOT)}:{second.lineno}")

        self.assertEqual(offenders, [], "TableParser is constructed then reloaded at: "
                                        + ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()


class GamesUnderTests(TempTree):
    """Five callers used to build a parser of their own and rescan everything.

    On the network share a real library lives on that was the whole cold scan again, each
    time, for a library the app already had loaded. `games_under` hands back the cache
    when the root is the configured one - and does not when it is not, because a report
    run against another folder is a different library and must not be answered with the
    wrong games.
    """

    def setUp(self) -> None:
        super().setUp()
        from common.games import game_repository
        self.repo = game_repository
        game_repository._PARSER = None
        self.addCleanup(setattr, game_repository, "_PARSER", None)

    def test_the_configured_root_is_answered_from_the_cache(self) -> None:
        write_game(self.root, "Example", info={"Info": {"Name": "Example"}})
        with mock.patch.object(self.repo, "get_games_path", return_value=str(self.root)):
            first = self.repo.games_under(str(self.root))
            with mock.patch.object(self.repo, "GameParser") as parser:
                again = self.repo.games_under(str(self.root))
                parser.assert_not_called()
        self.assertEqual(len(first), 1)
        self.assertEqual([g.gameDirName for g in again], ["Example"])

    def test_no_root_at_all_means_the_configured_one(self) -> None:
        write_game(self.root, "Example", info={"Info": {"Name": "Example"}})
        with mock.patch.object(self.repo, "get_games_path", return_value=str(self.root)):
            self.repo.games_under("")
            with mock.patch.object(self.repo, "GameParser") as parser:
                self.repo.games_under("")
                parser.assert_not_called()

    def test_another_root_is_parsed_rather_than_guessed_at(self) -> None:
        """The bug this shape avoids: answering a different folder with the cache."""
        other = self.root / "elsewhere"
        other.mkdir()
        write_game(self.root, "Configured", info={"Info": {"Name": "Configured"}})
        write_game(other, "Elsewhere", info={"Info": {"Name": "Elsewhere"}})

        with mock.patch.object(self.repo, "get_games_path", return_value=str(self.root)):
            self.repo.games_under(str(self.root))
            names = [g.gameDirName for g in self.repo.games_under(str(other))]

        self.assertEqual(names, ["Elsewhere"])


class LoaderPatchSitesTests(unittest.TestCase):
    """A test standing a library in front of the app has to reach every module.

    `all_games` is bound by `from ... import`, so patching one module leaves the
    others holding the real function. That is not hypothetical: patching only
    `frontend.api` and then reading `API.entries` - which resolves through
    `frontend.library_resolver` - ran the real loader against whatever root the preceding
    tests had configured, and failed only in a full run.
    """

    def test_the_sites_are_every_module_that_imported_it(self) -> None:
        """So a sixth importer fails here rather than as an intermittent somewhere else."""
        importers = set()
        for path in sorted(REPO_ROOT.glob("*/**/*.py")):
            rel = path.relative_to(REPO_ROOT)
            if rel.parts[0] not in {"common", "frontend", "httpapi", "managerui"}:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            # Module level only. A function-local import resolves through the defining
            # module when it runs, so patching that module already reaches it - and it
            # is not an attribute here to patch.
            for node in tree.body:
                if isinstance(node, ast.ImportFrom) and any(
                        alias.name == "all_games" for alias in node.names):
                    importers.add(".".join(rel.with_suffix("").parts))

        covered = set(library_loader.LOADER_SITES) - {"common.games.game_repository"}
        self.assertEqual(importers, covered,
                         "tests/support/library_loader.py names the modules a test has to "
                         "patch; this is the list of modules that actually import it")

