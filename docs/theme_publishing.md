# Theme Publishing

This document explains how VPinFE discovers, installs, updates, and serves published themes so you can publish a new theme correctly.

This is the publishing side of the theme system. For authoring the actual HTML/CSS/JS theme files, see [theme.md](theme.md).

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

VPinFE loads that registry in [`common/online/themes.py`](../common/online/themes.py).

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

### Serving more than one contract

3.0 introduces theme contract 2. A theme that moves to it stops working on 2.x builds, and
a 2.x build has no way to know that before it installs.

Rather than register a second theme or coordinate every release with the registry owner,
declare your release lines in a `vpinfe-theme.json` at the root of your default branch:

```json
{
  "releases": [
    { "contract": 1, "ref": "master", "version": "1.6" },
    { "contract": 2, "ref": "v2", "version": "2.1" }
  ]
}
```

Each entry says which contract that line speaks and which ref serves it. VPinFE installs
the highest contract it can run, and reads that line's `manifest.json` and source archive
from its own ref. A theme whose only release needs a newer VPinFE than the one asking is
not offered at all, which is how a build avoids installing something it cannot run.

**Write refs bare** - `v2`, not `refs/heads/v2`. GitHub and Forgejo spell fully qualified
refs differently and each returns 404 for the other's form, so VPinFE strips
`refs/heads/` and `refs/tags/` before building a URL. A fully qualified ref still works;
it is just rewritten. The one thing to avoid is a branch and a tag with the same name in
one repo, because a bare ref cannot then say which you meant.

You own this file, so a release is a merge in your repository. The registry is not
involved after the theme is registered once.

**Which line goes on your default branch decides whether 2.x users keep working.** A 2.x
build predates all of this: it ignores `vpinfe-theme.json` and always installs
`master.zip`, whatever that now contains. So keeping contract 1 on the default branch and
developing contract 2 on a branch - the layout above - leaves 2.x installs working and
still receiving your contract 1 updates. Moving your default branch to contract 2 breaks
them, and nothing in the registry can prevent that. Both are reasonable; just know which
one you are choosing.

A theme with no `vpinfe-theme.json` is read the way it always was: one contract 1 release,
`manifest.json` on the default branch. That is every theme published today, and none of
them need to do anything.

### Important behavior of the registry key

The registry key is not just a label. It affects runtime behavior:

- It is the key VPinFE uses internally for install/update/delete operations.
- It becomes the installed folder name under the local `themes/` directory.
- It is the value users set in `vpinfe.ini` for `[Settings] theme = ...`.
- The Manager UI uses it when building local preview URLs like `/themes/<theme_key>/<preview_image>`.

Because of that, choose the registry key carefully and keep it stable once published.

Registry keys do not have to match the repo name or the `manifest.json` `name` field. The live registry already includes keys with spaces such as `Slider Video` and `Basic Cab`. That is supported, but simple stable keys are easier to maintain.

## Per-Theme Repository

Each published theme lives in its own repository. VPinFE expects to install directly from the repository root.

The install code assumes:

- The repository is hosted on GitHub or on a Forgejo/Gitea server
- The theme files live at the repository root
- The repository serves `<base_url>/raw/<ref>/<path>` and `<base_url>/archive/<ref>.zip`

This behavior comes from [`common/online/theme_releases.py`](../common/online/theme_releases.py)
and [`common/online/theme_installer.py`](../common/online/theme_installer.py), which build URLs as:

```text
<theme_base_url>/raw/<ref>/manifest.json
<theme_base_url>/archive/<ref>.zip
```

With no `vpinfe-theme.json` the ref is `HEAD`, which both hosts resolve to whatever the
repository's default branch actually is - so a repo defaulting to `main` works without
saying anything.

### Publishing somewhere other than the stock registry

A theme does not have to be in the registry to be installable. A user can name your
repository directly in their config file, and VPinFE will treat it as a theme in its own
right:

```json
{
  "settings": {
    "themes": {
      "repositories": ["https://git.example.net/you/vpinfe-theme-aurora"]
    }
  }
}
```

**The theme is called whatever `manifest.json` says its `name` is** - not the repository's
name. A repository url names nothing, so the author's own choice is the one that counts,
and it is the name the theme installs under and the value to set for `theme`. Everything
else works the same way: `vpinfe-theme.json` chooses the release, `manifest.json`
describes it, and updates are found by version.

This works for any repository, including one already in the registry - so it is also how
you install a fork, or hold a published theme at a particular version. Because the name
comes from the manifest, a fork of Revolution is called `Revolution` too, and the registry
copy and yours are the same theme: yours wins, and VPinFE logs which one it dropped. Where
a registry key and a manifest name differ only in case - the registry says `cab`, the
manifest says `Cab` - they are two names and both install, with a warning.

#### Pinning a ref

Add `#<ref>` to hold a repository at one branch or tag:

```json
"repositories": ["https://git.example.net/you/vpinfe-theme-aurora#v1.4"]
```

A pin overrides release selection - it is you naming the ref, so `vpinfe-theme.json` does
not get to choose. Two things follow. If a declared release line serves that ref, its
contract still applies, so a build that cannot run it still declines rather than
installing something that will not work. And because the manifest at a fixed ref never
changes, a pinned theme is never offered an update; move the pin to take one.

The same file takes `registries`, a list of `themes.json` catalogs. The stock registry is
an ordinary entry in that list, so it can be reordered, replaced with a mirror, or
removed on an install that should not reach the internet. Repositories are resolved
before registries, so naming a repo directly wins if a name appears in both.

Neither list is editable in the Manager UI. A source is a URL VPinFE fetches and installs
code from, so adding one is a deliberate edit to the config file.

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

VPinFE validates the manifest in [`common/online/themes.py`](../common/online/themes.py).

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

At runtime, VPinFE mounts that directory as `/themes/` in the local HTTP server from [`main.py`](../main.py).

So after a theme is installed, files are served from URLs like:

- `/themes/<theme_key>/index_table.html`
- `/themes/<theme_key>/preview.png`

The frontend also builds the active page URL with [`frontend/api.py`](../frontend/api.py):

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

If you publish more than one contract, increment the version on the line you changed and
leave the other line's ref alone.

You do not need to change `themes.json` unless:

- the repository URL changes
- the manifest URL changes
- the registry key changes
- you want to change `default_install`

The Manager UI's update badge is driven by comparing the remote manifest version to the installed local manifest version.

## Common Publishing Pitfalls

### Using the wrong branch

Without a `vpinfe-theme.json`, the installer downloads `master.zip`, not `main.zip`. If your
theme only exists on `main`, name it as a release `ref` or installation will fail.

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

- Registry loading and install logic: [common/online/themes.py](../common/online/themes.py)
- Theme page in the Manager UI: [managerui/pages/themes.py](../managerui/pages/themes.py)
- Static theme file mounting and startup auto-install: [main.py](../main.py)
- Active theme page URL generation: [frontend/api.py](../frontend/api.py)
- Theme authoring guide: [docs/theme.md](theme.md)
