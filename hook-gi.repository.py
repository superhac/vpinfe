# PyInstaller hook for gi.repository
# This prevents PyInstaller from trying to analyze gi imports

# Don't collect anything - gi must come from system
hiddenimports = []

# Exclude ALL gi modules from the bundle
excludedimports = [
    'gi',
    'gi._constants',
    'gi._error',
    'gi._gi',
    'gi._gi_cairo',
    'gi.repository',
    'gi.repository.Gtk',
    'gi.repository.Gdk',
    'gi.repository.GLib',
    'gi.repository.GObject',
    'gi.repository.Gio',
    'gi.repository.WebKit2',
]
