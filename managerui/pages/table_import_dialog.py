from __future__ import annotations


def open_import_table_dialog(perform_scan_cb=None):
    from managerui.pages import tables
    return tables._open_import_table_dialog_impl(perform_scan_cb=perform_scan_cb)
