#!/usr/bin/env python3
"""SIONICAL RADIO - a stylish, themeable internet radio player.

Cross-platform (macOS Intel, macOS Apple Silicon, Windows; Linux works
too), built on PySide6 and the VLC engine.

DESIGN
    A themeable glass panel with a framed look. The header carries the
    traffic-light buttons (close, minimize, maximize), then the
    SIONICAL RADIO text logo (an SVG tinted with the theme), then the
    wire band chips (10, 20, 30, 40, 50) and the THEME button, all
    together in the top right corner. Below the header, a subtle 2 px
    hairline frames the station name and the scrolling "Artist - Song"
    marquee, which span the whole width of the app, with a fainter
    hairline under the marquee. Right after the station name, two wire
    pills show the stream's format and bitrate (MP3, 128 KBPS), drawn
    in the station name's color made 60% more transparent. The middle row pairs the big circular
    play/stop button (with three smaller circular controls beneath it:
    mute, love the station, next station) with the live FFT visualizer,
    whose bars always end on the same line as the mute / love / next
    buttons and never grow when the window is resized. The volume bar
    starts exactly where the visualizer starts, so both sit on one
    invisible vertical line. The station list is a drawer that slides
    out from UNDER the main panel when the STATIONS button is clicked,
    with the same rounded beauty at its bottom corners. The whole
    window is one smooth rounded rectangle (WINDOW_RADIUS below) with
    no OS title bar; dragging the panel moves the window. Every
    station row starts with a heart - filled and bright when loved
    (loved stations float to the top of the list), a clear outline
    when not.

FONTS (optional but recommended)
    Drop up to five TrueType files named exactly font1.ttf, font2.ttf,
    font3.ttf, font4.ttf and font5.ttf into a "components" folder next
    to this file. Every theme assigns FOUR DIFFERENT fonts to four
    roles:
        "brand" - spare role (kept for custom themes.json files)
        "title" - big labels: the station name and the marquee
        "body"  - general text: buttons, station rows, status line
        "wire"  - the wire-outline buttons (band chips, THEME button)
    Missing fonts simply fall back to the system font, so the app
    always runs.

ICONS (optional)
    The mute / love / next circles and the hearts in the station list
    use SVG files from the same "components" folder: unmuted.svg,
    muted.svg, heart-outline.svg, heart-filled.svg and next.svg. The
    header text logo is loaded from sionical-text-logo.svg (or
    sionical_text_only_logo_black.svg - both names work) and tinted
    with the theme's text color. A logo file named
    sionical-radio-logo.png (or .svg) becomes the window icon; the
    build scripts also turn it into the launcher and installer icon
    (SionicalRadio.icns on macOS, SionicalRadio.ico on Windows).
    Missing files fall back to built-in painted shapes.

THEMES
    Thirty-four themes are embedded below as JSON: seventeen dark
    themes followed by seventeen light themes. If the file
    components/themes.json exists, it replaces them all, so you can
    restyle the app without touching this code. The wire THEME button
    (top right) shows the current theme's name and cycles through the
    list at runtime.

SETUP (development machine only)
    pip install -r requirements.txt
    VLC must also be installed here (python-vlc is a thin wrapper around
    libvlc): https://www.videolan.org/vlc/
    End users do NOT need VLC: the installers carry their own engine.

RUN
    python SionicalRadio.py
    python SionicalRadio.py station.pls   (opens the file and plays)

BUILD A DISTRIBUTABLE APP
    macOS:  ./build-mac.sh   (bundles the components folder too)
    Windows and details: see the Setup and Build Guide, section 5.
"""

import array
import ctypes
import json
import math
import os
import re
import sys
import threading


def prepare_bundled_vlc():
    """Point python-vlc at a VLC engine shipped inside the app bundle.

    End users should not need to install VLC. When the app is built with
    PyInstaller, a "libvlc" folder is placed next to the executable,
    containing libvlc, libvlccore, and the plugin modules. If that folder
    is missing (e.g. during development), python-vlc falls back to its
    normal detection of an installed VLC on the machine.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller bundle: the directory that holds the executable.
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        # Development: look next to this source file.
        base = os.path.dirname(os.path.abspath(__file__))
    lib_dir = os.path.join(base, "libvlc")
    if not os.path.isdir(lib_dir):
        return
    if sys.platform.startswith("win"):
        lib_name = "libvlc.dll"
    elif sys.platform.startswith("darwin"):
        lib_name = "libvlc.dylib"
    else:
        lib_name = "libvlc.so"
    lib_path = os.path.join(lib_dir, lib_name)
    if not os.path.isfile(lib_path):
        return
    plugins_dir = os.path.join(lib_dir, "plugins")
    if os.path.isdir(plugins_dir):
        # VLC_PLUGIN_PATH tells the engine where its modules live.
        # PYTHON_VLC_MODULE_PATH is python-vlc's equivalent hint.
        os.environ.setdefault("VLC_PLUGIN_PATH", plugins_dir)
        os.environ.setdefault("PYTHON_VLC_MODULE_PATH", plugins_dir)
    # PYTHON_VLC_LIB_PATH makes python-vlc load this exact library.
    os.environ["PYTHON_VLC_LIB_PATH"] = lib_path


prepare_bundled_vlc()

try:
    import vlc
except (ImportError, OSError):
    # ImportError: the python-vlc package is missing.
    # OSError: the VLC engine (libvlc) could not be loaded - no bundled
    #           engine was found and VLC is not installed either.
    vlc = None

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtSvg import QSvgRenderer
except Exception:
    # QtSvg ships with every PySide6 wheel, but the app must never die
    # on an import: the painted-shape fallbacks keep every button
    # working even without it.
    QSvgRenderer = None

APP_NAME = "SionicalRadio"
WINDOW_TITLE = "SIONICAL RADIO"

# Fifteen free, listener-supported stations to show the app works out
# of the box. Each row in the app gets a heart (favorite, floats to
# the top) and a subtle remove button.
BUILT_IN_STATIONS = [
    ("SomaFM Groove Salad", "https://ice1.somafm.com/groovesalad-128-mp3"),
    ("SomaFM Drone Zone", "https://ice1.somafm.com/dronezone-128-mp3"),
    ("SomaFM Lush", "https://ice1.somafm.com/lush-128-mp3"),
    ("SomaFM Beat Blender", "https://ice1.somafm.com/beatblender-128-mp3"),
    ("SomaFM Underground 80s", "https://ice1.somafm.com/u80s-128-mp3"),
    ("SomaFM DEF CON Radio", "https://ice1.somafm.com/defcon-128-mp3"),
    ("SomaFM Secret Agent", "https://ice1.somafm.com/secretagent-128-mp3"),
    ("SomaFM Indie Pop Rocks", "https://ice1.somafm.com/indiepop-128-mp3"),
    ("SomaFM Boot Liquor", "https://ice1.somafm.com/bootliquor-128-mp3"),
    ("SomaFM Fluid", "https://ice1.somafm.com/fluid-128-mp3"),
    ("SomaFM Space Station", "https://ice1.somafm.com/spacestation-128-mp3"),
    ("SomaFM Digitalis", "https://ice1.somafm.com/digitalis-128-mp3"),
    ("SomaFM Left Coast 70s", "https://ice1.somafm.com/seventies-128-mp3"),
    ("SomaFM Seven Inch Soul", "https://ice1.somafm.com/7soul-128-mp3"),
    ("Radio Paradise", "https://stream.radioparadise.com/mp3-128"),
]

# ---------------------------------------------------------------------------
# THEMES (JSON)
# ---------------------------------------------------------------------------
# Every theme picks its colors AND its fonts. "fonts" maps FOUR roles to
# four DIFFERENT font files (font1.ttf to font5.ttf, loaded from the
# components folder):
#     "brand" - the "SIONICAL RADIO" wordmark (top right)
#     "title" - big labels: the station name and the marquee
#     "body"  - general text: buttons, station rows, the status line
#     "wire"  - the wire-outline buttons (band chips, THEME button)
#
# Colors are plain web hex values. There are twenty-four themes:
# numbers 1-12 are dark, numbers 13-24 are light (light backgrounds
# with dark text). The first theme, "Sionical Blue", is the main
# design: every color in it comes straight from the UI mockup. To
# customize, create a components/themes.json with the same structure
# and it wins. What each palette key is used for:
#     bg_top / bg_bottom - the window gradient (top and bottom ends)
#     panel              - the inner glass panel and the list rows
#     border             - outlines everywhere (panel, buttons, bars)
#     accent / accent2   - the primary pair: gradients, fills, hearts
#     deep               - the dark end of the button gradients
#     text               - body text
#     glow               - soft glows (the volume handle, the circle)
#     icon               - icons on the circular buttons (white works
#                          on every accent, light themes included)

THEMES_JSON = """
[
  {
    "name": "Sionical Blue",
    "fonts": { "brand": "font4", "title": "font2", "body": "font1",
               "wire": "font3" },
    "colors": {
      "bg_top": "#1A1F3A", "bg_bottom": "#0D1B2A",
      "panel": "#112240", "border": "#2196F3",
      "accent": "#4D94FF", "accent2": "#00BCD4",
      "deep": "#1A3A8F", "text": "#64B5F6",
      "glow": "#00BCD4", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Deep Cyan",
    "fonts": { "brand": "font5", "title": "font3", "body": "font1",
               "wire": "font2" },
    "colors": {
      "bg_top": "#04121F", "bg_bottom": "#02080F",
      "panel": "#082238", "border": "#155E75",
      "accent": "#22D3EE", "accent2": "#67E8F9",
      "deep": "#0E7490", "text": "#A5F3FC",
      "glow": "#22D3EE", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Royal Violet",
    "fonts": { "brand": "font1", "title": "font4", "body": "font2",
               "wire": "font3" },
    "colors": {
      "bg_top": "#17102E", "bg_bottom": "#0A0618",
      "panel": "#241A47", "border": "#6D28D9",
      "accent": "#8B5CF6", "accent2": "#C4B5FD",
      "deep": "#4C1D95", "text": "#DDD6FE",
      "glow": "#A78BFA", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Ember Night",
    "fonts": { "brand": "font2", "title": "font1", "body": "font3",
               "wire": "font5" },
    "colors": {
      "bg_top": "#1D1310", "bg_bottom": "#0C0605",
      "panel": "#2C1B14", "border": "#B45309",
      "accent": "#F97316", "accent2": "#FDBA74",
      "deep": "#9A3412", "text": "#FED7AA",
      "glow": "#FB923C", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Mint Glass",
    "fonts": { "brand": "font3", "title": "font4", "body": "font1",
               "wire": "font2" },
    "colors": {
      "bg_top": "#07211C", "bg_bottom": "#031210",
      "panel": "#0E3328", "border": "#0F766E",
      "accent": "#2DD4BF", "accent2": "#99F6E4",
      "deep": "#115E59", "text": "#CCFBF1",
      "glow": "#5EEAD4", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Graphite Night",
    "fonts": { "brand": "font5", "title": "font1", "body": "font2",
               "wire": "font4" },
    "colors": {
      "bg_top": "#191B21", "bg_bottom": "#0A0B0E",
      "panel": "#232733", "border": "#5B6472",
      "accent": "#9AA6B8", "accent2": "#C3CDDC",
      "deep": "#3A4250", "text": "#D6DCE6",
      "glow": "#8A96A8", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Rosewood Dark",
    "fonts": { "brand": "font1", "title": "font3", "body": "font4",
               "wire": "font2" },
    "colors": {
      "bg_top": "#241019", "bg_bottom": "#120509",
      "panel": "#3A1B28", "border": "#BE185D",
      "accent": "#EC4899", "accent2": "#F9A8D4",
      "deep": "#9D174D", "text": "#FBCFE8",
      "glow": "#F472B6", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Neon Lime",
    "fonts": { "brand": "font1", "title": "font2", "body": "font4",
               "wire": "font3" },
    "colors": {
      "bg_top": "#0D1508", "bg_bottom": "#060903",
      "panel": "#16240C", "border": "#65A30D",
      "accent": "#A3E635", "accent2": "#D9F99D",
      "deep": "#4D7C0F", "text": "#ECFCCB",
      "glow": "#BEF264", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Coral Dusk",
    "fonts": { "brand": "font4", "title": "font5", "body": "font2",
               "wire": "font1" },
    "colors": {
      "bg_top": "#2A1015", "bg_bottom": "#140708",
      "panel": "#3D1820", "border": "#F43F5E",
      "accent": "#FB7185", "accent2": "#FDA4AF",
      "deep": "#BE123C", "text": "#FFE4E6",
      "glow": "#FB7185", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Golden Noir",
    "fonts": { "brand": "font2", "title": "font3", "body": "font5",
               "wire": "font4" },
    "colors": {
      "bg_top": "#1C1503", "bg_bottom": "#0C0901",
      "panel": "#2B2008", "border": "#CA8A04",
      "accent": "#FACC15", "accent2": "#FDE047",
      "deep": "#A16207", "text": "#FEF3C7",
      "glow": "#EAB308", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Cyber Magenta",
    "fonts": { "brand": "font3", "title": "font1", "body": "font4",
               "wire": "font2" },
    "colors": {
      "bg_top": "#1B0B22", "bg_bottom": "#0C0510",
      "panel": "#291033", "border": "#C026D3",
      "accent": "#E879F9", "accent2": "#F5D0FE",
      "deep": "#86198F", "text": "#FAE8FF",
      "glow": "#D946EF", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Glacier Blue",
    "fonts": { "brand": "font5", "title": "font4", "body": "font1",
               "wire": "font3" },
    "colors": {
      "bg_top": "#0B1826", "bg_bottom": "#050B12",
      "panel": "#12283D", "border": "#38BDF8",
      "accent": "#7DD3FC", "accent2": "#BAE6FD",
      "deep": "#0369A1", "text": "#E0F2FE",
      "glow": "#38BDF8", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Deep Crimson",
    "fonts": { "brand": "font2", "title": "font4", "body": "font1",
               "wire": "font3" },
    "colors": {
      "bg_top": "#26060D", "bg_bottom": "#110307",
      "panel": "#38101B", "border": "#D93656",
      "accent": "#F0556F", "accent2": "#FCA5B5",
      "deep": "#9F1239", "text": "#FFE4E9",
      "glow": "#FB7185", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Indigo Dusk",
    "fonts": { "brand": "font3", "title": "font1", "body": "font5",
               "wire": "font4" },
    "colors": {
      "bg_top": "#101537", "bg_bottom": "#070A1E",
      "panel": "#1A224D", "border": "#6366F1",
      "accent": "#818CF8", "accent2": "#C7D2FE",
      "deep": "#3730A3", "text": "#E0E7FF",
      "glow": "#818CF8", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Copper Night",
    "fonts": { "brand": "font5", "title": "font2", "body": "font3",
               "wire": "font1" },
    "colors": {
      "bg_top": "#221208", "bg_bottom": "#100804",
      "panel": "#33200F", "border": "#C2743C",
      "accent": "#E8935A", "accent2": "#FBD0A8",
      "deep": "#9A5B2B", "text": "#FBEAD5",
      "glow": "#EFA96B", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Pine Hollow",
    "fonts": { "brand": "font4", "title": "font3", "body": "font2",
               "wire": "font5" },
    "colors": {
      "bg_top": "#08170F", "bg_bottom": "#030B06",
      "panel": "#0F2418", "border": "#2F9E63",
      "accent": "#34D17D", "accent2": "#A7F3CF",
      "deep": "#166534", "text": "#DCFCE8",
      "glow": "#4ADE80", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Storm Harbor",
    "fonts": { "brand": "font1", "title": "font5", "body": "font4",
               "wire": "font2" },
    "colors": {
      "bg_top": "#131A26", "bg_bottom": "#080C14",
      "panel": "#1D2739", "border": "#64748B",
      "accent": "#94A3B8", "accent2": "#CBD5E1",
      "deep": "#475569", "text": "#E2E8F0",
      "glow": "#9FB3C8", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Daylight Blue",
    "fonts": { "brand": "font4", "title": "font2", "body": "font1",
               "wire": "font5" },
    "colors": {
      "bg_top": "#EAF2FF", "bg_bottom": "#D3E4F8",
      "panel": "#F7FAFF", "border": "#8FB3DC",
      "accent": "#1E6FD9", "accent2": "#22A7D9",
      "deep": "#174EA6", "text": "#1F3A5F",
      "glow": "#5FA8E0", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Morning Mint",
    "fonts": { "brand": "font2", "title": "font3", "body": "font1",
               "wire": "font4" },
    "colors": {
      "bg_top": "#E6F7F1", "bg_bottom": "#CCEEE0",
      "panel": "#F2FBF7", "border": "#6FBFA4",
      "accent": "#0D9268", "accent2": "#14B8A6",
      "deep": "#065F46", "text": "#0B4F3A",
      "glow": "#34D399", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Sand Storm",
    "fonts": { "brand": "font1", "title": "font4", "body": "font2",
               "wire": "font3" },
    "colors": {
      "bg_top": "#FBF3E4", "bg_bottom": "#F0E2C6",
      "panel": "#FDFAF1", "border": "#D2B174",
      "accent": "#C07810", "accent2": "#D97706",
      "deep": "#92400E", "text": "#6B4A12",
      "glow": "#F59E0B", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Lavender Mist",
    "fonts": { "brand": "font5", "title": "font1", "body": "font3",
               "wire": "font2" },
    "colors": {
      "bg_top": "#F1EBFB", "bg_bottom": "#E1D5F2",
      "panel": "#F8F4FE", "border": "#A78BDB",
      "accent": "#7C3AED", "accent2": "#8B5CF6",
      "deep": "#5B21B6", "text": "#372563",
      "glow": "#A78BFA", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Rose Quartz",
    "fonts": { "brand": "font2", "title": "font4", "body": "font1",
               "wire": "font3" },
    "colors": {
      "bg_top": "#FBEBF0", "bg_bottom": "#F2D5E0",
      "panel": "#FEF5F8", "border": "#DB9BB2",
      "accent": "#DB2777", "accent2": "#EC4899",
      "deep": "#9D174D", "text": "#7A2348",
      "glow": "#F472B6", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Slate Paper",
    "fonts": { "brand": "font1", "title": "font2", "body": "font3",
               "wire": "font5" },
    "colors": {
      "bg_top": "#F3F5F8", "bg_bottom": "#E4E8EE",
      "panel": "#FAFBFD", "border": "#9AA8BC",
      "accent": "#3E5A82", "accent2": "#5C7CA6",
      "deep": "#2C4160", "text": "#22314A",
      "glow": "#7C93B5", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Sky Punch",
    "fonts": { "brand": "font1", "title": "font3", "body": "font4",
               "wire": "font2" },
    "colors": {
      "bg_top": "#E0F7FA", "bg_bottom": "#C2E9F6",
      "panel": "#EFFDFF", "border": "#5FB7CC",
      "accent": "#0891B2", "accent2": "#06B6D4",
      "deep": "#0E7490", "text": "#0F4C5C",
      "glow": "#22D3EE", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Peach Cream",
    "fonts": { "brand": "font2", "title": "font4", "body": "font3",
               "wire": "font5" },
    "colors": {
      "bg_top": "#FFF3E9", "bg_bottom": "#FFE4D0",
      "panel": "#FFF9F4", "border": "#F0A878",
      "accent": "#EA580C", "accent2": "#F97316",
      "deep": "#C2410C", "text": "#7C2D12",
      "glow": "#FB923C", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Sea Foam",
    "fonts": { "brand": "font3", "title": "font5", "body": "font1",
               "wire": "font4" },
    "colors": {
      "bg_top": "#E8FBF4", "bg_bottom": "#D0F4E4",
      "panel": "#F4FDF9", "border": "#7BC9A8",
      "accent": "#0D9488", "accent2": "#14B8A6",
      "deep": "#0F766E", "text": "#115E59",
      "glow": "#2DD4BF", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Butter Lemon",
    "fonts": { "brand": "font1", "title": "font5", "body": "font2",
               "wire": "font3" },
    "colors": {
      "bg_top": "#FFFDE7", "bg_bottom": "#FEF6C6",
      "panel": "#FFFEEA", "border": "#D9C24A",
      "accent": "#CA8A06", "accent2": "#EAB308",
      "deep": "#A16207", "text": "#713F12",
      "glow": "#FACC15", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Periwinkle Bloom",
    "fonts": { "brand": "font4", "title": "font3", "body": "font5",
               "wire": "font2" },
    "colors": {
      "bg_top": "#EEF2FF", "bg_bottom": "#DBE4FF",
      "panel": "#F5F7FF", "border": "#8B9CE0",
      "accent": "#4F46E5", "accent2": "#6366F1",
      "deep": "#4338CA", "text": "#312E81",
      "glow": "#818CF8", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Cherry Snow",
    "fonts": { "brand": "font1", "title": "font4", "body": "font2",
               "wire": "font3" },
    "colors": {
      "bg_top": "#FFF0F3", "bg_bottom": "#FFDDE5",
      "panel": "#FFF7F9", "border": "#F2A6BE",
      "accent": "#E11D48", "accent2": "#F43F5E",
      "deep": "#BE123C", "text": "#881337",
      "glow": "#FB7185", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Porcelain Ivory",
    "fonts": { "brand": "font3", "title": "font2", "body": "font4",
               "wire": "font1" },
    "colors": {
      "bg_top": "#FDFBF7", "bg_bottom": "#F1ECE1",
      "panel": "#FFFEFA", "border": "#CFC5B0",
      "accent": "#8C5E3C", "accent2": "#B08557",
      "deep": "#6E4526", "text": "#4A3B2A",
      "glow": "#C8A27A", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Sunrise Blush",
    "fonts": { "brand": "font2", "title": "font5", "body": "font1",
               "wire": "font4" },
    "colors": {
      "bg_top": "#FFF1EC", "bg_bottom": "#FFDCD2",
      "panel": "#FFFAF7", "border": "#F2B8A0",
      "accent": "#E5484D", "accent2": "#F4795B",
      "deep": "#BE3E4B", "text": "#7C2D2E",
      "glow": "#FB9E8C", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Meadow Light",
    "fonts": { "brand": "font4", "title": "font1", "body": "font3",
               "wire": "font2" },
    "colors": {
      "bg_top": "#F0F9E8", "bg_bottom": "#DDEECB",
      "panel": "#F8FDF2", "border": "#A3C47C",
      "accent": "#5B9B3A", "accent2": "#7DB94F",
      "deep": "#3F7A28", "text": "#33531F",
      "glow": "#8CCB5E", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Moonlit Silver",
    "fonts": { "brand": "font5", "title": "font3", "body": "font2",
               "wire": "font4" },
    "colors": {
      "bg_top": "#F2F5F9", "bg_bottom": "#DCE3EC",
      "panel": "#F9FBFE", "border": "#AEBFCE",
      "accent": "#52657A", "accent2": "#6E8399",
      "deep": "#3B4A5C", "text": "#2E3B49",
      "glow": "#8AA1B8", "icon": "#FFFFFF"
    }
  },
  {
    "name": "Frost Aqua",
    "fonts": { "brand": "font1", "title": "font4", "body": "font5",
               "wire": "font3" },
    "colors": {
      "bg_top": "#ECFAFB", "bg_bottom": "#D2EEF2",
      "panel": "#F5FEFF", "border": "#93CCD6",
      "accent": "#17A2B0", "accent2": "#34C3CF",
      "deep": "#0F7E8C", "text": "#0B5560",
      "glow": "#4FD2DF", "icon": "#FFFFFF"
    }
  }
]
"""

THEMES = json.loads(THEMES_JSON)
THEME_INDEX = 0
THEME = THEMES[0]

# The loaded TrueType families, keyed "font1" to "font5".
FONT_FAMILIES = {}

# The visualizer uses a second, silent VLC player that feeds decoded PCM
# to Python (the audible player is untouched). That means the stream is
# downloaded twice while playing. Set this to False if you would rather
# save the bandwidth; the visualizer then falls back to a gentle idle
# animation whenever the app is streaming.
ENABLE_ANALYSER = True

# Audio format requested from the silent analyser player.
ANALYSER_RATE = 44100
ANALYSER_CHANNELS = 2

# FFT size for the visualizer. 512 samples at 44.1 kHz is about 12 ms of
# audio per frame - plenty of resolution for 10 to 50 log-spaced bands,
# and small enough to stay smooth in pure Python.
FFT_SIZE = 512

# --- EASY TWEAKS -----------------------------------------------------------
# The visual numbers that shape the app, collected in one place so you
# can change the design without hunting through the code.
WINDOW_RADIUS = 25.0    # corner radius of the outermost window frame
PANEL_RADIUS = 18.0     # corner radius of the inner glass panel
PANEL_INSET = 9.0       # gap between the window edge and the glass panel
PLAY_BUTTON = 150       # diameter (px) of the big play/stop circle
SMALL_BUTTON = 46       # diameter (px) of the mute / love / next circles
CONTROLS_GAP = 12       # gap (px) between the big circle and the circles
LOGO_HEIGHT = 26        # height (px) of the SIONICAL RADIO text logo
LOGO_GAP = 40           # air (px) between the green window button and
                        # the text logo
# The visualizer column is fixed to exactly the height of the play
# column, so the bottom of the bars always sits on the same line as
# the bottom of the mute / love / next buttons and NEVER grows when
# the window is resized.
EQ_HEIGHT = PLAY_BUTTON + CONTROLS_GAP + SMALL_BUTTON
EQ_TICK_MS = 16         # visualizer refresh rate (16 ms is about 60 fps)
EQ_ATTACK = 0.30        # how fast a bar rises toward a louder target
EQ_RELEASE = 0.07       # how slowly a bar falls toward a quieter target
EQ_BAR_OPACITY = 0.60   # 0..1 opacity of the visualizer bars (60%)
MARQUEE_FONT_SIZE = 22  # marquee ("Artist - Song") font size in points
STATION_FONT_SIZE = 33  # station name font size in points
PILL_FONT_SIZE = 9     # format / bitrate pill font size in points
PILL_ALPHA = 102        # pill wire + text: the station name's color
                        # made 60% more transparent (0.4 x 255)
PILL_PAD_X = 12         # horizontal padding (px) inside a pill
PILL_PAD_Y = 4          # vertical padding (px) inside a pill
ICON_PAD = 14           # px of padding inside the small circles, all the
                        # way round their SVG icons (the icon is this
                        # much smaller than the button on every side);
                        # 14 px makes the icons about 35% smaller than
                        # the old 10 px, still perfectly centered
ROW_ICON = 16           # side (px) of the SVG hearts in the station rows
CHIP_GAP = 7            # gap (px) between the 10..50 band chips (half
                        # the header's own 14 px spacing)
THEME_GAP = 3           # gap (px) between the 50 chip and the THEME
                        # button (half the old 6 px)
HAIRLINE_TOP_ALPHA = 110    # the 2 px line above the station name (0-255)
HAIRLINE_BOTTOM_ALPHA = 55  # the fainter 2 px line below the marquee
SHELF_AREA = 188        # visible height (px) of the stations drawer:
                        # 176 px of list plus breathing room so the
                        # first row clears the panel's bottom edge
SHELF_OVERLAP = 26      # how far (px) the drawer tucks under the panel


def components_dir():
    """Return the folder holding fonts and themes.json.

    Works both in development (next to this source file) and inside a
    PyInstaller build (next to the executable / in _MEIPASS).
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(
            os.path.abspath(sys.executable)
        )
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "components")


def load_fonts_and_themes():
    """Load font1.ttf to font5.ttf and an optional themes.json override.

    IMPORTANT: call this only AFTER a QApplication object exists.
    QFontDatabase.addApplicationFont() talks to Qt's platform font
    database, which does not exist until QApplication is constructed;
    calling it earlier dereferences a null platform pointer and
    segfaults (SIGSEGV in QFontDatabasePrivate::addAppFont).

    Everything is optional: missing fonts fall back to the system font,
    and a broken themes.json is ignored (the embedded themes stay).
    """
    global THEMES, THEME, THEME_INDEX
    folder = components_dir()
    # font5.ttf is optional too: a theme may use any four of the five.
    for num in ("font1", "font2", "font3", "font4", "font5"):
        path = os.path.join(folder, num + ".ttf")
        if not os.path.isfile(path):
            continue
        try:
            font_id = QFontDatabase.addApplicationFont(path)
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    FONT_FAMILIES[num] = families[0]
        except Exception:
            pass
    override = os.path.join(folder, "themes.json")
    if os.path.isfile(override):
        try:
            loaded = json.loads(open(override, "r", encoding="utf-8").read())
            if isinstance(loaded, list) and loaded:
                THEMES = loaded
                THEME_INDEX = 0
                THEME = THEMES[0]
        except Exception:
            pass


def theme_font(role, point_size=11, bold=False, letter_spacing=0):
    """Build a QFont for a font role of the current theme.

    The four roles, each mapped to a DIFFERENT font file per theme:
        "brand" - the "SIONICAL RADIO" wordmark (top right)
        "title" - big labels: the station name and the marquee
        "body"  - general text: buttons, station rows, the status line
        "wire"  - the wire-outline buttons (band chips, THEME button)

    If the theme's font file was not found, Qt's default font is used
    so the app still looks coherent.
    """
    key = THEME["fonts"].get(role)
    family = FONT_FAMILIES.get(key) if key else None
    font = QFont(family) if family else QFont()
    font.setPointSize(point_size)
    font.setBold(bold)
    if letter_spacing:
        font.setLetterSpacing(QFont.AbsoluteSpacing, letter_spacing)
    return font


def col(name, alpha=255):
    """Return a QColor for a palette key of the current theme."""
    color = QColor(THEME["colors"][name])
    if alpha != 255:
        color.setAlpha(alpha)
    return color


def rgba(name, alpha):
    """Return a CSS rgba() string for a palette key (for stylesheets)."""
    color = QColor(THEME["colors"][name])
    return "rgba(%d, %d, %d, %d)" % (color.red(), color.green(), color.blue(), alpha)


def build_qss():
    """Build the application stylesheet from the current theme.

    Hand-painted widgets (buttons, bars, the visualizer) draw their own
    gradients, and PanelFrame paints the entire rounded window
    background, so QSS only needs to handle the station list and the
    scrollbar.

    The QMainWindow rule must stay TRANSPARENT, and it must stay LAST.
    Two reasons: the window is translucent (WA_TranslucentBackground,
    so the corners can be rounded by PanelFrame), and QMainWindow is a
    subclass of QWidget - when two type selectors tie on specificity
    the LATER rule wins, so an opaque background here would cover the
    rounded paint and the window would fall back to a plain rectangle
    (the same class of bug that once made every theme's panel gray).
    """
    c = THEME["colors"]
    body_family = FONT_FAMILIES.get(THEME["fonts"].get("body"), "")
    font_line = "font-family: '%s';" % body_family if body_family else ""
    return """
        QWidget { background: transparent; %(font_line)s font-size: 13px; }
        QLabel { background: transparent; }
        QListWidget { background: transparent; border: none; outline: none; }
        QListWidget::item {
            color: %(text)s; background: %(panel)s;
            border-radius: 10px; margin: 3px 6px; padding: 9px 14px;
        }
        QListWidget::item:hover { background: rgba(255, 255, 255, 22); }
        QListWidget::item:selected { background: %(accent)s; color: #ffffff; }
        QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
        QScrollBar::handle:vertical {
            background: %(border)s; border-radius: 4px; min-height: 30px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QMainWindow {
            background: transparent;
        }
    """ % dict(c, font_line=font_line)


# ---------------------------------------------------------------------------
# SVG ICONS (components folder), tinted with the theme
# ---------------------------------------------------------------------------
# The mute / love / next circles and the station-row hearts load their
# artwork from the components folder as SVG files (unmuted.svg,
# muted.svg, heart-outline.svg, heart-filled.svg, next.svg). The files
# are black-on-transparent; svg_icon() tints them with the current
# theme's colors on every render, so the icons always match the
# palette. Missing files (or a missing QtSvg) return None and callers
# fall back to the painted shapes in this file, so nothing ever breaks.

_ICON_CACHE = {}


def svg_icon(name, color, size):
    """Return a QPixmap of components/<name>.svg, tinted with `color`.

    The SVGs are black-on-transparent, so tinting is one render plus
    one CompositionMode_SourceIn fill: the icon keeps its exact
    silhouette and alpha, only the color changes. Icons render at 2x
    and carry that device pixel ratio, so they stay crisp on Retina
    and HiDPI displays. Results are cached per (file, color, size);
    switching themes just creates new cache keys.
    """
    if QSvgRenderer is None or size <= 0:
        return None
    path = os.path.join(components_dir(), name + ".svg")
    if not os.path.isfile(path):
        return None
    key = (path, color.name(), color.alpha(), float(size))
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return None
    pixels = max(2, int(round(size * 2.0)))  # 2x for smooth Retina icons
    image = QImage(pixels, pixels, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    # Tint: paint `color` only where the icon's pixels are, clipped to
    # the icon's own alpha - the black shape becomes a themed shape.
    painter = QPainter(image)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(image.rect(), color)
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(2.0)
    _ICON_CACHE[key] = pixmap
    return pixmap


# The header text logo: a wide SVG ("sionicalradio" in Gobold uplow),
# black-on-transparent like the other SVGs. Either file name works;
# drop it into the components folder.
LOGO_ASPECT = 542.0 / 129.0  # width / height of the text logo SVG
LOGO_FILENAMES = ("sionical-text-logo.svg",
                  "sionical_text_only_logo_black.svg")


def svg_text_logo(color, height):
    """Return the wide text-logo pixmap tinted with `color`, or None.

    Works exactly like svg_icon() - render, then one
    CompositionMode_SourceIn fill - but keeps the SVG's wide 542 x 129
    aspect ratio instead of a square. Rendered at 2x for HiDPI screens
    and cached per (file, color, height), so theme switches just pick
    the new color from the cache.
    """
    if QSvgRenderer is None or height <= 0:
        return None
    for name in LOGO_FILENAMES:
        path = os.path.join(components_dir(), name)
        if not os.path.isfile(path):
            continue
        key = (path, color.name(), color.alpha(), float(height))
        if key in _ICON_CACHE:
            return _ICON_CACHE[key]
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            continue
        pixels_w = max(2, int(round(height * LOGO_ASPECT * 2.0)))
        pixels_h = max(2, int(round(height * 2.0)))
        image = QImage(pixels_w, pixels_h, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        painter = QPainter(image)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(image.rect(), color)
        painter.end()
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(2.0)
        _ICON_CACHE[key] = pixmap
        return pixmap
    return None


def app_icon():
    """Return a QIcon built from the logo in components, or None.

    Used for the window / dock / taskbar icon at runtime; the build
    scripts turn the same logo into the launcher and installer icons
    (SionicalRadio.icns on macOS, SionicalRadio.ico on Windows).
    """
    for filename in ("sionical-radio-logo.png", "sionicalradio-logo.svg"):
        path = os.path.join(components_dir(), filename)
        if not os.path.isfile(path):
            continue
        try:
            icon = QIcon(path)
            if not icon.isNull():
                return icon
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# PLAIN TEXT PARSING (unchanged behavior)
# ---------------------------------------------------------------------------

def parse_pls(path):
    """Parse a .pls playlist file into a list of {title, url} dicts."""
    entries = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            match = re.match(
                r"^(File|Title|Length)(\d+)\s*=\s*(.*)$",
                line.strip(),
                re.IGNORECASE,
            )
            if not match:
                continue
            key = match.group(1).lower()
            idx = int(match.group(2))
            entry = entries.setdefault(idx, {"title": None, "url": None})
            if key == "file":
                entry["url"] = match.group(3).strip()
            elif key == "title":
                entry["title"] = match.group(3).strip()
    stations = []
    for idx in sorted(entries):
        entry = entries[idx]
        if entry.get("url"):
            if not entry.get("title"):
                entry["title"] = "Station %d" % idx
            stations.append(entry)
    if not stations:
        raise ValueError("no playable entries found in that file")
    return stations


def is_stream_junk(url, text):
    """Return True when `text` is stream plumbing, not track info.

    THE "mp3-128" PROBLEM: some stations never fill the ICY "Now
    Playing" field, and VLC then invents a title out of the stream URL -
    "mp3-128" for a stream that ends in /mp3-128. That is not music
    information, and showing it in the marquee looks broken.

    A text is treated as junk when it is empty, when it is a bare
    codec/bitrate label ("128", "mp3-128", "128 kbps", "aac+"), or when
    every word of it already appears in the stream URL - which is how
    URL-derived fake titles are built. Real "Artist - Song" strings
    contain words the URL does not, so they pass through untouched.
    """
    if not text:
        return True
    cleaned = re.sub(r"[\s\-_|]+", " ", text.strip().lower())
    if not cleaned:
        return True
    # Bare codec names ("mp3", "aac+") or bare bitrates ("128", "96 kbps").
    if re.match(r"^(mp3|aac|ogg|opus|mp4)\+?$", cleaned):
        return True
    if re.match(r"^(mp3|aac|ogg|opus|mp4)?\s*\d{2,3}(\s*k?bps)?$", cleaned):
        return True
    # Every word already inside the URL: the text was derived from it.
    if url:
        url_low = url.lower()
        words = cleaned.split()
        if words and all(word in url_low for word in words):
            return True
    return False


# ---------------------------------------------------------------------------
# AUDIO ANALYSIS (PCM tap + pure Python FFT)
# ---------------------------------------------------------------------------

class PcmTap(object):
    """A tiny thread-safe FIFO of raw PCM frames.

    VLC invokes the audio play callback on one of its own threads, so
    every method here is kept minimal and only holds the lock briefly.
    """

    BYTES_PER_FRAME = 4  # "S16N" stereo: 2 bytes per sample, 2 channels.

    def __init__(self, max_bytes=65536):
        self._lock = threading.Lock()
        self._buf = bytearray()
        self._max = max_bytes

    def feed(self, data):
        """Append PCM bytes arriving from the analyser player."""
        with self._lock:
            self._buf.extend(data)
            if len(self._buf) > self._max:
                # Keep only the newest audio; never grow without bound.
                del self._buf[:len(self._buf) - self._max]

    def clear(self):
        with self._lock:
            self._buf = bytearray()

    def take(self, frames):
        """Return up to `frames` mono float samples, or None if too little.

        The whole buffer is consumed on every call: the visualizer reads
        roughly 30 times per second while audio arrives 44100 times per
        second, so this naturally keeps the bars pinned to the newest
        sound without a growing backlog (or lag).
        """
        need = frames * self.BYTES_PER_FRAME
        with self._lock:
            if len(self._buf) < 1024:
                return None  # not enough fresh audio yet
            if len(self._buf) >= need:
                chunk = bytes(self._buf[-need:])
            else:
                chunk = bytes(self._buf)
            self._buf = bytearray()
        samples = array.array("h")
        samples.frombytes(chunk)
        usable = len(samples) - (len(samples) % 2)
        # Mix the two channels into one mono signal, normalized to -1..1.
        return [(samples[i] + samples[i + 1]) / 65536.0
                for i in range(0, usable, 2)]


def fft_pow2(real, imag):
    """In-place iterative radix-2 FFT (pure Python, no extra packages).

    `real` and `imag` must be equal-length lists whose length is a
    power of two. On return they hold the transform's real and
    imaginary parts.
    """
    n = len(real)
    # 1) Bit-reversal permutation.
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            real[i], real[j] = real[j], real[i]
            imag[i], imag[j] = imag[j], imag[i]
    # 2) Butterfly passes, doubling the sub-transform size each round.
    size = 2
    while size <= n:
        half = size >> 1
        angle = -2.0 * math.pi / size
        wr = math.cos(angle)
        wi = math.sin(angle)
        for start in range(0, n, size):
            cr = 1.0
            ci = 0.0
            for k in range(start, start + half):
                b = k + half
                tr = real[b] * cr - imag[b] * ci
                ti = real[b] * ci + imag[b] * cr
                real[b] = real[k] - tr
                imag[b] = imag[k] - ti
                real[k] += tr
                imag[k] += ti
                cr, ci = cr * wr - ci * wi, cr * wi + ci * wr
        size <<= 1


def band_bin_ranges(count):
    """Map FFT bins onto `count` logarithmically spaced frequency bands.

    Returns a list of (first_bin, last_bin) index pairs that are
    contiguous and never overlap: each band starts where the previous
    one ended. Low bands get a handful of narrow bins each at 44.1 kHz /
    512, high bands get progressively wider slices, which matches how
    hearing works.
    """
    bin_hz = ANALYSER_RATE / float(FFT_SIZE)
    lo_bin = max(1, int(round(90.0 / bin_hz)))
    hi_bin = min(FFT_SIZE // 2 - 1, int(round(11000.0 / bin_hz)))
    ratio = float(hi_bin) / lo_bin
    ranges = []
    start = lo_bin
    for k in range(count):
        edge = lo_bin * ratio ** ((k + 1.0) / count)
        end = max(start + 1, int(math.floor(edge)))
        if k == count - 1:
            end = hi_bin + 1  # the last band reaches the top frequency
        ranges.append((start, end))
        start = end
    return ranges


# ---------------------------------------------------------------------------
# ENGINE
# ---------------------------------------------------------------------------

# ICY "NowPlaying" metadata key, which differs across python-vlc versions.
NOWPLAYING_META = None
if vlc is not None:
    NOWPLAYING_META = getattr(vlc.Meta, "NowPlaying",
                              getattr(vlc.Meta, "Nowplaying", None))


def http_variant(url):
    """Return the plain-http form of an https:// stream URL.

    WHY THIS EXISTS: VLC 3 plays https:// streams perfectly, but its
    HTTPS access module DROPS the ICY "now playing" metadata blocks -
    only the plain http:// module parses them (a long-standing VLC 3
    limitation, fixed only in VLC 4). Radio stations overwhelmingly
    serve the same stream over both schemes, so the silent analyser
    player connects over the plain-http variant and hands the marquee
    the real "Artist - Song" text. If a station offers no plain-http
    stream at all, check_analyser() notices the failed open and
    quietly reconnects the analyser over https - the visualizer keeps
    working and only the metadata stays missing.
    """
    if url and url.lower().startswith("https://"):
        return "http://" + url[len("https://"):]
    return url


class StreamEngine(object):
    """Everything audio: the audible player plus the silent analyser.

    The audible player is a completely normal libvlc media player that
    feeds the speakers. The analyser is a SECOND media player whose
    audio output is a set of callbacks into Python: VLC hands us the
    decoded PCM, we never play it, and the visualizer gets real
    frequency data. The analyser also carries the marquee's "Artist -
    Song" text: it connects over the plain-http variant of the URL
    (see http_variant) because VLC 3 only parses ICY metadata over
    plain http. If anything about the analyser fails (or it is
    disabled), the app keeps playing music and the visualizer uses its
    idle animation instead; check_analyser() reconnects it when its
    plain-http variant of the stream does not exist.
    """

    def __init__(self):
        if vlc is None:
            raise RuntimeError(
                "Could not load the VLC engine. Install VLC from "
                "https://www.videolan.org/vlc/ (and the python-vlc "
                "package: pip install python-vlc). For a built app, "
                "make sure the libvlc folder sits next to the "
                "executable (see the build guide)."
            )
        self.instance = vlc.Instance("--no-video")
        self.player = self.instance.media_player_new()

        # ---- silent analyser player ----------------------------------
        self.pcm_tap = PcmTap()
        self.analyser = None
        self._cb_keepalive = []  # must stay referenced or VLC crashes
        if ENABLE_ANALYSER:
            try:
                self._init_analyser()
            except Exception:
                # Anything wrong here is non-fatal: sound is the product,
                # the visualizer is decoration.
                self.analyser = None

        # Analyser health bookkeeping, used by check_analyser(), which
        # the window's once-a-second heartbeat calls.
        self._analyser_url = None      # the URL the audible player uses
        self._analyser_ticks = 0       # heartbeat ticks since play()
        self._analyser_retried = False  # retry once per play()

    def _init_analyser(self):
        """Create the callback-fed player that feeds the visualizer."""
        cb = vlc.CallbackDecorators
        play = cb.AudioPlayCb(self._on_pcm)
        pause = cb.AudioPauseCb(lambda data, pts: None)
        resume = cb.AudioResumeCb(lambda data, pts: None)
        flush = cb.AudioFlushCb(self._on_flush)
        drain = cb.AudioDrainCb(lambda data: None)
        self._cb_keepalive = [play, pause, resume, flush, drain]

        self.analyser = self.instance.media_player_new()
        # Callbacks and format must be set before playback starts.
        self.analyser.audio_set_format("S16N", ANALYSER_RATE, ANALYSER_CHANNELS)
        self.analyser.audio_set_callbacks(
            play, pause, resume, flush, drain, None)

    # ---- analyser callbacks (run on a VLC thread: be quick) ----------

    def _on_pcm(self, data, samples, count, pts):
        try:
            # count is per channel; S16N stereo means 4 bytes per frame.
            self.pcm_tap.feed(ctypes.string_at(samples, count * 4))
        except Exception:
            pass

    def _on_flush(self, data, pts):
        self.pcm_tap.clear()

    # ---- transport ------------------------------------------------------

    def play(self, url):
        media = self.instance.media_new_location(url)
        self.player.set_media(media)
        self.player.play()
        self._analyser_url = url
        self._analyser_ticks = 0
        self._analyser_retried = False
        # The audible player keeps the exact URL the user chose. The
        # analyser asks for the plain-http variant instead, so that its
        # connection also carries the ICY "Artist - Song" metadata
        # (VLC 3 drops it over https - see http_variant). If the
        # plain-http variant does not exist, check_analyser()
        # reconnects the analyser on the original URL after a few
        # seconds.
        self._start_analyser(http_variant(url))

    def _start_analyser(self, url):
        """Point the silent analyser player at `url` and play it."""
        if self.analyser is None:
            return
        try:
            analysis_media = self.instance.media_new_location(url)
            self.analyser.set_media(analysis_media)
            self.analyser.play()
        except Exception:
            pass

    def check_analyser(self):
        """Nurse the analyser connection once per heartbeat tick.

        If the plain-http variant never opened (the station is
        https-only), the analyser sits in a dead state and the
        visualizer would idle forever. This waits a couple of ticks
        for it to come up, and if it has not, reconnects it on the
        original URL - once per play(). Never raises.
        """
        if self.analyser is None or self._analyser_url is None:
            return
        self._analyser_ticks += 1
        if self._analyser_retried or self._analyser_ticks < 2:
            return
        try:
            state = self.analyser.get_state()
        except Exception:
            return
        alive = (vlc.State.Opening, vlc.State.Buffering,
                 vlc.State.Playing, vlc.State.Paused)
        if state not in alive:
            self._analyser_retried = True
            self._start_analyser(self._analyser_url)

    def stop(self):
        self.player.stop()
        self._analyser_url = None
        if self.analyser is not None:
            try:
                self.analyser.stop()
            except Exception:
                pass
        self.pcm_tap.clear()

    def set_volume(self, percent):
        self.player.audio_set_volume(int(percent))

    def is_streaming(self):
        if vlc is None:
            return False
        try:
            return self.player.get_state() in (
                vlc.State.Opening,
                vlc.State.Buffering,
                vlc.State.Playing,
            )
        except Exception:
            return False

    def now_playing(self):
        """Return the "Artist - Song" info the station broadcasts.

        Most internet radio stations put the current track in the ICY
        "Now Playing" metadata field. Some never send one, and VLC then
        invents a title from the stream URL - "mp3-128" for a stream
        ending in /mp3-128. is_stream_junk() (see above) filters those
        out, so the marquee keeps its "Waiting for track info..." line
        until something real arrives instead of showing a bitrate.

        TWO readers are tried, in order:
          1. the audible player's media - covers VLC versions that do
             expose the ICY title over https (VLC 4 and plain-http
             streams on VLC 3),
          2. the silent analyser player's media - which is connected
             over the plain-http variant of the URL precisely because
             VLC 3 only parses ICY metadata over plain http (see
             http_variant). This is the reader that makes "Artist -
             Song" appear for https:// stations on VLC 3.
        """
        if vlc is None:
            return ""
        for player in (self.player, self.analyser):
            text = self._read_now_playing(player)
            if text:
                return text
        return ""

    def stream_info(self):
        """Return (format, kbps) describing the stream, or (None, None).

        libvlc's track description of the playing media names the codec
        (a fourcc integer) and usually carries the bitrate. Feeds the
        two wire pills next to the station name. Anything unavailable -
        nothing parsed yet, an older python-vlc without
        get_tracks_info(), a secretive stream - comes back as None and
        the caller falls back to probe_url_info()'s URL guess.
        """
        fmt = None
        kbps = None
        try:
            media = self.player.get_media()
            tracks = media.get_tracks_info() if media else []
        except Exception:
            return None, None
        for track in tracks or []:
            name = fourcc_to_format(getattr(track, "codec", 0))
            rate = int(getattr(track, "bitrate", 0) or 0)
            if name and fmt is None:
                fmt = name
            # Bitrate sanity: a real audio stream lands between 8 kbps
            # and about 2 Mbps; anything else is not a bitrate.
            if rate and kbps is None and 8000 <= rate <= 2000000:
                kbps = int(round(rate / 1000.0))
        return fmt, kbps

    def _read_now_playing(self, player):
        """Read the ICY now-playing text off one player's media."""
        if player is None:
            return ""
        try:
            media = player.get_media()
        except Exception:
            return ""
        if media is None:
            return ""
        try:
            url = media.get_mrl() or ""
        except Exception:
            url = ""
        text = ""
        try:
            if NOWPLAYING_META is not None:
                text = (media.get_meta(NOWPLAYING_META) or "").strip()
        except Exception:
            text = ""
        if not text:
            try:
                artist = (media.get_meta(vlc.Meta.Artist) or "").strip()
                title = (media.get_meta(vlc.Meta.Title) or "").strip()
                if artist and title and artist.lower() != title.lower():
                    text = "%s - %s" % (artist, title)
                else:
                    text = title or artist
            except Exception:
                text = ""
        # Drop URL-derived fakes such as "mp3-128".
        if is_stream_junk(url, text):
            return ""
        return text


# ---------------------------------------------------------------------------
# PAINTED WIDGETS
# ---------------------------------------------------------------------------

def rounded_path(rect, radius):
    """Return a QPainterPath for a rounded rectangle."""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


class PanelFrame(QWidget):
    """The glassy rounded frame drawn around the whole interface.

    The window itself is translucent and frameless (see SionicalWindow),
    so this widget is what the user sees as "the main player". It
    paints TWO rounded rectangles:
      1. the OUTER one: the window body, with the theme's background
         gradient and a smooth WINDOW_RADIUS (25 px) on every corner -
         this is what gives the app its fully rounded silhouette.
      2. the INNER one: the glass panel, inset by PANEL_INSET px, with
         a gentler PANEL_RADIUS - the "rounded rectangle inside" look.

    DRAWER MODE: while the stations drawer (StationShelf) is out, the
    window body continues below this frame. Both rounded rects are then
    extended past the frame's bottom edge, and the widget's own
    clipping cuts them off - so the bottom corners, the bottom border
    and the inner panel's bottom line all vanish, and the silhouette
    flows straight into the drawer with no seam. Both gradients are
    mapped in ABSOLUTE window coordinates (the full open height), so
    the panel and the drawer always sample one continuous body of
    color.

    To change the look, tune WINDOW_RADIUS / PANEL_RADIUS / PANEL_INSET
    in the EASY TWEAKS block near the top of this file.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bottom_open = False

    def set_bottom_open(self, opened):
        """Switch between closed (rounded bottom) and drawer mode."""
        if bool(opened) != self._bottom_open:
            self._bottom_open = bool(opened)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        widget = QRectF(self.rect())
        win_h = float(self.window().height())

        # In drawer mode, push both rects below the frame by more than
        # the corner radius: the widget clips the overflow away, which
        # squares off the bottom corners and hides the bottom strokes
        # (the drawer continues them instead).
        drop = (WINDOW_RADIUS + 2.0) if self._bottom_open else 0.0

        # ---- 1) the outer rounded window -------------------------------
        # Covers almost the whole widget (a 1 px hairline of air so the
        # border sits fully inside the window). Everything outside this
        # rounded rect is genuinely transparent, which is what rounds
        # the corners of the OS window itself.
        outer = widget.adjusted(1.0, 1.0, -1.0, -1.0 + drop)
        window_fill = QLinearGradient(QPointF(0.0, 0.0), QPointF(0.0, win_h))
        window_fill.setColorAt(0.0, col("bg_top"))
        window_fill.setColorAt(1.0, col("bg_bottom"))
        painter.setPen(QPen(col("border", 170), 1.2))
        painter.setBrush(window_fill)
        painter.drawPath(rounded_path(outer, WINDOW_RADIUS))

        # ---- 2) the inner glass panel ----------------------------------
        # A clearly theme-colored glass fill: the panel color shading
        # into the window's bottom color for depth. This, together with
        # the window gradient behind it, is what makes each theme's
        # panel visibly distinct instead of a washed-out gray.
        rect = widget.adjusted(PANEL_INSET, PANEL_INSET,
                              -PANEL_INSET, -PANEL_INSET + drop)
        fill = QLinearGradient(QPointF(0.0, PANEL_INSET),
                               QPointF(0.0, win_h - PANEL_INSET))
        fill.setColorAt(0.0, col("panel", 242))
        fill.setColorAt(1.0, col("bg_bottom", 216))
        painter.setPen(QPen(col("border", 110), 1.0))
        painter.setBrush(fill)
        painter.drawPath(rounded_path(rect, PANEL_RADIUS))

    def mousePressEvent(self, event):
        """Drag anywhere on the panel to move the frameless window."""
        if event.button() == Qt.LeftButton:
            window = self.window()
            handle = window.windowHandle() if window is not None else None
            if handle is not None:
                handle.startSystemMove()


class GradientButton(QPushButton):
    """A rounded button painted with a gradient fill and a glass bevel.

    variant:
        "normal" - flat panel fill with a themed border (ADD STREAM...)
        "accent" - accent-to-deep gradient (primary actions)
        "tiny"   - small checkable option chip
        "wire"   - a thin themed border with absolutely NO background:
                   used by the equalizer band chips and the THEME
                   button. Hover brightens the border, checked state
                   switches border and text to the accent color, but
                   nothing is ever filled in.
    arrow: None, or "down"/"up" to draw a small arrow after the text
    (used by the STATIONS accordion toggle).
    """

    def __init__(self, text="", variant="normal", arrow=None, parent=None,
                 checkable=None):
        super().__init__(text, parent)
        self.variant = variant
        self.arrow = arrow
        self.setCursor(Qt.PointingHandCursor)
        self._tiny = variant in ("tiny", "wire")
        # Wire and tiny chips are checkable by default (band selectors);
        # pass checkable=False for buttons that should not stay pressed,
        # like the THEME cycler.
        if checkable is None:
            checkable = self._tiny
        self.setCheckable(checkable)

    def sizeHint(self):
        # Wire buttons wear their own font role ("wire"); everything
        # else uses the body font.
        role = "wire" if self.variant == "wire" else "body"
        metrics = QFontMetrics(theme_font(role, 9 if self._tiny else 11, True))
        width = metrics.horizontalAdvance(self.text())
        width += 30 if self._tiny else 40
        if self.arrow:
            width += 16
        height = 24 if self._tiny else 36
        return QSize(width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 8.0 if self._tiny else 12.0
        path = rounded_path(rect, radius)

        # ---- base fill ------------------------------------------------
        if self.variant == "wire":
            # Wire buttons: a border outline only. Never a fill - not
            # on hover, not when checked; just brighter borders and
            # (when checked) the accent color on border and text.
            if self._tiny and self.isChecked():
                painter.setPen(QPen(col("accent"), 1.3))
            elif self.underMouse():
                painter.setPen(QPen(col("accent2"), 1.2))
            else:
                painter.setPen(QPen(col("border", 170), 1.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        elif self._tiny and self.isChecked():
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            gradient.setColorAt(0.0, col("accent"))
            gradient.setColorAt(1.0, col("accent2"))
            painter.setBrush(gradient)
            painter.setPen(QPen(col("icon", 150), 1.0))
        elif self.variant == "accent":
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            gradient.setColorAt(0.0, col("accent"))
            gradient.setColorAt(1.0, col("deep"))
            painter.setBrush(gradient)
            painter.setPen(QPen(col("accent2", 150), 1.0))
        else:
            painter.setBrush(col("panel", 235))
            painter.setPen(QPen(col("border", 130), 1.0))
        painter.drawPath(path)

        if self.variant != "wire":
            # ---- glass bevel (wire buttons stay flat) ------------------
            bevel = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            bevel.setColorAt(0.0, QColor(255, 255, 255, 26))
            bevel.setColorAt(0.45, QColor(255, 255, 255, 0))
            bevel.setColorAt(1.0, col("bg_bottom", 70))
            painter.setPen(Qt.NoPen)
            painter.setBrush(bevel)
            painter.drawPath(path)

            # ---- hover / pressed feedback ------------------------------
            if self.isDown():
                painter.setBrush(col("bg_bottom", 90))
                painter.drawPath(path)
            elif self.underMouse():
                painter.setBrush(QColor(255, 255, 255, 18))
                painter.drawPath(path)

        # ---- text ------------------------------------------------------
        # Wire buttons use the theme's "wire" font; other buttons the
        # "body" font. Change the roles per theme in THEMES_JSON.
        role = "wire" if self.variant == "wire" else "body"
        font = theme_font(role, 9 if self._tiny else 11, True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text = self.text()
        text_width = metrics.horizontalAdvance(text)
        arrow_room = 10 if self.arrow else 0
        x = (rect.width() - text_width - arrow_room) / 2.0
        if self.variant == "wire" and self._tiny and self.isChecked():
            painter.setPen(col("accent"))
        elif self._tiny and self.isChecked():
            painter.setPen(col("icon"))
        elif self.variant == "accent":
            painter.setPen(col("icon"))
        else:
            painter.setPen(col("text"))
        painter.drawText(
            QRectF(x, rect.top(), text_width + 4.0, rect.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            text,
        )

        # ---- optional arrow --------------------------------------------
        if self.arrow:
            center_y = rect.center().y()
            ax = x + text_width + 4.0
            if self.arrow == "down":
                arrow = QPolygonF([
                    QPointF(ax, center_y - 2.0),
                    QPointF(ax + 8.0, center_y - 2.0),
                    QPointF(ax + 4.0, center_y + 3.0),
                ])
            else:
                arrow = QPolygonF([
                    QPointF(ax + 4.0, center_y - 3.0),
                    QPointF(ax, center_y + 2.0),
                    QPointF(ax + 8.0, center_y + 2.0),
                ])
            painter.setPen(Qt.NoPen)
            painter.setBrush(col("text"))
            painter.drawPolygon(arrow)


class PlayCircleButton(QPushButton):
    """The big circular play/stop control: a pure circle element.

    Nothing is painted outside the circle - no glow, no shadow - so the
    button never reads as a square. Clicks are only accepted inside the
    circle too (hitButton), and the focus rectangle is disabled.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(PLAY_BUTTON, PLAY_BUTTON)
        self.setFlat(True)
        self.setFocusPolicy(Qt.NoFocus)
        self._playing = False

    def set_playing(self, playing):
        if self._playing != playing:
            self._playing = playing
            self.update()

    def hitButton(self, pos):
        """Only the circle itself is clickable, not the square widget."""
        diameter = float(min(self.width(), self.height())) - 30.0
        radius = max(1.0, diameter / 2.0)
        dx = pos.x() - self.width() / 2.0
        dy = pos.y() - self.height() / 2.0
        return dx * dx + dy * dy <= radius * radius

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        side = float(min(self.width(), self.height()))
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        diameter = side - 12.0

        # ---- body: radial gradient for a 3D glass look -------------------
        body = QRadialGradient(
            cx - diameter * 0.18, cy - diameter * 0.22, diameter * 0.78)
        body.setColorAt(0.0, col("accent"))
        body.setColorAt(1.0, col("deep"))
        circle = QRectF(cx - diameter / 2.0, cy - diameter / 2.0,
                        diameter, diameter)
        painter.setBrush(body)
        painter.setPen(QPen(col("border", 200), 1.4))
        painter.drawEllipse(circle)

        # ---- glass highlight on the upper half ---------------------------
        glass = QLinearGradient(circle.topLeft(), circle.bottomLeft())
        glass.setColorAt(0.0, QColor(255, 255, 255, 52))
        glass.setColorAt(0.5, QColor(255, 255, 255, 0))
        glass.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setOpacity(0.55)
        painter.setBrush(glass)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(circle.adjusted(2.0, 2.0, -2.0, -2.0))
        painter.setOpacity(1.0)

        # ---- hover / pressed feedback -------------------------------------
        if self.isDown():
            painter.setBrush(col("bg_bottom", 90))
            painter.drawEllipse(circle)
        elif self.underMouse():
            painter.setBrush(QColor(255, 255, 255, 22))
            painter.drawEllipse(circle)

        # ---- icon: white play triangle or stop square ---------------------
        painter.setPen(Qt.NoPen)
        painter.setBrush(col("icon"))
        if self._playing:
            side_len = diameter * 0.30
            stop = QRectF(cx - side_len / 2.0, cy - side_len / 2.0,
                          side_len, side_len)
            painter.drawRoundedRect(stop, 4.0, 4.0)
        else:
            triangle = QPolygonF([
                QPointF(cx - diameter * 0.15, cy - diameter * 0.21),
                QPointF(cx - diameter * 0.15, cy + diameter * 0.21),
                QPointF(cx + diameter * 0.25, cy),
            ])
            painter.drawPolygon(triangle)


class SmallCircleButton(QPushButton):
    """One of the three circular buttons under the big play button.

    They mirror the big circle's look - the same radial accent-to-deep
    gradient with a glass highlight - but are painted at 70% opacity
    (i.e. 30% transparent), so the big play button stays the visual
    anchor. SMALL_BUTTON (in the EASY TWEAKS block) sets the diameter;
    three of them plus two 6 px gaps add up to exactly the big play
    button's width.

    Icons come from SVG files in the components folder, tinted with
    the theme's colors and drawn with ICON_PAD (10) px of padding all
    round: unmuted.svg / muted.svg for the mute circle,
    heart-outline.svg / heart-filled.svg for the love circle and
    next.svg for the skip circle. When a file is missing the painted
    shapes below take over, so the app always runs.

    kind:
        "mute"  - checkable. Unmuted / muted speaker icons.
        "heart"  - checkable. The same filled / outline hearts as the
                  station rows, accent-tinted when the current
                  station is loved.
        "next"   - momentary (not checkable). Skip-forward, jumps to
                  the next station.
    """

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(SMALL_BUTTON, SMALL_BUTTON)
        self.setFlat(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        if kind in ("mute", "heart"):
            self.setCheckable(True)

    def hitButton(self, pos):
        """Only the circle is clickable, not the square widget."""
        radius = max(1.0, SMALL_BUTTON / 2.0 - 2.0)
        dx = pos.x() - self.width() / 2.0
        dy = pos.y() - self.height() / 2.0
        return dx * dx + dy * dy <= radius * radius

    def enterEvent(self, event):
        self.update()

    def leaveEvent(self, event):
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        d = float(SMALL_BUTTON) - 8.0
        circle = QRectF(cx - d / 2.0, cy - d / 2.0, d, d)

        # ---- body: same gradient as the big circle, but 30% transparent
        painter.setOpacity(0.70)
        body = QRadialGradient(
            cx - d * 0.18, cy - d * 0.22, d * 0.78)
        body.setColorAt(0.0, col("accent"))
        body.setColorAt(1.0, col("deep"))
        painter.setBrush(body)
        painter.setPen(QPen(col("border", 200), 1.2))
        painter.drawEllipse(circle)

        # ---- glass highlight on the upper half -------------------------
        glass = QLinearGradient(circle.topLeft(), circle.bottomLeft())
        glass.setColorAt(0.0, QColor(255, 255, 255, 52))
        glass.setColorAt(0.5, QColor(255, 255, 255, 0))
        glass.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glass)
        painter.drawEllipse(circle.adjusted(1.5, 1.5, -1.5, -1.5))

        # ---- hover / pressed feedback ------------------------------------
        if self.isDown():
            painter.setBrush(col("bg_bottom", 90))
            painter.drawEllipse(circle)
        elif self.underMouse():
            painter.setBrush(QColor(255, 255, 255, 22))
            painter.drawEllipse(circle)
        painter.setOpacity(1.0)

        # ---- icon: the SVG from components, else a painted shape ------
        # The SVG icons sit with ICON_PAD (10) px of padding all round,
        # so the artwork is smaller than the button by that much on
        # every side.
        side = float(SMALL_BUTTON) - 2.0 * ICON_PAD
        icon = self._svg_icon(side)
        if icon is not None:
            painter.drawPixmap(
                QPointF(cx - side / 2.0, cy - side / 2.0), icon)
            return
        painter.setPen(Qt.NoPen)
        painter.setBrush(col("icon"))
        if self.kind == "heart":
            # Reuse the exact heart shape from the station rows
            # (IconButton.HEART), so both hearts are identical.
            points = QPolygonF([
                QPointF(cx + (px - 0.5) * d, cy + (py - 0.5) * d)
                for px, py in IconButton.HEART
            ])
            if self.isChecked():
                painter.setPen(QPen(col("accent2", 150), 1.0))
                painter.setBrush(col("accent"))
            else:
                painter.setPen(QPen(col("icon", 200), 1.2))
                painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(points)
        elif self.kind == "mute":
            self._paint_speaker(painter, cx, cy, d)
        else:  # "next": skip-forward, two triangles plus a bar
            tri_w = d * 0.16
            for offset in (-d * 0.18, d * 0.10):
                painter.drawPolygon(QPolygonF([
                    QPointF(cx + offset - tri_w / 2.0, cy - d * 0.14),
                    QPointF(cx + offset - tri_w / 2.0, cy + d * 0.14),
                    QPointF(cx + offset + tri_w, cy),
                ]))
            bar_x = cx + d * 0.28
            painter.drawRoundedRect(
                QRectF(bar_x, cy - d * 0.14, d * 0.05, d * 0.28), 1.5, 1.5)

    def _svg_icon(self, side):
        """Return this button's tinted SVG icon, or None to fall back."""
        if self.kind == "mute":
            name = "muted" if self.isChecked() else "unmuted"
            return svg_icon(name, col("icon", 235), side)
        if self.kind == "heart":
            if self.isChecked():
                return svg_icon("heart-filled", col("accent", 235), side)
            return svg_icon("heart-outline", col("icon", 210), side)
        return svg_icon("next", col("icon", 235), side)

    def _paint_speaker(self, painter, cx, cy, d):
        """Speaker + sound waves; a small cross replaces them when muted."""
        speaker = QPolygonF([
            QPointF(cx - d * 0.28, cy - d * 0.10),
            QPointF(cx - d * 0.16, cy - d * 0.10),
            QPointF(cx + d * 0.00, cy - d * 0.24),
            QPointF(cx + d * 0.00, cy + d * 0.24),
            QPointF(cx - d * 0.16, cy + d * 0.10),
            QPointF(cx - d * 0.28, cy + d * 0.10),
        ])
        painter.setBrush(col("icon"))
        painter.drawPolygon(speaker)
        if self.isChecked():
            # Muted: cross out the silence.
            painter.setPen(QPen(col("icon"), 1.8))
            painter.setBrush(Qt.NoBrush)
            r = d * 0.15
            ax = cx + d * 0.12
            painter.drawLine(QPointF(ax - r, cy - r), QPointF(ax + r, cy + r))
            painter.drawLine(QPointF(ax + r, cy - r), QPointF(ax - r, cy + r))
        else:
            # Sound waves: two arcs opening away from the speaker.
            painter.setPen(QPen(col("icon"), 1.6))
            painter.setBrush(Qt.NoBrush)
            for radius in (d * 0.15, d * 0.27):
                arc = QRectF(cx + d * 0.12 - radius, cy - radius,
                             radius * 2.0, radius * 2.0)
                painter.drawArc(arc, -50 * 16, 100 * 16)


class VolumeBar(QWidget):
    """The large custom-painted volume slider.

    Emits valueChanged(int) from 0 to 100 whenever the user drags the
    bar, uses the mouse wheel, or clicks anywhere along the track.
    """

    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(34)
        self._value = 80
        self._dragging = False

    def value(self):
        return self._value

    def set_value(self, value, emit=True):
        value = max(0, min(100, int(value)))
        if value != self._value:
            self._value = value
            self.update()
            if emit:
                self.valueChanged.emit(value)

    def _value_from_x(self, x):
        margin = 12.0
        span = max(1.0, self.width() - 2.0 * margin)
        return int(round(100.0 * max(0.0, min(1.0,
                    (x - margin) / span))))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.set_value(self._value_from_x(event.position().x()))

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.set_value(self._value_from_x(event.position().x()))

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def wheelEvent(self, event):
        step = 4 if event.angleDelta().y() > 0 else -4
        self.set_value(self._value + step)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        margin = 12.0
        track = rect.adjusted(margin, rect.height() * 0.28,
                              -margin, -rect.height() * 0.28)
        radius = track.height() / 2.0
        fraction = self._value / 100.0

        # ---- track --------------------------------------------------------
        painter.setBrush(col("panel", 220))
        painter.setPen(QPen(col("border", 120), 1.0))
        painter.drawRoundedRect(track, radius, radius)

        # ---- filled part with a gradient and soft glow ---------------------
        fill = QRectF(track)
        fill.setWidth(max(track.width() * fraction, 2.0 * radius))
        gradient = QLinearGradient(fill.topLeft(), fill.topRight())
        gradient.setColorAt(0.0, col("accent2"))
        gradient.setColorAt(1.0, col("accent"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(col("glow", 70))
        painter.drawRoundedRect(fill.adjusted(-2.0, -3.0, 2.0, 3.0),
                                radius + 3.0, radius + 3.0)
        painter.setBrush(gradient)
        painter.drawRoundedRect(fill, radius, radius)

        # ---- handle ----------------------------------------------------------
        handle_x = track.left() + track.width() * fraction
        center_y = track.center().y()
        glow = QRadialGradient(handle_x, center_y, 14.0)
        glow.setColorAt(0.0, col("glow", 130))
        glow.setColorAt(1.0, col("glow", 0))
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(handle_x, center_y), 14.0, 14.0)
        painter.setBrush(col("icon"))
        painter.setPen(QPen(col("accent2"), 2.0))
        painter.drawEllipse(QPointF(handle_x, center_y), 6.0, 6.0)


class EqualizerWidget(QWidget):
    """The live equalizer visualization.

    Every EQ_TICK_MS (16 ms, about 60 fps) the widget pulls the freshest
    PCM from the engine's tap and runs a small FFT; each bar shows the
    energy of one logarithmic frequency band - a single rounded
    rectangle that grows and shrinks with the music, painted at
    EQ_BAR_OPACITY (60%) so the bars read like tinted glass.

    SMOOTHING (the anti-flicker): raw FFT band energies jump around a
    lot from frame to frame, which used to look jarring. Two things
    tame it. First, the tick is fast, so every step is small. Second,
    each bar is exponentially TWEENED toward its target - EQ_ATTACK
    (0.30) on the way up, the much gentler EQ_RELEASE (0.07) on the way
    down - which turns flicker into a fluid bounce. Lower the two
    constants for calmer bars; raise them for snappier ones. Both live
    in the EASY TWEAKS block near the top of the file.

    If no PCM is arriving (analyser disabled, stream hiccup, or simply
    stopped), the bars either idle-animate while streaming or gently
    settle to the baseline, so the UI never looks dead.
    """

    BAND_CHOICES = (10, 20, 30, 40, 50)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = None
        self.band_count = 20
        self._ranges = band_bin_ranges(20)
        self._levels = [0.03] * 20
        self._phase = 0.0
        self.setMinimumHeight(110)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(EQ_TICK_MS)

    def set_engine(self, engine):
        self._engine = engine

    def set_band_count(self, count):
        self.band_count = count
        self._ranges = band_bin_ranges(count)
        self._levels = [0.03] * count
        self.update()

    # ---- data ----------------------------------------------------------

    def _target_levels(self):
        """Compute the current target height (0..1) for every band."""
        engine = self._engine
        mono = None
        if engine is not None:
            mono = engine.pcm_tap.take(FFT_SIZE)
        if mono is not None:
            # Real frequency data: FFT the latest window of audio.
            real = mono[:FFT_SIZE]
            real += [0.0] * (FFT_SIZE - len(real))
            imag = [0.0] * FFT_SIZE
            fft_pow2(real, imag)
            targets = []
            for first, last in self._ranges:
                magnitude = 0.0
                for i in range(first, last):
                    magnitude += math.hypot(real[i], imag[i])
                magnitude = magnitude / (last - first) / (FFT_SIZE / 4.0)
                db = 20.0 * math.log10(magnitude + 1e-9)
                targets.append(max(0.03, min(1.0, (db + 46.0) / 42.0)))
            return targets
        # No fresh PCM. While streaming, idle-animate so the design stays
        # alive; otherwise relax to the baseline. The phase step is
        # scaled to the faster tick (0.05 per 33 ms is 0.024 per 16 ms),
        # so the idle wave keeps its original calm speed.
        self._phase += 0.024
        streaming = bool(engine is not None and engine.is_streaming())
        targets = []
        for k in range(self.band_count):
            if streaming:
                wave = (math.sin(self._phase * 1.6 + k * 0.8)
                        * math.sin(self._phase * 0.55 + k * 0.31))
                targets.append(max(0.04, 0.30 + 0.22 * wave))
            else:
                targets.append(0.03)
        return targets

    def _tick(self):
        targets = self._target_levels()
        for k, target in enumerate(targets):
            current = self._levels[k]
            # The tween: fast attack, much slower release. This is the
            # whole anti-flicker mechanism - see the class docstring.
            blend = EQ_ATTACK if target > current else EQ_RELEASE
            self._levels[k] = current * (1.0 - blend) + target * blend
        self.update()

    # ---- painting --------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        count = self.band_count
        slot = rect.width() / count
        # At most 10 px of air between neighboring bars: wide slots
        # (few bars) get wide bars, tight slots (50 bars) shrink the
        # gap proportionally so the bars never touch.
        gap = min(10.0, slot * 0.45)
        bar_width = max(4.0, slot - gap)
        # The bars end EXACTLY on the widget's bottom edge, which is
        # the same line the mute / love / next buttons end on (the
        # middle row is exactly EQ_HEIGHT tall).
        bottom = rect.bottom()
        top = rect.top() + 3.0
        usable = bottom - top

        # Faint baseline the bars sit on.
        painter.setPen(QPen(col("border", 90), 1.0))
        painter.drawLine(QPointF(rect.left(), bottom),
                         QPointF(rect.right(), bottom))

        # The bars are translucent glass (EQ_BAR_OPACITY = 60%). The
        # baseline above stays solid. Raise EQ_BAR_OPACITY toward 1.0
        # for solid bars; lower it for even fainter ones.
        painter.setOpacity(EQ_BAR_OPACITY)
        for k in range(count):
            x = rect.left() + slot * k + (slot - bar_width) / 2.0
            level = self._levels[k]
            height = max(2.0, usable * level)
            bar = QRectF(x, bottom - height, bar_width, height)
            gradient = QLinearGradient(bar.bottomLeft(), bar.topLeft())
            gradient.setColorAt(0.0, col("accent", 235))
            gradient.setColorAt(1.0, col("accent2", 255))
            painter.setBrush(gradient)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar, 3.0, 3.0)
        painter.setOpacity(1.0)  # full opacity for anything painted later


class MarqueeLabel(QLabel):
    """A label that continuously scrolls its text: a true moving marquee.

    Used for the "Artist - Song" line. The text always drifts slowly
    leftward, whether it fits or not, so the design stays alive; enough
    copies are drawn to fill the width and the loop is seamless.
    """

    GAP = 72.0  # blank space between consecutive scrolling copies

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._offset = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(50)

    def _on_timer(self):
        if self.text():
            metrics = QFontMetrics(self.font())
            advance = metrics.horizontalAdvance(self.text())
            self._offset = (self._offset + 1.5) % (advance + self.GAP)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        metrics = QFontMetrics(self.font())
        advance = metrics.horizontalAdvance(self.text())
        painter.setFont(self.font())
        painter.setPen(col("text"))
        painter.setClipRect(rect)
        x = -self._offset
        while x < rect.width():
            painter.drawText(QRectF(x, 0.0, advance + 8.0, rect.height()),
                             Qt.AlignVCenter | Qt.AlignLeft, self.text())
            x += advance + self.GAP


class LogoLabel(QWidget):
    """The SIONICAL RADIO text logo, tinted with the theme.

    Loads the wide wordmark SVG from the components folder
    (svg_text_logo) and repaints it with the theme's TEXT color on
    every paint, so cycling themes recolors the logo instantly. Fixed
    to LOGO_HEIGHT tall (EASY TWEAKS); the width follows the SVG's
    542 x 129 aspect ratio. If the file is missing the widget simply
    paints nothing - the traffic lights still show and nothing breaks.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(int(round(LOGO_HEIGHT * LOGO_ASPECT)), LOGO_HEIGHT)

    def paintEvent(self, event):
        pixmap = svg_text_logo(col("text"), LOGO_HEIGHT)
        if pixmap is None:
            return
        painter = QPainter(self)
        painter.drawPixmap(0, 0, pixmap)


class Hairline(QWidget):
    """A full-width 2 px divider, tinted with the theme's border color.

    Two of these frame the big text rows: a subtle one above the
    station name and an even fainter one below the marquee. The alpha
    (0..255) sets how faint the line is - tune HAIRLINE_TOP_ALPHA and
    HAIRLINE_BOTTOM_ALPHA in the EASY TWEAKS block.
    """

    def __init__(self, alpha, parent=None):
        super().__init__(parent)
        self._alpha = int(alpha)
        self.setFixedHeight(2)

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = QRectF(self.rect())
        painter.setPen(QPen(col("border", self._alpha), 2.0))
        painter.drawLine(QPointF(rect.left() + 1.0, 1.0),
                         QPointF(rect.right() - 1.0, 1.0))


class WirePill(QWidget):
    """A small wire-outline pill, e.g. the stream's format or bitrate.

    The border and the text both use the STATION NAME's color (the
    theme accent) at PILL_ALPHA - the same color made 60% more
    transparent - in the same "title" font as the station name, just
    smaller (PILL_FONT_SIZE). The pill hugs its text and hides itself
    completely while it has nothing to say.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self.setVisible(False)

    def text(self):
        """The pill's current text ("" when there is nothing to show)."""
        return self._text

    def set_pill_text(self, text):
        """Set the text; an empty text hides the pill."""
        text = text or ""
        if text != self._text:
            self._text = text
            self.setVisible(bool(text))
            self.updateGeometry()
            self.update()

    def refresh(self):
        """Re-measure after a theme or font change."""
        self.updateGeometry()
        self.update()

    def _pill_font(self):
        return theme_font("title", PILL_FONT_SIZE, True, 2.0)

    def sizeHint(self):
        if not self._text:
            return QSize(0, 0)
        metrics = QFontMetrics(self._pill_font())
        return QSize(metrics.horizontalAdvance(self._text) + 2 * PILL_PAD_X,
                     metrics.height() + 2 * PILL_PAD_Y)

    def paintEvent(self, event):
        if not self._text:
            return
        painter = QPainter(self)
        painter.setFont(self._pill_font())
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        color = col("accent", PILL_ALPHA)
        # The wire: a rounded rect whose radius is half the height,
        # so the ends are perfectly round (a true pill).
        painter.setPen(QPen(color, 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, rect.height() / 2.0, rect.height() / 2.0)
        # The label, in the very same color.
        painter.setPen(color)
        painter.drawText(QRectF(self.rect()), Qt.AlignCenter, self._text)


def probe_url_info(url):
    """Guess the stream's (format, kbps) from its URL, or (None, None).

    Most station URLs simply say what they are: ".../groovesalad-128-mp3",
    ".../mp3-128", ".../aac-64". The codec tag and one of the common
    bitrate numbers are picked out; the numbers must sit between
    non-digits so ports and frequencies are never mistaken for a
    bitrate. Used as the instant answer when a station is selected,
    and as the fallback whenever the live stream does not volunteer
    its track info.
    """
    low = (url or "").lower()
    fmt = None
    for tag, name in (("aac", "AAC"), ("m4a", "AAC"), ("opus", "OPUS"),
                      ("vorbis", "OGG"), ("ogg", "OGG"), ("flac", "FLAC"),
                      ("mp3", "MP3")):
        if tag in low:
            fmt = name
            break
    kbps = None
    for rate in (320, 256, 224, 192, 160, 128, 112, 96, 80, 64, 56,
                 48, 40, 32):
        if re.search(r"(?<![0-9])%d(?![0-9])" % rate, low):
            kbps = rate
            break
    return fmt, kbps


def fourcc_to_format(fourcc):
    """Decode a libvlc codec fourcc (an int) into a friendly name.

    libvlc describes a track's codec as a four-character code packed
    into an integer ("mp3 " for MP3, "mp4a" for AAC). Returns None for
    codecs with no friendly name here.
    """
    try:
        raw = "".join(chr((int(fourcc) >> (8 * shift)) & 0xFF)
                      for shift in range(4)).strip().lower()
    except Exception:
        return None
    if not raw:
        return None
    if "mp3" in raw or "mpga" in raw or "mp2" in raw or "mpeg" in raw:
        return "MP3"
    if "mp4a" in raw or "aac" in raw:
        return "AAC"
    if "a52" in raw:
        return "AC3"
    if "opus" in raw:
        return "OPUS"
    if "vorb" in raw:
        return "OGG"
    if "flac" in raw:
        return "FLAC"
    if "s16" in raw or "s24" in raw or "s32" in raw or "pcm" in raw \
            or "u8" in raw:
        return "PCM"
    return None


class WindowButton(QPushButton):
    """A macOS-style traffic light used on the frameless window.

    kind: "close" (red), "minimize" (yellow) or "maximize" (green).
    The glyph only appears on hover, like the real thing.
    """

    COLORS = {
        "close": QColor("#FF5F57"),
        "minimize": QColor("#FEBC2E"),
        "maximize": QColor("#28C840"),
    }

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(16, 16)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        painter.setPen(QPen(QColor(0, 0, 0, 60), 1.0))
        painter.setBrush(self.COLORS[self.kind])
        painter.drawEllipse(rect)
        if not self._hover:
            return
        # Glyphs on hover: an X, a minus or a small circle.
        painter.setPen(QPen(QColor(0, 0, 0, 150), 1.4))
        painter.setBrush(Qt.NoBrush)
        cx = rect.center().x()
        cy = rect.center().y()
        if self.kind == "close":
            r = rect.width() * 0.20
            painter.drawLine(QPointF(cx - r, cy - r), QPointF(cx + r, cy + r))
            painter.drawLine(QPointF(cx + r, cy - r), QPointF(cx - r, cy + r))
        elif self.kind == "minimize":
            painter.drawLine(QPointF(cx - 3.0, cy), QPointF(cx + 3.0, cy))
        else:
            painter.drawEllipse(QRectF(cx - 2.2, cy - 2.2, 4.4, 4.4))


class IconButton(QPushButton):
    """A small, subtle icon-only button used in the station rows.

    kind:
        "heart" - checkable: heart-outline.svg when the station is not
                  favorited, heart-filled.svg (accent-tinted) when it
                  is. Both come from the components folder and are
                  tinted with the theme; the painted QPolygonF heart
                  below is the fallback for when the files are missing.
        "close" - a thin X that removes the station
    No background is drawn except a faint accent tint on hover.
    """

    # Heart outline in normalized (x, y) coordinates, y growing down.
    HEART = [
        (0.50, 0.92), (0.10, 0.46), (0.11, 0.24), (0.27, 0.11),
        (0.42, 0.16), (0.50, 0.30), (0.58, 0.16), (0.73, 0.11),
        (0.89, 0.24), (0.90, 0.46),
    ]

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        if kind == "heart":
            self.setCheckable(True)

    def sizeHint(self):
        return QSize(22, 22)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        if self.underMouse():
            painter.setPen(Qt.NoPen)
            painter.setBrush(col("accent", 26))
            painter.drawEllipse(rect.adjusted(2.0, 2.0, -2.0, -2.0))
        if self.kind == "heart":
            # The SVG hearts from components, tinted with the theme:
            # filled + accent when loved, a clearly visible outline in
            # the text color when not (the tint follows the theme, so
            # it stays readable on light backgrounds too).
            if self.isChecked():
                icon = svg_icon("heart-filled", col("accent"), ROW_ICON)
            else:
                icon = svg_icon("heart-outline", col("text", 150),
                                ROW_ICON)
            if icon is not None:
                off = QPointF((rect.width() - ROW_ICON) / 2.0,
                             (rect.height() - ROW_ICON) / 2.0)
                painter.drawPixmap(rect.topLeft() + off, icon)
                return
            points = QPolygonF([
                QPointF(rect.left() + rect.width() * px,
                        rect.top() + rect.height() * py)
                for px, py in self.HEART
            ])
            if self.isChecked():
                # Loved: filled with the accent color and a soft glow
                # border, impossible to miss.
                painter.setPen(QPen(col("accent2", 150), 1.0))
                painter.setBrush(col("accent"))
            else:
                # Not loved: a very, very faint outline - visible enough
                # to invite a click, quiet enough to vanish next to the
                # station name. Raise the 60 alpha for a louder ghost.
                painter.setPen(QPen(col("text", 60), 1.1))
                painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(points)
        else:  # "close": a thin X
            painter.setPen(QPen(col("text", 160), 1.3))
            painter.setBrush(Qt.NoBrush)
            inset = rect.width() * 0.28
            box = rect.adjusted(inset, inset, -inset, -inset)
            painter.drawLine(box.topLeft(), box.bottomRight())
            painter.drawLine(box.topRight(), box.bottomLeft())


# ---------------------------------------------------------------------------
# THE STATION DRAWER
# ---------------------------------------------------------------------------

class StationShelf(QWidget):
    """The station drawer that slides out from under the main panel.

    The shelf is a sibling of PanelFrame inside the window's central
    canvas (a plain, transparent QWidget). PanelFrame paints the main
    player, this widget paints the protrusion below it, and together
    they read as ONE continuous glass body:

      * the fills use the SAME window gradients as PanelFrame, mapped
        in absolute window coordinates, so there is no seam or color
        boundary where the panel ends - the drawer looks like it slid
        out of the very same glass;
      * the bottom corners are rounded with WINDOW_RADIUS (and the
        inner glass panel's with PANEL_RADIUS) - the same beauty as the
        main window - while the top of the shelf tucks
        SHELF_OVERLAP px under the panel;
      * no border is drawn along the top edge: the panel's left and
        right borders continue straight into the drawer's.

    The rounded rects are extended ABOVE this widget by more than
    SHELF_OVERLAP, and the widget's own clipping cuts the overflow
    away - so only the rounded bottom corners and the side borders
    ever show. The station list is pinned to the bottom of the shelf
    with a stretch above it, so while the drawer animates open the
    rows emerge from under the main panel exactly like a drawer being
    pulled out. SionicalWindow places and resizes this widget (see
    _place_frame_children) and drives the slide with a
    QVariantAnimation.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 8)
        layout.setSpacing(0)
        # The stretch pins the list to the bottom: the rows appear
        # from under the panel while the shelf grows downward.
        layout.addStretch(1)
        self.station_list = QListWidget()
        # SHELF_AREA holds the list plus breathing room: the list must
        # start BELOW the SHELF_OVERLAP zone the panel covers (its top
        # 26 px), otherwise the first row's top edge hides under the
        # main panel - 4 px of clearance plus an 8 px bottom margin,
        # so the list itself is SHELF_AREA - 12 tall.
        self.station_list.setFixedHeight(SHELF_AREA - 12)
        layout.addWidget(self.station_list)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        widget = QRectF(self.rect())
        win_h = float(self.window().height())
        y_off = float(self.y())

        # ---- 1) the outer window body, continued -----------------------
        lift = SHELF_OVERLAP + WINDOW_RADIUS + 2.0
        outer = widget.adjusted(1.0, -lift, -1.0, -1.0)
        window_fill = QLinearGradient(QPointF(0.0, -y_off),
                                      QPointF(0.0, win_h - y_off))
        window_fill.setColorAt(0.0, col("bg_top"))
        window_fill.setColorAt(1.0, col("bg_bottom"))
        painter.setPen(QPen(col("border", 170), 1.2))
        painter.setBrush(window_fill)
        painter.drawPath(rounded_path(outer, WINDOW_RADIUS))

        # ---- 2) the inner glass panel, continued -----------------------
        inner_lift = SHELF_OVERLAP + PANEL_RADIUS + 2.0
        rect = widget.adjusted(PANEL_INSET, -inner_lift,
                               -PANEL_INSET, -PANEL_INSET)
        fill = QLinearGradient(QPointF(0.0, PANEL_INSET - y_off),
                               QPointF(0.0, win_h - PANEL_INSET - y_off))
        fill.setColorAt(0.0, col("panel", 242))
        fill.setColorAt(1.0, col("bg_bottom", 216))
        painter.setPen(QPen(col("border", 110), 1.0))
        painter.setBrush(fill)
        painter.drawPath(rounded_path(rect, PANEL_RADIUS))


# ---------------------------------------------------------------------------
# MAIN WINDOW
# ---------------------------------------------------------------------------

class SionicalWindow(QMainWindow):
    """Assembles the whole interface and wires it to the engine."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        # No OS title bar: the close / minimize / maximize traffic lights
        # live inside the panel (see _build_ui), and dragging the panel
        # moves the window (see PanelFrame.mousePressEvent).
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        # ROUNDED WINDOW: a translucent window background lets PanelFrame
        # paint a rounded rectangle (WINDOW_RADIUS, 25 px) with truly
        # transparent corners. Without this attribute the window would
        # be an opaque square and the rounding would be invisible.
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(840, 560)
        # The middle row (play column + visualizer) now keeps a FIXED
        # height (EQ_HEIGHT), so the window needs a slightly taller
        # floor than before to fit every row comfortably.
        self.setMinimumSize(660, 520)
        self.setAcceptDrops(True)

        self.engine = None
        self.current_station = None
        self.playing = False
        self.stream_ok = False
        self._stations_open = False
        # The station drawer: how far it has slid out from under the
        # panel (0 = closed). _panel_h is the main panel's height,
        # maintained by _place_frame_children().
        self._shelf_extent = 0.0
        self._shelf_anim = None
        self._panel_h = 560
        # Volume remembered from before the last mute, so the mute
        # button can restore it.
        self._volume_before_mute = 80
        # The station model: a list of {title, url, favorite} dicts. The
        # QListWidget is just a view of this, rebuilt whenever it changes.
        self._stations = []

        self._build_ui()
        self.apply_theme()

        for title, url in BUILT_IN_STATIONS:
            self.add_station(title, url, rebuild=False)
        self.rebuild_station_list()

        # A .pls file passed on the command line starts playing right away.
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            self.open_pls_file(sys.argv[1])

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(1000)

    # ---- UI construction ---------------------------------------------

    def _build_ui(self):
        # The central widget is a plain, transparent canvas. PanelFrame
        # (the main player) and StationShelf (the drawer) are children
        # of the canvas, placed manually by _place_frame_children(): a
        # layout would stretch one widget over the whole window, but the
        # drawer must sit BELOW the panel's rounded bottom, like a tray
        # pulled out from under it.
        canvas = QWidget()
        self.setCentralWidget(canvas)
        self.panel = PanelFrame(canvas)
        self.shelf = StationShelf(canvas)
        self.shelf.lower()  # the drawer slides out from UNDER the panel

        self.station_list = self.shelf.station_list
        self.station_list.itemDoubleClicked.connect(
            self.on_item_double_clicked)

        root = QVBoxLayout(self.panel)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)

        # == header: traffic lights + the text logo (left), then the
        # band chips and the THEME button, all together (top right).
        header = QHBoxLayout()
        header.setSpacing(14)

        # Traffic lights (the OS title bar is gone): close, minimize,
        # maximize - subtle circles that match the panel's look.
        win_row = QHBoxLayout()
        win_row.setSpacing(7)
        self.close_button = WindowButton("close")
        self.close_button.clicked.connect(self.close)
        win_row.addWidget(self.close_button)
        self.minimize_button = WindowButton("minimize")
        self.minimize_button.clicked.connect(self.showMinimized)
        win_row.addWidget(self.minimize_button)
        self.maximize_button = WindowButton("maximize")
        self.maximize_button.clicked.connect(self.on_toggle_maximize)
        win_row.addWidget(self.maximize_button)
        header.addLayout(win_row)

        # The SIONICAL RADIO text logo, LOGO_GAP (40) px to the right
        # of the green window button and tinted with the theme.
        header.addSpacing(LOGO_GAP)
        self.logo = LogoLabel()
        header.addWidget(self.logo)
        header.addStretch(1)

        # The wire band chips (10..50) plus the THEME button, all
        # together in the top right corner, packed tight: CHIP_GAP (7)
        # between the chips and THEME_GAP (3) before the THEME button,
        # both half of what they used to be.
        chip_row = QHBoxLayout()
        chip_row.setSpacing(CHIP_GAP)
        self._band_buttons = {}
        for count in EqualizerWidget.BAND_CHOICES:
            chip = GradientButton(str(count), "wire")
            chip.setChecked(count == 20)
            chip.clicked.connect(
                lambda checked, c=count: self.on_band_clicked(c))
            chip_row.addWidget(chip)
            self._band_buttons[count] = chip
        header.addLayout(chip_row)
        header.addSpacing(THEME_GAP)
        self.theme_button = GradientButton("THEME", "wire", checkable=False)
        self.theme_button.clicked.connect(self.on_theme_clicked)
        header.addWidget(self.theme_button)
        root.addLayout(header)

        # == the two big text rows, full width, framed by hairlines ===
        self.hairline_top = Hairline(HAIRLINE_TOP_ALPHA)
        root.addWidget(self.hairline_top)
        # The station name, with the format and bitrate pills right
        # after it ("MP3", "128 KBPS") - the same accent color as the
        # name, made 60% more transparent, in the same font smaller.
        station_row = QHBoxLayout()
        station_row.setSpacing(14)
        self.station_label = QLabel(WINDOW_TITLE)
        station_row.addWidget(self.station_label)
        self.format_pill = WirePill()
        station_row.addWidget(self.format_pill, 0, Qt.AlignVCenter)
        self.bitrate_pill = WirePill()
        station_row.addWidget(self.bitrate_pill, 0, Qt.AlignVCenter)
        station_row.addStretch(1)
        root.addLayout(station_row)
        self.marquee = MarqueeLabel(
            "Double-click a station, drop a .pls file anywhere, "
            "or open one with ADD PLS.")
        root.addWidget(self.marquee)
        self.hairline_bottom = Hairline(HAIRLINE_BOTTOM_ALPHA)
        root.addWidget(self.hairline_bottom)

        # == middle: play column (big circle + 3 small circles) + the
        # visualizer. The row keeps its NATURAL height (no stretch), so
        # the bars never grow when the window is resized and their
        # bottom always sits on the same line as the small circles.
        mid = QHBoxLayout()
        mid.setSpacing(18)

        # The play column: the big circle on top, and below it a row of
        # three circular controls - MUTE, LOVE (heart the station) and
        # NEXT. Three 46 px buttons plus two 6 px gaps add up to the
        # big circle's 150 px width, so the row is exactly as wide as
        # the play button above it.
        play_col = QVBoxLayout()
        play_col.setSpacing(CONTROLS_GAP)
        self.play_button = PlayCircleButton()
        self.play_button.clicked.connect(self.on_play_clicked)
        play_col.addWidget(self.play_button, 0, Qt.AlignHCenter)

        small_row = QHBoxLayout()
        small_row.setSpacing(6)
        self.mute_button = SmallCircleButton("mute")
        self.mute_button.toggled.connect(self.on_mute_toggled)
        small_row.addWidget(self.mute_button)
        self.love_button = SmallCircleButton("heart")
        self.love_button.toggled.connect(self.on_love_toggled)
        small_row.addWidget(self.love_button)
        self.next_button = SmallCircleButton("next")
        self.next_button.clicked.connect(self.on_next_station)
        small_row.addWidget(self.next_button)
        play_col.addLayout(small_row)
        mid.addLayout(play_col)

        # The visualizer: fixed to EQ_HEIGHT (exactly the play column's
        # height), so its bars start level with the top of the big play
        # circle and end level with the bottom of the mute / love /
        # next buttons - on one invisible line, at any window size.
        self.equalizer = EqualizerWidget()
        self.equalizer.setFixedHeight(EQ_HEIGHT)
        mid.addWidget(self.equalizer, 1)
        root.addLayout(mid)

        # Extra window height (resize or zoom) gathers here, above the
        # volume bar - the middle row never changes.
        root.addStretch(1)

        # == volume: the percent label sits under the play column and
        # the bar starts exactly where the visualizer starts, because
        # both rows are [a PLAY_BUTTON-wide slot][18 px][the rest].
        vol_row = QHBoxLayout()
        vol_row.setSpacing(18)
        self.volume_label = QLabel("VOLUME 80%")
        self.volume_label.setFixedWidth(PLAY_BUTTON)
        vol_row.addWidget(self.volume_label, 0, Qt.AlignVCenter)
        self.volume = VolumeBar()
        self.volume.valueChanged.connect(self.on_volume_changed)
        vol_row.addWidget(self.volume, 1)
        root.addLayout(vol_row)

        # == bottom bar: status (left), actions (right) ================
        # The STATIONS button toggles the drawer that protrudes from
        # the bottom of the app (see on_toggle_stations).
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.status_label = QLabel("Ready.")
        bottom.addWidget(self.status_label, 1)
        self.stations_toggle = GradientButton("STATIONS", "normal", arrow="down")
        self.stations_toggle.clicked.connect(self.on_toggle_stations)
        bottom.addWidget(self.stations_toggle)
        self.open_pls_button = GradientButton("ADD PLS", "accent")
        self.open_pls_button.clicked.connect(self.on_open_pls)
        bottom.addWidget(self.open_pls_button)
        self.add_stream_button = GradientButton("ADD STREAM", "normal")
        self.add_stream_button.clicked.connect(self.on_add_url)
        bottom.addWidget(self.add_stream_button)
        root.addLayout(bottom)

        self._place_frame_children()

    def resizeEvent(self, event):
        """Keep the panel and the drawer placed after any resize."""
        super().resizeEvent(event)
        if hasattr(self, "panel"):
            self._place_frame_children()

    def _place_frame_children(self):
        """Position the main panel and the drawer inside the canvas.

        The drawer's "extent" is how far it has slid out (0 when
        closed). Its top SHELF_OVERLAP px tuck under the panel, so the
        window height grows only by the part that is actually visible.
        """
        extent = int(round(self._shelf_extent))
        visible = max(0, extent - SHELF_OVERLAP)
        w = self.width()
        self._panel_h = max(1, self.height() - visible)
        self.panel.setGeometry(0, 0, w, self._panel_h)
        shelf_out = extent > SHELF_OVERLAP
        self.shelf.setGeometry(0, self._panel_h - SHELF_OVERLAP, w,
                               max(1, extent))
        self.shelf.setVisible(shelf_out)
        self.panel.set_bottom_open(shelf_out)

    # ---- theming -------------------------------------------------------

    def apply_theme(self):
        """Re-apply fonts, stylesheet and label colors to the whole UI.

        Font roles and sizes live in the EASY TWEAKS block and in each
        theme's "fonts" mapping. The station name and the marquee are
        the two big rows, both in the theme's "title" font.
        """
        self.station_label.setFont(theme_font("title", STATION_FONT_SIZE,
                                              True))
        self.station_label.setStyleSheet("color: %s;"
                                         % THEME["colors"]["accent"])
        self.marquee.setFont(theme_font("title", MARQUEE_FONT_SIZE))
        self.volume_label.setFont(theme_font("body", 10, True, 2.0))
        self.volume_label.setStyleSheet("color: %s;"
                                        % THEME["colors"]["accent2"])
        self.status_label.setFont(theme_font("body", 9))
        self.status_label.setStyleSheet("color: %s;"
                                        % rgba("accent", 170))
        # The wire THEME button carries the current theme's name.
        self.theme_button.setText("THEME : %s" % THEME["name"].upper())
        QApplication.instance().setStyleSheet(build_qss())
        self.rebuild_station_list()
        # Repaint the themed surfaces: the logo (tinted with the theme's
        # text color), the pills (their font is the title font), the
        # hairlines, the panel and the drawer.
        self.format_pill.refresh()
        self.bitrate_pill.refresh()
        self.logo.update()
        self.panel.update()
        self.shelf.update()
        self.update()

    def on_theme_clicked(self):
        """Cycle to the next theme (colors and fonts together)."""
        global THEME, THEME_INDEX
        THEME_INDEX = (THEME_INDEX + 1) % len(THEMES)
        THEME = THEMES[THEME_INDEX]
        self.apply_theme()
        self.status_label.setText("Theme: %s." % THEME["name"])

    # ---- visualizer options ----------------------------------------------

    def on_band_clicked(self, count):
        """Switch the equalizer between 10, 20, 30, 40 and 50 bars."""
        for other, chip in self._band_buttons.items():
            chip.setChecked(other == count)
        self.equalizer.set_band_count(count)

    # ---- the station drawer ------------------------------------------------

    def on_toggle_stations(self):
        """Slide the station drawer out from under the panel, or in.

        The drawer is a protrusion from the bottom of the app: the
        window itself grows downward, so the list genuinely looks like
        it slid out from UNDER the main player. The QVariantAnimation
        drives _set_shelf_extent, which both resizes the window and
        re-places the panel and the drawer each frame.
        """
        self._stations_open = not self._stations_open
        self.stations_toggle.arrow = "up" if self._stations_open else "down"
        self.stations_toggle.update()
        if getattr(self, "_shelf_anim", None) is not None:
            try:
                self._shelf_anim.stop()
            except RuntimeError:
                # DeleteWhenStopped already freed the FINISHED
                # animation; only its Python wrapper lingered here.
                # Nothing to stop - just drop the stale reference.
                pass
            self._shelf_anim = None
        animation = QVariantAnimation(self)
        animation.setDuration(280)
        animation.setStartValue(float(self._shelf_extent))
        animation.setEndValue(
            float(SHELF_AREA + SHELF_OVERLAP) if self._stations_open
            else 0.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.valueChanged.connect(self._set_shelf_extent)
        self._shelf_anim = animation
        animation.start(QVariantAnimation.DeleteWhenStopped)
        if self._stations_open and self.station_list.count():
            self.station_list.setCurrentRow(0)

    def _set_shelf_extent(self, value):
        """One animation frame: grow (or shrink) the window for the
        drawer and re-place the panel and the shelf."""
        self._shelf_extent = float(value)
        extent = int(round(self._shelf_extent))
        visible = max(0, extent - SHELF_OVERLAP)
        target_h = self._panel_h + visible
        if target_h != self.height():
            self.resize(self.width(), target_h)
        else:
            self._place_frame_children()

    # ---- stations --------------------------------------------------------

    def add_station(self, title, url, favorite=False, rebuild=True):
        """Add a station to the model and refresh the list view."""
        self._stations.append({"title": title, "url": url,
                               "favorite": bool(favorite)})
        if rebuild:
            self.rebuild_station_list()

    def rebuild_station_list(self):
        """Rebuild the station list view from the model.

        Favorites (hearted stations) always float to the top; within
        each group the original order is kept. Every row shows the
        station name plus a heart and a subtle remove button. The
        current selection survives the rebuild.
        """
        current_url = None
        item = self.station_list.currentItem()
        if item is not None:
            current_url = item.data(Qt.UserRole)
        self.station_list.clear()
        ordered = sorted(self._stations, key=lambda s: not s["favorite"])
        for station in ordered:
            list_item = QListWidgetItem(station["title"])
            list_item.setData(Qt.UserRole, station["url"])
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 4, 8, 4)
            row_layout.setSpacing(6)
            # The heart comes FIRST, before the station name, so loved
            # stations read at a glance. Unloved stations show a very
            # faint heart outline (see IconButton.paintEvent).
            heart = IconButton("heart")
            heart.setChecked(bool(station["favorite"]))
            heart.clicked.connect(
                lambda checked, s=station: self.on_toggle_favorite(s))
            row_layout.addWidget(heart)
            name = QLabel(station["title"])
            name.setFont(theme_font("body", 10))
            row_layout.addWidget(name, 1)
            remove = IconButton("close")
            remove.clicked.connect(
                lambda s=station: self.on_remove_station(s))
            row_layout.addWidget(remove)
            list_item.setSizeHint(row.sizeHint())
            self.station_list.addItem(list_item)
            self.station_list.setItemWidget(list_item, row)
            if station["url"] == current_url:
                self.station_list.setCurrentItem(list_item)
        # Keep the heart under the play circle in sync with the model.
        self._sync_love_button()

    def _sync_love_button(self):
        """Mirror the playing station's favorite state onto the heart
        circle under the play button (checked = loved)."""
        checked = False
        if self.current_station is not None:
            station = self._station_by_url(self.current_station[1])
            checked = bool(station and station["favorite"])
        self.love_button.blockSignals(True)
        self.love_button.setChecked(checked)
        self.love_button.blockSignals(False)

    def _station_by_url(self, url):
        """Return the station dict for a URL, or None."""
        for station in self._stations:
            if station["url"] == url:
                return station
        return None

    def on_toggle_favorite(self, station):
        """Heart (or unheart) a station; hearts always float to the top."""
        station["favorite"] = not station["favorite"]
        self.rebuild_station_list()  # re-sorts, and re-syncs the heart
        self.status_label.setText("Added to favorites." if
                                  station["favorite"] else
                                  "Removed from favorites.")

    def on_love_toggled(self, checked):
        """The heart circle under the play button: love the playing station.

        It toggles the exact same favorite flag as the row hearts, so
        the two can never disagree: the rebuild re-sorts the list and
        _sync_love_button mirrors the state back onto this circle.
        """
        if self.current_station is None:
            self.status_label.setText("Play a station first, then "
                                      "heart it.")
            self._sync_love_button()
            return
        station = self._station_by_url(self.current_station[1])
        if station is not None:
            station["favorite"] = bool(checked)
            self.rebuild_station_list()

    def on_mute_toggled(self, checked):
        """The mute circle: park the volume bar at 0, remember the old value.

        Muting only touches the volume bar - the bar emits valueChanged,
        which the engine hears, so audio and label follow for free.
        Unmuting restores the volume from before the mute (60 if the
        remembered value was 0). Dragging the bar away from zero while
        muted unmutes automatically; see on_volume_changed.
        """
        if checked:
            self._volume_before_mute = self.volume.value()
            self.volume.set_value(0)
        else:
            restore = self._volume_before_mute
            self.volume.set_value(restore if restore > 0 else 60)

    def on_next_station(self):
        """The NEXT circle: play the next station in list order.

        The order is the one displayed (favorites first), and the list
        wraps around: pressing NEXT at the end returns to the top.
        """
        ordered = sorted(self._stations, key=lambda s: not s["favorite"])
        if not ordered:
            self.status_label.setText("No stations yet. ADD PLS or "
                                      "ADD STREAM.")
            return
        start = 0
        if self.current_station is not None:
            urls = [s["url"] for s in ordered]
            if self.current_station[1] in urls:
                start = urls.index(self.current_station[1])
        nxt = ordered[(start + 1) % len(ordered)]
        self.play_station(nxt["title"], nxt["url"])

    def on_remove_station(self, station):
        """Remove a station from the list; stop first if it is playing."""
        if (self.playing and self.current_station is not None
                and self.current_station[1] == station["url"]):
            self.stop_stream()
        if station in self._stations:
            self._stations.remove(station)
        self.rebuild_station_list()

    def on_toggle_maximize(self):
        """The green traffic light: zoom the window or restore it."""
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ---- playback ----------------------------------------------------------

    def _ensure_engine(self):
        """Create the engine on first use so the error dialog is friendly."""
        if self.engine is not None:
            return True
        try:
            self.engine = StreamEngine()
            self.engine.set_volume(self.volume.value())
            self.equalizer.set_engine(self.engine)
            return True
        except RuntimeError as exc:
            QMessageBox.critical(self, APP_NAME, str(exc))
            return False

    def play_station(self, title, url):
        if not self._ensure_engine():
            return
        self.current_station = (title, url)
        self.engine.play(url)
        self.playing = True
        self.stream_ok = False
        self.station_label.setText(title)
        # The pills start from the URL's own hints right away; the
        # live stream's real track info follows on the next ticks.
        self.update_stream_pills()
        # The marquee belongs to the Artist - Song metadata only; the
        # station name lives in the big title above it, once.
        self.marquee.setText("Waiting for track info from the station...")
        self.status_label.setText("Connecting...")
        self.play_button.set_playing(True)
        # Highlight the row that is now playing, and mirror this
        # station's favorite state onto the heart circle.
        for row_index in range(self.station_list.count()):
            item = self.station_list.item(row_index)
            if item is not None and item.data(Qt.UserRole) == url:
                self.station_list.setCurrentItem(item)
                break
        self._sync_love_button()

    def stop_stream(self):
        if self.engine:
            self.engine.stop()
        self.playing = False
        self.stream_ok = False
        self.current_station = None
        self.station_label.setText(WINDOW_TITLE)
        # No station, no stream info: the pills tuck themselves away.
        self.update_stream_pills()
        self.marquee.setText("Double-click a station, drop a .pls file "
                             "anywhere, or open one with ADD PLS.")
        self.status_label.setText("Stopped.")
        self.play_button.set_playing(False)
        self._sync_love_button()

    def on_play_clicked(self):
        """The big circle: play the selected station, or stop if playing."""
        if self.playing:
            self.stop_stream()
            return
        item = self.station_list.currentItem()
        if item is None and self.station_list.count():
            item = self.station_list.item(0)
        if item is None:
            self.status_label.setText("No stations yet. ADD PLS or "
                                     "ADD STREAM.")
            return
        self.play_station(item.text(), item.data(Qt.UserRole))

    def on_item_double_clicked(self, item):
        self.play_station(item.text(), item.data(Qt.UserRole))

    def on_volume_changed(self, value):
        """Volume changed from the bar: forward to the engine and label."""
        self.volume_label.setText("VOLUME %d%%" % value)
        if self.engine:
            self.engine.set_volume(value)
        if value > 0 and self.mute_button.isChecked():
            # Dragging away from zero unmutes. Signals are blocked for
            # the toggle so the mute handler does not "restore" the old
            # volume over the top of the user's drag.
            self.mute_button.blockSignals(True)
            self.mute_button.setChecked(False)
            self.mute_button.blockSignals(False)

    def update_stream_pills(self):
        """Refresh the format / bitrate pills beside the station name.

        Two sources, most honest first: the LIVE stream's track
        description (engine.stream_info, available a few seconds into
        playback) and the URL's own hints (probe_url_info, instant).
        The pills hide themselves while neither knows anything.
        """
        fmt, kbps = None, None
        if self.current_station:
            fmt, kbps = probe_url_info(self.current_station[1])
        if self.playing and self.engine is not None:
            live_fmt, live_kbps = self.engine.stream_info()
            fmt = live_fmt or fmt
            kbps = live_kbps or kbps
        self.format_pill.set_pill_text(fmt or "")
        self.bitrate_pill.set_pill_text("%d KBPS" % kbps if kbps else "")

    def on_tick(self):
        """Once per second: connection status and now-playing metadata."""
        if not self.playing:
            return
        if self.engine is None:
            return
        # Keep the analyser healthy: it may be connected over the
        # plain-http variant of the stream (see http_variant in the
        # engine), and if that variant does not exist the analyser is
        # reconnected on the original URL here.
        self.engine.check_analyser()
        if self.engine.is_streaming():
            if not self.stream_ok:
                self.stream_ok = True
                self.status_label.setText("Streaming live.")
        else:
            self.stream_ok = False
            self.status_label.setText("Connection lost or stopped.")
        # Once VLC has parsed the live stream it can report the real
        # codec and bitrate for the pills; until then they show the
        # URL's own hints, so they are only refreshed while something
        # is still missing.
        if not self.format_pill.text() or not self.bitrate_pill.text():
            self.update_stream_pills()
        title = self.current_station[0] if self.current_station else ""
        # now_playing() has already rejected stream plumbing such as a
        # bare "mp3-128" invented from the URL (see is_stream_junk), so
        # whatever lands here is real metadata or an empty string.
        meta = self.engine.now_playing()
        if meta and meta != title:
            # Real "Artist - Song" metadata: the marquee's whole job.
            if self.marquee.text() != meta:
                self.marquee.setText(meta)
        elif not self.marquee.text().startswith("Waiting"):
            # Nothing broadcast yet (or the stream only repeats the
            # station name): say so instead of duplicating the title.
            self.marquee.setText("Waiting for track info from the station...")

    # ---- adding stations ------------------------------------------------

    def open_pls_file(self, path=None):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Open .pls file",
                "",
                "PLS playlists (*.pls);;All files (*.*)",
            )
            if not path:
                return
        try:
            stations = parse_pls(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, APP_NAME,
                                "Could not read that file: %s" % exc)
            return
        for station in stations:
            self.add_station(station["title"], station["url"])
        first = stations[0]
        # Show the freshly added stations, then start the first one.
        if not self._stations_open:
            self.on_toggle_stations()
        self.station_list.setCurrentRow(self.station_list.count()
                                       - len(stations))
        self.play_station(first["title"], first["url"])

    def on_open_pls(self):
        self.open_pls_file()

    def on_add_url(self):
        url, ok = QInputDialog.getText(
            self, "Add stream URL", "Stream URL (http or https):"
        )
        if ok and url.strip().lower().startswith("http"):
            self.add_station(url.strip().rsplit("/", 1)[-1] or "New station",
                             url.strip())

    # ---- drag and drop over the whole window ------------------------------

    def dragEnterEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pls"):
                event.acceptProposedAction()
                return
        if event.mimeData().hasText() and event.mimeData().text().startswith("http"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pls"):
                # Dropping a .pls file anywhere plays it instantly.
                self.open_pls_file(path)
                event.acceptProposedAction()
                return
        text = event.mimeData().text()
        if text.startswith("http"):
            self.add_station(text.rsplit("/", 1)[-1] or "Dropped station", text)
            event.acceptProposedAction()

    def closeEvent(self, event):
        # Stop the audio threads cleanly when the window closes.
        if self.engine:
            self.engine.stop()
        super().closeEvent(event)


def main():
    # Create QApplication FIRST. Loading fonts before it exists crashes:
    # QFontDatabase.addApplicationFont() needs Qt's platform font
    # database, which is only created when QApplication is constructed.
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    icon = app_icon()
    if icon is not None:
        # The logo from components becomes the window / dock / taskbar
        # icon. The built installers get their launcher icons from the
        # same file, generated by the build scripts.
        app.setWindowIcon(icon)
    load_fonts_and_themes()
    window = SionicalWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()