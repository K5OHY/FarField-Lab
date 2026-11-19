"""The Log check tab on My spots: upload a contact log (ADIF) and see it beside your RBN spots and the WSPR stations near you."""
import hashlib

import pandas as pd
import streamlit as st

import log_check as lc
import log_check_html as lh
from data_sources import load_contact_places, load_nearby, load_rbn_listening
from maps import build_map
from ui_common import KM_PER_MILE
from wspr_data import WsprError

RADIUS_KM = 300 * KM_PER_MILE   # the WSPR stations counted as "near you", as on the Band conditions page
MAX_LOG_BYTES = 5_000_000


def _signature(raw, power, spots):
    """What a finished comparison was made from, so a new file, a new power or new spots start again."""
    return (hashlib.sha1(raw).hexdigest(), float(power), len(spots), str(spots["time"].min()), str(spots["time"].max()))


def _run(log, spots, locs, home, power, label):
    """Fetches what the comparison needs, with progress shown, and returns lc.compare's tables (or None after saying what went wrong)."""
    cw = log[log["mode"] == "CW"]
    start, end = cw["time"].min() - pd.Timedelta(minutes=lc.LOOKBACK_MIN), cw["time"].max() + pd.Timedelta(minutes=lc.WINDOW_PAD_MIN)
    days = tuple(sorted({f"{d:%Y%m%d}" for d in pd.date_range(start.floor("D"), end.floor("D"))}))
    with st.status("Comparing your log with RBN and WSPR…", expanded=True) as status:
        try:
            st.write("Finding the skimmers that were on the band (this reads the day's RBN file; the first time can take a minute)…")
            listening = load_rbn_listening(days, start, end)
            st.write(f"Fetching the WSPR stations within 300 miles of {label}, one stretch at a time…")
            result = lc.compare(log, spots, lambda a, b: load_nearby(home[0], home[1], RADIUS_KM, a, b), listening, locs, home, power)
        except (WsprError, RuntimeError) as exc:
            status.update(label="Could not finish", state="error")
            st.error(str(exc))
            return None
        status.update(label="Done", state="complete", expanded=False)
    return result


def _regions_section(result):
    """A band by region: pick a band, see each region's contacts, skimmers and the page's figure. It opens on the band with the most DX."""
    shown = result["bands"][result["bands"]["contacts"] >= 3]      # the bands that have a row in the table above
    bands, regions = list(shown["band"]), result["regions"]
    if not bands or regions.empty:
        return
    dx = regions[~regions["region"].isin(lh.NEAR_REGIONS)].groupby("band")["contacts"].sum()
    first = int(bands.index(dx.idxmax())) if len(dx) and dx.max() > 0 and dx.idxmax() in bands else 0
    st.markdown("#### A band by region")
    pick = st.radio("Band", bands, index=first, horizontal=True, key="log_region_band_" + "_".join(bands), label_visibility="collapsed")
    st.html(lh.CSS + lh.regions_html(regions, pick))


def _contacts_section(log, summary, spots, locs, home, label, who, tiles, units, signature):
    """The map of who heard you and who you worked, once the contacts have been placed, and a table of where each was."""
    st.markdown("#### Map: who heard you and who you worked")
    saved = st.session_state.get("log_places")
    places = saved["places"] if saved and saved["signature"] == signature[0] else None
    if places is None:
        st.caption("Each station in the log is looked up at the FCC (callook.info) and HamDB, the way your own callsign is, and shown at the centre "
                   "of its grid square, not at an address. The first time it takes a minute or two; the answers are remembered.")
        if st.button("Place my contacts on the map", key="log_place"):
            calls = log.drop_duplicates("call")[["call", "state", "country"]]
            bar = st.progress(0.0, text="Looking up your contacts\u2026")
            found = load_contact_places(list(calls.itertuples(index=False, name=None)), locs,
                                        progress=lambda done, total: bar.progress(done / total, text=f"Looked up {done} of {total}\u2026"))
            bar.empty()
            st.session_state["log_places"] = {"signature": signature[0], "places": found}
            st.rerun()
        return
    worked = lc.where_worked(log, places)
    missing = log["call"].nunique() - worked["call"].nunique()
    window = spots[(spots["time"] >= log["time"].min() - pd.Timedelta(minutes=10)) & (spots["time"] <= log["time"].max() + pd.Timedelta(minutes=10))]
    show = st.radio("Show on the map", ["Both", "Skimmers that spotted you", "Stations you worked"], horizontal=True, key="log_map_show")
    contacts_on, spots_on = show != "Skimmers that spotted you", show != "Stations you worked"
    levels = places["level"].value_counts()
    tail = f". The skimmers are those that spotted you from {window['time'].min():%H:%M}Z to {window['time'].max():%H:%M}Z." if len(window) else "."
    st.caption(f"{worked['call'].nunique()} stations placed ({levels.get('grid', 0)} from a lookup, {levels.get('state', 0)} at the centre of "
               f"their state, {levels.get('country', 0)} at the centre of their country)" + (f"; {missing} could not be placed" if missing else "") + tail)
    if spots_on and window.empty:
        st.warning("No RBN spots in the hours of this log, so only the stations you worked are shown.")
        spots_on = False
    m = build_map(window if spots_on else spots.iloc[0:0], locs, home, label, who, False, tiles, units, None, title=f"{who} \u00b7 log and spots",
                  contacts=worked if contacts_on else None, show_spots=spots_on)
    st.iframe(m.get_root().render(), height=640)
    st.caption("Diamonds are the stations you worked, coloured by the report they gave you; click one for each contact and the reports. "
               "Dots are the skimmers, coloured by SNR. Dotted lines are paths to the stations you worked.")
    table = lc.region_table(worked, window, locs)
    if len(table):
        st.dataframe(table.rename(columns={"contacts": "Contacts", "stations": "Stations worked", "skimmers": "Skimmers that spotted you"}),
                     width="stretch")


def log_tab(spots, locs, home, label, kind, who="", tiles="Street", units="mi"):
    """The tab. `spots` are the loaded RBN spots (all bands), `locs` the skimmer locations, `home` where you were."""
    st.markdown("Upload the log of a session (an ADIF file from your logging program) to set it beside the skimmers that heard you and "
                "the WSPR stations around you. Your log is used for this visit only and is not saved or shared.")
    if kind == "WSPR":
        st.info(icon=":material/info:", body="This works with Reverse Beacon Network spots, which only hear CW. Load RBN spots for the day of the "
                                             "log, then come back here.")
        return
    file = st.file_uploader("Your log (ADIF file)", type=["adi", "adif"], key="log_file",
                            help="Most logging programs can export one. Contacts need a call, date, time and band.")
    if file is None:
        return
    raw = file.getvalue()
    if len(raw) > MAX_LOG_BYTES:
        st.error("That file is larger than 5 MB. Export just the day you want to look at.")
        return
    try:
        log = lc.parse_adif(raw.decode("utf-8", errors="replace"))
    except ValueError as exc:
        st.error(str(exc))
        return
    cw = log[log["mode"] == "CW"]
    summary = lc.summary(log)
    rep = lc.repeat_stations(log)
    c1, c2 = st.columns([1, 3])
    power = c1.number_input("Your power (watts)", min_value=1, max_value=1500, value=100, step=5, key="log_power",
                            help="A log does not say. It is used to restate the WSPR stations' signals to your power, so enter what you ran.")
    c2.caption(f":material/location_on: Taken from the place in the sidebar: {label}. If you operated somewhere else, put that grid in "
               "the sidebar and click **Load spots** again. The comparison uses the CW contacts, because RBN only hears CW and RTTY.")
    signature = _signature(raw, power, spots)
    saved = st.session_state.get("log_result")
    result = saved["result"] if saved and saved["signature"] == signature else None
    st.html(lh.CSS + lh.tiles_html(summary, result["overall"] if result else None, len(rep)))
    if cw.empty:
        st.info(icon=":material/info:", body="There are no CW contacts in this log, so there is nothing to set beside the RBN spots. "
                                             "The facts below come from the log alone.")
    else:
        spot_days = set(spots["time"].dt.date)
        loaded = log[log["time"].dt.date.isin(spot_days)]
        on_loaded = loaded[loaded["mode"] == "CW"]
        if on_loaded.empty:
            st.warning("None of the CW contacts are on a day you have loaded spots for. Load spots for "
                       f"{cw['time'].min():%d %b %Y} and come back.")
        else:
            if len(on_loaded) < len(cw):
                st.caption(f"{len(cw) - len(on_loaded)} CW contacts are on days without loaded spots and are left out of the comparison.")
            if st.button("Compare with RBN and WSPR", type="primary", key="log_compare",
                         help="Fetches the WSPR stations near you for each stretch on a band. It can take a minute or two."):
                fresh = _run(loaded, spots, locs, home, power, label)
                if fresh is not None:
                    st.session_state["log_result"] = {"signature": signature, "result": fresh}
                    st.rerun()
    if result is not None:
        st.html(lh.CSS + lh.band_table_html(result["bands"]))
        o = result["overall"]
        notes = [f"Page and skimmers: in regions with at least {lc.cond.THIN} WSPR receivers, the page's chance averaged {lh.pct(o['page'])} "
                 f"and {lh.pct(o['spotted'])} of the {o['listening']} skimmers on the band spotted you." if o["listening"] else None,
                 f"Regions with too few WSPR receivers (greyed on the Band conditions page): {o['thin_spotted']} of {o['thin_listening']} "
                 "skimmers on the band spotted you." if o["thin_listening"] else None,
                 f"Strength spread between receivers: {o['spread_db']:.1f} dB." if o["matches"] > 2 else None]
        st.caption(" ".join(n for n in notes if n))
        _regions_section(result)
    _contacts_section(log, summary, spots, locs, home, label, who, tiles, units, (signature[0],))
    st.html(lh.CSS + lh.afternoon_html(log, spots))
    st.html(lh.CSS + lh.followers_html(log, summary, result["bands"] if result else None, lc.report_summary(log)))
    st.caption(f"\"Stronger than a typical station\" sets the skimmers' reports against the WSPR stations near you, restated to your power. "
               f"Skimmers and WSPR receivers are different equipment, so an ordinary station reads about {lc.TYPICAL_OFFSET_DB:.0f} dB higher "
               "on RBN than on the Band conditions page (found from two checks of stations whose power is known), and that is taken off. "
               f"With fewer than {lc.MIN_MATCHES} matched receivers a bar is striped, and it is a hint, not a score. The percentages "
               "compare the page's chance for each region with the share of skimmers on the band that spotted you, which is lower, because "
               "a skimmer has to be tuned to you and decode you. A log shows who worked you; RBN only shows who a skimmer decoded.")
