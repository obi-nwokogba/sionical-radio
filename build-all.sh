#!/bin/bash
# build-all.sh - build every SIONICAL RADIO installer this machine can.
#
# One honest limitation first: PyInstaller cannot cross-build between
# operating systems. A Mac can build both macOS DMGs (Intel and Apple
# Silicon), and a Windows PC can build the Windows .exe/.msi. This
# script simply runs whatever applies to the machine you are on, and
# tells you exactly what to run where for the rest.
#
# Usage (from the project root, next to SionicalRadio.py):
#   bash build-all.sh
#
# All installers land in the "binaries" folder.

set -e
cd "$(dirname "$0")"

echo "==> SIONICAL RADIO - building everything this machine can"

case "$(uname -s)" in
    Darwin)
        bash build-mac-intel.sh
        bash build-mac-silicon.sh
        echo ""
        echo "==> macOS installers are in binaries/."
        echo "    The Windows .exe and .msi must be built on a Windows PC"
        echo "    (Git Bash from https://gitforwindows.org):"
        echo "        bash build-windows.sh"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        bash build-windows.sh
        echo ""
        echo "==> Windows installers are in binaries/."
        echo "    The macOS DMGs must be built on a Mac:"
        echo "        bash build-mac-intel.sh && bash build-mac-silicon.sh"
        ;;
    *)
        echo "ERROR: this machine is neither macOS nor Windows (Git Bash)."
        echo "Run this script on a Mac or on a Windows PC inside Git Bash."
        exit 1
        ;;
esac

echo ""
echo "All applicable installers are in binaries/."
