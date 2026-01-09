# PyInstaller runtime hook for gi module
# Preload gi from system before any other imports
import sys
import os

# Add system site-packages TEMPORARILY to import gi
system_paths = [
    '/usr/lib/python3/dist-packages',
    f'/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages',
]

# Save original sys.path
original_path = sys.path.copy()

# Temporarily add system paths at the beginning
for sys_path in reversed(system_paths):
    if os.path.exists(sys_path):
        sys.path.insert(0, sys_path)

# Pre-import gi and gi.repository to load them from system
try:
    import gi
    import gi.repository
    # Mark them as successfully imported from system
    sys.modules['gi'].__file__ = gi.__file__
except ImportError:
    pass  # gi not available on this system

# Restore original sys.path, but keep gi in sys.modules
sys.path = original_path
