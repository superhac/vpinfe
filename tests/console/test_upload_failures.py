"""What the page says when files it was sending stop arriving."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from common.i18n import t
from console import uploads


class WhatAStoppedUploadSays(unittest.TestCase):
    def _notified(self, payload: dict) -> mock.Mock:
        with mock.patch.object(uploads, "context"), \
                mock.patch.object(uploads, "ui") as ui:
            uploads.listener(mock.Mock())(SimpleNamespace(args=payload))
        return ui.notify

    def test_an_install_that_could_not_be_reached_is_named(self) -> None:
        notify = self._notified({"status": "error", "unreached": "192.168.1.50"})

        notify.assert_called_once_with(
            t("console.uploads.could_not_read"),
            caption=t("said.why.unreachable_at", host="192.168.1.50"), type="negative")

    def test_an_install_that_refused_says_why_in_its_own_words(self) -> None:
        refused = t("error.uploads.over_size_limit", limit=4)

        notify = self._notified({"status": "error", "said": refused})

        notify.assert_called_once_with(t("console.uploads.could_not_read"),
                                       caption=refused, type="negative")

    def test_the_browser_s_own_words_are_never_shown(self) -> None:
        notify = self._notified({"status": "error", "message": "Failed to fetch"})

        notify.assert_called_once_with(t("console.uploads.could_not_read"), caption="",
                                       type="negative")

    def test_the_script_sends_no_exception_text(self) -> None:
        self.assertNotIn("err.message", uploads._DND_SCRIPT)


if __name__ == "__main__":
    unittest.main()
