from __future__ import annotations

import configparser
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from common import libdmdutil_service


class LibDmdUtilServiceTests(unittest.TestCase):
    def setUp(self):
        self.config = configparser.ConfigParser()
        self.config["libdmdutil"] = {"enabled": "true"}
        self.iniconfig = mock.Mock(config=self.config)
        self.addCleanup(self._reset_service_state)
        self._reset_service_state()

    def _reset_service_state(self):
        with libdmdutil_service._LOCK:
            libdmdutil_service._CONTROLLER = None
            libdmdutil_service._CURRENT_IMAGE = None

    def test_show_image_uses_default_realdmd_image_when_image_is_missing(self):
        controller = mock.Mock()
        with libdmdutil_service._LOCK:
            libdmdutil_service._CONTROLLER = controller

        self.assertTrue(libdmdutil_service.show_image(self.iniconfig, "/tmp/does-not-exist-realdmd.png"))

        fallback = str(libdmdutil_service._DEFAULT_REALDMD_IMAGE)
        controller.hold_image.assert_called_once_with(fallback)
        controller.clear.assert_not_called()
        self.assertEqual(libdmdutil_service._CURRENT_IMAGE, fallback)

    def test_show_image_uses_default_realdmd_image_when_image_is_none(self):
        controller = mock.Mock()
        with libdmdutil_service._LOCK:
            libdmdutil_service._CONTROLLER = controller

        self.assertTrue(libdmdutil_service.show_image(self.iniconfig, None))

        controller.hold_image.assert_called_once_with(str(libdmdutil_service._DEFAULT_REALDMD_IMAGE))
        controller.clear.assert_not_called()

    def test_show_image_clears_when_requested_and_default_images_are_missing(self):
        controller = mock.Mock()
        with libdmdutil_service._LOCK:
            libdmdutil_service._CONTROLLER = controller

        with TemporaryDirectory() as temp_dir:
            missing_default = Path(temp_dir) / "missing-default.png"
            with mock.patch.object(libdmdutil_service, "_DEFAULT_REALDMD_IMAGE", missing_default):
                self.assertFalse(libdmdutil_service.show_image(self.iniconfig, None))

        controller.clear.assert_called_once_with()
        controller.hold_image.assert_not_called()
        self.assertIsNone(libdmdutil_service._CURRENT_IMAGE)


if __name__ == "__main__":
    unittest.main()
