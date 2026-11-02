#!/bin/bash
# build-windows.sh - build SIONICAL RADIO for Windows x64.
# Run this ON WINDOWS, inside Git Bash (https://gitforwindows.org).
# PyInstaller cannot cross-build from macOS, so the Windows installers
# must be produced on a Windows PC.
#
# One-time setup on the Windows machine:
#   1. Install Python 3.12, 64-bit, from python.org (tick "Add to PATH").
#   2. Install VLC for Windows: https://www.videolan.org/vlc/
#   3. Optional, only for the MSI: install WiX Toolset v3 and add its
#      bin folder (candle.exe, light.exe) to PATH.
# Usage (Git Bash, from the project root, next to SionicalRadio.py):
#   bash build-windows.sh
#
# Output in binaries/:
#   SionicalRadio-Windows-x64/       the app folder (SionicalRadio.exe)
#   SionicalRadio-Windows-x64.zip    portable copy of the above
#   SionicalRadio-Setup-x64.msi      installer (only if WiX is present)
#
# The script builds inside its own private venv (.venv-build), so your
# development venv is never touched.

set -e
cd "$(dirname "$0")"

APP_NAME=SionicalRadio
SCRIPT=SionicalRadio.py
SLUG=Windows-x64
VENV=.venv-build
UPGRADE_CODE="B7E2C5A4-31D9-4F8B-9C60-2A5E7F1D4B22"

echo "==> SIONICAL RADIO - $SLUG build"

case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) : ;;
    *)
        echo "ERROR: this script builds Windows binaries, so it must run"
        echo "on Windows, inside Git Bash (https://gitforwindows.org)."
        echo "It cannot be run on macOS or Linux."
        exit 1
        ;;
esac

if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: $SCRIPT not found next to this script."
    exit 1
fi

# ---- find Python ----------------------------------------------------------
PYCMD=""
if command -v python >/dev/null 2>&1; then
    PYCMD=python
elif command -v py >/dev/null 2>&1; then
    PYCMD="py -3"
else
    echo "ERROR: Python not found. Install 64-bit Python 3.12 from"
    echo "python.org and tick 'Add to PATH', then rerun."
    exit 1
fi

# ---- find the installed VLC engine ----------------------------------------
VLC_DIR=""
for candidate in "/c/Program Files/VideoLAN/VLC" \
                 "/c/Program Files (x86)/VideoLAN/VLC"; do
    if [ -d "$candidate" ]; then
        VLC_DIR="$candidate"
        break
    fi
done
if [ -z "$VLC_DIR" ]; then
    echo "ERROR: VLC not found in Program Files."
    echo "Install it from https://www.videolan.org/vlc/ then rerun."
    exit 1
fi
echo "    using VLC from: $VLC_DIR"

# ---- private build venv (created once, reused afterwards) ----------------
if [ ! -d "$VENV" ]; then
    echo "==> Creating the private build venv ($VENV)"
    $PYCMD -m venv "$VENV"
fi
PY="$VENV/Scripts/python"
"$PY" -m pip install --quiet --upgrade pip
echo "==> Installing build requirements"
"$PY" -m pip install --quiet -r requirements.txt

# ---- PyInstaller build ------------------------------------------------------
echo "==> Building the app folder with PyInstaller (a few minutes)"
rm -rf build dist
EXTRA_ARGS=""
if [ -d components ]; then
    # On Windows, --add-data uses a semicolon separator.
    EXTRA_ARGS="--add-data components;components"
fi
"$PY" -m PyInstaller -y --windowed --onedir --name "$APP_NAME" \
    $EXTRA_ARGS "$SCRIPT"

APP_DIR="dist/$APP_NAME"

# ---- bundle the VLC engine --------------------------------------------------
echo "==> Bundling the VLC engine (end users never install VLC)"
mkdir -p "$APP_DIR/libvlc"
cp "$VLC_DIR/libvlc.dll" "$VLC_DIR/libvlccore.dll" "$APP_DIR/libvlc/"
cp -R "$VLC_DIR/plugins" "$APP_DIR/libvlc/plugins"

# ---- collect everything into binaries/ --------------------------------------
echo "==> Collecting the results in binaries/"
mkdir -p binaries
rm -rf "binaries/$APP_NAME-$SLUG" "binaries/$APP_NAME-$SLUG.zip" \
       "binaries/$APP_NAME-Setup-$SLUG.msi"
cp -R "$APP_DIR" "binaries/$APP_NAME-$SLUG"
echo "    app folder: binaries/$APP_NAME-$SLUG (SionicalRadio.exe inside)"

echo "==> Creating the portable ZIP"
if command -v zip >/dev/null 2>&1; then
    (cd dist && zip -r -q "../binaries/$APP_NAME-$SLUG.zip" "$APP_NAME")
else
    powershell.exe -NoProfile -Command \
        "Compress-Archive -Path 'dist/$APP_NAME/*' -DestinationPath 'binaries/$APP_NAME-$SLUG.zip' -Force"
fi
echo "    portable: binaries/$APP_NAME-$SLUG.zip"

# ---- the MSI (optional: needs the free WiX Toolset v3) ----------------------
if command -v candle >/dev/null 2>&1 && command -v light >/dev/null 2>&1; then
    echo "==> Generating the MSI with WiX"
    mkdir -p build/wix
    WXS="build/wix/SionicalRadio.wxs"

    # Generate the WiX source by walking the app tree: one <Component>
    # per file, nested <Directory> elements per subfolder, plus Start
    # Menu and Desktop shortcuts. No heat.exe needed.
    IDX=0
    REFS=""
    emit_tree() {
        local rel="$1"
        local entry name winpath
        for entry in "$APP_DIR/$rel"*; do
            name="${entry##*/}"
            if [ -d "$entry" ]; then
                IDX=$((IDX + 1))
                echo "        <Directory Id=\"d$IDX\" Name=\"$name\">"
                emit_tree "$rel$name/"
                echo "        </Directory>"
            elif [ -f "$entry" ]; then
                IDX=$((IDX + 1))
                winpath=$(echo "dist/$APP_NAME/$rel$name" | sed 's|/|\\|g')
                echo "        <Component Id=\"c$IDX\" Guid=\"*\" Win64=\"yes\">"
                echo "          <File Id=\"f$IDX\" Name=\"$name\" Source=\"$winpath\" />"
                echo "        </Component>"
                REFS="$REFS      <ComponentRef Id=\"c$IDX\" />"$'\n'
            fi
        done
    }

    {
        echo '<?xml version="1.0" encoding="UTF-8"?>'
        echo '<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">'
        echo "  <Product Id=\"*\" Name=\"$APP_NAME\" Language=\"1033\" Version=\"1.0.0\" Manufacturer=\"Obilo Nwokogba\" UpgradeCode=\"{$UPGRADE_CODE}\">"
        echo '    <Package InstallerVersion="200" Compressed="yes" InstallScope="perMachine" Description="An elegant internet radio player." />'
        echo '    <MajorUpgrade AllowDowngrades="yes" />'
        echo '    <MediaTemplate EmbedCab="yes" />'
        echo '    <Directory Id="TARGETDIR" Name="SourceDir">'
        echo '      <Directory Id="ProgramFilesFolder">'
        echo "        <Directory Id=\"INSTALLDIR\" Name=\"$APP_NAME\">"
        emit_tree ""
        # Start Menu + Desktop shortcuts (components live inside
        # INSTALLDIR so MSI removes them on uninstall).
        echo '        <Component Id="c_startmenu" Guid="*" Win64="yes">'
        echo "          <Shortcut Id=\"sc_start\" Directory=\"AppShortcutsDir\" Name=\"$APP_NAME\" Target=\"[INSTALLDIR]$APP_NAME.exe\" WorkingDirectory=\"INSTALLDIR\" />"
        echo '          <RemoveFolder Id="rf_start" Directory="AppShortcutsDir" On="uninstall" />'
        echo '          <RegistryValue Root="HKCU" Key="Software\SionicalRadio" Name="startmenu" Type="integer" Value="1" KeyPath="yes" />'
        echo '        </Component>'
        echo '        <Component Id="c_desktop" Guid="*" Win64="yes">'
        echo "          <Shortcut Id=\"sc_desktop\" Directory=\"DesktopFolder\" Name=\"$APP_NAME\" Target=\"[INSTALLDIR]$APP_NAME.exe\" WorkingDirectory=\"INSTALLDIR\" />"
        echo '          <RegistryValue Root="HKCU" Key="Software\SionicalRadio" Name="desktop" Type="integer" Value="1" KeyPath="yes" />'
        echo '        </Component>'
        echo '        </Directory>'
        echo '      </Directory>'
        echo '      <Directory Id="ProgramMenuFolder">'
        echo "        <Directory Id=\"AppShortcutsDir\" Name=\"$APP_NAME\" />"
        echo '      </Directory>'
        echo '    </Directory>'
        echo '    <Feature Id="Complete" Level="1">'
        printf '%s' "$REFS"
        echo '      <ComponentRef Id="c_startmenu" />'
        echo '      <ComponentRef Id="c_desktop" />'
        echo '    </Feature>'
        echo '  </Product>'
        echo '</Wix>'
    } > "$WXS"

    set +e
    candle -arch x64 -out build/wix/SionicalRadio.wixobj "$WXS" \
        2> build/wix/candle.log
    CANDLE_RC=$?
    if [ $CANDLE_RC -eq 0 ]; then
        light -out "binaries/$APP_NAME-Setup-$SLUG.msi" \
            build/wix/SionicalRadio.wixobj 2> build/wix/light.log
        LIGHT_RC=$?
    else
        LIGHT_RC=1
    fi
    set -e
    if [ -f "binaries/$APP_NAME-Setup-$SLUG.msi" ]; then
        echo "    installer: binaries/$APP_NAME-Setup-$SLUG.msi"
    else
        echo "    WARNING: the MSI could not be produced;"
        echo "    see build/wix/candle.log and build/wix/light.log."
        echo "    The app folder and ZIP above are still fine."
    fi
else
    echo "==> WiX Toolset not found - skipping the MSI"
    echo "    To also get an installer (MSI), install the free WiX"
    echo "    Toolset v3 and add its bin folder to PATH, then rerun."
    echo "    The app folder and ZIP above are still fine."
fi

echo ""
echo "DONE. Results are in binaries/:"
echo "    $APP_NAME-$SLUG (folder with SionicalRadio.exe)"
echo "    $APP_NAME-$SLUG.zip (portable)"
if [ -f "binaries/$APP_NAME-Setup-$SLUG.msi" ]; then
    echo "    $APP_NAME-Setup-$SLUG.msi (installer)"
fi
