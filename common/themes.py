import logging
import os
import concurrent.futures
from io import BytesIO
from typing import Dict, Any

from common.paths import CONFIG_DIR
from common.theme_installer import ThemeInstallStore
from common.theme_registry_client import ThemeRegistryClient, ThemeRegistryError


logger = logging.getLogger("vpinfe.common.themes")


class ThemeRegistry:
    def __init__(self, timeout: int = 10):
        self.registry_url = "https://raw.githubusercontent.com/superhac/vpinfe-themes/master/themes.json"
        self.timeout = timeout
        self.client = ThemeRegistryClient(timeout=timeout)
        self.themes_index: Dict[str, Any] = {}
        self.themes: Dict[str, Any] = {}

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

    def load_registry(self):
        data = self._fetch_json(self.registry_url)

        if "themes" not in data or not isinstance(data["themes"], dict):
            raise ThemeRegistryError("Invalid registry format.")

        self.themes_index = data["themes"]

    def load_theme_manifests(self, default_only: bool = False):
        if not self.themes_index:
            raise ThemeRegistryError("Registry not loaded.")

        # Reset loaded themes for this pass.
        self.themes = {}

        theme_jobs = []
        for theme_key, theme_info in self.themes_index.items():
            if default_only and not theme_info.get("default_install", False):
                continue
            manifest_url = theme_info.get("theme_manifest_url")
            if not manifest_url:
                continue
            theme_jobs.append((theme_key, theme_info, manifest_url))

        def _load_one(job):
            theme_key, theme_info, manifest_url = job
            manifest = self._fetch_json(manifest_url)
            self._validate_manifest(theme_key, manifest)
            return theme_key, theme_info, manifest

        # Network-bound workload: parallelize manifest fetches.
        max_workers = min(8, max(1, len(theme_jobs)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_load_one, job): job[0] for job in theme_jobs}
            for future in concurrent.futures.as_completed(futures):
                try:
                    theme_key, theme_info, manifest = future.result()
                    self.themes[theme_key] = {
                        "registry_info": theme_info,
                        "manifest": manifest,
                    }
                except Exception as e:
                    failed_key = futures.get(future, "unknown")
                    logger.error("%s: %s", failed_key, e)

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
            "supported_screens",
            "type",
        ]

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

        base_url = theme_data["registry_info"].get("theme_base_url")
        return self.store.installed_version(theme_key, base_url)

    def _remove_existing_install(self, base_url: str):
        self.store.remove_existing_install(base_url)

    def _is_version_newer(self, remote: str, local: str) -> bool:
        return self.store.is_version_newer(remote, local)

    def _build_zip_url(self, base_url: str) -> str:
        return self.store.build_zip_url(base_url)

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
        base_url = theme_data["registry_info"]["theme_base_url"]

        remote_version = manifest["version"]
        local_version = self._get_installed_version(theme_key)

        if not force and local_version:
            if not self._is_version_newer(remote_version, local_version):
                logger.info("%s already up to date (%s)", theme_key, local_version)
                return

        logger.info("Installing %s v%s", theme_key, remote_version)

        zip_url = self._build_zip_url(base_url)
        zip_data = self._download_zip(zip_url)

        self.store.install_zip(theme_key, base_url, zip_data)

        logger.info("Installed %s", theme_key)


    # =========================================================
    # UPDATE & STATUS
    # =========================================================

    def check_for_updates(self, theme_keys: list[str] | None = None) -> Dict[str, dict]:
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
        base_url = theme_data["registry_info"].get("theme_base_url") if theme_data else None
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

    def get_themes(self) -> Dict[str, Any]:
        return self.themes


# =============================================================
# MAIN TEST
# =============================================================

def main():
    logger.info("Initializing Theme Manager...")

    registry = ThemeRegistry()

    registry.load_registry()
    registry.load_theme_manifests()

    logger.info("Themes directory: %s", registry.themes_dir)

    logger.info("Loaded Themes and Installation Status:")
    for key in registry.get_themes():
        installed_status = "Installed" if registry.is_installed(key) else "Not installed"
        folder_name = registry.get_installed_folder(key)
        logger.info(" - %s (%s) -> folder: %s", key, installed_status, folder_name)

    logger.info("Auto installing default themes...")
    registry.auto_install_defaults()

    logger.info("Checking for updates...")
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

    logger.info("After Loaded Themes and Installation Status:")
    for key in registry.get_themes():
        installed_status = "Installed" if registry.is_installed(key) else "Not installed"
        folder_name = registry.get_installed_folder(key)
        logger.info(" - %s (%s) -> folder: %s", key, installed_status, folder_name)
             
    logger.info("Done.")


if __name__ == "__main__":
    main()
