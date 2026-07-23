## VPinFE Release Notes

### Summary
vpinfe v2.5.0. Adds drag and drop importing in the Manager UI, backglass (.directb2s) detection and filtering, and a setting to reopen the frontend on the last table you launched.

### What's New
- Drag and drop imports. Drop a table file, an archive (zip, rar, or 7z), or a whole table folder onto the Manager UI and it is analyzed and imported automatically, instead of finding the right upload button first. It works on the Tables page (drop to create a new table, or drop onto a row to import into that table), on the table detail dialog, and on every media cell in the Media view. Archives and folders are scanned for tables, backglasses, ROMs, color files, altsound, PUP packs, music, and media, and each piece goes to its usual place. New tables can be matched to the Virtual Pinball Spreadsheet right in the confirmation dialog, and a table folder brought over from another machine keeps its .info — play stats and per-table settings are merged in, never overwritten. Thanks @MizterB
- Backglass detection and filter. Tables with a .directb2s are now detected, and a new B2S filter lets you find tables that have or are missing a backglass. Thanks @MizterB
- Reopen on last table. A new Restore Last Table setting (on by default) reopens the frontend wheel on the last table you launched instead of the first. It saves the table by path, so your spot survives re-sorting and filtering, and falls back to the first table when the setting is off or the saved table is not in the current view. Thanks @MizterB
- RAR Tool Path setting to point at the unrar/unar tool when it is not on your PATH (blank means auto-detect). RAR imports need an unrar, unar, or bsdtar tool installed; if none is found the app tells you up front instead of failing mid-import. Thanks @MizterB

### Fixes
- Score parser now returns canonical ROM casing on case-insensitive filesystems (macOS), so score reads resolve to the right ROM. Thanks @MizterB
- Test suite isolation and macOS path handling fixes for a clean run on case-insensitive filesystems. Thanks @MizterB

### Notes
- Drag and drop adds two Python dependencies: py7zr (7z, pure Python) and rarfile (rar). rarfile also needs an unrar, unar, or bsdtar binary at runtime — macOS ships bsdtar; on Linux install unar or unrar from your package manager.
