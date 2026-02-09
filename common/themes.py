import requests
import json
import os
import time
import zipfile
import shutil
from io import BytesIO
from typing import Dict, Any
from platformdirs import user_config_dir


class ThemeRegistryError(Exception):
    pass


class ThemeRegistry:
    def __init__(self, timeout: int = 10):
        self.registry_url = "https://raw.githubusercontent.com/superhac/vpinfe-themes/master/themes.json"
        self.timeout = timeout
        self.themes_index: Dict[str, Any] = {}
        self.themes: Dict[str, Any] = {}

        # Correct platform dir usage (two args to match rest of codebase)
        self.base_dir = user_config_dir("vpinfe", "vpinfe")
        self.themes_dir = os.path.join(self.base_dir, "themes")
        os.makedirs(self.themes_dir, exist_ok=True)

    # =========================================================
    # NETWORK
    # =========================================================

    def _fetch_json(self, url: str) -> dict:
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise ThemeRegistryError(f"Failed to fetch JSON from {url}: {e}")
        except json.JSONDecodeError:
            raise ThemeRegistryError(f"Invalid JSON returned from {url}")

    def _download_zip(self, url: str, max_retries: int = 3) -> BytesIO:
        for attempt in range(max_retries):
            response = requests.get(url, timeout=60)
            if response.status_code == 429:
                wait = int(response.headers.get('Retry-After', 5 * (attempt + 1)))
                print(f"[RATE-LIMITED] 429 on zip download, waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return BytesIO(response.content)
        raise ThemeRegistryError(f"Failed to download {url} after {max_retries} retries (rate limited)")

    # =========================================================
    # REGISTRY
    # =========================================================

    def load_registry(self):
        data = self._fetch_json(self.registry_url)

        if "themes" not in data or not isinstance(data["themes"], dict):
            raise ThemeRegistryError("Invalid registry format.")

        self.themes_index = data["themes"]

    def load_theme_manifests(self):
        if not self.themes_index:
            raise ThemeRegistryError("Registry not loaded.")

        for theme_key, theme_info in self.themes_index.items():
            manifest_url = theme_info.get("theme_manifest_url")
            if not manifest_url:
                continue

            try:
                manifest = self._fetch_json(manifest_url)
                self._validate_manifest(theme_key, manifest)

                self.themes[theme_key] = {
                    "registry_info": theme_info,
                    "manifest": manifest
                }

            except Exception as e:
                print(f"[ERROR] {theme_key}: {e}")

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
        return base_url.rstrip("/").split("/")[-1]

    def _get_installed_version(self, theme_key: str) -> str | None:
        theme_data = self.themes.get(theme_key)
        if not theme_data:
            return None

        folder_name = self.get_installed_folder(theme_key)
        if not folder_name:
            return None

        manifest_path = os.path.join(self.themes_dir, folder_name, "manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("version")
        return None

    def _remove_existing_install(self, base_url: str):
        repo_name = self._get_repo_name(base_url)

        for folder in os.listdir(self.themes_dir):
            if folder.startswith(repo_name):
                shutil.rmtree(os.path.join(self.themes_dir, folder))

    def _is_version_newer(self, remote: str, local: str) -> bool:
        def parse(v):
            return [int(x) for x in v.split(".")]
        return parse(remote) > parse(local)

    def _build_zip_url(self, base_url: str) -> str:
        return f"{base_url}/archive/refs/heads/master.zip"

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
                print(f"[SKIP] {theme_key} already up to date ({local_version})")
                return

        print(f"[INSTALL] {theme_key} v{remote_version}")

        zip_url = self._build_zip_url(base_url)
        zip_data = self._download_zip(zip_url)

        self._remove_existing_install(base_url)

        with zipfile.ZipFile(zip_data) as z:
            z.extractall(self.themes_dir)

        # Rename extracted folder (e.g. "repo-name-master") to the theme_key
        repo_name = self._get_repo_name(base_url)
        for folder in os.listdir(self.themes_dir):
            if folder.startswith(repo_name) and folder != theme_key:
                src = os.path.join(self.themes_dir, folder)
                dst = os.path.join(self.themes_dir, theme_key)
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                os.rename(src, dst)
                break

        print(f"[DONE] Installed {theme_key}")


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
        if os.path.isdir(os.path.join(self.themes_dir, theme_key)):
            return theme_key

        # Fallback: scan for repo-name prefix (pre-rename installs)
        theme_data = self.themes.get(theme_key)
        if not theme_data:
            return None

        repo_name = self._get_repo_name(theme_data["registry_info"]["theme_base_url"])

        for folder in os.listdir(self.themes_dir):
            if folder.startswith(repo_name):
                return folder
        return None

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
            shutil.rmtree(os.path.join(self.themes_dir, folder))
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
    print("Initializing Theme Manager...\n")

    registry = ThemeRegistry()

    registry.load_registry()
    registry.load_theme_manifests()

    print(f"Themes directory: {registry.themes_dir}\n")

    print("Loaded Themes and Installation Status:")
    for key in registry.get_themes():
        installed_status = "Installed" if registry.is_installed(key) else "Not installed"
        folder_name = registry.get_installed_folder(key)
        print(f" - {key} ({installed_status}) -> folder: {folder_name}")

    print("\nAuto installing default themes...\n")
    registry.auto_install_defaults()

    print("\nChecking for updates...\n")
    updates = registry.check_for_updates()
    for key, info in updates.items():
        status = "UPDATE AVAILABLE" if info["update_available"] else "Up to date"
        print(f"{key}: {status} (installed: {info['installed_version']}, remote: {info['remote_version']})")

    print("After Loaded Themes and Installation Status:")
    for key in registry.get_themes():
        installed_status = "Installed" if registry.is_installed(key) else "Not installed"
        folder_name = registry.get_installed_folder(key)
        print(f" - {key} ({installed_status}) -> folder: {folder_name}")
             
    print("\nDone.")


if __name__ == "__main__":
    main()
