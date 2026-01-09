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
- **Linux**: `vpinfe-linux-x86_64.tar.gz`
- **Windows**: `vpinfe-windows-x86_64.zip`
- **macOS**: `vpinfe-macos-x86_64.tar.gz` (contains `.app` bundle)

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

# Output will be in dist/vpinfe/
```

### Notes

- Artifacts are retained for 30 days on non-release builds
- Release builds are permanent and attached to the GitHub release
- The macOS build creates an `.app` bundle compatible with macOS application standards
- Windows builds include all necessary DLLs
- Linux builds may require GTK/WebKit2GTK on the target system
