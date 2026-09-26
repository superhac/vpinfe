"""What Add asks before a launcher exists."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from console import launchers

ASKED = [{"key": "bin_path", "label": "Program", "path": "exe", "blank": ""},
         {"key": "ini_path", "label": "Settings File", "path": "file",
          "blank": "Visual Pinball's own"}]


class _Cancelled:
    """The dialog, answered Cancel."""

    def __enter__(self) -> _Cancelled:
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def submit(self, _answer: Any) -> None:
        return None

    def __await__(self) -> Any:
        return _answered(False).__await__()


async def _answered(value: bool) -> bool:
    return value


class EmptyPaths(unittest.IsolatedAsyncioTestCase):
    async def test_an_empty_path_reads_as_the_word_its_app_gives_it(self) -> None:
        hints: list[str] = []

        def field(value: str = "", *, placeholder: str = "", lines: int = 0) -> Mock:
            hints.append(placeholder)
            return Mock(value=value)

        def facts(_target: Any, entries: list[tuple[Any, Any]]) -> None:
            for _label, draw in entries:
                draw()

        with patch.object(launchers.frame, "opened", return_value=_Cancelled()), \
                patch.object(launchers.frame, "field", side_effect=field), \
                patch.object(launchers.frame, "footer"), \
                patch.object(launchers.frame, "cancel"), \
                patch.object(launchers.frame, "answer"), \
                patch.object(launchers.frame, "focus"), \
                patch.object(launchers.frame, "enter_presses"), \
                patch.object(launchers.panel, "facts", side_effect=facts):
            await launchers.ask_name("New", "Add", [], AsyncMock(), asked=ASKED,
                                     placeholder="VPX")

        self.assertEqual(hints, ["VPX", "", "Visual Pinball's own"])


if __name__ == "__main__":
    unittest.main()
