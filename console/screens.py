"""This machine's screens, described the same way wherever one is picked."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from common.host import display_service
from common.i18n import t
from console import panel


def connected() -> list[Any]:
    """The screens the frontend would open its windows on now, in its order. Blocking."""
    return list(display_service.get_display_monitors(refresh=True))


def described(screen: Any) -> str:
    return t("console.screens.at", width=screen.width, height=screen.height,
             x=screen.x, y=screen.y)


def choices(screens: Sequence[Any], value: str, *, blank: bool) -> dict[str, str]:
    """Each screen by its number, and a stored number no screen answers to."""
    offered = {"": t("word.none")} if blank or not value else {}
    offered.update({str(number): described(screen) for number, screen in enumerate(screens)})
    if value not in offered:
        offered[value] = t("console.screens.numbered", number=value)
    return offered


def mark(screens: Sequence[Any], value: str) -> dict[str, str]:
    if not value or (value.isdigit() and int(value) < len(screens)):
        return {}
    return {"state": "missing", "reason": t("console.screens.not_connected")}


def picker(screens: Sequence[Any], value: Any, save: Callable[[Any], Any], *,
           blank: bool, disabled: bool = False) -> Callable[[], None]:
    """Stores the number, or "" for no window."""
    said = "" if value is None else str(value).strip()
    found = mark(screens, said)

    def pick(event: Any) -> Any:
        chosen = str(event.value or "")
        return save(int(chosen) if chosen else "")

    return panel.select(choices(screens, said, blank=blank), said, pick, disabled=disabled,
                        status=panel.value_state(found.get("state", ""),
                                                 found.get("reason", "")))
