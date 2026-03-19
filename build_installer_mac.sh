#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  Build MediaDownloader-Setup.exe on macOS using Wine
#  (Alternative to GitHub Actions — requires Wine with a Windows Python inside)
#
#  Setup (one-time):
#    1. Install Wine:
#         brew install --cask wine-stable
#       On Apple Silicon (M1/M2) you need Rosetta + x86 Wine:
#         softwareupdate --install-rosetta --agree-to-license
#         arch -x86_64 brew install --cask wine-stable
#
#    2. Download Windows Python 3.12 (64-bit) installer from python.org
#       and install it inside Wine:
#         wine ~/Downloads/python-3.12.9-amd64.exe
#       Accept defaults; make sure "Add Python to PATH" is checked.
#       After install, Python will be at:
#         ~/.wine/drive_c/Python312/python.exe
#
#    3. Run this script once:
#         chmod +x build_installer_mac.sh
#         ./build_installer_mac.sh
#
#  Output:  dist/MediaDownloader-Setup.exe  (a real Windows EXE)
# ─────────────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

# ── Find the Windows Python inside Wine ──────────────────────────────────────
WINE_PYTHON=""
for candidate in \
    "$HOME/.wine/drive_c/Python312/python.exe" \
    "$HOME/.wine/drive_c/Python311/python.exe" \
    "$HOME/.wine/drive_c/Python310/python.exe" \
    "$HOME/.wine/drive_c/users/$USER/AppData/Local/Programs/Python/Python312/python.exe"
do
    if [ -f "$candidate" ]; then
        WINE_PYTHON="$candidate"
        break
    fi
done

if [ -z "$WINE_PYTHON" ]; then
    echo "❌  Could not find Windows Python inside Wine."
    echo ""
    echo "   Install it first:"
    echo "     1. brew install --cask wine-stable"
    echo "     2. Download python-3.12.x-amd64.exe from python.org"
    echo "     3. wine ~/Downloads/python-3.12.x-amd64.exe"
    echo ""
    echo "   Or use GitHub Actions instead (easier):"
    echo "     Push to GitHub → Actions tab → 'Build Windows Installer' → Run workflow"
    exit 1
fi

echo "✓  Found Wine Python: $WINE_PYTHON"
echo ""

# ── Install/upgrade PyInstaller inside Wine Python ───────────────────────────
echo "📦  Installing PyInstaller inside Wine Python…"
wine "$WINE_PYTHON" -m pip install pyinstaller --upgrade --quiet
echo ""

# ── Build the EXE ────────────────────────────────────────────────────────────
echo "🔨  Building MediaDownloader-Setup.exe…"
echo ""

wine "$WINE_PYTHON" -m PyInstaller \
    --onefile \
    --windowed \
    --name "MediaDownloader-Setup" \
    installer.pyw

echo ""
if [ -f "dist/MediaDownloader-Setup.exe" ]; then
    SIZE=$(du -sh dist/MediaDownloader-Setup.exe | cut -f1)
    echo "✅  Build complete!  dist/MediaDownloader-Setup.exe  (${SIZE})"
    echo ""
    echo "   Copy this EXE to your HTPC and run it to install Media Downloader."
else
    echo "❌  Build failed — check the output above for errors."
    exit 1
fi
