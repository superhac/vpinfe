"""What the Manager UI's drop zone says when files it was sending stop arriving."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from common.i18n import t
from managerui.pages import dnd_drop_zone

SCRIPT = Path(dnd_drop_zone.__file__).resolve().parent.parent / "static" / "dnd_upload.js"


class WhatAStoppedUploadSays(unittest.TestCase):
    def _notified(self, payload: dict) -> mock.Mock:
        with mock.patch.object(dnd_drop_zone, "ui") as ui, \
                mock.patch.object(dnd_drop_zone, "context"), \
                mock.patch.object(dnd_drop_zone, "_ensure_assets"), \
                mock.patch.object(dnd_drop_zone, "uuid4",
                                  return_value=SimpleNamespace(hex="a1b2c3d4e5f6")):
            dnd_drop_zone.create_drop_zone(label="Drop here",
                                           get_context=dnd_drop_zone.DropContext)
            heard = ui.on.call_args.args[1]
            heard(SimpleNamespace(args={"token": "a1b2c3d4e5f6", "status": "error",
                                        **payload}))
        return ui.notify

    def test_an_install_that_could_not_be_reached_is_named(self) -> None:
        notify = self._notified({"unreached": "192.168.1.50"})

        notify.assert_called_once_with(
            "Upload failed", caption=t("said.why.unreachable_at", host="192.168.1.50"),
            type="negative")

    def test_an_install_that_refused_says_why_in_its_own_words(self) -> None:
        refused = t("error.uploads.upload_gone")

        notify = self._notified({"said": refused})

        notify.assert_called_once_with("Upload failed", caption=refused, type="negative")

    def test_the_browser_s_own_words_are_never_shown(self) -> None:
        notify = self._notified({"message": "Failed to fetch"})

        notify.assert_called_once_with("Upload failed", caption="", type="negative")

    def test_the_script_sends_no_exception_text(self) -> None:
        self.assertNotIn("err.message", SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
