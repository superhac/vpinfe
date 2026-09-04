"""Finding themes to install, from every source the user has configured."""

import concurrent.futures
import logging
import os
from io import BytesIO
from typing import Any

from common.app_version import get_version
from common.online import theme_releases, theme_sources
from common.online.theme_installer import ThemeInstallStore
from common.online.theme_registry_client import ThemeRegistryClient, ThemeRegistryError
from common.paths import CONFIG_DIR, get_ini_config
from common.values import parse_version

# What a theme states as the oldest build it runs on. Named here rather than imported
# from the frontend: the installer runs on installs that have no frontend at all.
MIN_VERSION_KEY = "min_vpinfe"


class ThemeVersionError(ThemeRegistryError):
    """A theme that needs a newer VPinFE than the one asked to install it."""

logger = logging.getLogger("vpinfe.common.online.themes")

# The highest theme contract this build serves.
CURRENT_CONTRACT = 2


class ThemeRegistry:
    """Every theme available to install, gathered from all configured sources."""

    def __init__(self, timeout: int = 10, serves_contract: int = CURRENT_CONTRACT,
                 sources: theme_sources.ThemeSources | None = None):
        # Read at load time, not here: constructing a registry should not touch the disk,
        # and every test that builds one would otherwise need a config file.
        self.sources = sources
        # The highest contract this build can run. A theme offering only something newer
        # is not listed, which is the protection a shipped 2.x client cannot give itself.
        self.serves_contract = serves_contract
        self.timeout = timeout
        self.client = ThemeRegistryClient(timeout=timeout)
        self.themes_index: dict[str, Any] = {}
        self.themes: dict[str, Any] = {}

        self.base_dir = str(CONFIG_DIR)
        self.themes_dir = os.path.join(self.base_dir, "themes")
        self.store = ThemeInstallStore(self.themes_dir)

    # =========================================================
    # NETWORK
    # =========================================================

    def _fetch_json(self, url: str) -> dict:
        return self.client.fetch_json(url)

    def _download_zip(self, url: str, max_retries: int = 3) -> BytesIO:
        return self.client.download_zip(url, max_retries=max_retries)

    # =========================================================
    # REGISTRY
    # =========================================================

    def _catalog(self, url: str) -> dict:
        """The themes a registry names, or {} with a reason logged.

        One unreachable or malformed source must not cost the user the others - that is
        the whole point of there being more than one.
        """
        try:
            data = self._fetch_json(url)
        except Exception as exc:
            logger.error("Theme registry %s: %s", url, exc)
            return {}
        themes = data.get("themes")
        if not isinstance(themes, dict):
            logger.error("Theme registry %s: no themes object, so nothing to read", url)
            return {}
        return themes

    def load_registry(self):
        sources = self.sources
        if sources is None:
            sources = theme_sources.from_config(get_ini_config())

        # Repositories first: naming one repo is a more specific act than subscribing to
        # a catalog, so a user's own theme wins a name collision with a published one.
        # Keyed by url until its manifest says what it is really called.
        parts = [(url, {url: theme_sources.repository_entry(url)})
                 for url in sources.repositories if url.strip()]
        parts += [(url, self._catalog(url)) for url in sources.registries if url.strip()]

        index = theme_sources.merge(parts)
        if not index and parts:
            raise ThemeRegistryError("No theme source could be read.")

        self.themes_index = index

    @staticmethod
    def _base_url(entry: dict) -> str:
        """Where a theme lives, under either registry shape.

        The new registry holds a name and a url and nothing else, so that registration
        happens once and every later release is a merge in the author's own repo. The
        old one is still read unchanged, which is what lets this ship before the
        registry moves.
        """
        return str(entry.get("url") or entry.get("theme_base_url") or "").strip()

    def _resolve_release(self, base_url: str, entry: dict):
        """The release this build should run, and where its manifest is.

        Asks the author's index first. A theme without one is what every published theme
        is today: a single contract 1 line on the default branch, whose manifest url the
        old registry names outright.
        """
        index = None
        try:
            index = self._fetch_json(theme_releases.index_url(base_url))
        except Exception:
            index = None

        declared = theme_releases.releases_in(index)

        pinned = str(entry.get("ref") or "").strip()
        if pinned:
            # The user named an exact ref, so release selection is theirs. The gate still
            # applies where it can: if a declared line serves this ref, its contract is
            # known and a build that cannot run it still declines.
            chosen = theme_releases.for_ref(declared, pinned)
            if chosen.contract > self.serves_contract:
                return None, None, index
            return chosen, theme_releases.raw_url(base_url, pinned, "manifest.json"), index

        if declared:
            chosen = theme_releases.pick(declared, self.serves_contract)
            if chosen is None:
                return None, None, index
            return chosen, theme_releases.raw_url(base_url, chosen.ref, "manifest.json"), index

        legacy_url = str(entry.get("theme_manifest_url") or "").strip()
        chosen = theme_releases.fallback_release()
        return chosen, legacy_url or theme_releases.raw_url(base_url, "HEAD", "manifest.json"), index

    def load_theme_manifests(self, default_only: bool = False):
        if not self.themes_index:
            raise ThemeRegistryError("Registry not loaded.")

        # Reset loaded themes for this pass.
        self.themes = {}

        theme_jobs = []
        for theme_key, theme_info in self.themes_index.items():
            if default_only and not theme_info.get("default_install", False):
                continue
            base_url = self._base_url(theme_info)
            if not base_url:
                continue
            theme_jobs.append((theme_key, theme_info, base_url))

        def _load_one(job):
            theme_key, theme_info, base_url = job
            release, manifest_url, index = self._resolve_release(base_url, theme_info)
            if release is None:
                # Every release this theme offers needs a newer VPinFE than this one.
                logger.debug("%s offers nothing this build can run", theme_key)
                return theme_key, theme_info, None, None, None
            manifest = self._fetch_json(manifest_url)
            self._validate_manifest(theme_key, manifest)
            # Only now can a repository say what it is called, so the key settles here.
            return (theme_sources.name_of(theme_key, theme_info, manifest),
                    theme_info, manifest, release, index)

        # Network-bound workload: parallelize manifest fetches. Submitted all at once, then
        # collected in source order rather than completion order - a repository's name is
        # only known once its manifest lands, so this is where two sources can turn out to
        # mean the same theme, and which one wins must not depend on who answered first.
        max_workers = min(8, max(1, len(theme_jobs)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {job[0]: pool.submit(_load_one, job) for job in theme_jobs}
            for provisional, future in futures.items():
                try:
                    theme_key, theme_info, manifest, release, index = future.result()
                    if manifest is None:
                        continue
                    if theme_key in self.themes:
                        logger.warning("Two sources both provide '%s' - keeping the first, "
                                       "ignoring %s", theme_key, self._base_url(theme_info))
                        continue
                    twin = next((k for k in self.themes if k.lower() == theme_key.lower()), None)
                    if twin:
                        logger.warning("'%s' and '%s' differ only in case, so both install",
                                       theme_key, twin)
                    self.themes[theme_key] = {
                        "registry_info": theme_info,
                        "manifest": manifest,
                        "release": release,
                        "index": index,
                    }
                except Exception as e:
                    logger.error("%s: %s", provisional, e)

    # =========================================================
    # VALIDATION
    # =========================================================

    def _validate_manifest(self, theme_key: str, manifest: dict):
        required_fields = [
            "name",
            "version",
            "author",
            "description",
            "preview_image",
            "type",
        ]
        # `windows` names the screens; `supported_screens` only ever counted them. A
        # theme has to say one or the other, and a 2.x theme said the count.
        if "windows" not in manifest:
            required_fields.append("supported_screens")

        for field in required_fields:
            if field not in manifest:
                raise ThemeRegistryError(
                    f"{theme_key} missing required field '{field}'"
                )

        if manifest["type"] not in ("desktop", "cab", "both"):
            raise ThemeRegistryError(
                f"{theme_key} invalid type '{manifest['type']}'"
            )

    # =========================================================
    # INSTALL HELPERS
    # =========================================================

    def _get_repo_name(self, base_url: str) -> str:
        return self.store.repo_name(base_url)

    def _get_installed_version(self, theme_key: str) -> str | None:
        theme_data = self.themes.get(theme_key)
        if not theme_data:
            return None

        folder_name = self.get_installed_folder(theme_key)
        if not folder_name:
            return None

        return self.store.installed_version(theme_key, self._base_url(theme_data["registry_info"]))

    def _is_version_newer(self, remote: str, local: str) -> bool:
        return self.store.is_version_newer(remote, local)

    def _build_zip_url(self, base_url: str, ref: str = "refs/heads/master") -> str:
        return self.store.build_zip_url(base_url, ref)

    # =========================================================
    # INSTALLATION
    # =========================================================

    def auto_install_defaults(self):
        """Auto-install all themes marked as default_install=True"""
        for key, theme in self.themes.items():
            if theme["registry_info"].get("default_install", False):
                self.install_theme(key)


    def install_theme(self, theme_key: str, force: bool = False):
        if theme_key not in self.themes:
            raise ThemeRegistryError(f"Theme '{theme_key}' not loaded.")

        theme_data = self.themes[theme_key]
        manifest = theme_data["manifest"]
        base_url = self._base_url(theme_data["registry_info"])
        release = theme_data.get("release") or theme_releases.fallback_release()

        remote_version = manifest["version"]
        local_version = self._get_installed_version(theme_key)

        # Before anything is downloaded, and before the up-to-date check: a theme that
        # needs a newer build than this one is not an update, and installing it over a
        # working theme leaves the frontend rendering against a contract this build does
        # not serve. The theme's own gate decides which contract it *gets*; nothing was
        # deciding whether it should arrive at all.
        needs = parse_version(manifest.get(MIN_VERSION_KEY))
        running = parse_version(get_version())
        if needs and running and needs > running:
            raise ThemeVersionError(
                f"{theme_key} needs VPinFE {manifest[MIN_VERSION_KEY]} and this is "
                f"{get_version()}")

        if not force and local_version:
            if not self._is_version_newer(remote_version, local_version):
                logger.debug("%s already up to date (%s)", theme_key, local_version)
                return

        logger.info("Installing %s v%s", theme_key, remote_version)

        zip_url = self._build_zip_url(base_url, release.ref)
        zip_data = self._download_zip(zip_url)

        self.store.install_zip(theme_key, base_url, zip_data)

        logger.info("Installed %s", theme_key)


    # =========================================================
    # UPDATE & STATUS
    # =========================================================

    def check_for_updates(self, theme_keys: list[str] | None = None) -> dict[str, dict]:
        if theme_keys is None:
            theme_keys = list(self.themes.keys())

        updates = {}
        for key in theme_keys:
            if key not in self.themes:
                continue

            remote_version = self.themes[key]["manifest"]["version"]
            local_version = self._get_installed_version(key)

            updates[key] = {
                "installed_version": local_version,
                "remote_version": remote_version,
                "update_available": (
                    local_version is None or self._is_version_newer(remote_version, local_version)
                )
            }

        return updates

    def is_installed(self, theme_key: str) -> bool:
        return self._get_installed_version(theme_key) is not None

    def get_installed_folder(self, theme_key: str) -> str | None:
        """
        Returns the actual folder name under `themes/` for the given theme.
        None if theme is not installed.
        """
        # Check for exact theme_key match first (post-rename)
        theme_data = self.themes.get(theme_key)
        base_url = self._base_url(theme_data["registry_info"]) if theme_data else None
        return self.store.installed_folder(theme_key, base_url)

    # =========================================================
    # DELETE
    # =========================================================

    def delete_theme(self, theme_key: str):
        """Delete an installed theme. Raises if theme has default_install=True."""
        theme_data = self.themes.get(theme_key)
        if theme_data and theme_data["registry_info"].get("default_install", False):
            raise ThemeRegistryError(f"Cannot delete default theme '{theme_key}'")

        folder = self.get_installed_folder(theme_key)
        if folder:
            self.store.delete(folder)
        else:
            raise ThemeRegistryError(f"Theme '{theme_key}' is not installed")

    # =========================================================
    # GETTERS
    # =========================================================

    def get_themes(self) -> dict[str, Any]:
        return self.themes


# =============================================================
# MAIN TEST
# =============================================================

def main():
    logger.debug("Initializing Theme Manager...")

    registry = ThemeRegistry()

    registry.load_registry()
    registry.load_theme_manifests()

    logger.debug("Themes directory: %s", registry.themes_dir)

    logger.debug("Loaded Themes and Installation Status:")
    for key in registry.get_themes():
        installed_status = "Installed" if registry.is_installed(key) else "Not installed"
        folder_name = registry.get_installed_folder(key)
        logger.debug(" - %s (%s) -> folder: %s", key, installed_status, folder_name)

    logger.debug("Auto installing default themes...")
    registry.auto_install_defaults()

    logger.debug("Checking for updates...")
    updates = registry.check_for_updates()
    for key, info in updates.items():
        status = "UPDATE AVAILABLE" if info["update_available"] else "Up to date"
        logger.info(
            "%s: %s (installed: %s, remote: %s)",
            key,
            status,
            info['installed_version'],
            info['remote_version'],
        )

    logger.debug("After Loaded Themes and Installation Status:")
    for key in registry.get_themes():
        installed_status = "Installed" if registry.is_installed(key) else "Not installed"
        folder_name = registry.get_installed_folder(key)
        logger.debug(" - %s (%s) -> folder: %s", key, installed_status, folder_name)

    logger.info("Done.")


if __name__ == "__main__":
    main()
