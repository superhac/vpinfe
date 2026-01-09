# PyInstaller runtime hook to add system site-packages for gi module
import sys
import os

# Add system site-packages to sys.path so gi can be imported
# APPEND (not insert) so bundled packages take priority
system_site_packages = '/usr/lib/python3/dist-packages'
if os.path.exists(system_site_packages) and system_site_packages not in sys.path:
    sys.path.append(system_site_packages)
