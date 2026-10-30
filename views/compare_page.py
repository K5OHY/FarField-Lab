"""The Compare antennas page: load one station's spots, say how the antennas were switched, and read which got out better."""
import streamlit as st

from data_sources import skimmer_data
from ui_common import RBN_SNR_SCALE, brand_strip, SPLIT_FREQ, SPLIT_LOG, WSPR_SNR_SCALE, WSPR_SOURCE
from views import inputs, test_link
from views.compare_view import compare_view

STEPS_CSS = """<style>
.cs { display:flex; flex-wrap:wrap; gap:10px; margin:4px 0 14px 0; }
.cs div { flex:1 1 200px; border:1px solid rgba(128,128,128,.3); background:rgba(128,128,128,.07); border-radius:12px;
  padding:10px 14px; display:flex; gap:12px; align-items:center; }
.cs b { width:30px; height:30px; border-radius:50%; border:1.5px solid currentColor; display:flex; align-items:center;
  justify-content:center; flex:none; font-size:15px; }
.cs span { font-size:15px; font-weight:600; display:block; } .cs small { opacity:.7; font-size:13px; display:block; }
.cs .done { border-color:#3fb950; } .cs .done b { background:#3fb950; border-color:#3fb950; color:#0d1117; }
.cs .now { border-color:#4da3ff; background:rgba(77,163,255,.10); } .cs .now b { background:#4da3ff; border-color:#4da3ff; color:#0d1117; }
.cs .next { opacity:.6; }
</style>"""


def _steps(loaded, comparing_rbn):
    """The three steps of a comparison as a row, with where you are marked. Shown until the setup is confirmed."""
    states = ["done", "now", "next"] if loaded else ["now", "next", "next"]
    labels = [("Load your spots", "in the sidebar (the » at the top left on a phone)"),
              ("Say how you switched", "I guessed it: check it below, then confirm" if loaded
               else "which frequency was which" if comparing_rbn else "which antenna, and when"),
              ("Read the result", "the verdict and the evidence")]
    cells = "".join(f'<div class="{state}"><b>{"&#10003;" if state == "done" else n}</b><div style="border:0;background:none;padding:0;'
                    f'display:block"><span>{head}</span><small>{sub}</small></div></div>'
                    for n, (state, (head, sub)) in enumerate(zip(states, labels), 1))
    st.html(STEPS_CSS + f'<div class="cs">{cells}</div>')


def _how_to_test():
    """What to do before there is anything to compare, in plain steps."""
    left, right = st.columns(2)
    left.markdown(
        "#### With WSPR, the best way\n"
        "1. Connect your WSPR transmitter to an A/B coax switch, antenna A on one side and B on the other. Keep the band, power and settings the same.\n"
        "2. Decide how long each antenna stays on before you switch: **one transmission** (2 minutes), or a **set time**, for example 10 to 30 minutes. Write down the times.\n"
        "3. Switch in this order, **always starting with A**:\n"
        "   - **A, B, B, A, A, B, B, A …** is usually best. Each antenna gets the same mix of earlier and later turns, so a steady change in the band cancels out. Each antenna stays on for two turns in a row, so use shorter turns (for example 15 minutes instead of 30).\n"
        "   - **A, B, A, B …** is simpler, but B always goes second.\n"
        "4. **How long?** A test can be as short as 4 transmissions (about 8 minutes) or run for hours. More data is better: it narrows the uncertainty, and a long test also shows how changing band conditions affect the result.\n"
        "5. Wait about five minutes after the last transmission. Enter your callsign and the date in the sidebar, choose the band, and click **Load spots**.\n"
        "6. Tell the page how you switched. It works out which antenna got out better, by how much, and in which directions.")
    right.markdown(
        "#### With RBN, for a quick CW check\n"
        "1. Call CQ on one frequency with antenna A, then on a nearby frequency with antenna B, a minute or two apart, "
        "at the same speed and power.\n"
        "2. Pick **Download a day** (for yesterday or earlier) or copy the spots from reversebeacon.net and pick "
        "**Paste spots**.\n"
        "3. Load the spots and confirm which frequency was A and which was B.\n\n"
        "RBN is a rough check: skimmers report a CQ a minute or more after it was sent, so the two antennas can only be told "
        "apart by frequency. WSPR is better for a careful test.")


CARDS_CSS = """<style>
  [class*="st-key-excard_"] { min-height: 16.5rem; }
  [class*="st-key-hero_"] { margin-top: auto; }
</style>"""


def _example_cards():
    """Real tests to look at, each one open with a click and labelled with how its antennas were switched."""
    st.markdown(CARDS_CSS, unsafe_allow_html=True)
    st.markdown("#### Look at a real test first")
    st.caption("Each is a real test, set up the way it was run. Open one to see what a result looks like.")
    cards = inputs.COMPARE_EXAMPLES
    for row in (cards[:3], cards[3:]):
        for col, (key, how, title, blurb) in zip(st.columns(3), row):
            with col, st.container(border=True, key=f"excard_{key}"):
                st.caption(f":material/swap_horiz: {how}")
                st.markdown(f"**{title}**")
                st.caption(blurb)
                st.button("Open this example", key=f"hero_{key}", type="primary" if key == "quick" else "secondary", width="stretch",
                          on_click=inputs.start_example, args=(key,))


def compare_page():
    brand_strip()
    st.title(":material/balance: Compare antennas")
    st.markdown('<p class="subtitle">Which of two antennas, power levels or tests gets out better? Load the spots from one '
                'station, say how you switched, and read the verdict, with the evidence behind it.</p>', unsafe_allow_html=True)

    skimmers, refresh_msg = skimmer_data()
    ss, cfg, pick = inputs.begin(default_source=WSPR_SOURCE)
    inputs.leave_foreign_example(ss, inputs.COMPARE_KEYS, WSPR_SOURCE)
    test_link.read(ss, st.query_params)
    with st.sidebar:
        where = inputs.where_inputs(ss, cfg, second_call=True)
        load = st.button("Load spots", type="primary", width="stretch")
        st.button("Start over", type="tertiary", on_click=inputs.start_over, kwargs={"source": WSPR_SOURCE},
                  help="Clears everything: the callsigns, grid, dates, loaded spots and test setup.")
        where.load = inputs.take_autoload(ss, load)
        st.divider()
        view = inputs.view_controls(ss, cfg, pick, where.kind, comparing=True)
        link_slot = st.container()  # the link is drawn last, once the test's setup widgets exist
        st.caption(f":material/satellite_alt: {refresh_msg}")
    inputs.load_spots(ss, skimmers, where)
    _result(ss, skimmers, where, view)
    inputs.remember(ss, cfg, where, view, extra=test_link.params(ss, view.units), slot=link_slot)


def _result(ss, skimmers, where, view):
    """Everything under the title once spots are (or are not yet) loaded."""
    loaded = ss.raw is not None and not ss.raw.empty
    if not (loaded and ss.get("setup_ok")):  # once the setup is confirmed the strip has done its job; the result gets the room
        _steps(loaded, comparing_rbn=where.kind == "RBN")
    if ss.raw is None:
        _example_cards()
        _how_to_test()
        return
    if inputs.nothing_found_message(ss, "**Start over** in the sidebar brings back the examples, which show"):
        return

    wspr = ss.kind == "WSPR"
    locs = ss.locs if wspr else skimmers
    scale = WSPR_SNR_SCALE if wspr else RBN_SNR_SCALE
    noun = "receiver" if wspr else "skimmer"
    spots = ss.raw
    spots = spots[(spots["time"].dt.time >= view.start_t) & (spots["time"].dt.time <= view.end_t) & (spots["snr"] >= view.min_snr)]
    if view.band != "All":
        spots = spots[spots["band"] == view.band]
    if spots.empty:
        st.warning("No spots match the current filters. Set **Band** to All, or widen the UTC time window in the sidebar.")
        return

    lat, lon, label = ss.home
    if ss.notice:
        st.warning(ss.notice)
    inputs.example_banner(ss)
    if wspr and ss.loaded_at is not None:
        st.caption(f":material/schedule: Loaded at {ss.loaded_at:%H:%M} UTC. The newest transmission in it is at "
                   f"{ss.raw['time'].max():%H:%M} UTC. Sent something since? Click **Load spots** again.")
    st.caption(f":material/location_on: {ss.callsign}" + (f" (A) and {ss.tx_call_b} (B)" if ss.get("tx_call_b") else "") + f" · {label}")
    if not wspr:
        st.caption("RBN tells A and B apart by frequency: call CQ on one frequency with the first antenna, then on a nearby "
                   "frequency with the other, back to back (a minute or two apart).")
    compare_view(spots, locs, (lat, lon), label, ss.callsign, ss.file_date, view.tiles, view.show_all and not wspr, view.units,
                 SPLIT_LOG if wspr else SPLIT_FREQ, 0.5, scale, noun, ss.kind, ss.raw)
