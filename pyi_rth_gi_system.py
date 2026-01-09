# PyInstaller runtime hook for gi module - custom import handling
import sys
import os
import importlib.abc
import importlib.machinery

# Store the original sys.path before we modify it
_original_path = sys.path.copy()

# System paths where gi is located
_system_paths = [
    '/usr/lib/python3/dist-packages',
    f'/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages',
]

class GiImportFinder(importlib.abc.MetaPathFinder):
    """Custom finder that redirects gi imports to system site-packages"""

    def find_spec(self, fullname, path, target=None):
        # Only handle gi and gi.repository imports
        if not fullname.startswith('gi'):
            return None

        # Search in system paths for gi
        for sys_path in _system_paths:
            if not os.path.exists(sys_path):
                continue

            # Temporarily add system path to find gi
            if sys_path not in sys.path:
                sys.path.insert(0, sys_path)

            try:
                # Use the default PathFinder to locate the module in system paths
                spec = importlib.machinery.PathFinder.find_spec(fullname, [sys_path])
                if spec is not None:
                    return spec
            finally:
                # Remove the temporary path addition
                if sys_path in sys.path and sys_path not in _original_path:
                    sys.path.remove(sys_path)

        return None

# Install our custom finder at the beginning of sys.meta_path
sys.meta_path.insert(0, GiImportFinder())
