# Building VPinFE

This document describes how to build standalone executables of VPinFE for distribution.

## Prerequisites

- Python 3.11+ (3.11 recommended for best compatibility)
- PyInstaller
- All VPinFE dependencies installed

## Quick Start

### Install Build Dependencies

```bash
pip install pyinstaller
pip install -r requirements.txt
```

For macOS, also install:
```bash
pip install -r osx_requirements.txt
```

### Build

```bash
pyinstaller vpinfe.spec
```

The built application will be in the `dist/` directory.

## Platform-Specific Instructions

### Linux

#### Dependencies
```bash
sudo apt-get install -y \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    gir1.2-webkit2-4.1 \
    libgirepository1.0-dev \
    gcc \
    libcairo2-dev \
    pkg-config \
    python3-dev
```

#### Build
```bash
pip install pyinstaller
pip install -r requirements.txt
pyinstaller vpinfe.spec
```

#### Output
- Directory: `dist/vpinfe/`
- Run: `./dist/vpinfe/vpinfe`

#### Distribution
```bash
cd dist
tar -czf vpinfe-linux-x86_64.tar.gz vpinfe/
```

#### Notes
- End users will need GTK3 and WebKit2GTK installed
- The binary is dynamically linked to system GTK libraries
- Tested on Ubuntu 22.04+ and Debian 13

### Windows

#### Build
```bash
pip install pyinstaller
pip install -r requirements.txt
pyinstaller vpinfe.spec
```

#### Output
- Directory: `dist\vpinfe\`
- Run: `dist\vpinfe\vpinfe.exe`

#### Distribution
Package the entire `dist\vpinfe\` directory as a ZIP file.

#### Notes
- Uses Edge WebView2 (built into Windows 10/11)
- All dependencies are bundled
- No additional runtime requirements on modern Windows

### macOS

#### Build
```bash
pip install pyinstaller
pip install -r osx_requirements.txt
pyinstaller vpinfe.spec
```

#### Output
- Application Bundle: `dist/VPinFE.app`
- Run: Double-click `VPinFE.app` or run `open dist/VPinFE.app`

#### Distribution
```bash
cd dist
tar -czf vpinfe-macos-x86_64.tar.gz VPinFE.app/
```

Or create a DMG (requires additional tools):
```bash
# Using create-dmg (install via: brew install create-dmg)
create-dmg \
  --volname "VPinFE" \
  --window-pos 200 120 \
  --window-size 800 400 \
  --icon-size 100 \
  --app-drop-link 600 185 \
  vpinfe-installer.dmg \
  dist/VPinFE.app
```

#### Notes
- Uses native macOS WebView (WKWebView)
- Requires macOS 10.15 (Catalina) or later
- Universal binary (Intel + Apple Silicon) requires additional configuration

## Automated Builds (GitHub Actions)

VPinFE includes a GitHub Actions workflow that automatically builds for all platforms.

### Trigger Builds

**On every push/PR:**
```bash
git push origin master
```

**Create a release:**
```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

This will:
1. Build on Linux, Windows, and macOS
2. Create GitHub release
3. Upload all build artifacts

### Manual Trigger
1. Go to GitHub Actions tab
2. Select "Build VPinFE" workflow
3. Click "Run workflow"

## Customization

### Changing the Icon

Edit `vpinfe.spec` and set the icon path:

```python
exe = EXE(
    ...
    icon='path/to/icon.ico',  # Windows/Linux
    ...
)

# For macOS
app = BUNDLE(
    ...
    icon='path/to/icon.icns',  # macOS
    ...
)
```

### Adjusting Bundle Size

To reduce the bundle size, exclude unused modules in `vpinfe.spec`:

```python
a = Analysis(
    ...
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        # Add more modules to exclude
    ],
    ...
)
```

### Console vs GUI Mode

To hide the console window on Windows/Linux:

```python
exe = EXE(
    ...
    console=False,  # Change from True to False
    ...
)
```

## Troubleshooting

### Missing Modules
If PyInstaller misses a module, add it to `hiddenimports` in `vpinfe.spec`:

```python
hiddenimports=[
    'your.missing.module',
    ...
]
```

### Missing Data Files
Add data files in `vpinfe.spec`:

```python
datas=[
    ('source/path', 'destination/path'),
    ...
]
```

### Runtime Errors
Run the built executable from the terminal to see error messages:

```bash
# Linux/macOS
./dist/vpinfe/vpinfe

# Windows
dist\vpinfe\vpinfe.exe
```

### Build Fails on macOS
Ensure you have Xcode Command Line Tools installed:

```bash
xcode-select --install
```

### GTK/WebView Issues on Linux
The end user system must have GTK3 and WebKit2GTK installed. Include this in your distribution notes:

```bash
# Ubuntu/Debian
sudo apt install python3-gi gir1.2-webkit2-4.1

# Fedora
sudo dnf install python3-gobject webkit2gtk3
```

## Testing Builds

After building, test the executable:

1. **Basic launch test:**
   ```bash
   ./dist/vpinfe/vpinfe --help
   ```

2. **Configuration test:**
   ```bash
   ./dist/vpinfe/vpinfe --listres
   ```

3. **Full application test:**
   - Set up a test `vpinfe.ini`
   - Run the application
   - Test gamepad configuration
   - Test table loading
   - Test all CLI options

## Distribution Checklist

- [ ] Build on all target platforms
- [ ] Test executables on clean systems
- [ ] Include README with system requirements
- [ ] Document required runtime dependencies
- [ ] Test with real VPX tables and configuration
- [ ] Verify all CLI options work
- [ ] Test gamepad functionality
- [ ] Test web UI (manager/remote)
- [ ] Create release notes
- [ ] Tag release in git
- [ ] Upload to GitHub releases

## Size Expectations

Typical build sizes:
- **Linux**: ~80-120 MB (compressed: ~40-50 MB)
- **Windows**: ~60-80 MB (compressed: ~30-40 MB)
- **macOS**: ~100-150 MB (compressed: ~50-70 MB)

These sizes can vary based on Python version and included dependencies.
