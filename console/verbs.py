"""One icon per verb, named for the verb rather than for the drawing.

Every button takes its drawing from here. A new verb that means what one of these means
takes that one's drawing. The marks at the end say what kind a thing is, and no button
wears one.
"""

from __future__ import annotations

# Leaving without taking what was offered.
CANCEL = "close"
CLOSE = "close"
SKIP = "close"
DISCARD = "close"

# Taking what was offered.
ACCEPT = "check"
DONE = "check"
CHOOSE = "check"

# Bringing something into the library.
ADD = "add"
CREATE = "add"
IMPORT = "upload"
COPY = "content_copy"
DUPLICATE = "content_copy"

# Changing something that is already here.
EDIT = "edit"
RENAME = "edit"
SAVE = "save"
MAKE_DEFAULT = "check_circle"
SPLIT = "call_split"
SHARE = "folder_shared"

# Binding a record to a catalog, and letting it go. The chain is this and nothing else -
# a link that navigates is an anchor and carries no icon at all.
MATCH = "link"
UNMATCH = "delete_outline"

# Taking something away. Emptying a field is not deleting a thing, and the three stay apart.
CLEAR = "backspace"
REMOVE = "remove"
DELETE = "delete_outline"
# Keeping out what a rule would bring back.
EXCLUDE = "close"

# Keeping something out of what is offered, and letting it back in. Nothing is removed.
HIDE = "visibility_off"
UNHIDE = "visibility"

# Answering a question a dialog asked.
KEEP = "check"
FORGET = "remove"
REPLACE = "swap_horiz"
FETCH = "download"
ACTIVATE = "check_circle"
SEND = "send"
RESET = "restart_alt"

# What an extension asked for, where it declares a label and no drawing.
RUN = "play_arrow"

# Moving, looking and running.
BACK = "arrow_back"
NEXT = "arrow_forward"
GO = "arrow_forward"
SEARCH = "search"
STOP = "stop"
RESTORE = "restore"
EXTRACT = "unarchive"
BROWSE = "folder_open"
MERGE = "merge"
OPEN_OUT = "open_in_new"

# Asking for the current state of something held elsewhere.
REFRESH = "refresh"
UPDATE = "system_update_alt"

# Bringing art or a file in, by where it comes from.
FROM_FILE = "upload_file"
FROM_ONLINE = "cloud_download"
ADD_ART = "add_photo_alternate"
ADD_TO_LIST = "playlist_add"

# Working on what is on screen.
ENLARGE = "open_in_full"
TUNE = "tune"
WRAP = "wrap_text"
ROTATE_LEFT = "rotate_left"
ROTATE_RIGHT = "rotate_right"
REVERT = "replay"
PIN = "push_pin"
CONTAIN = "south_west"

# Moving through a list or opening one row of it.
MORE = "more_vert"
DRILL = "chevron_right"
UP = "arrow_upward"
DOWN = "arrow_downward"
COLLAPSE = "keyboard_arrow_up"
EXPAND = "keyboard_arrow_down"

# For a verb with no drawing of its own, by what kind of act it is.
FALLBACK = {"open": OPEN_OUT, "change": EDIT, "add": ADD, "remove": CANCEL}

# A collection whose rules add games. The plain gear is Settings'.
SMART = "settings_suggest"
OPENS_ON = "home"


def declared() -> frozenset[str]:
    """Every drawing this module allows, for the check that nothing else is used."""
    return frozenset(
        value for name, value in globals().items()
        if name.isupper() and isinstance(value, str)
    ) | frozenset(FALLBACK.values())
