"""`python -m tests`: it runs what `unittest discover` runs, each shard in dirs of its own."""

from __future__ import annotations

import io
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

import tests
from tests import __main__ as runner

PASSING = """
    import unittest

    class T(unittest.TestCase):
        def test_passes(self):
            pass

        @unittest.skip("not here")
        def test_skipped(self):
            pass
"""
FAILING = """
    import unittest

    class T(unittest.TestCase):
        def test_fails(self):
            self.assertEqual(1, 2)
"""
BROKEN = "raise RuntimeError('broken at import')\n"


def _cases(suite: unittest.TestSuite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _cases(test)
        else:
            yield test


class _Probe(unittest.TestCase):
    """A package of its own in a temp dir, gone from `sys.modules` and `sys.path` after."""

    PACKAGE = "runnerprobe0"

    def setUp(self) -> None:
        self.top = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.addCleanup(self._unload)

    def _unload(self) -> None:
        for name in [n for n in sys.modules if n.split(".")[0] == self.PACKAGE]:
            del sys.modules[name]
        while str(self.top) in sys.path:
            sys.path.remove(str(self.top))
        sys.path_importer_cache.pop(str(self.top), None)

    def write(self, files: dict[str, str]) -> None:
        for relative, text in files.items():
            path = self.top / self.PACKAGE / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text), encoding="utf-8")


class DiscoveryTests(_Probe):
    def test_it_finds_what_unittest_discover_loads_in_the_order_it_loads_them(self) -> None:
        self.write({"__init__.py": "", "test_b.py": PASSING, "test_a.py": PASSING,
                    "testc.py": PASSING, "helper.py": PASSING, "test-d.py": PASSING,
                    "inner/__init__.py": "", "inner/test_e.py": PASSING,
                    "loose/test_f.py": PASSING})
        start = self.top / self.PACKAGE
        loaded = unittest.TestLoader().discover(str(start), top_level_dir=str(self.top))
        discovered = list(dict.fromkeys(type(test).__module__ for test in _cases(loaded)))

        self.assertEqual(["runnerprobe0.inner.test_e", "runnerprobe0.test_a",
                          "runnerprobe0.test_b", "runnerprobe0.testc"], discovered)
        self.assertEqual(discovered, runner.modules(start, self.top))


class RunTests(_Probe):
    def test_a_module_that_raises_on_import_fails_and_the_next_one_still_runs(self) -> None:
        self.write({"__init__.py": "", "test_a.py": BROKEN, "test_b.py": PASSING,
                    "test_c.py": FAILING})
        records: list[dict] = []
        runner.run_modules([f"{self.PACKAGE}.test_{x}" for x in "abc"], io.StringIO(),
                           records.append, top=self.top)
        broken, passing, failing = records

        self.assertEqual((1, 1), (broken["tests"], broken["errors"]))
        self.assertIn("RuntimeError: broken at import", broken["report"])
        self.assertEqual((2, 1, ""), (passing["tests"], passing["skipped"], passing["report"]))
        self.assertEqual(1, failing["failures"])
        self.assertTrue(failing["report"].startswith("=" * 70), failing["report"])
        self.assertIn("AssertionError: 1 != 2", failing["report"])

    def test_every_module_is_imported_before_any_test_runs(self) -> None:
        self.write({"__init__.py": "state = 'as imported'\nseen = []\n",
                    "test_a.py": """
                        import unittest

                        import runnerprobe0

                        class T(unittest.TestCase):
                            def test_leaves_state_behind(self):
                                runnerprobe0.state = 'left by test_a'
                    """,
                    "test_b.py": """
                        import unittest

                        import runnerprobe0

                        AT_IMPORT = runnerprobe0.state

                        class T(unittest.TestCase):
                            def test_reads_what_its_import_saw(self):
                                runnerprobe0.seen.append(AT_IMPORT)
                    """})
        runner.run_modules([f"{self.PACKAGE}.test_a", f"{self.PACKAGE}.test_b"],
                           io.StringIO(), [].append, top=self.top)
        self.assertEqual(["as imported"], sys.modules[self.PACKAGE].seen)

    def test_every_class_is_torn_down_once(self) -> None:
        tearing = """
            import unittest

            from runnerprobe0 import torn

            class T(unittest.TestCase):
                @classmethod
                def tearDownClass(cls):
                    torn.append(__name__)

                def test_passes(self):
                    pass
        """
        self.write({"__init__.py": "torn = []\n", "test_a.py": tearing, "test_b.py": tearing})
        runner.run_modules([f"{self.PACKAGE}.test_a", f"{self.PACKAGE}.test_b"],
                           io.StringIO(), [].append, top=self.top)
        self.assertEqual(["runnerprobe0.test_a", "runnerprobe0.test_b"],
                         sys.modules[self.PACKAGE].torn)


class PlanTests(unittest.TestCase):
    def test_the_longest_goes_first_onto_the_process_with_the_least(self) -> None:
        shards = runner.plan(["a", "b", "c", "d", "e"],
                             {"a": 1.0, "b": 10.0, "c": 6.0, "d": 5.0, "e": 1.0}, 2)
        self.assertEqual([["a", "b", "e"], ["c", "d"]], [shard.modules for shard in shards])
        self.assertEqual([12.0, 11.0], [shard.planned for shard in shards])

    def test_a_module_never_timed_weighs_by_whether_it_drives_a_browser(self) -> None:
        for source in ("from tests.support.live_instance import LiveInstance\n",
                       "from tests.support.browser_session import BrowserSession\n",
                       "import os\nfrom tests.support import browser_session\n"):
            self.assertEqual(runner.UNTIMED_BROWSER_MODULE, runner.guess(source), source)
        for source in ("from tests.support.library import write_game\n",
                       "# a comment that names tests.support.live_instance\n"):
            self.assertEqual(runner.UNTIMED_MODULE, runner.guess(source), source)

    def test_a_recorded_time_outweighs_the_guess(self) -> None:
        name = "tests.theming.test_render_smoke"
        self.assertEqual({name: 3.0}, runner.weights([name], {name: 3.0}))

    def test_a_module_that_is_gone_loses_its_recorded_time(self) -> None:
        kept = runner.recorded_after(
            {"tests.invariants.test_bootstrap_runs": 5.0, "tests.nowhere.test_gone": 2.0},
            {"tests.invariants.test_bootstrap_runs": 0.5})
        self.assertEqual({"tests.invariants.test_bootstrap_runs": 0.5}, kept)


class EnvironmentTests(unittest.TestCase):
    def test_each_process_gets_a_config_dir_and_a_temp_dir_of_its_own(self) -> None:
        base = {"VPINFE_CONFIG_DIR": "/shared/config", "TMPDIR": "/shared/tmp",
                "PATH": "/bin"}
        root = Path("/run")
        first, second = (runner.shard_environment(base, root, n) for n in (0, 1))
        for key in ("VPINFE_CONFIG_DIR", "TMPDIR", "TEMP", "TMP"):
            self.assertNotEqual(first[key], second[key], key)
            self.assertNotEqual(base.get(key), first[key], key)
            self.assertTrue(Path(first[key]).is_relative_to(root), key)
        self.assertEqual("/bin", first["PATH"])

    def test_a_config_dir_the_caller_set_is_refused_with_more_than_one_process(self) -> None:
        why = runner.refusal(4, "/mine")
        self.assertIsNotNone(why)
        self.assertIn("VPINFE_CONFIG_DIR is set to /mine", str(why))
        self.assertIn("-j 1", str(why))
        self.assertIsNone(runner.refusal(1, "/mine"))
        self.assertIsNone(runner.refusal(4, None))

    def test_the_refusal_comes_before_anything_runs(self) -> None:
        with mock.patch.object(tests, "CALLER_CONFIG_DIR", "/mine"), \
                mock.patch.object(runner, "run_modules") as ran, \
                mock.patch.object(runner, "in_processes") as spawned, \
                redirect_stderr(io.StringIO()) as said:
            code = runner.main(["-j", "2", str(runner.PACKAGE / "invariants")])
        self.assertEqual(2, code)
        ran.assert_not_called()
        spawned.assert_not_called()
        self.assertIn("VPINFE_CONFIG_DIR is set to /mine", said.getvalue())


class ReportTests(unittest.TestCase):
    PASSED = {"tests": 3, "failures": 0, "errors": 0, "skipped": 1, "expected_failures": 0,
              "unexpected_successes": 0}

    def test_the_closing_lines_and_exit_code_are_unittest_s(self) -> None:
        failed = {**self.PASSED, "failures": 1, "errors": 2}
        self.assertEqual((["Ran 3 tests in 1.000s", "", "OK (skipped=1)"], 0),
                         runner.summary([self.PASSED], 1.0, 0))
        self.assertEqual((["Ran 6 tests in 1.000s", "",
                           "FAILED (failures=1, errors=2, skipped=2)"], 1),
                         runner.summary([self.PASSED, failed], 1.0, 0))
        self.assertEqual((["Ran 0 tests in 0.500s", "", "NO TESTS RAN"], 5),
                         runner.summary([], 0.5, 0))

    def test_a_process_that_stopped_fails_the_run(self) -> None:
        lines, code = runner.summary([self.PASSED], 1.0, 1)
        self.assertEqual("FAILED (processes stopped=1, skipped=1)", lines[-1])
        self.assertEqual(1, code)


class LeakGateTests(unittest.TestCase):
    def _root(self, tmp: str, *, number: int = 0) -> Path:
        root = Path(tmp)
        (root / f"config{number}").mkdir()
        (root / f"tmp{number}").mkdir()
        return root

    def test_a_leftover_entry_fails_the_shard_and_names_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            (root / "tmp0" / "leaked.txt").write_text("x")
            shard = runner.Shard(0)

            runner._clean(root, [shard])

            self.assertFalse((root / "tmp0").exists())
        self.assertIn("leaked.txt", shard.stopped)

    def test_an_empty_temp_root_leaves_the_shard_passing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            shard = runner.Shard(0)

            runner._clean(root, [shard])

        self.assertEqual("", shard.stopped)

    def test_a_leak_does_not_override_why_the_shard_already_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(tmp)
            (root / "tmp0" / "leaked.txt").write_text("x")
            shard = runner.Shard(0)
            shard.stopped = "Process 1 of 1 exited with code 1 after its last module."

            runner._clean(root, [shard])

        self.assertIn("exited with code 1", shard.stopped)
        self.assertIn("leaked.txt", shard.stopped)


if __name__ == "__main__":
    unittest.main()
