"""A write a game folder refuses names the folder, not a file VPinFE made beside its target.

Each write goes into a real folder made read-only, and the failure is read the way the
Console shows it, through `why()`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest import mock

from common.atomic_write import naming_folder
from common.failures import why
from common.games import asset_ops
from common.games.game_service import replace_table
from common.games.info_migration import (
    copy_aside,
    replace_atomic,
    write_backup,
    write_json_atomic,
)
from common.i18n import t
from tests.support.library import TempTree, fake_game, write_game
from tests.support.skips import needs_posix_permissions

GAME_ID = "Refused001"
FOLDER = "Locked Game (Original 2024)"


@needs_posix_permissions
class RefusedWriteTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        info = {"Info": {"Name": "Locked Game"}, "vpinfe": {"game_id": GAME_ID}}
        self.folder = write_game(self.root, FOLDER, info=info)
        self.info = self.folder / f"{FOLDER}.info"
        self.game = fake_game(self.folder, FOLDER, meta=info)
        self.folder.chmod(0o555)
        self.addCleanup(self.folder.chmod, 0o755)
        self.source = self.root / "source"
        self.source.write_text("{}", encoding="utf-8")

    def _assert_names_the_folder(self, write: Callable[[], object]) -> None:
        with self.assertRaises(OSError) as caught:
            write()
        self.assertEqual(why(caught.exception),
                         t("said.why.no_permission_at", path=str(self.folder)))

    def test_an_atomic_write(self) -> None:
        self._assert_names_the_folder(lambda: write_json_atomic(self.info, {}))

    def test_a_copy_put_in_its_place(self) -> None:
        self._assert_names_the_folder(lambda: replace_atomic(self.source, self.info))

    def test_the_restore_point_an_upgrade_keeps(self) -> None:
        self._assert_names_the_folder(lambda: write_backup(self.info, "{}"))

    def test_the_copy_a_restore_sets_aside(self) -> None:
        self._assert_names_the_folder(lambda: copy_aside(self.info))

    def test_a_placed_file(self) -> None:
        source = self.root / "new.directb2s"
        source.write_bytes(b"backglass")

        with mock.patch("common.games.game_repository.catalog",
                        return_value={GAME_ID: self.game}):
            self._assert_names_the_folder(
                lambda: asset_ops.place_file(GAME_ID, "backglass", "", source))

    def test_a_table_replaced_under_its_own_name(self) -> None:
        with mock.patch("common.games.game_service.refresh_game"):
            self._assert_names_the_folder(lambda: replace_table(
                self.folder, f"{FOLDER}.vpx", b"vpx", "vpx", f"{FOLDER}.vpx"))

    def test_a_table_replaced_under_a_new_name(self) -> None:
        with mock.patch("common.games.game_service.refresh_game"):
            self._assert_names_the_folder(lambda: replace_table(
                self.folder, "New Table.vpx", b"vpx", "vpx", f"{FOLDER}.vpx"))


class NamingFolderTests(TempTree):
    def _named(self, filename: Path) -> object:
        with self.assertRaises(OSError) as caught, naming_folder(self.root / "Example.info"):
            raise PermissionError(13, "Permission denied", str(filename))
        return caught.exception.filename

    def test_a_file_made_beside_the_target_names_the_folder(self) -> None:
        self.assertEqual(self._named(self.root / ".vpinfe_write_abc.tmp"), str(self.root))

    def test_the_target_itself_keeps_its_name(self) -> None:
        target = self.root / "Example.info"

        self.assertEqual(self._named(target), str(target))

    def test_a_file_in_another_folder_keeps_its_name(self) -> None:
        elsewhere = self.root / "other" / "source.info"

        self.assertEqual(self._named(elsewhere), str(elsewhere))
