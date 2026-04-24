from __future__ import annotations

from typing import Callable, Optional


def open_missing_tables_dialog(missing_rows: list[dict], on_close: Optional[Callable[[], None]] = None):
    from managerui.pages import tables
    return tables._open_missing_tables_dialog_impl(missing_rows, on_close=on_close)


def open_match_vps_dialog(
    missing_row: dict,
    refresh_missing: Optional[Callable[[], None]] = None,
    refresh_installed: Optional[Callable[[], None]] = None,
    use_own_media_switch=None,
):
    from managerui.pages import tables
    return tables._open_match_vps_dialog_impl(
        missing_row,
        refresh_missing=refresh_missing,
        refresh_installed=refresh_installed,
        use_own_media_switch=use_own_media_switch,
    )
