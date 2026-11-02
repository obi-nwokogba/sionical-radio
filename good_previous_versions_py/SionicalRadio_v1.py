#!/usr/bin/env python3
"""SIONICAL RADIO - a stylish, themeable internet radio player.

Cross-platform (macOS Intel, macOS Apple Silicon, Windows; Linux works
too), built on PySide6 and the VLC engine.

DESIGN
    Dark blue glass panel with a framed look, a big circular play/stop
    button with a cyan glow, a live FFT equalizer (5, 10, 15 or 20
    bands), a large volume bar with a percent readout, and an accordion
    station list that only appears when the STATIONS arrow is clicked.

FONTS (optional but recommended)
    Drop up to four TrueType files named exactly font1.ttf, font2.ttf,
    font3.ttf and font4.ttf into a "components" folder next to this
    file. Each theme picks which font plays which role. Missing fonts
    simply fall back to the system font, so the app always runs.

THEMES
    Five themes are embedded below as JSON. If the file
    components/themes.json exists, it replaces them all, so you can
    restyle the app without touching this code. The tiny THEME button
    (top right) cycles themes at runtime.

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
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
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

APP_NAME = "SionicalRadio"
WINDOW_TITLE = "SIONICAL RADIO"

# A few free, listener-supported stations to show the app works out of
# the box.
BUILT_IN_STATIONS = [
    ("SomaFM Groove Salad", "https://ice1.somafm.com/groovesalad-128-mp3"),
    ("SomaFM Drone Zone", "https://ice1.somafm.com/dronezone-128-mp3"),
    ("SomaFM Underground 80s", "https://ice1.somafm.com/u80s-128-mp3"),
    ("SomaFM DEF CON Radio", "https://ice1.somafm.com/defcon-128-mp3"),
]

# ---------------------------------------------------------------------------
# THEMES (JSON)
# ---------------------------------------------------------------------------
# Every theme picks its colors AND its fonts. "fonts" maps the roles
# "title" and "body" to one of the font files font1.ttf to font4.ttf
# (loaded from the components folder). Colors are plain web hex values.
# The first theme, "Sionical Blue", is the main design: every color in
# it comes straight from the UI mockup. To customize, create a
# components/themes.json with the same structure and it wins.

THEMES_JSON = """
[
  {
    "name": "Sionical Blue",
    "fonts": { "title": "font2", "body": "font1" },
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
    "fonts": { "title": "font3", "body": "font1" },
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
    "fonts": { "title": "font4", "body": "font2" },
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
    "fonts": { "title": "font1", "body": "font3" },
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
    "fonts": { "title": "font4", "body": "font1" },
    "colors": {
      "bg_top": "#07211C", "bg_bottom": "#031210",
      "panel": "#0E3328", "border": "#0F766E",
      "accent": "#2DD4BF", "accent2": "#99F6E4",
      "deep": "#115E59", "text": "#CCFBF1",
      "glow": "#5EEAD4", "icon": "#FFFFFF"
    }
  }
]
"""

THEMES = json.loads(THEMES_JSON)
THEME_INDEX = 0
THEME = THEMES[0]

# The loaded TrueType families, keyed "font1" to "font4".
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
# audio per frame - plenty of resolution for 5 to 20 log-spaced bands,
# and small enough to stay smooth in pure Python.
FFT_SIZE = 512


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
    """Load font1.ttf to font4.ttf and an optional themes.json override.

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
    for num in ("font1", "font2", "font3", "font4"):
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
    """Build a QFont for a role ("title" or "body") of the current theme.

    If the theme's font file was not found, Qt's default font is used so
    the app still looks coherent.
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
    gradients, so QSS only needs to handle the window background, the
    station list and the scrollbar.

    ORDER MATTERS. QMainWindow is a subclass of QWidget, and when two
    type selectors tie on specificity the LATER rule wins. The plain
    QWidget rule must therefore come FIRST and the QMainWindow gradient
    LAST, or "background: transparent" would override the gradient and
    the window would fall back to the platform's default light gray -
    the exact bug that once made every theme's panel look the same.
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
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 %(bg_top)s, stop:1 %(bg_bottom)s);
        }
    """ % dict(c, font_line=font_line)


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


class StreamEngine(object):
    """Everything audio: the audible player plus the silent analyser.

    The audible player is a completely normal libvlc media player that
    feeds the speakers. The analyser is a SECOND media player on the
    same URL whose audio output is a set of callbacks into Python: VLC
    hands us the decoded PCM, we never play it, and the visualizer gets
    real frequency data. If anything about the analyser fails (or it is
    disabled), the app keeps playing music and the visualizer uses its
    idle animation instead.
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
        if self.analyser is not None:
            try:
                analysis_media = self.instance.media_new_location(url)
                self.analyser.set_media(analysis_media)
                self.analyser.play()
            except Exception:
                pass

    def stop(self):
        self.player.stop()
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
        "Now Playing" metadata field; some fill the plain Artist/Title
        fields instead, so both are tried before giving up.
        """
        if vlc is None:
            return ""
        media = self.player.get_media()
        if media is None:
            return ""
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
    """The glassy rounded frame drawn around the whole interface."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(9.0, 9.0, -9.0, -9.0)
        # A clearly theme-colored glass fill: the panel color shading
        # into the window's bottom color for depth. This, together with
        # the window gradient behind it, is what makes each theme's
        # panel visibly distinct instead of a washed-out gray.
        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0.0, col("panel", 242))
        fill.setColorAt(1.0, col("bg_bottom", 216))
        painter.setPen(QPen(col("border", 110), 1.0))
        painter.setBrush(fill)
        painter.drawPath(rounded_path(rect, 18.0))


class GradientButton(QPushButton):
    """A rounded button painted with a gradient fill and a glass bevel.

    variant:
        "normal" - flat panel fill with a themed border (ADD STREAM...)
        "accent" - accent-to-deep gradient (primary actions)
        "tiny"   - small checkable option chip (the band selectors)
    arrow: None, or "down"/"up" to draw a small arrow after the text
    (used by the STATIONS accordion toggle).
    """

    def __init__(self, text="", variant="normal", arrow=None, parent=None,
                 checkable=None):
        super().__init__(text, parent)
        self.variant = variant
        self.arrow = arrow
        self.setCursor(Qt.PointingHandCursor)
        self._tiny = variant == "tiny"
        # Tiny chips are checkable by default (band selectors); pass
        # checkable=False for tiny buttons that should not stay pressed,
        # like the THEME cycler.
        if checkable is None:
            checkable = self._tiny
        self.setCheckable(checkable)

    def sizeHint(self):
        metrics = QFontMetrics(theme_font("body", 9 if self._tiny else 11, True))
        width = metrics.horizontalAdvance(self.text())
        width += 22 if self._tiny else 40
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
        if self._tiny and self.isChecked():
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

        # ---- glass bevel: light along the top, shade along the bottom --
        bevel = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        bevel.setColorAt(0.0, QColor(255, 255, 255, 26))
        bevel.setColorAt(0.45, QColor(255, 255, 255, 0))
        bevel.setColorAt(1.0, col("bg_bottom", 70))
        painter.setPen(Qt.NoPen)
        painter.setBrush(bevel)
        painter.drawPath(path)

        # ---- hover / pressed feedback ---------------------------------
        if self.isDown():
            painter.setBrush(col("bg_bottom", 90))
            painter.drawPath(path)
        elif self.underMouse():
            painter.setBrush(QColor(255, 255, 255, 18))
            painter.drawPath(path)

        # ---- text ------------------------------------------------------
        font = theme_font("body", 9 if self._tiny else 11, True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text = self.text()
        text_width = metrics.horizontalAdvance(text)
        arrow_room = 10 if self.arrow else 0
        x = (rect.width() - text_width - arrow_room) / 2.0
        if self._tiny and self.isChecked():
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
    """The big circular play/stop control with radial gradient and glow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(150, 150)
        self._playing = False

    def set_playing(self, playing):
        if self._playing != playing:
            self._playing = playing
            self.update()

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
        diameter = side - 30.0  # leave room for the glow

        # ---- outer glow -------------------------------------------------
        glow = QRadialGradient(cx, cy, diameter * 0.85)
        glow.setColorAt(0.0, col("glow", 110))
        glow.setColorAt(0.62, col("glow", 70))
        glow.setColorAt(1.0, col("glow", 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), diameter * 0.85, diameter * 0.85)

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

    Every 33 ms the widget pulls the freshest PCM from the engine's tap
    and runs a small FFT; each bar shows the energy of one logarithmic
    frequency band. If no PCM is arriving (analyser disabled, stream
    hiccup, or simply stopped), the bars either idle-animate while
    streaming or gently settle to the baseline, so the UI never looks
    dead. Peaks sit on top of each bar and fall slowly, like the design.
    """

    BAND_CHOICES = (5, 10, 15, 20)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = None
        self.band_count = 5
        self._ranges = band_bin_ranges(5)
        self._levels = [0.03] * 5
        self._peaks = [0.03] * 5
        self._phase = 0.0
        self.setMinimumHeight(110)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def set_engine(self, engine):
        self._engine = engine

    def set_band_count(self, count):
        self.band_count = count
        self._ranges = band_bin_ranges(count)
        self._levels = [0.03] * count
        self._peaks = [0.03] * count
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
        # alive; otherwise relax to the baseline.
        self._phase += 0.05
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
            # Fast attack, slow release keeps the motion musical.
            blend = 0.55 if target > current else 0.16
            self._levels[k] = current * (1.0 - blend) + target * blend
            # Peak caps hover above the bar and decay steadily.
            self._peaks[k] = max(self._peaks[k] - 0.011, self._levels[k])
        self.update()

    # ---- painting --------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        count = self.band_count
        slot = rect.width() / count
        # At most 10 px of air between neighboring bars: wide slots
        # (few bands) get wide bars, tight slots (20 bands) shrink the
        # gap proportionally so the bars never touch.
        gap = min(10.0, slot * 0.45)
        bar_width = max(4.0, slot - gap)
        bottom = rect.bottom() - 3.0
        top = rect.top() + 3.0
        usable = bottom - top

        # Faint baseline the bars sit on.
        painter.setPen(QPen(col("border", 90), 1.0))
        painter.drawLine(QPointF(rect.left(), bottom),
                         QPointF(rect.right(), bottom))

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
            # Peak cap: a thin bright marker floating above the bar.
            peak = self._peaks[k]
            peak_y = bottom - max(2.0, usable * peak) - 5.0
            painter.setBrush(col("accent2"))
            painter.drawRoundedRect(
                QRectF(x, peak_y, bar_width, 3.0), 1.5, 1.5)


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


# ---------------------------------------------------------------------------
# MAIN WINDOW
# ---------------------------------------------------------------------------

class SionicalWindow(QMainWindow):
    """Assembles the whole interface and wires it to the engine."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(840, 560)
        self.setMinimumSize(660, 470)
        self.setAcceptDrops(True)

        self.engine = None
        self.current_station = None
        self.playing = False
        self.stream_ok = False
        self._stations_open = False

        self._build_ui()
        self.apply_theme()

        for title, url in BUILT_IN_STATIONS:
            self.add_station(title, url)

        # A .pls file passed on the command line starts playing right away.
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            self.open_pls_file(sys.argv[1])

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(1000)

    # ---- UI construction ---------------------------------------------

    def _build_ui(self):
        central = PanelFrame()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)

        # == header: station name (left) + brand (right) =================
        header = QHBoxLayout()
        header_left = QVBoxLayout()
        header_left.setSpacing(2)
        self.station_label = QLabel(WINDOW_TITLE)
        self.marquee = MarqueeLabel(
            "Double-click a station, drop a .pls file anywhere, "
            "or open one with ADD PLS.")
        header_left.addWidget(self.station_label)
        header_left.addWidget(self.marquee)
        header.addLayout(header_left)
        header.addStretch(1)
        header_right = QVBoxLayout()
        header_right.setSpacing(6)
        self.brand_label = QLabel(WINDOW_TITLE)
        header_right.addWidget(self.brand_label, 0, Qt.AlignRight)
        self.theme_button = GradientButton("THEME", "tiny", checkable=False)
        self.theme_button.clicked.connect(self.on_theme_clicked)
        header_right.addWidget(self.theme_button, 0, Qt.AlignRight)
        header.addLayout(header_right)
        root.addLayout(header)

        # == middle: big play circle + equalizer ==========================
        mid = QHBoxLayout()
        mid.setSpacing(18)
        self.play_button = PlayCircleButton()
        self.play_button.clicked.connect(self.on_play_clicked)
        mid.addWidget(self.play_button, 0, Qt.AlignVCenter)

        eq_column = QVBoxLayout()
        eq_column.setSpacing(6)
        eq_top = QHBoxLayout()
        self.eq_label = QLabel("EQUALIZER")
        eq_top.addWidget(self.eq_label)
        eq_top.addStretch(1)
        self._band_buttons = {}
        for count in EqualizerWidget.BAND_CHOICES:
            chip = GradientButton(str(count), "tiny")
            chip.setChecked(count == 5)
            chip.clicked.connect(
                lambda checked, c=count: self.on_band_clicked(c))
            eq_top.addWidget(chip)
            self._band_buttons[count] = chip
        eq_column.addLayout(eq_top)
        self.equalizer = EqualizerWidget()
        eq_column.addWidget(self.equalizer, 1)
        mid.addLayout(eq_column, 1)
        root.addLayout(mid, 1)

        # == volume: label with percent + large bar =======================
        vol_row = QHBoxLayout()
        vol_row.setSpacing(12)
        self.volume_label = QLabel("VOLUME 80%")
        vol_row.addWidget(self.volume_label, 0, Qt.AlignVCenter)
        self.volume = VolumeBar()
        self.volume.valueChanged.connect(self.on_volume_changed)
        vol_row.addWidget(self.volume, 1)
        root.addLayout(vol_row)

        # == collapsible station list (accordion) =========================
        self.stations_panel = QWidget()
        panel_layout = QVBoxLayout(self.stations_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        self.stations_panel.setMaximumHeight(0)
        self.station_list = QListWidget()
        self.station_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        panel_layout.addWidget(self.station_list)
        # Stretch 1 (and no fixed spacer above it): when the list opens
        # it grows up from the bottom bar, and while it is closed the
        # equalizer section takes the free space instead - so there is
        # never a permanent empty strip under the volume bar.
        root.addWidget(self.stations_panel, 1)

        # == bottom bar: status (left), actions (right) ====================
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

    # ---- theming -------------------------------------------------------

    def apply_theme(self):
        """Re-apply fonts, stylesheet and label colors to the whole UI."""
        self.station_label.setFont(theme_font("title", 24, True))
        self.station_label.setStyleSheet("color: %s;"
                                         % THEME["colors"]["accent"])
        self.brand_label.setFont(theme_font("body", 10, True, 3.0))
        self.brand_label.setStyleSheet("color: %s;"
                                       % THEME["colors"]["accent2"])
        self.marquee.setFont(theme_font("title", 12))
        self.eq_label.setFont(theme_font("body", 9, True, 2.0))
        self.eq_label.setStyleSheet("color: %s;"
                                    % THEME["colors"]["accent2"])
        self.volume_label.setFont(theme_font("body", 10, True, 2.0))
        self.volume_label.setStyleSheet("color: %s;"
                                        % THEME["colors"]["accent2"])
        self.status_label.setFont(theme_font("body", 9))
        self.status_label.setStyleSheet("color: %s;"
                                        % rgba("accent", 170))
        QApplication.instance().setStyleSheet(build_qss())
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
        """Switch the equalizer between 5, 10, 15 and 20 bands."""
        for other, chip in self._band_buttons.items():
            chip.setChecked(other == count)
        self.equalizer.set_band_count(count)

    # ---- accordion ---------------------------------------------------------

    def on_toggle_stations(self):
        """Expand or collapse the station list with a smooth animation."""
        self._stations_open = not self._stations_open
        self.stations_toggle.arrow = "up" if self._stations_open else "down"
        self.stations_toggle.update()
        animation = QPropertyAnimation(
            self.stations_panel, b"maximumHeight", self)
        animation.setDuration(230)
        animation.setEndValue(190 if self._stations_open else 0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start(QPropertyAnimation.DeleteWhenStopped)
        if self._stations_open and self.station_list.count():
            self.station_list.setCurrentRow(0)

    # ---- stations --------------------------------------------------------

    def add_station(self, title, url):
        item = QListWidgetItem(title)
        item.setData(Qt.UserRole, url)
        self.station_list.addItem(item)
        return item

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
        # The marquee belongs to the Artist - Song metadata only; the
        # station name lives in the big title above it, once.
        self.marquee.setText("Waiting for track info from the station...")
        self.status_label.setText("Connecting...")
        self.play_button.set_playing(True)

    def stop_stream(self):
        if self.engine:
            self.engine.stop()
        self.playing = False
        self.stream_ok = False
        self.current_station = None
        self.station_label.setText(WINDOW_TITLE)
        self.marquee.setText("Double-click a station, drop a .pls file "
                             "anywhere, or open one with ADD PLS.")
        self.status_label.setText("Stopped.")
        self.play_button.set_playing(False)

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

    def on_tick(self):
        """Once per second: connection status and now-playing metadata."""
        if not self.playing:
            return
        if self.engine is None:
            return
        if self.engine.is_streaming():
            if not self.stream_ok:
                self.stream_ok = True
                self.status_label.setText("Streaming live.")
        else:
            self.stream_ok = False
            self.status_label.setText("Connection lost or stopped.")
        title = self.current_station[0] if self.current_station else ""
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
    load_fonts_and_themes()
    window = SionicalWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()