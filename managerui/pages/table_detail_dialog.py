from __future__ import annotations

from typing import Callable, Optional

from managerui.pages.table_dialog_context import TableDialogContext, default_context


def open_table_dialog(
    row_data: dict,
    on_close: Optional[Callable[[], None]] = None,
    context: TableDialogContext | None = None,
):
    context = context or default_context()
    on_close = on_close or context.refresh_tables
    from managerui.pages import tables
    return tables._open_table_dialog_impl(row_data, on_close=on_close)
