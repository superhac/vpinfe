"""Which release of a theme this build can run, read from the author's `vpinfe-theme.json`.

A theme with no such file is one contract 1 release on the default branch, which is every
theme published today. See PAR-42 for why release lines live in the author's repository
rather than the registry.
"""

from __future__ import annotations

from dataclasses import dataclass

# What an author publishes, at the root of their default branch.
INDEX_FILE = "vpinfe-theme.json"

# What a theme speaks when it says nothing - everything published before contracts.
ASSUMED_CONTRACT = 1


@dataclass(frozen=True)
class Release:
    """One line an author publishes: a contract, and the ref that serves it."""

    contract: int
    ref: str
    version: str = ""

    @property
    def is_default_branch(self) -> bool:
        return self.ref in ("", "HEAD", "refs/heads/master", "refs/heads/main")


def bare_ref(ref: str) -> str:
    """A ref spelled the one way both GitHub and Forgejo serve (PAR-43).

    So a branch and a tag of the same name are ambiguous - a naming rule for authors,
    in `theme_publishing.md`, rather than something to solve here.
    """
    reference = str(ref or "").strip() or "HEAD"
    for prefix in ("refs/heads/", "refs/tags/"):
        if reference.startswith(prefix):
            return reference[len(prefix):].strip() or "HEAD"
    return reference


def raw_url(base_url: str, ref: str, path: str) -> str:
    """A raw file URL for a repo at a given ref, on GitHub or on Forgejo."""
    root = str(base_url or "").rstrip("/")
    return f"{root}/raw/{bare_ref(ref)}/{path}"


def index_url(base_url: str) -> str:
    """Always the default branch: it is the one place that names every other place."""
    return raw_url(base_url, "HEAD", INDEX_FILE)


def releases_in(index: dict | None) -> list[Release]:
    """The releases an author declared, newest contract first.

    No usable entries reads as none, so the caller falls back rather than guessing.
    """
    out: list[Release] = []
    for entry in (index or {}).get("releases") or []:
        if not isinstance(entry, dict):
            continue
        try:
            contract = int(entry.get("contract", ASSUMED_CONTRACT))
        except (TypeError, ValueError):
            continue
        ref = str(entry.get("ref") or "").strip()
        if not ref:
            continue
        out.append(Release(contract, ref, str(entry.get("version") or "").strip()))
    return sorted(out, key=lambda r: r.contract, reverse=True)


def pick(releases, serves_contract: int) -> Release | None:
    """The highest release at or below what this build serves, or None if there is none.

    None means don't offer the theme: every line it publishes needs a newer VPinFE.
    """
    for release in sorted(releases or [], key=lambda r: r.contract, reverse=True):
        if release.contract <= serves_contract:
            return release
    return None


def fallback_release() -> Release:
    """What a theme with no index is: one contract 1 line on the default branch."""
    return Release(ASSUMED_CONTRACT, "HEAD")


def for_ref(releases, ref: str) -> Release:
    """The release a pinned ref names, or an assumed one when nothing declares it.

    Matched on the bare form so `v2` finds a line written `refs/heads/v2`.
    """
    wanted = bare_ref(ref)
    for release in releases or []:
        if bare_ref(release.ref) == wanted:
            return release
    return Release(ASSUMED_CONTRACT, ref)
