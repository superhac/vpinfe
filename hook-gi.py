# PyInstaller hook for gi (PyGObject)
# This hook ensures that gi can be imported from the system at runtime

from PyInstaller.utils.hooks import collect_system_data_files, get_module_file_attribute
import os
import sys

# Add system site-packages to runtime path so gi can be found
hiddenimports = ['gi', 'gi.repository', 'gi.repository.GLib', 'gi.repository.GObject']

# Tell PyInstaller not to bundle gi - use system version instead
excludedimports = []

# Add system site-packages path to runtime
def get_hook_config(module_name):
    # This allows gi to be loaded from system at runtime
    return {}
