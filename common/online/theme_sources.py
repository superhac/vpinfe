"""Where themes come from: the catalogs and the single-theme repos a user lists.

A registry is a `themes.json` naming many themes; a repository is one theme standing in
for a registry entry of its own, which since PAR-42 holds only a name and a url. Both
lists are config-file only - see PAR-43 for why neither reaches the Manager UI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from common.config_access import cfg_list

logger = logging.getLogger("vpinfe.common.online.theme_sources")

SECTION = "themes"

# Set on an entry whose name is not known until its manifest is read.
NAMED_BY_MANIFEST = "named_by_manifest"


@dataclass(frozen=True)
class ThemeSources:
    """Every place this install looks for themes, in the order it trusts them."""

    registries: tuple[str, ...] = ()
    repositories: tuple[str, ...] = ()


def from_config(source) -> ThemeSources:
    return ThemeSources(
        registries=tuple(cfg_list(source, SECTION, "registries")),
        repositories=tuple(cfg_list(source, SECTION, "repositories")),
    )


def split_ref(url: str) -> tuple[str, str]:
    """A repo url, and the ref pinned onto it with `#` if there is one.

    `#` cannot occur in a repo path, and `repo#ref` is npm's spelling for the same idea.
    """
    base, _, ref = str(url or "").strip().partition("#")
    return base.strip().rstrip("/"), ref.strip()


def repository_entry(url: str) -> dict:
    base, ref = split_ref(url)
    entry = {"url": base, NAMED_BY_MANIFEST: True}
    if ref:
        entry["ref"] = ref
    return entry


def name_of(index_key: str, entry: dict, manifest: dict) -> str:
    """What a theme is called, from whoever chose it: the entry, the registry key, or -
    for a url, which names nothing - the author's `manifest.json`."""
    declared = str((entry or {}).get("name") or "").strip()
    if declared:
        return declared
    if (entry or {}).get(NAMED_BY_MANIFEST):
        return str((manifest or {}).get("name") or "").strip() or index_key
    return index_key


def merge(parts) -> dict:
    """One index from many sources, first mention winning and the loser logged.

    Settles registry keys only. A repository is keyed by its url until its manifest
    arrives, so `ThemeRegistry.load_theme_manifests` runs the same contest again.
    """
    index: dict = {}
    origins: dict = {}
    for origin, themes in parts:
        for key, entry in (themes or {}).items():
            if key in index:
                logger.warning("Theme '%s' from %s is already provided by %s - keeping the first",
                               key, origin, origins[key])
                continue
            index[key] = entry
            origins[key] = origin
    return index
