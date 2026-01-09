# PyInstaller hook for gi.repository
# This prevents PyInstaller from trying to analyze gi imports

from PyInstaller.utils.hooks import collect_submodules

# Don't collect anything - gi must come from system
hiddenimports = []
excludedimports = ['gi', 'gi.repository']
