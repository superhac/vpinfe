# PyInstaller hook for webview.platforms.gtk
# This prevents PyInstaller from trying to import gi during build

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Don't try to import gi during the build
hiddenimports = []

# Exclude gi - it will be loaded from system at runtime
excludedimports = ['gi', 'gi.repository']
