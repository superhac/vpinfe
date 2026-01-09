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
- Single executable: `dist/vpinfe`
- Run: `./dist/vpinfe`

#### Distribution
The executable is ready to distribute as-is. No archiving needed. Users just download and run:
```bash
chmod +x vpinfe
./vpinfe --help
```

#### Notes
- End users will need GTK3 and WebKit2GTK installed on their system
- The binary is dynamically linked to system GTK libraries
- Data files (web assets) are embedded in the executable
- Tested on Ubuntu 22.04+ and Debian 13

### Windows

#### Build
```bash
pip install pyinstaller
pip install -r requirements.txt
pyinstaller vpinfe.spec
```

#### Output
- Single executable: `dist\vpinfe.exe`
- Run: `dist\vpinfe.exe`

#### Distribution
The executable is ready to distribute as-is. Users just download and run `vpinfe.exe`.

#### Notes
- Uses Edge WebView2 (built into Windows 10/11)
- All dependencies are bundled in the single executable
- Data files (web assets) are embedded in the executable
- No additional runtime requirements on modern Windows

### macOS

#### Build
```bash
pip install pyinstaller
pip install -r osx_requirements.txt
pyinstaller vpinfe.spec
```

#### Output
- Single executable: `dist/vpinfe`
- Run: `./dist/vpinfe` or `./vpinfe --help`

#### Distribution
The executable is ready to distribute as-is. Users just download and run:
```bash
chmod +x vpinfe
./vpinfe --help
```

#### Notes
- Uses native macOS WebView (WKWebView)
- All dependencies and data files are bundled in the single executable
- Requires macOS 10.15 (Catalina) or later
- Universal binary (Intel + Apple Silicon) requires additional configuration
- Single-file executables on macOS extract to a temporary directory on first run

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

Typical single-file executable sizes:
- **Linux**: ~80-120 MB
- **Windows**: ~60-80 MB
- **macOS**: ~100-150 MB

These sizes can vary based on Python version and included dependencies. Single-file executables are larger than folder-based distributions because all dependencies and data files are embedded, but they're much more convenient for end users.
