"""Settings, colours, constants and small helpers shared by every page."""
import html
import json
import re
from pathlib import Path

import matplotlib.colors as mcolors
import numpy as np
import streamlit as st

from world_map import MAX_KM, SNR_CMAP


# Same colours the RBN website uses for each band.
BAND_COLORS = {
    "2200m": "#8b4513", "630m": "#008080",  # not on the RBN website; chosen to stand apart from the others
    "160m": "#ffe000", "80m": "#093F00", "60m": "#777777", "40m": "#ffa500",
    "30m": "#ff0000", "20m": "#800080", "17m": "#0000ff", "15m": "#444444",
    "12m": "#00ffff", "10m": "#ff00ff", "6m": "#ffc0cb",
}


# Key-free basemaps: (base tiles, optional labels overlay). Esri "Canvas" is the closest match to CARTO's look.
_ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"


_ESRI_ATTR = "Tiles &copy; Esri"


TILE_STYLES = {
    "Light": (_ESRI.format("Canvas/World_Light_Gray_Base"), _ESRI.format("Canvas/World_Light_Gray_Reference")),
    "Dark": (_ESRI.format("Canvas/World_Dark_Gray_Base"), _ESRI.format("Canvas/World_Dark_Gray_Reference")),
    "Satellite": (_ESRI.format("World_Imagery"), _ESRI.format("Reference/World_Boundaries_and_Places")),
    "Street": ("OpenStreetMap", None),
}


# Weak = small green, medium = yellow, strong = large dark red. What counts as weak or strong depends on the
# source: RBN CW reports typically run ~5-35 dB, while WSPR decodes far below the noise, roughly -28 to +2 dB.
RBN_SNR_SCALE = (5, 35)


WSPR_SNR_SCALE = (-28, 2)




KM_PER_MILE = 1.609344


MAX_DAYS = 7


SETTINGS_FILE = Path(__file__).with_name("settings.json")


def snr_strength(snr, scale=RBN_SNR_SCALE):
    """0 (weak) .. 1 (strong)"""
    lo, hi = scale
    return float(np.clip((snr - lo) / (hi - lo), 0, 1))


def snr_color(snr, scale=RBN_SNR_SCALE):
    return mcolors.to_hex(SNR_CMAP(snr_strength(snr, scale)))


def snr_radius(snr, scale=RBN_SNR_SCALE):
    return 5 + 6 * snr_strength(snr, scale)


# ----------------------------------------------------------------- comparing antennas

# The ways the Compare page can tell the A side from the B side (these are the labels people see).
SPLIT_FREQ = "Two frequencies"


SPLIT_LOG = "Antenna log"


def esc(text):
    """`text` made safe to put into HTML: anything typed by a visitor (an antenna name from a shared link, say) or read from outside the
    app (a receiver's callsign) is shown as text and can never become markup or script."""
    return html.escape(str(text))


def clean_name(text, limit=60):
    """An antenna name as typed or carried in a link, without the characters that make HTML tags, markdown links or code, and without
    control characters, on one line and at most `limit` characters. Ordinary names ('40m loop, 20 ft', 'Vertical (tuned)') are unchanged."""
    text = re.sub(r"[<>\[\]`\\\x00-\x1f\x7f]", "", str(text or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _bold(text):
    """Text with **bold** marked up, escaped first so nothing in it can become HTML."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(str(text), quote=False))


def _pretty_date(file_date):
    """'20261004' -> '2026-10-04', '20261004-20261006' -> '2026-10-04 to 2026-10-06'."""
    parts = [f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 and d.isdigit() else d for d in str(file_date).split("-")]
    return " to ".join(parts)


def _views(units):
    km = 1.609344 if units == "mi" else 1.0
    return {f"Nearby ({3000 if units == 'mi' else 5000:,} {units})": (3000 * km if units == "mi" else 5000.0),
            f"Half the world ({7500 if units == 'mi' else 12000:,} {units})": (7500 * km if units == "mi" else 12000.0),
            "Whole world": MAX_KM}


# -------------------------------------------------------------------------- app

CSS = """
<style>
  .block-container { padding-top: 4rem; max-width: 1400px; }
  h1 { font-weight: 700; letter-spacing: -0.5px; margin-bottom: 0; }
  .subtitle { color: inherit; opacity: .78; margin: 0 0 1.2rem 0; }
  [data-testid="stCaptionContainer"] { color: inherit; opacity: .86; }
  [data-testid="stCaptionContainer"] p { color: inherit; }
  div[data-testid="stMetric"] {
      background: rgba(128,128,128,.10); border-radius: 10px; padding: 12px 16px;
  }
  iframe { border-radius: 12px; }
  div[data-testid="stImage"] img { border-radius: 12px; }
  div[data-testid="stTooltipContent"] { max-width: 15rem; white-space: normal; }
</style>
"""


BANNER = Path(__file__).resolve().parent / "images" / "branding" / "farfield-banner.png"


def signed(value):
    """A gain with its sign (+3.5, -2), and a plain 0 for none, never -0."""
    return "0" if round(float(value), 1) == 0 else f"{value:+g}"


STRIP = BANNER.with_name("farfield-strip.png")


def brand_strip():
    """A slim header band for the pages that are not the home page."""
    if STRIP.exists():
        st.image(str(STRIP), width="stretch")


def running_locally():
    """Settings are stored in a file, so only do it when run on your own PC, never on a shared web host."""
    try:
        return st.context.headers.get("Host", "").split(":")[0] in ("localhost", "127.0.0.1")
    except Exception:
        return False


def load_settings():
    if not running_locally():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return {}


def save_settings(settings):
    if not running_locally():
        return
    try:
        if settings != load_settings():
            SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    except OSError:
        pass  # read-only install; settings just won't be remembered


RBN_SOURCES = ["Download by date", "Paste from RBN site"]


WSPR_SOURCE = "WSPR"


SOURCE_CODES = {"rbn": "Download by date", "paste": "Paste from RBN site", "wspr": WSPR_SOURCE}  # as they appear in a link


GITHUB_URL = "https://github.com/K5OHY/FarField-Lab"


def github_url():
    """The repository the app comes from (the live site is its main branch, the beta site its beta branch)."""
    return GITHUB_URL
