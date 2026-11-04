# build-windows.ps1 - build SIONICAL RADIO for Windows x64.
# Run this ON A WINDOWS PC, in PowerShell:
#     powershell -ExecutionPolicy Bypass -File .\build-windows.ps1
# (or right-click the file in Explorer and choose "Run with PowerShell").
# PyInstaller cannot cross-build from macOS, so the Windows installers
# must be produced on a Windows PC.
#
# One-time setup on the Windows machine:
#   1. Install Python 3.12, 64-bit, from python.org (tick "Add to PATH").
#   2. Install VLC for Windows: https://www.videolan.org/vlc/
#   3. Optional, only for the MSI: install WiX Toolset v3 and add its
#      bin folder (candle.exe, light.exe) to PATH.
#
# Output in binaries\:
#   SionicalRadio-Windows-x64\       the app folder (SionicalRadio.exe)
#   SionicalRadio-Windows-x64.zip    portable copy of the above
#   SionicalRadio-Setup-x64.msi      installer (only if WiX is present)
#
# The script builds inside its own private venv (.venv-build), so your
# development Python is never touched. If components\sionical-radio-logo.png
# exists, it is turned into the app's icon (.ico) via Pillow.

$ErrorActionPreference = "Stop"

$AppName        = "SionicalRadio"
$Script         = "SionicalRadio.py"
$Slug           = "Windows-x64"
$Venv           = ".venv-build"
$UpgradeCode    = "B7E2C5A4-31D9-4F8B-9C60-2A5E7F1D4B22"
$ProductVersion = "8.0.0"
$MsiPath        = "binaries\" + $AppName + "-Setup-" + $Slug + ".msi"

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Say($msg)  { Write-Host ("==> " + $msg) }
function Warn($msg) { Write-Host ("    " + $msg) }
function Die($msg)  { Write-Host ("ERROR: " + $msg); exit 1 }

Say "SIONICAL RADIO - $Slug build"

# ---- this is a Windows build ------------------------------------------
if (-not $env:OS -or $env:OS -ne "Windows_NT") {
    Die "This script builds Windows binaries, so it must run on Windows, in PowerShell."
}

if (-not (Test-Path $Script)) {
    Die "$Script not found next to this script."
}

# ---- find Python ------------------------------------------------------
$BasePy = $null
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) {
    $BasePy = $pythonCmd.Source
} else {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        # Ask the launcher where its Python 3 lives. Stderr must be
        # silenced with a relaxed ErrorActionPreference, or PowerShell
        # 5.1 turns the launcher's stderr chatter into a stop error.
        $exe = $null
        $oldEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $exe = (& $pyLauncher.Source -3 -c "import sys; print(sys.executable)") 2>$null
        } catch { }
        $ErrorActionPreference = $oldEap
        if ($exe) {
            $exe = "$exe".Trim()
            if ($exe -and (Test-Path $exe)) { $BasePy = $exe }
        }
    }
}
if (-not $BasePy) {
    Die "Python not found. Install 64-bit Python 3.12 from python.org and tick 'Add to PATH', then rerun."
}
Say ("Python: " + $BasePy)

# ---- 64-bit check ------------------------------------------------------
$bits = (& $BasePy -c "import struct; print(struct.calcsize('P') * 8)")
if ("$bits".Trim() -ne "64") {
    Die "This Python is $bits-bit. Install the 64-bit Python 3.12 from python.org, then rerun."
}

# ---- find the installed VLC engine --------------------------------------
$VlcDir = $null
foreach ($cand in @("$env:ProgramFiles\VideoLAN\VLC",
                    "${env:ProgramFiles(x86)}\VideoLAN\VLC")) {
    if ($cand -and (Test-Path (Join-Path $cand "libvlc.dll"))) {
        $VlcDir = $cand
        break
    }
}
if (-not $VlcDir) {
    Die "VLC not found in Program Files. Install it from https://www.videolan.org/vlc/ then rerun."
}
Say ("using VLC from: " + $VlcDir)

# ---- private build venv (created once, reused afterwards) ---------------
if (-not (Test-Path $Venv)) {
    Say "creating the private build venv ($Venv)"
    & $BasePy -m venv $Venv
}
$Py = Join-Path $Venv "Scripts\python.exe"
& $Py -m pip install --quiet --upgrade pip
Say "installing build requirements"
# Pillow is only needed here (the macOS scripts use the built-in sips
# to make the .icns instead).
& $Py -m pip install --quiet -r requirements.txt pillow==11.3.0
if ($LASTEXITCODE -ne 0) { Die "pip install failed." }

# ---- clean previous build output ----------------------------------------
Say "building the app folder with PyInstaller (a few minutes)"
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist" }
New-Item -ItemType Directory -Force -Path "build" | Out-Null

# ---- app icon (from components\sionical-radio-logo.png) ------------------
$IconArgs = @()
if (Test-Path "components\sionical-radio-logo.png") {
    Say "turning the logo into the app icon (.ico)"
    $icoCode = 'from PIL import Image; Image.open("components/sionical-radio-logo.png").convert("RGBA").save("build/SionicalRadio.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])'
    & $Py -c $icoCode
    if (Test-Path "build\SionicalRadio.ico") {
        $IconArgs = @("--icon", "build\SionicalRadio.ico")
    } else {
        Warn "the .ico could not be generated; building with the default icon"
    }
} else {
    Warn "no components\sionical-radio-logo.png; building with the default icon"
}

# ---- PyInstaller build -----------------------------------------------------
$DataArgs = @()
if (Test-Path "components") {
    # On Windows, --add-data uses a semicolon separator.
    $DataArgs = @("--add-data", "components;components")
}
& $Py -m PyInstaller -y --windowed --onedir --name $AppName @DataArgs @IconArgs $Script
if ($LASTEXITCODE -ne 0) { Die "PyInstaller failed." }
$AppDir = "dist\" + $AppName

# ---- bundle the VLC engine --------------------------------------------------
Say "bundling the VLC engine (end users never install VLC)"
New-Item -ItemType Directory -Force -Path "$AppDir\libvlc" | Out-Null
Copy-Item "$VlcDir\libvlc.dll"    "$AppDir\libvlc\"
Copy-Item "$VlcDir\libvlccore.dll" "$AppDir\libvlc\"
Copy-Item "$VlcDir\plugins" "$AppDir\libvlc\plugins" -Recurse -Force

# ---- collect everything into binaries\ ---------------------------------------
Say "collecting the results in binaries\"
New-Item -ItemType Directory -Force -Path "binaries" | Out-Null
$OutDir = "binaries\" + $AppName + "-" + $Slug
if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }
if (Test-Path ($OutDir + ".zip")) { Remove-Item -Force ($OutDir + ".zip") }
if (Test-Path $MsiPath) { Remove-Item -Force $MsiPath }
Copy-Item -Recurse $AppDir $OutDir
Warn ("app folder: " + $OutDir + " (SionicalRadio.exe inside)")

Say "creating the portable ZIP"
try {
    Compress-Archive -Path $OutDir -DestinationPath ($OutDir + ".zip") -Force
    Warn ("portable: " + $OutDir + ".zip")
} catch {
    Warn "the ZIP could not be produced; the app folder above is still fine."
}

# ---- the MSI (optional: needs the free WiX Toolset v3) ----------------------
$candle = Get-Command candle -ErrorAction SilentlyContinue
$light  = Get-Command light  -ErrorAction SilentlyContinue
if ($candle -and $light) {
    Say "generating the MSI with WiX"
    New-Item -ItemType Directory -Force -Path "build\wix" | Out-Null

    # Generate the WiX source by walking the app tree: one <Component>
    # per file, nested <Directory> elements per subfolder, plus Start
    # Menu and Desktop shortcuts. No heat.exe needed.
    $script:Idx = 0
    $script:AppRoot = (Resolve-Path $AppDir).Path
    $script:Body = New-Object System.Text.StringBuilder
    $script:Refs = New-Object System.Text.StringBuilder

    function Emit-Tree([string]$RelDir) {
        if ($RelDir -eq "") {
            $Base = $script:AppRoot
        } else {
            $Base = Join-Path $script:AppRoot $RelDir
        }
        foreach ($entry in (Get-ChildItem -LiteralPath $Base)) {
            $script:Idx = $script:Idx + 1
            if ($entry.PSIsContainer) {
                [void]$script:Body.AppendLine(("        <Directory Id=`"d{0}`" Name=`"{1}`">" -f $script:Idx, $entry.Name))
                Emit-Tree ($RelDir + $entry.Name + "\")
                [void]$script:Body.AppendLine("        </Directory>")
            } else {
                [void]$script:Body.AppendLine(("        <Component Id=`"c{0}`" Guid=`"*`" Win64=`"yes`">" -f $script:Idx))
                $src = "dist\" + $AppName + "\" + $RelDir + $entry.Name
                [void]$script:Body.AppendLine(("          <File Id=`"f{0}`" Name=`"{1}`" Source=`"{2}`" />" -f $script:Idx, $entry.Name, $src))
                [void]$script:Body.AppendLine("        </Component>")
                [void]$script:Refs.AppendLine(("      <ComponentRef Id=`"c{0}`" />" -f $script:Idx))
            }
        }
    }

    Emit-Tree ""

    $Wxs = New-Object System.Text.StringBuilder
    [void]$Wxs.AppendLine('<?xml version="1.0" encoding="UTF-8"?>')
    [void]$Wxs.AppendLine('<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">')
    [void]$Wxs.AppendLine('  <Product Id="*" Name="' + $AppName + '" Language="1033" Version="' + $ProductVersion + '" Manufacturer="Obilo Nwokogba" UpgradeCode="{' + $UpgradeCode + '">')
    [void]$Wxs.AppendLine('    <Package InstallerVersion="200" Compressed="yes" InstallScope="perMachine" Description="An elegant internet radio player." />')
    [void]$Wxs.AppendLine('    <MajorUpgrade AllowDowngrades="yes" />')
    [void]$Wxs.AppendLine('    <MediaTemplate EmbedCab="yes" />')
    [void]$Wxs.AppendLine('    <Directory Id="TARGETDIR" Name="SourceDir">')
    [void]$Wxs.AppendLine('      <Directory Id="ProgramFilesFolder">')
    [void]$Wxs.AppendLine('        <Directory Id="INSTALLDIR" Name="' + $AppName + '">')
    [void]$Wxs.Append($script:Body.ToString())
    # Start Menu + Desktop shortcuts (components live inside
    # INSTALLDIR so MSI removes them on uninstall).
    [void]$Wxs.AppendLine('        <Component Id="c_startmenu" Guid="*" Win64="yes">')
    [void]$Wxs.AppendLine('          <Shortcut Id="sc_start" Directory="AppShortcutsDir" Name="' + $AppName + '" Target="[INSTALLDIR]' + $AppName + '.exe" WorkingDirectory="INSTALLDIR" />')
    [void]$Wxs.AppendLine('          <RemoveFolder Id="rf_start" Directory="AppShortcutsDir" On="uninstall" />')
    [void]$Wxs.AppendLine('          <RegistryValue Root="HKCU" Key="Software\SionicalRadio" Name="startmenu" Type="integer" Value="1" KeyPath="yes" />')
    [void]$Wxs.AppendLine('        </Component>')
    [void]$Wxs.AppendLine('        <Component Id="c_desktop" Guid="*" Win64="yes">')
    [void]$Wxs.AppendLine('          <Shortcut Id="sc_desktop" Directory="DesktopFolder" Name="' + $AppName + '" Target="[INSTALLDIR]' + $AppName + '.exe" WorkingDirectory="INSTALLDIR" />')
    [void]$Wxs.AppendLine('          <RegistryValue Root="HKCU" Key="Software\SionicalRadio" Name="desktop" Type="integer" Value="1" KeyPath="yes" />')
    [void]$Wxs.AppendLine('        </Component>')
    [void]$Wxs.AppendLine('        </Directory>')
    [void]$Wxs.AppendLine('      </Directory>')
    [void]$Wxs.AppendLine('      <Directory Id="ProgramMenuFolder">')
    [void]$Wxs.AppendLine('        <Directory Id="AppShortcutsDir" Name="' + $AppName + '" />')
    [void]$Wxs.AppendLine('      </Directory>')
    [void]$Wxs.AppendLine('    </Directory>')
    [void]$Wxs.AppendLine('    <Feature Id="Complete" Level="1">')
    [void]$Wxs.Append($script:Refs.ToString())
    [void]$Wxs.AppendLine('      <ComponentRef Id="c_startmenu" />')
    [void]$Wxs.AppendLine('      <ComponentRef Id="c_desktop" />')
    [void]$Wxs.AppendLine('    </Feature>')
    [void]$Wxs.AppendLine('  </Product>')
    [void]$Wxs.AppendLine('</Wix>')

    $WxsPath = "build\wix\SionicalRadio.wxs"
    [IO.File]::WriteAllText($WxsPath, $Wxs.ToString())

    # candle and light write chatter to stderr, which a redirected
    # PowerShell call would turn into errors; run them detached and
    # capture their output in log files instead.
    $proc = Start-Process -FilePath $candle.Source `
        -ArgumentList @("-arch", "x64", "-out", "build\wix\SionicalRadio.wixobj", $WxsPath) `
        -NoNewWindow -Wait -PassThru -RedirectStandardError "build\wix\candle.log"
    if ($proc.ExitCode -eq 0) {
        $null = Start-Process -FilePath $light.Source `
            -ArgumentList @("-out", $MsiPath, "build\wix\SionicalRadio.wixobj") `
            -NoNewWindow -Wait -PassThru -RedirectStandardError "build\wix\light.log"
    }
    if (Test-Path $MsiPath) {
        Warn ("installer: " + $MsiPath)
    } else {
        Warn "the MSI could not be produced;"
        Warn "see build\wix\candle.log and build\wix\light.log."
        Warn "the app folder and ZIP above are still fine."
    }
} else {
    Say "WiX Toolset not found - skipping the MSI"
    Warn "to also get an installer (MSI), install the free WiX"
    Warn "Toolset v3 and add its bin folder to PATH, then rerun."
    Warn "the app folder and ZIP above are still fine."
}

Write-Host ""
Write-Host "DONE. Results are in binaries\:"
Warn ($AppName + "-" + $Slug + " (folder with SionicalRadio.exe)")
Warn ($AppName + "-" + $Slug + ".zip (portable)")
if (Test-Path $MsiPath) {
    Warn ($AppName + "-Setup-" + $Slug + ".msi (installer)")
}

# Keep the window open when launched by right-click "Run with PowerShell".
Write-Host ""
$null = Read-Host "Press Enter to close"
