"""The Tools registry: what it finds, in what order, and what it says when it finds nothing."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from common.host import tools, vpinos

POSIX = not sys.platform.startswith("win")


def _program(folder: Path, name: str, script: str = "exit 0") -> Path:
    """An executable in `folder` that runs `script` under sh."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _works(_path: Path) -> tools.Probe:
    return tools.Probe(True, "1.0")


def _fails(_path: Path) -> tools.Probe:
    return tools.Probe(False, reason=tools.FAILED)


def _tool(probe: Callable[[Path], tools.Probe] = _works,
          names: tuple[str, ...] = ("thing",)) -> tools.Tool:
    return tools.Tool(id="thing", option="tools.thing_path", name="Thing",
                      names={tools.LINUX: names}, probe=probe,
                      hint={tools.LINUX: "tools.rar.hint.linux",
                            tools.VPINOS: "tools.hint.vpinos"})


@unittest.skipUnless(POSIX, "the programs here are shell scripts")
class _OnLinux(unittest.TestCase):
    """A Linux device whose PATH and whose places beyond it are folders of this test's,
    with nothing probed yet and no setting."""

    def setUp(self) -> None:
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        self.root = Path(held.name)
        self.path = self.root / "path"
        self.place = self.root / "place"
        self.path.mkdir()
        self.place.mkdir()
        for patch in (mock.patch.object(tools, "here", return_value=tools.LINUX),
                      mock.patch.object(vpinos, "detected", return_value=False),
                      mock.patch.dict(os.environ, {"PATH": str(self.path)}),
                      mock.patch.dict(tools._PLACES, {tools.LINUX: (str(self.place),)}),
                      mock.patch.dict(tools._probes, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)


class ResolveTests(_OnLinux):
    def test_a_tool_with_nothing_to_run_here_is_not_here(self) -> None:
        asked = mock.Mock(side_effect=_works)
        with mock.patch.object(tools, "here", return_value=tools.WINDOWS):
            found = tools.resolve(_tool(asked), "")

        self.assertIs(found.state, tools.State.NOT_HERE)
        asked.assert_not_called()

    def test_found_on_path(self) -> None:
        program = _program(self.path, "thing")

        found = tools.resolve(_tool(), "")

        self.assertIs(found.state, tools.State.FOUND)
        self.assertEqual(found.path, program)
        self.assertFalse(found.set_here)

    def test_found_where_a_short_path_does_not_look(self) -> None:
        program = _program(self.place, "thing")

        self.assertEqual(tools.resolve(_tool(), "").path, program)

    def test_the_first_name_wins_over_where_a_copy_is(self) -> None:
        _program(self.path, "worse")
        better = _program(self.place, "better")

        self.assertEqual(tools.resolve(_tool(names=("better", "worse")), "").path, better)

    def test_the_setting_wins_when_its_program_runs(self) -> None:
        _program(self.path, "thing")
        mine = _program(self.root / "mine", "thing")

        found = tools.resolve(_tool(), str(mine))

        self.assertEqual(found.path, mine)
        self.assertTrue(found.set_here)

    def test_a_setting_whose_program_does_not_run_is_passed_over(self) -> None:
        found_on_path = _program(self.path, "thing")
        broken = _program(self.root / "mine", "thing")

        def probe(path: Path) -> tools.Probe:
            return _fails(path) if path == broken else _works(path)

        found = tools.resolve(_tool(probe), str(broken))

        self.assertIs(found.state, tools.State.FOUND)
        self.assertEqual(found.path, found_on_path)
        self.assertFalse(found.set_here)

    def test_a_setting_naming_nothing_is_passed_over(self) -> None:
        program = _program(self.path, "thing")

        self.assertEqual(tools.resolve(_tool(), str(self.root / "gone")).path, program)

    def test_found_but_not_running_is_unusable(self) -> None:
        program = _program(self.path, "thing")

        found = tools.resolve(_tool(_fails), "")

        self.assertIs(found.state, tools.State.UNUSABLE)
        self.assertEqual(found.path, program)

    def test_nothing_anywhere_is_missing(self) -> None:
        self.assertIs(tools.resolve(_tool(), "").state, tools.State.MISSING)


class ProbeOnceTests(_OnLinux):
    def test_a_program_is_asked_once_until_the_file_changes(self) -> None:
        program = _program(self.path, "thing")
        asked = mock.Mock(side_effect=_works)
        tool = _tool(asked)

        tools.resolve(tool, "")
        tools.resolve(tool, "")
        self.assertEqual(asked.call_count, 1)

        _program(self.path, "thing", "echo a newer build\nexit 0")
        tools.resolve(tool, "")
        self.assertEqual(asked.call_count, 2)
        self.assertEqual(asked.call_args.args, (program,))

    def test_a_program_that_did_not_work_is_asked_again(self) -> None:
        _program(self.path, "thing")
        asked = mock.Mock(side_effect=_fails)

        tools.resolve(_tool(asked), "")
        tools.resolve(_tool(asked), "")

        self.assertEqual(asked.call_count, 2)


class RowTests(_OnLinux):
    def test_found(self) -> None:
        program = _program(self.path, "thing")

        row = tools.row(tools.resolve(_tool(), ""))

        self.assertEqual(row, {
            "id": "thing", "name": "Thing", "setting": "tools.thing_path",
            "state": "found", "path": str(program), "version": "1.0", "set_here": False,
            "reason": None, "fix": "none", "remedy": None})

    def test_missing_carries_its_remedy(self) -> None:
        row = tools.row(tools.resolve(_tool(), ""))

        self.assertEqual((row["state"], row["fix"]), ("missing", "user"))
        self.assertEqual(row["remedy"], {"key": "tools.rar.hint.linux",
                                         "params": {"tool": "Thing"},
                                         "setting": "tools.thing_path"})

    def test_unusable_says_why_and_how_to_fix_it(self) -> None:
        _program(self.path, "thing")

        row = tools.row(tools.resolve(_tool(_fails), ""))

        self.assertEqual(row["state"], "unusable")
        self.assertEqual(row["reason"], {"key": tools.FAILED, "params": {}})
        self.assertEqual(row["fix"], "user")
        self.assertIsNotNone(row["remedy"])


class HintTests(_OnLinux):
    def test_on_vpinos_the_hint_is_vpinos_own(self) -> None:
        with mock.patch.object(vpinos, "detected", return_value=True):
            said = tools.hint(_tool())

        self.assertTrue(said.startswith("VPinOS doesn't include Thing yet"), said)
        self.assertNotIn("package manager", said)

    def test_elsewhere_on_linux_it_is_the_distribution_s(self) -> None:
        self.assertIn("package manager", tools.hint(_tool()))

    def test_a_hint_names_the_setting_that_points_at_one(self) -> None:
        self.assertIn("RAR Tool Path", tools.hint(tools.RAR))


@unittest.skipUnless(POSIX, "the programs here are shell scripts")
class AskTests(unittest.TestCase):
    def setUp(self) -> None:
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        self.root = Path(held.name)

    def test_both_streams_are_read(self) -> None:
        program = _program(self.root, "talks", 'echo "out $1"\necho "err" >&2')

        said = tools.ask(program, "-version")

        self.assertIn("out -version", said)
        self.assertIn("err", said)

    def test_a_program_that_fails_is_not_the_tool(self) -> None:
        program = _program(self.root, "fails", "exit 3")

        self.assertEqual(tools.probing(lambda path: tools.Probe(True, tools.ask(path)))(
            program).reason, tools.FAILED)

    def test_a_program_that_does_not_finish_timed_out(self) -> None:
        program = _program(self.root, "waits", "sleep 5")

        with mock.patch.object(tools, "TIMEOUT", 0.2):
            probe = tools.probing(lambda path: tools.Probe(True, tools.ask(path)))(program)

        self.assertEqual(probe.reason, tools.TIMED_OUT)

    def test_a_file_that_cannot_be_run_did_not_start(self) -> None:
        text = self.root / "notes"
        text.write_text("not a program", encoding="utf-8")

        probe = tools.probing(lambda path: tools.Probe(True, tools.ask(path)))(text)

        self.assertEqual(probe.reason, tools.DID_NOT_START)


class VersionTests(unittest.TestCase):
    def test_the_first_dotted_number_on_the_first_line(self) -> None:
        for said, version in (
            ("ffmpeg version 9.0.1 Copyright (c) 2000-2026 the FFmpeg developers\n"
             "built with Apple clang version 21.0.0", "9.0.1"),
            ("ffmpeg version 7.1-full_build-www.gyan.dev Copyright (c) 2000-2024", "7.1"),
            ("ffmpeg version N-118000-g1a2b3c4d Copyright (c) 2000-2025\n"
             "built with gcc 14.2.0", ""),
            ("bsdtar 3.5.3 - libarchive 3.7.4 zlib/1.2.12", "3.5.3"),
            ("v1.10.8\n", "1.10.8"),
            ("\n7-Zip [64] 16.02 : Copyright (c) 1999-2016 Igor Pavlov", "16.02"),
            ("", ""),
        ):
            with self.subTest(said=said[:30]):
                self.assertEqual(tools.version_in(said), version)


class RarTests(unittest.TestCase):
    def test_each_program_is_the_rarfile_backend_its_name_says(self) -> None:
        for name, backend in (("unrar", "UNRAR"), ("UnRAR.exe", "UNRAR"),
                              ("unar", "UNAR"), ("7zz", "SEVENZIP2"),
                              ("7z.exe", "SEVENZIP"), ("bsdtar", "BSDTAR"),
                              ("rar-extractor", "UNRAR")):
            with self.subTest(name=name):
                self.assertEqual(tools.rar_backend(Path(name)), backend)

    @unittest.skipUnless(POSIX, "the programs here are shell scripts")
    def test_it_is_probed_with_the_check_rarfile_runs(self) -> None:
        import rarfile

        with tempfile.TemporaryDirectory() as held:
            check = " ".join(rarfile.UNAR_CONFIG["check_cmd"][1:])
            unar = _program(Path(held), "unar",
                            f'[ "$*" = "{check}" ] || exit 1\necho v1.10.8')

            probe = tools.RAR.probe(unar)

        self.assertTrue(probe.works)
        self.assertEqual(probe.version, "1.10.8")

    @unittest.skipUnless(POSIX, "the places are Windows folders named from a variable")
    def test_on_windows_it_looks_where_winrar_and_7zip_install(self) -> None:
        with tempfile.TemporaryDirectory() as held:
            seven = _program(Path(held) / "7-Zip", "7z")
            with (mock.patch.object(tools, "here", return_value=tools.WINDOWS),
                  mock.patch.dict(os.environ, {"PATH": "", "ProgramFiles": held}),
                  mock.patch.object(tools, "probed", return_value=tools.Probe(True))):
                self.assertEqual(tools.resolve(tools.RAR, "").path, seven)


class VPinOSTests(unittest.TestCase):
    def setUp(self) -> None:
        vpinos.detected.cache_clear()
        self.addCleanup(vpinos.detected.cache_clear)

    def _on_linux_reading(self, read: mock.Mock) -> bool:
        with (mock.patch.object(vpinos.sys, "platform", "linux"),
              mock.patch.object(vpinos.platform, "freedesktop_os_release", read)):
            return vpinos.detected()

    def test_vpinos_names_itself(self) -> None:
        self.assertTrue(self._on_linux_reading(
            mock.Mock(return_value={"ID": "vpinos", "ID_LIKE": "debian"})))

    def test_another_distribution_is_not(self) -> None:
        self.assertFalse(self._on_linux_reading(mock.Mock(return_value={"ID": "debian"})))

    def test_no_os_release_is_not(self) -> None:
        self.assertFalse(self._on_linux_reading(mock.Mock(side_effect=OSError)))

    def test_not_linux_is_not_asked(self) -> None:
        with (mock.patch.object(vpinos.sys, "platform", "darwin"),
              mock.patch.object(vpinos.platform, "freedesktop_os_release") as read):
            self.assertFalse(vpinos.detected())
        read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
