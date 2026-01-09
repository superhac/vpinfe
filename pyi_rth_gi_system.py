# PyInstaller runtime hook for gi module
# Add system site-packages to sys.path so gi can be imported
import sys
import os
import site

# System paths where gi might be located
system_paths = [
    '/usr/lib/python3/dist-packages',
    f'/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages',
    f'/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}/dist-packages',
    f'/usr/local/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages',
    f'/usr/local/lib/python{sys.version_info.major}.{sys.version_info.minor}/dist-packages',
]

# Also add system site-packages from site module
try:
    system_paths.extend(site.getsitepackages())
except:
    pass

# Add system paths to sys.path if they exist and aren't already there
# APPEND them so bundled packages take priority (avoids typing_extensions conflicts)
for sys_path in system_paths:
    if sys_path and os.path.exists(sys_path) and sys_path not in sys.path:
        sys.path.append(sys_path)
