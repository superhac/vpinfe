"""VPinFE's tests, grouped by what they exercise.

This file is what keeps the group folders from colliding with the packages they test:
without it, `tests/frontend/` is importable as top-level `frontend` and shadows the real
one. With it, every module is `tests.<group>.<name>` and nothing is ambiguous.

`python -m unittest discover tests` finds everything, as it always has.
"""
