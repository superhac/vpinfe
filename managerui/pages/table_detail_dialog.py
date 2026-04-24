from __future__ import annotations

from typing import Callable, Optional


def open_table_dialog(row_data: dict, on_close: Optional[Callable[[], None]] = None):
    from managerui.pages import tables
    return tables._open_table_dialog_impl(row_data, on_close=on_close)
