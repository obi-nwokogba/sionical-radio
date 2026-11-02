# SIONICAL RADIO

An elegant internet radio player for macOS (Intel and Apple Silicon) and Windows.

I have always wanted a genuinely beautiful internet radio player that runs
natively on every machine I use: an Intel Mac, an Apple Silicon Mac, and a
Windows PC. I looked around and noticed there was no player like that, so I
built one. SIONICAL RADIO is the result: a single, carefully crafted app
that feels at home on all three platforms.

## Features

- A fully rounded, frameless window with macOS-style traffic lights
- 24 hand-crafted themes: 12 dark, 12 light
- A real FFT equalizer (10 to 50 bars) that dances to the live audio
- A continuously scrolling "Artist - Song" marquee
- One big play/stop circle, with mute, love, and next-station controls
- Station favorites: hearts float loved stations to the top of the list
- .pls playlist support: open, drag, and drop to play
- A custom volume bar with a percent readout
- Up to five custom fonts, each theme picks four of them for four roles
- A bundled VLC engine, so listeners install nothing
- A real "Artist - Song" line, read from the station's ICY metadata

## Run it

```
python SionicalRadio.py
```

## Build it yourself

My goal is for anyone to be able to build SIONICAL RADIO locally, even if
a ready-made installer does not work on their machine. Each platform has
its own small build script, written in plain bash, using only free tools.
Every script drops its installers into a `binaries` folder next to the
project.

```
./build-mac-intel.sh     # macOS Intel (.dmg)
./build-mac-silicon.sh   # macOS Apple Silicon (.dmg)
./build-windows.sh       # Windows x64: .exe and .msi (run in Git Bash)
./build-all.sh           # every installer this machine can build
```

What you need first: Python 3.12 and VLC installed. Each script creates
its own private build environment, so your Python setup is never touched.
For the Windows MSI, install the free WiX Toolset; without it you still
get the .exe. Drop your logo in as `components/sionical-radio-logo.png`
and the scripts automatically turn it into the launcher and installer
icon on every platform.

One honest limitation: installers cannot be cross-built between operating
systems. A Mac builds both macOS DMGs, and a Windows PC (Git Bash) builds
the .exe and .msi. `build-all.sh` simply runs whichever of the three apply
to the machine you are on and tells you where to run the rest.

The macOS apps are signed ad hoc, so on first launch right-click the app
and choose Open, then Open again.

## About

This project is made by me, Obilo Nwokogba.

Visit my personal website: [www.obilo.io](https://www.obilo.io)