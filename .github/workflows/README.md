# GitHub Actions Build Workflow

This directory contains the GitHub Actions workflow for building VPinFE on multiple platforms.

## Workflow: `build.yml`

Builds VPinFE for Linux, Windows, and macOS using PyInstaller.

### Triggers
- Push to `master` or `main` branches
- Pull requests to `master` or `main`
- Tags starting with `v*` (e.g., `v1.0.0`)
- Manual workflow dispatch

### Build Outputs

Distribution archives:
- **Linux**: `vpinfe-linux-x86_64.tar.gz`
- **Windows**: `vpinfe-windows-x86_64.zip`
- **macOS**: `vpinfe-macos-x86_64.tar.gz`

Each archive contains a `vpinfe/` folder with the executable and required libraries.

### Creating a Release

To create a release with built binaries:

1. Tag your commit:
   ```bash
   git tag -a v1.0.0 -m "Release v1.0.0"
   git push origin v1.0.0
   ```

2. The workflow will automatically:
   - Build on all three platforms
   - Create a GitHub release
   - Attach the build artifacts

### Manual Build

You can manually trigger a build from the GitHub Actions tab:
1. Go to Actions → Build VPinFE
2. Click "Run workflow"
3. Select the branch
4. Click "Run workflow"

### Local Testing

To test PyInstaller builds locally:

```bash
# Install PyInstaller
pip install pyinstaller

# Build
pyinstaller vpinfe.spec

# Output will be in dist/vpinfe/ folder
# Run: ./dist/vpinfe/vpinfe (Linux/macOS)
# Run: dist\vpinfe\vpinfe.exe (Windows)
```

### Notes

- Artifacts are retained for 30 days on non-release builds
- Release builds are permanent and attached to the GitHub release
- All builds create folder-based distributions with executable + libraries
- Windows builds include all necessary DLLs in the `_internal` directory
- Linux builds require GTK/WebKit2GTK on the target system (system libraries, not bundled)
- macOS builds use native WebView framework
- Archives are compressed for easier distribution
