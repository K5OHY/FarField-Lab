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
    "4m": "#9acd32", "2m": "#00c853", "70cm": "#b8860b", "23cm": "#4682b4",  # not on the RBN website either
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
  /* The boxes that open to options (More settings, the test setup, Leave out some reports) are tinted with a bar on the left, so
     they are not missed when scrolling. Translucent blue, so it reads on both the light and the dark theme. */
  .st-key-more_box [data-testid="stExpander"] details,
  .st-key-setup_box [data-testid="stExpander"] details,
  .st-key-leave_box [data-testid="stExpander"] details {
      background: rgba(30, 91, 255, .10); border: 1px solid rgba(30, 91, 255, .45); border-left: 5px solid #1E5BFF;
  }
  .st-key-more_box [data-testid="stExpander"] summary,
  .st-key-setup_box [data-testid="stExpander"] summary,
  .st-key-leave_box [data-testid="stExpander"] summary { font-weight: 600; }
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


PAGES = {}   # the app's pages by short name (set in web.py), so a page can link to another


# What each page says about itself. The same four parts on every page, so it is learned once: what it is for, the steps, what you get, and
# what it cannot tell you.
GUIDES = {
    "spots": dict(
        purpose="Where was my signal decoded, and at what SNR? It maps the Reverse Beacon Network skimmers and WSPR receivers that decoded your signal, and shows the SNR each one reported.",
        steps=["Type your callsign and pick a day in the sidebar (RBN for CW, WSPR for a WSPR transmitter). Or click **Try an example** to see real spots first.",
               "Click **Load spots**.",
               "Use the band buttons above the map to look at one band. The **Session report** tab always covers every band."],
        shows=["A map with a line to every station that heard you, coloured by band, with the farthest one circled.",
               "Tiles for the number of spots and stations, the farthest distance, and the best and average signal.",
               "A chart of which directions you were heard in, and a world view from your station.",
               "A **Session report** of when you were heard, band by hour, and by region. You can also download the map or a PDF report.",
               "For CW, the speed the skimmers measured for you: a tile, the speed in each skimmer's popup, and a table of how you were heard at each speed."],
        limits="It shows where your signal was decoded, not everywhere it could be heard. Only stations running a skimmer or a WSPR receiver "
               "can report you, so a quiet part of the map can mean no one was listening there, not that the path was closed."),
    "compare": dict(
        purpose="Which of two antennas (or two power levels) gets out better? It compares the reports one station received while switching "
                "between them. The page walks you through three steps: load your spots (WSPR is the recommended test, RBN a quick check for CW), say how you "
                "switched, then read the result.",
        steps=[],            # the three steps are the strip drawn just under this box
        shows=["Which antenna was stronger and by how many dB, with a range and a plain statement of how sure the test can be.",
               "How many stations heard both antennas, and what was left out and why.",
               "How the difference changes with distance and direction, and, for a long test, how it moved as conditions changed.",
               "Real example tests you can open first, to see what a result looks like."],
        limits="A short test, or few stations, gives a rough answer, and the page says so. The range shown is approximate: it does not include "
               "every source of error, such as changing band conditions or several receivers at one site. It compares what receivers heard, "
               "not the antennas' own patterns."),
    "conditions": dict(
        purpose="Which bands look open from here right now? It takes the WSPR stations transmitting near you in the last half hour and "
                "restates their reports for your power and mode.",
        steps=["Enter your callsign or grid square in the sidebar (the one you are operating from, if you are portable), or use **My location**.",
               "Set your power and mode.",
               "Read the band tiles and highlights, then pick a band or two under them to look closer."],
        shows=["A tile for each band: open, marginal or quiet, whether it is opening or fading, and how far the best receiver was.",
               "A table of regions (US East, Europe, South America and so on) with the estimated chance a receiver there would hear you.",
               "A map of the receivers, with the day and night line, and the farthest ones.",
               "Space weather from NOAA, and the maximum usable frequency (MUF) near you."],
        limits="It is an estimate from other people's signals near you, not a measurement of yours, and it is good to a few dB at best. No "
               "reports on a band means nothing was heard, not that the band is closed. Reports arrive a few minutes late."),
    "log": dict(
        purpose="What happened in this session, and who heard you? Upload your log (a POTA or SOTA activation works too) and see it beside "
                "the skimmers and WSPR stations that reported you. Three sources are used: your log says who you worked, WSPR near you shows which paths "
                "were reported, and RBN shows which skimmers decoded your CW.",
        steps=["Set your power first. This page does not read it from the log, and the work starts as soon as a log is loaded.",
               "Upload your ADIF log (most logging programs can export one) and check the callsign and grid square taken from it.",
               "Read the row of findings under the numbers: each one is a link to the part of the page it comes from.",
               "In the openings, pick a destination from the tabs (only those with something to show are listed), read the lines worth a look, then open *Details for one band and time* and switch on *Show what is behind this window* to see the stations, spots and contacts behind a bar. *Nearby WSPR shows* switches between what was decoded and an estimate for your station. *Regional* shows the eight compass directions."],
        shows=["Your session in numbers: contacts, stations, bands, the active rate, and who worked you on more than one band.",
               "What you worked: DXCC entities, continents, US states, provinces and CQ zones, and session highlights: when each other continent first answered, the farthest contact on each band, and a note when stations were worked again on the same band.",
               "A session chart with a lane for each band, your sending speed as the skimmers measured it, and two maps side by side: the stations you worked, and the skimmers that spotted you.",
               "For a POTA or SOTA log, how your activation compares with the others listed for that park or summit, and a picture to share in the shape your site wants.",
               "How you used the openings, one destination at a time: where nearby WSPR showed a path, your logged activity above a lane for each band, and who you worked there, with the time of each path set against the time of each contact.",
               "The signal comparison: how far the skimmers' reports sat above or below what the WSPR stations near you would give at your power, with the stations behind it."],
        limits="A log holds only what you wrote down, so it says when you logged contacts, not when you were listening or calling. WSPR shows reported paths, "
               "not what you could have worked. A band with no reports can just mean nobody was listening. Skimmers only hear CW, so the spotter map covers your "
               "CW contacts. The signal comparison rests on a reference correction that is experimental, and it says nothing about your antenna. The log is used "
               "for this visit only; your callsign is sent to public services (RBN, WSPR and callsign lookups) to get the data."),
}


# The four goals as Help's Start here shows them: what you need, three steps, and what to know about examples. The steps follow the page guides above.
QUICK = [
    dict(key="spots", goal="See where my signal was decoded", icon=":material/cell_tower:", page="My spots",
         need="Your callsign and a day that has RBN or WSPR reports.",
         steps=["Type your callsign and pick a day. Use RBN for CW or WSPR for a WSPR transmitter.", "Click **Load spots**.", "Look at the map and the band buttons above it. Click a station's dot to see its SNR over time, band by band."],
         note="No data handy? Click **Try an example** on that page."),
    dict(key="compare", goal="Compare two antennas", icon=":material/balance:", page="Compare antennas",
         need="Reports from a test where you switched between two antennas. A WSPR transmitter is the recommended test; RBN is a quick check for CW.",
         steps=["Load the spots from your test.", "Say how you switched, and check which antenna is A and which is B.", "Read the **Summary** card."],
         note="Real example tests open from the page, so you can see a result first."),
    dict(key="conditions", goal="Check which bands are open", icon=":material/public:", page="Band conditions",
         need="A callsign or grid square, your power and your mode. Nothing to upload.",
         steps=["Enter your callsign or a grid square (the one you are operating from, if you are portable), or use **My location**.", "Set your power and mode.",
                "Read the band tiles."],
         note="It uses WSPR stations near you, so you don't need a transmitter."),
    dict(key="log", goal="Make sense of a session", icon=":material/fact_check:", page="Log analysis",
         need="An ADIF file (.adi or .adif) exported from your logging program, and the power you used. Made with POTA and SOTA activations in mind; any log works.",
         steps=["Set your power.", "Upload your ADIF file.", "Start with the row of findings under the numbers."],
         note="Example logs open from the page: a POTA activation, a SOTA summit, a solar-storm day."),
]


def show_guide(key):
    """Draw the guide for the page `key`: what it is for, the steps, what you get, and what it cannot tell you. The page's own box and the
    Help page both use it, so the two always say the same."""
    g = GUIDES[key]
    st.markdown(f"**{g['purpose']}**")
    if g["steps"]:
        st.markdown("\n".join(f"{n}. {step}" for n, step in enumerate(g["steps"], 1)))
    st.markdown("**You get:**\n" + "\n".join(f"- {item}" for item in g["shows"]))
    st.markdown(f"**What it cannot tell you:** {g['limits']}")


def page_guide(key):
    """The 'How to use this page' box for the page `key`. Always closed: the page's pictures come first, and the words are one click away."""
    with st.expander("What this page does and how to use it", icon=":material/info:", expanded=False):
        show_guide(key)


CHOOSER = [("spots", "See where my signal was decoded", "Map your RBN or WSPR reports by band, strength, distance and direction.", ":material/cell_tower:", "Open the map"),
           ("compare", "Compare antennas", "Compare two setups using reports from the same receivers.", ":material/balance:", "Open comparison"),
           ("conditions", "Check the bands now", "Explore recent WSPR paths near your operating location.", ":material/public:", "Check conditions"),
           ("log", "Analyze a log", "Discover multiband hunters, session highlights and the conditions around your contacts.", ":material/fact_check:", "Upload a log")]


PICTURES = Path(__file__).resolve().parent / "images" / "ui"   # screenshots of the app's own pages (thumb_*.jpg for the cards, big_*.jpg)


def preview(key, caption):
    """A large screenshot of what the page `key` produces, for a page that has nothing on it yet."""
    pic = PICTURES / f"big_{key}.jpg"
    if pic.exists():
        with st.container(border=True):
            st.caption(f":material/image: **Example picture.** {caption} This is a screenshot, so nothing on it is clickable.")
            st.image(str(pic), width="stretch")


def task_chooser(current):
    """Four cards, one for each job the app does, each linking to its page (the one you are on is marked). The link sits along the bottom."""
    st.markdown("#### What would you like to do?")
    st.markdown('<style>[class*="st-key-choose_"] { min-height: 19rem; } [class*="st-key-choose_"] > :last-child { margin-top: auto; }</style>',
                unsafe_allow_html=True)
    for col, (key, title, blurb, icon, action) in zip(st.columns(4), CHOOSER):
        with col, st.container(border=True, key=f"choose_{key}"):
            thumb = PICTURES / f"thumb_{key}.jpg"
            if thumb.exists():                  # a real screenshot of what the page produces
                st.image(str(thumb), width="stretch")
            st.markdown(f"**{title}**")
            st.caption(blurb)
            if key == current:
                st.caption(":material/arrow_upward: You are here")
            elif key in PAGES:
                st.page_link(PAGES[key], label=action, icon=icon)


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
