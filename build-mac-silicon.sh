#!/bin/bash
# build-mac-silicon.sh - build SIONICAL RADIO for Apple Silicon (arm64).
# The DMG installer lands in the "binaries" folder next to this script.
#
# It works from an Intel Mac too: as long as Python is the universal2
# build from python.org (and PySide6's wheels are universal2), PyInstaller
# can target arm64 from either Mac.
#
# One-time setup on the Mac:
#   1. Install Python 3.12 (the universal2 build from python.org)
#   2. Install VLC:  brew install --cask vlc
# Usage (from the project root, next to SionicalRadio.py):
#   chmod +x build-mac-silicon.sh
#   ./build-mac-silicon.sh
#
# The script builds inside its own private venv (.venv-build), so your
# development venv is never touched.

set -e
cd "$(dirname "$0")"

APP_NAME=SionicalRadio
SCRIPT=SionicalRadio.py
ARCH=arm64
SLUG=macOS-AppleSilicon
VENV=.venv-build
VLC_APP=/Applications/VLC.app

echo "==> SIONICAL RADIO - $SLUG ($ARCH) build"

if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: $SCRIPT not found next to this script."
    exit 1
fi
if [ ! -d "$VLC_APP" ]; then
    echo "ERROR: $VLC_APP not found. Install VLC first:"
    echo "    brew install --cask vlc"
    exit 1
fi

# ---- private build venv (created once, reused afterwards) -------------
if [ ! -d "$VENV" ]; then
    echo "==> Creating the private build venv ($VENV)"
    python3 -m venv "$VENV"
fi
PY="$VENV/bin/python"
"$PY" -m pip install --quiet --upgrade pip
echo "==> Installing build requirements"
"$PY" -m pip install --quiet -r requirements.txt

# ---- preflight: can this Python produce the target architecture? ------
BASE_PY=$("$PY" -c "import sys, os; print(os.path.realpath(sys.executable))")
PY_ARCHS=$(lipo -archs "$BASE_PY" 2>/dev/null || echo "")
case "$PY_ARCHS" in
    *$ARCH*) : ;;
    *)
        echo "ERROR: this Python ($PY_ARCHS) cannot produce a $ARCH build."
        echo "Fix: install the universal2 Python 3.12 from python.org"
        echo "(that is the default installer), or run this script on an"
        echo "Apple Silicon Mac, then rerun."
        exit 1
        ;;
esac

# ---- PyInstaller build -------------------------------------------------
echo "==> Building the .app with PyInstaller (about 1-2 minutes)"
rm -rf build dist
EXTRA_ARGS=""
if [ -d components ]; then
    EXTRA_ARGS="--add-data components:components"
fi
"$PY" -m PyInstaller -y --windowed --onedir --name "$APP_NAME" \
    --target-architecture "$ARCH" $EXTRA_ARGS "$SCRIPT"

# ---- bundle the VLC engine ---------------------------------------------
echo "==> Bundling the VLC engine (end users never install VLC)"
MACOS="dist/$APP_NAME.app/Contents/MacOS"
mkdir -p "$MACOS/libvlc"
cp -R "$VLC_APP/Contents/MacOS/lib/." "$MACOS/libvlc/"
cp -R "$VLC_APP/Contents/MacOS/plugins" "$MACOS/libvlc/plugins"

# VLC's dylibs reference each other as @rpath/... and carry no rpath
# of their own (the VLC app normally provides it). Adding the rpath to
# OUR executable makes every @rpath reference resolve inside the bundle.
install_name_tool -add_rpath @executable_path/libvlc "$MACOS/$APP_NAME"

echo "==> Signing the bundle (ad hoc)"
codesign --force --deep --sign - "dist/$APP_NAME.app"

echo "==> Verifying the built architecture"
lipo -archs "$MACOS/$APP_NAME" 2>/dev/null || true

# ---- installer ----------------------------------------------------------
echo "==> Creating the DMG installer in binaries/"
mkdir -p binaries
rm -f "binaries/$APP_NAME-$SLUG.dmg"
hdiutil create -volname "$APP_NAME" -srcfolder "dist/$APP_NAME.app" \
    -ov -format UDZO "binaries/$APP_NAME-$SLUG.dmg"

echo ""
echo "DONE: binaries/$APP_NAME-$SLUG.dmg"
echo "The raw .app is also in dist/$APP_NAME.app"
