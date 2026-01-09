# PyInstaller hook for gi module
# This prevents PyInstaller from trying to analyze or bundle gi

# Don't collect anything - gi must come from system
hiddenimports = []

# Exclude ALL gi submodules from analysis and bundling
excludedimports = [
    'gi',
    'gi._constants',
    'gi._error',
    'gi._gi',
    'gi._gi_cairo',
    'gi.repository',
]
