# Theme Publishing

This document explains how VPinFE discovers, installs, updates, and serves published themes so you can publish a new theme correctly.

This is the publishing side of the theme system. For authoring the actual HTML/CSS/JS theme files, see [theme.md](/home/superhac/repos/testing/vpinfe/docs/theme.md).

## Overview

Published themes are not stored inside the main VPinFE repository. The system is split into:

1. A central registry repository: `https://github.com/superhac/vpinfe-themes`
2. One GitHub repository per theme
3. A local installed copy under the user's VPinFE config directory

At startup and when the Manager UI refreshes the registry, VPinFE:

1. Downloads `https://raw.githubusercontent.com/superhac/vpinfe-themes/master/themes.json`
2. Reads the `themes` object in that file
3. Fetches each theme's `manifest.json` from the `theme_manifest_url`
4. Builds the available theme list shown in the Themes page
5. Installs any themes marked `default_install: true`

When a user installs or updates a theme, VPinFE downloads the theme repository as a ZIP from GitHub, extracts it into the local themes directory, and renames the extracted folder to the registry key for that theme.

## Registry Repository

The central registry is currently:

- `https://github.com/superhac/vpinfe-themes`
- Raw registry file: `https://raw.githubusercontent.com/superhac/vpinfe-themes/master/themes.json`

VPinFE loads that registry in [`common/themes.py`](/home/superhac/repos/testing/vpinfe/common/themes.py).

### Registry format

The registry must be a JSON object with a top-level `themes` object:

```json
{
  "themes": {
    "carousel-desktop": {
      "theme_base_url": "https://github.com/superhac/vpinfe-theme-carousel-desktop",
      "theme_manifest_url": "https://github.com/superhac/vpinfe-theme-carousel-desktop/raw/refs/heads/master/manifest.json",
      "default_install": true
    }
  }
}
```

Each entry under `themes` is keyed by the theme's registry key.

### Registry fields

Each theme entry currently uses these fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `theme_base_url` | Yes | GitHub repository URL for the theme. |
| `theme_manifest_url` | Yes | Raw URL to the theme's `manifest.json` on the `master` branch. |
| `default_install` | No, but expected | If `true`, VPinFE auto-installs the theme at startup. |

### Important behavior of the registry key

The registry key is not just a label. It affects runtime behavior:

- It is the key VPinFE uses internally for install/update/delete operations.
- It becomes the installed folder name under the local `themes/` directory.
- It is the value users set in `vpinfe.ini` for `[Settings] theme = ...`.
- The Manager UI uses it when building local preview URLs like `/themes/<theme_key>/<preview_image>`.

Because of that, choose the registry key carefully and keep it stable once published.

Registry keys do not have to match the repo name or the `manifest.json` `name` field. The live registry already includes keys with spaces such as `Slider Video` and `Basic Cab`. That is supported, but simple stable keys are easier to maintain.

## Per-Theme Repository

Each published theme lives in its own GitHub repository. VPinFE expects to install directly from the repository root.

The current install code assumes:

- The repository is hosted on GitHub
- The theme files live at the repository root
- The publish branch is `master`
- The repository can be downloaded as `https://github.com/<owner>/<repo>/archive/refs/heads/master.zip`

This behavior comes from [`common/themes.py`](/home/superhac/repos/testing/vpinfe/common/themes.py), which builds ZIP URLs as:

```text
<theme_base_url>/archive/refs/heads/master.zip
```

### Required repository contents

At minimum, the repository should contain:

```text
<repo root>/
├── manifest.json
├── index_table.html
├── index_bg.html
├── index_dmd.html
├── style.css
├── theme.js
└── preview.png
```

This matches both the current theme loader and the example template repository.

The published template repository currently includes:

- `manifest.json`
- `index_table.html`
- `index_bg.html`
- `index_dmd.html`
- `style.css`
- `theme.js`
- `preview.png`

Optional files are allowed, such as:

- `config.json`
- `fonts/`
- additional images, videos, or assets used by the theme
- `README.md`

## `manifest.json`

Each published theme repository must include a `manifest.json` at the repository root.

VPinFE validates the manifest in [`common/themes.py`](/home/superhac/repos/testing/vpinfe/common/themes.py).

### Required manifest fields

These fields are currently required:

| Field | Purpose |
| --- | --- |
| `name` | Display name shown in the Manager UI. |
| `version` | Version string used for update checks. |
| `author` | Theme author name. |
| `description` | Description shown in the Manager UI. |
| `preview_image` | Preview filename or URL. Usually `preview.png`. |
| `supported_screens` | Number of supported screens. |
| `type` | Must be `desktop`, `cab`, or `both`. |

The Manager UI also reads:

| Field | Purpose |
| --- | --- |
| `change_log` | Optional text shown as "What's new" for uninstalled themes or when an update is available. |

### Example manifest

```json
{
  "name": "Template",
  "version": "1.4",
  "author": "superhac",
  "description": "A template theme demonstrating all VPinFE theme patterns.",
  "preview_image": "preview.png",
  "supported_screens": 3,
  "type": "desktop",
  "change_log": "updated all documented patterns."
}
```

### Version format requirements

Update checks use numeric dot-separated version parsing:

```python
[int(x) for x in v.split(".")]
```

That means versions should be simple numeric values like:

- `1.0`
- `1.4`
- `2.0.3`

Avoid non-numeric version strings such as:

- `v1.0`
- `1.0-beta`
- `2026.03-release`

Those will not parse correctly with the current code.

## Install And Update Flow

Theme installation works like this:

1. VPinFE reads the registry entry for a theme.
2. It fetches the remote `manifest.json`.
3. It compares the remote `manifest.version` to the locally installed version.
4. It downloads `master.zip` from the theme repository.
5. It extracts the ZIP into the local themes directory.
6. It renames the extracted GitHub folder, such as `repo-name-master`, to the registry key.

Important consequences:

- Publishing is branch-based, not release-based.
- The `master` branch is the published artifact.
- Updating `manifest.json` on `master` is what makes a new version visible.
- A repo rename does not automatically change the registry key used locally.

## Local Install Location

Installed themes are stored under the user's VPinFE config directory:

- Linux: `~/.config/vpinfe/themes/`
- Other platforms: the matching `platformdirs.user_config_dir("vpinfe", "vpinfe")` path

At runtime, VPinFE mounts that directory as `/themes/` in the local HTTP server from [`main.py`](/home/superhac/repos/testing/vpinfe/main.py).

So after a theme is installed, files are served from URLs like:

- `/themes/<theme_key>/index_table.html`
- `/themes/<theme_key>/preview.png`

The frontend also builds the active page URL with [`frontend/api.py`](/home/superhac/repos/testing/vpinfe/frontend/api.py):

```text
http://127.0.0.1:<themeassetsport>/themes/<active theme>/index_<window>.html?window=<window>
```

## How Preview Images Are Resolved

The Manager UI uses the manifest's `preview_image` field in two different ways:

- If the theme is installed, it serves the preview locally from `/themes/<theme_key>/<preview_image>`
- If the theme is not installed, it derives a remote preview URL from the directory containing `theme_manifest_url`
- If `preview_image` itself is already an absolute `http...` URL, it uses that directly

For the simplest publishing flow, keep `preview_image` as a filename in the repo root, for example:

```json
"preview_image": "preview.png"
```

## Publishing Checklist

To publish a new theme:

1. Create a GitHub repository for the theme.
2. Put the theme files in the repository root, including `manifest.json`.
3. Make sure the repository's published branch is `master`.
4. Make sure `manifest.json` has all required fields.
5. Use a numeric version string such as `1.0`.
6. Commit and push the files to GitHub.
7. Add an entry for the theme to `https://github.com/superhac/vpinfe-themes` in `themes.json`.
8. Set:
   - `theme_base_url` to the repo URL
   - `theme_manifest_url` to the raw `manifest.json` URL on `master`
   - `default_install` as desired
9. Commit and push the registry update.
10. In VPinFE, refresh the Themes page or restart the app.

## Updating An Existing Theme

To publish an update:

1. Update the theme repository contents on `master`
2. Increment `manifest.json` `version`
3. Optionally update `change_log`
4. Push to GitHub

You do not need to change `themes.json` unless:

- the repository URL changes
- the manifest URL changes
- the registry key changes
- you want to change `default_install`

The Manager UI's update badge is driven by comparing the remote manifest version to the installed local manifest version.

## Common Publishing Pitfalls

### Using the wrong branch

The current installer downloads `master.zip`, not `main.zip`. If your theme only exists on `main`, installation will fail unless the code or registry strategy changes.

### Putting files in a subdirectory

The installer extracts the repository and expects `manifest.json` and the theme HTML files at the repository root. If everything is inside a nested folder, the active theme URLs will not line up with the installed layout.

### Using non-numeric versions

The current version comparison only supports dot-separated integers.

### Changing the registry key after publishing

Because the registry key is used as the installed folder name and config value, changing it is effectively a theme identity change.

### Forgetting `manifest.json`

If the registry points to a bad manifest URL or the manifest is missing required fields, the theme will be skipped when VPinFE loads manifests.

## Recommended Conventions

These conventions are not strictly required by the current code, but they will make publishing more predictable:

- Keep the registry key, repo name, and manifest `name` closely related
- Store all theme runtime files in the repository root
- Use `preview.png` at the root unless you need something else
- Use `change_log` for update notes visible in the Manager UI
- Keep versions numeric and increment them for every published update
- Test install, update, activate, and delete from the Themes page before announcing the theme

## Related Files In This Repo

The implementation described above lives here:

- Registry loading and install logic: [common/themes.py](/home/superhac/repos/testing/vpinfe/common/themes.py)
- Theme page in the Manager UI: [managerui/pages/themes.py](/home/superhac/repos/testing/vpinfe/managerui/pages/themes.py)
- Static theme file mounting and startup auto-install: [main.py](/home/superhac/repos/testing/vpinfe/main.py)
- Active theme page URL generation: [frontend/api.py](/home/superhac/repos/testing/vpinfe/frontend/api.py)
- Theme authoring guide: [docs/theme.md](/home/superhac/repos/testing/vpinfe/docs/theme.md)
