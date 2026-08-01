## VPinFE Release Notes

### Summary
vpinfe v2.6.0. Adds a way to get your data back when a newer VPinFE changes how it stores
things, and fixes a held direction key freezing the wheel.

### What's New
- **Core + Manager UI** — Restore your data after a format change. A newer VPinFE can
  change how table metadata and collections are stored; it keeps a copy of the originals
  first, and this release can put them back. Ratings, favorites, tags, play counts and
  collections all come back. The Tables page offers it when it applies, or use
  `--restore-info`.

### Fixes
- **Frontend** — Holding a direction no longer freezes the wheel. The OS key-repeat rate
  went straight into the carousel, commonly thirty table changes a second, and under that
  flood a theme's animation guard could throw and never clear, leaving the wheel dead until
  restart. Automatic repeat is capped at one move per 150ms; pressing deliberately is never
  throttled and holding still scrolls.
- **Core** — A `.info` file is written through a temporary file and renamed into place, so
  an interrupted write can no longer leave a truncated one behind.
- **Core** — One unreadable `.info` no longer stops the whole library loading. That table is
  left out and named in the log, and its file is left untouched.
- **Manager UI** — Remote launch failures are logged instead of failing silently, and a
  remote launch no longer raises on Linux.
- **Core** — Dropped some dead ROM lookup paths in the score parser.

### Notes
If you try a newer VPinFE preview, install this one first. The backups a newer version
writes are only useful to a release that knows to look for them, and earlier versions do not.
