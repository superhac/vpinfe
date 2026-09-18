"""Visual Pinball - the app we understand, and the reference for the rest.

10.8 is the supported floor. What a particular install can do is probed rather than
derived from its version; see `capability`.
"""

from __future__ import annotations

from common.apps.contract import App, Claim, Field, Kinds

from .capability import VPXCapability
from .config import VPXConfig
from .launch import VPXLaunch

# What sits beside a table and belongs to it: its settings, a patched script, its
# backglass, a point of view, a saved camera. Here rather than in a generic module
# because it is this program's list and the next app's will differ.
COMPANION_SUFFIXES: tuple[str, ...] = (".ini", ".vbs", ".directb2s", ".pov", ".scv")

# What running Visual Pinball takes, in the order a person meets it: what to run, then
# what to run it with, then the two overrides. The names have shed the `vpx_` prefix -
# a field on a Visual Pinball launcher does not need to say which app it belongs to.
FIELDS: tuple[Field, ...] = (
    Field("bin_path", "Program", path="exe",
          description="The Visual Pinball executable this launcher runs."),
    Field("ini_path", "Configuration File", path="file",
          description="The VPinballX.ini this launcher reads. Leave empty for the one "
                      "Visual Pinball finds itself."),
    Field("launch_env", "Environment",
          description="Variables to set before launching, one NAME=value per line."),
    Field("log_delete_on_start", "Clear the Log on Launch", type="bool", default="false",
          description="Delete Visual Pinball's log before each table, so what is in it "
                      "is about the table that just ran."),
    Field("ini_override", "Override File", path="file",
          description="Launch every table with this ini instead of the usual one."),
    Field("table_ini_override_enabled", "Per-Table Override", type="bool",
          default="false",
          description="Let a table use its own ini file when one sits beside it."),
    Field("table_ini_override_mask", "Per-Table Override Pattern",
          description="How a table's own ini is named, relative to the table."),
)

# `format` is unset: reading a table's OLE container still lives in core, and moving it
# is its own piece of work. A group nothing implements answers None, which every
# consumer already handles.
VPX = App(
    id="vpx",
    name="Visual Pinball X",
    claim=Claim(suffixes=(".vpx",),
                # Stem-matched files that belong to one of its tables.
                companions=COMPANION_SUFFIXES),
    fields=FIELDS,
    kinds=Kinds(),
    launch=VPXLaunch(),
    config=VPXConfig(),
    capability=VPXCapability(),
)
