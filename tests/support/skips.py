"""What a test cannot construct on the platform it is running on.

Skipping is the honest answer where the *setup* is impossible, not the behaviour: the code
under one of these is fine on Windows, the fixture is not.

**Do not name a module here after a standard library one.** It shadows it for everything
that imports this package.
"""
from __future__ import annotations

import sys
import unittest

WINDOWS = sys.platform.startswith("win")

needs_posix_permissions = unittest.skipIf(
    WINDOWS,
    "chmod cannot make a directory read-only for its owner on Windows, so the fixture "
    "this asserts against cannot be built here")
