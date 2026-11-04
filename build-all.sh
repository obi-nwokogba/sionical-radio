#!/bin/bash
# build-all.sh - build every SIONICAL RADIO installer this machine can.
#
# On a Mac it produces BOTH macOS installers:
#   binaries/SionicalRadio-macOS-Intel.dmg
#   binaries/SionicalRadio-macOS-AppleSilicon.dmg
# On Windows it tells you the one command to run in PowerShell (the
# Windows build needs PowerShell, not bash).
#
# Usage:
#   chmod +x build-all.sh
#   ./build-all.sh

set -e
cd "$(dirname "$0")"

case "$(uname -s)" in
    Darwin)
        echo "==> macOS: building both Intel and Apple Silicon installers"
        ./build-mac-intel.sh
        ./build-mac-silicon.sh
        echo ""
        echo "The Windows build must be made on a Windows PC in PowerShell:"
        echo "    powershell -ExecutionPolicy Bypass -File .\build-windows.ps1"
        ;;
    MINGW*|MSYS*|CYGWIN*|Windows*)
        echo "==> Windows detected (bash shell)."
        echo "The Windows build is a PowerShell script. Run it like this:"
        echo "    powershell -ExecutionPolicy Bypass -File ./build-windows.ps1"
        echo "or right-click build-windows.ps1 in Explorer and choose"
        echo "'Run with PowerShell'."
        ;;
    *)
        echo "ERROR: unsupported system ($(uname -s))."
        echo "Use build-mac-intel.sh / build-mac-silicon.sh on a Mac,"
        echo "or build-windows.ps1 in PowerShell on a Windows PC."
        exit 1
        ;;
esac

echo ""
echo "DONE"
