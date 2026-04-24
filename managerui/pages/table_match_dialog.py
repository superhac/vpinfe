from __future__ import annotations

from typing import Callable, Optional

from managerui.pages.table_dialog_context import TableDialogContext, default_context


def open_missing_tables_dialog(
    missing_rows: list[dict],
    on_close: Optional[Callable[[], None]] = None,
    context: TableDialogContext | None = None,
):
    context = context or default_context()
    on_close = on_close or context.refresh_missing
    from managerui.pages import tables
    return tables._open_missing_tables_dialog_impl(missing_rows, on_close=on_close)


def open_match_vps_dialog(
    missing_row: dict,
    refresh_missing: Optional[Callable[[], None]] = None,
    refresh_installed: Optional[Callable[[], None]] = None,
    use_own_media_switch=None,
    context: TableDialogContext | None = None,
):
    context = context or default_context()
    refresh_missing = refresh_missing or context.refresh_missing
    refresh_installed = refresh_installed or context.refresh_tables
    from managerui.pages import tables
    return tables._open_match_vps_dialog_impl(
        missing_row,
        refresh_missing=refresh_missing,
        refresh_installed=refresh_installed,
        use_own_media_switch=use_own_media_switch,
    )
