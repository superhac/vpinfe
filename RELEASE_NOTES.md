## VPinFE Release Notes

### Summary
This is the offical release of vpinfe v2.4.5

### What's New
None

### Fixes
- Commit 6116c3ee9 ("Fix Chrome crashing on Linux with release builds", May 30) changed get_chromium_path() to return [path, using_local_install] instead of a bare string. It has two callers, and only one was updated.  Thanks @phil-gb!

### Notes
