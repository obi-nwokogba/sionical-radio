cat > build-mac.sh <<'EOF'
#!/bin/bash
# build-mac.sh - build the standalone SionicalRadio.app and open it.
# One-time setup:
#   pip install -r requirements.txt
#   brew install --cask vlc          (puts VLC in /Applications)
# Usage (from PyCharm's terminal so the venv is active):
#   ./build-mac.sh

set -e
cd "$(dirname "$0")"

APP_NAME=SionicalRadio
SCRIPT=SionicalRadio.py

if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: $SCRIPT not found next to this script."
    exit 1
fi
if [ ! -d /Applications/VLC.app ]; then
    echo "ERROR: /Applications/VLC.app not found."
    echo "Install it first:  brew install --cask vlc"
    exit 1
fi

echo "==> Cleaning previous build"
rm -rf build dist

echo "==> Building (PyInstaller, about 1-2 minutes)"
# Bundle the components folder (font1.ttf..font4.ttf, themes.json) when
# it exists, so fonts and themes ship inside the app.
EXTRA_ARGS=""
if [ -d components ]; then
    EXTRA_ARGS="--add-data components:components"
fi
python -m PyInstaller --windowed --onedir --name "$APP_NAME" $EXTRA_ARGS "$SCRIPT"

echo "==> Bundling the VLC engine"
MACOS=dist/$APP_NAME.app/Contents/MacOS
mkdir -p "$MACOS/libvlc"
cp -R /Applications/VLC.app/Contents/MacOS/lib/. "$MACOS/libvlc/"
cp -R /Applications/VLC.app/Contents/MacOS/plugins "$MACOS/libvlc/plugins"

echo "==> Wiring the engine's library search paths"
install_name_tool -add_rpath @executable_path/libvlc "$MACOS/$APP_NAME"

echo "==> Re-signing the bundle"
codesign --force --deep --sign - dist/$APP_NAME.app

echo "==> Launching"
open dist/$APP_NAME.app

# Optional: wrap the finished app in a DMG for distribution:
# hdiutil create -volname SionicalRadio -srcfolder dist/SionicalRadio.app \
#     -ov -format UDZO SionicalRadio.dmg
EOF
chmod +x build-mac.sh