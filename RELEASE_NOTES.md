## VPinFE Release Notes

### Summary
vpinfe v2.6.1. Fixes tables starting paused on Windows, an upgrade quietly turning cab mode
and DOF back off, and an alt title sorting under the wrong letter.

### What's New
None

### Fixes
- **Frontend** — Windows: a table no longer starts paused. VPX pauses itself whenever its
  window does not have focus, and Windows will not let VPinFE hand focus to a table it just
  started, so the table sat there waiting until you alt-tabbed to it. The frontend windows
  now step aside as the table launches and come back when it exits. Most visible on a
  multi-screen cab, where there is rarely a keyboard to alt-tab with. Applies to launches
  from the wheel and from the Manager UI. Linux and macOS are unchanged.
- **Core** — Upgrading no longer turns cab mode and DOF off. `cabmode`, `enabledof` and
  `splashscreen` each moved to a different section, and the move ran too late to see what
  you had set, so your value was dropped and the default took its place, with nothing in the
  log to explain it. The move now runs first and keeps your value. Anything an earlier build
  already reset needs setting once more.
- **Frontend + Manager UI** — An alt title now sorts where it reads. A table only used its
  alt title when an alt VPS ID was set too, so without one the wheel showed your title but
  sorted and lettered by the original name. The alt title now stands on its own, and is
  still left exactly as you entered it.

### Notes
None
