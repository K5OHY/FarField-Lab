"""The Log analysis page: upload a contact log (ADIF) and the callsign, place and days come from the log. The RBN spots and the WSPR stations
near you are fetched, and the log is set beside them."""
import hashlib
import threading

import pandas as pd
import streamlit as st

import conditions as cond
import log_check as lc
import log_check_html as lh
import log_foundations as lf
import log_highlights as hl
import log_openings as lo
import share_card as sc
import space_weather as sw
from compare_stats import locate as skimmer_location
from data_sources import download_rbn_day, load_contact_places, load_nearby, load_pota_park, load_rbn_listening, load_sota_summit, skimmer_data
from maps import build_map, great_circle, park_map
from rbn_data import lookup_callsign_location, maidenhead_to_latlon
from ui_common import BAND_COLORS, BANNER, KM_PER_MILE, page_guide, preview
from wspr_data import WsprError

MAX_LOG_BYTES = 5_000_000
MAX_DAYS = 4                    # each day is a large file to read, so a log is limited to a few days
MAPS_HEADING = "Maps for CW: where RBN heard you, and who you worked"
HEARD_TITLE, WORKED_TITLE = "Where RBN heard you on {band}", "Stations you worked on {band}"


def _signature(raw, power, call, grid, spots, radius_km=lf.DEFAULT_RADIUS_KM):
    """What a finished comparison was made from, so a new file, power, callsign, place, radius or spots start again."""
    return (hashlib.sha1(raw).hexdigest(), float(power), call, grid, len(spots), str(spots["time"].min()), str(spots["time"].max()), float(radius_km))


@st.cache_data(ttl=3600, show_spinner=False)
def _space_history(start_iso, end_iso):
    """The Kp, solar flux and flares over a past stretch of time, kept for an hour (GFZ Potsdam and NOAA)."""
    return sw.history(pd.Timestamp(start_iso), pd.Timestamp(end_iso))


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _pota_park(ref):
    """POTA's record of a park and its activations, kept for six hours. Raises RuntimeError when POTA cannot be reached (and so is not kept)."""
    return load_pota_park(ref)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _sota_summit(ref):
    """SOTA's record of a summit and its activations, kept for six hours. Raises RuntimeError when SOTA cannot be reached (and so is not kept)."""
    return load_sota_summit(ref)


def _log_grids(log):
    """The grid square the log gives each station, by callsign (the first one given), so those stations are placed with no lookup."""
    if "their_grid" not in log:
        return {}
    given = log[log["their_grid"] != ""].drop_duplicates("call")
    return dict(zip(given["call"], given["their_grid"]))


def _pota_cards(log, call):
    """One card for each park (POTA) or summit (SOTA) the log was made from (at most four): a headline across the top, then a map and what is known
    about the place on the left and how the activations compare on the right. A note instead when the program cannot be reached. Returns the
    comparisons that were made."""
    cards = []
    jobs = [("POTA", r) for r in lc.pota_refs(log)] + [("SOTA", r) for r in lc.sota_refs(log)]
    for program, ref in jobs[:4]:
        noun = "summit" if program == "SOTA" else "park"
        try:
            park, acts, totals = _sota_summit(ref) if program == "SOTA" else _pota_park(ref)
        except RuntimeError as exc:
            st.caption(f"{ref}: {exc} The {noun} comparison is left out.")
            continue
        if park is None and acts.empty:
            st.caption(f"{program} does not know {ref}, so there is no {noun} comparison.")
            continue
        card = lc.pota_compare(log, ref, park, acts, call, totals, program)
        cards.append(card)
        banner = lh.pota_banner_html(card)
        if banner:
            st.html(lh.CSS + banner)
        if park and park.get("latitude") is not None and park.get("longitude") is not None:
            left, right = st.columns([2, 3])
            left.iframe(park_map(float(park["latitude"]), float(park["longitude"]), f"{ref} {park.get('name', '')}".strip()).get_root().render(), height=300)
            facts = lh.summit_facts_html(card) if program == "SOTA" else lh.park_facts_html(card)
            if facts:
                left.html(lh.CSS + facts)
            right.html(lh.CSS + lh.pota_html(card))
        else:
            st.html(lh.CSS + lh.pota_html(card))
    return cards


def _where(grid, call, skimmers):
    """(lat, lon, label) of where you operated: the grid square when there is one, otherwise where the callsign is registered."""
    if grid:
        try:
            lat, lon = maidenhead_to_latlon(grid)
        except ValueError:
            raise RuntimeError(f"\"{grid}\" is not a grid square. Use something like DM81wx, or leave it empty to use where the callsign is registered.")
        return lat, lon, grid
    found = lookup_callsign_location(call, skimmers)
    if not found:
        raise RuntimeError(f"The log does not say where you were and no location was found for {call}. Type your grid square above.")
    return found[0], found[1], f"{found[2] or 'near ' + call} (where {call} is registered)"


def _what_was_read(log, name, call="", where=""):
    """One line under the uploader: how many contacts were read, from which file, which callsign and place they are for, and, when records were left
    out, how many and why."""
    n, seen = len(log), log.attrs.get("records", len(log))
    who = (f" for {call}" if call else "") + (f", at {where}" if where else "")
    if seen == n:
        st.caption(f"Read {n} contacts from {name}{who}.")
        return
    why = [f"{k} without a usable {what}" for k, what in ((log.attrs.get("no_time", 0), "date or time"), (log.attrs.get("no_band", 0), "band")) if k]
    st.caption(f"Read {n} of the {seen} records in {name}{who}. {seen - n} left out: {', '.join(why)}.")


def _mixed_log_warning(log):
    """Says so when the log was made under more than one callsign or from more than one place, because the comparison uses one of each."""
    for column, noun, kind in (("my_grid", "place", "grid squares"), ("station", "callsign", "callsigns")):
        found = lc.origin_counts(log, column)
        if len(found) > 1:
            listed = ", ".join(f"{v} ({n} contacts)" for v, n in found[:4]) + (" and more" if len(found) > 4 else "")
            st.warning(f"This log has more than one {noun}: {listed}. The comparison uses the one with the most contacts, {found[0][0]}, for "
                       f"all of them. If you moved or used another callsign, export each {noun} as its own file to compare it properly.")


def _visitor_timezone():
    """The visitor's time zone name from their browser, or None when it is not known."""
    try:
        return st.context.timezone
    except Exception:
        return None


def _rbn_spots(raw_key, call, days):
    """Your RBN spots for the log's days, kept for this log and callsign. Returns (spots, the days RBN has no file for)."""
    saved = st.session_state.get("log_spots")
    if saved and saved["key"] == (raw_key, call):
        return saved["spots"], saved["missing"]
    frames, missing = [], []
    with st.status(f"Reading the Reverse Beacon Network files for {call}…", expanded=True) as status:
        for i, day in enumerate(days):
            st.write(f"Day {i + 1} of {len(days)}: {day[:4]}-{day[4:6]}-{day[6:]} (the first time a day can take a minute)")
            try:
                frames.append(download_rbn_day(day, call))
            except RuntimeError:
                missing.append(day)
        status.update(label="RBN spots read" if len(missing) < len(days) else "RBN has no file for this log yet",
                      state="complete" if len(missing) < len(days) else "error", expanded=False)
    spots = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame({"spotter": [], "band": [], "snr": [], "time": pd.to_datetime([])})
    st.session_state["log_spots"] = {"key": (raw_key, call), "spots": spots, "missing": missing}
    return spots, missing


def _run(log, spots, locs, home, power, label, radius_km=lf.DEFAULT_RADIUS_KM):
    """Fetches what the comparison needs, with progress shown, and returns lc.compare's tables (or None after saying what went wrong)."""
    cw = log[log["mode"] == "CW"]
    start, end = cw["time"].min() - pd.Timedelta(minutes=lc.LOOKBACK_MIN), cw["time"].max() + pd.Timedelta(minutes=lc.WINDOW_PAD_MIN)
    days = tuple(sorted({f"{d:%Y%m%d}" for d in pd.date_range(start.floor("D"), end.floor("D"))}))
    with st.status("Comparing your log with RBN and WSPR…", expanded=True) as status:
        try:
            st.write("Finding the skimmers that were on the band (this reads the day's RBN file; the first time can take a minute)…")
            listening = load_rbn_listening(days, start, end)
            st.write(f"Fetching the WSPR stations within {lf.radius_text(radius_km)} of {label}, one stretch at a time…")
            result = lc.compare(log, spots, lambda a, b: load_nearby(home[0], home[1], radius_km, a, b), listening, locs, home, power)
        except (WsprError, RuntimeError) as exc:
            status.update(label="Could not finish", state="error")
            st.error(str(exc))
            return None
        status.update(label="Done", state="complete", expanded=False)
    return result


def _conditions(log, home, power, label, digest, radius_km=lf.DEFAULT_RADIUS_KM):
    """The grid of how open each band looked while you were on the air, kept for this log, power and place. It needs only WSPR, so it works
    on the day of the activation, before RBN has published its file."""
    key = (digest, float(power), round(home[0], 3), round(home[1], 3), float(radius_km))
    held = st.session_state.get("log_conditions")
    if held and held["key"] == key:
        return held["grid"]
    with st.status(f"Looking at how open each band was near {label}…", expanded=True) as status:
        try:
            st.write(f"Fetching the WSPR stations within {lf.radius_text(radius_km)} of you for the hours of the activation…")
            grid = lc.conditions_grid(log, lambda a, b: load_nearby(home[0], home[1], radius_km, a, b), home, power, radius_km=radius_km)
        except (WsprError, RuntimeError) as exc:
            status.update(label="Could not work out the band conditions", state="error")
            st.error(str(exc))
            return None
        status.update(label="Band conditions worked out", state="complete", expanded=False)
    st.session_state["log_conditions"] = {"key": key, "grid": grid}
    return grid


def _foundations_section(grid, log, home, places):
    """The rules behind the picture, with their numbers: the clock-aligned bins, the exact WSPR window behind each box and how much of it the
    box before shared, how many stations stand behind each box and what it can say, and where your contacts were seen from your station."""
    bin_min = grid.attrs.get("bin_min", lc.CONDITIONS_SLOT_MIN)
    ev = grid.attrs.get("evidence") or {}
    near = lf.radius_text(ev["radius_km"]) if ev.get("radius_km") else "300 miles"
    table = lc.coverage_table(grid)
    st.markdown("**Time bins and WSPR coverage**")
    st.caption(f"Your contacts, the RBN spots and the WSPR are all sorted into the same clock-aligned {bin_min}-minute bins, so a box means the same thing for each. "
               f"A box is judged on the hour of WSPR up to its end, from transmitters within {near} of you, so each box uses part of the same hour as the box before it. "
               "The table gives the exact window and how many of its minutes the box before used too: reports in the shared minutes speak for both boxes. "
               "A box with fewer than "
               f"{lf.SPARSE_MIN_TRANSMITTERS} transmitters or {lf.SPARSE_MIN_RECEIVERS} receivers behind it is marked as having insufficient coverage and says nothing.")
    states = grid["state"].value_counts()
    st.caption("Of the " + f"{len(grid)} boxes: " + ", ".join(f"{n} {name}" for name, n in states.items()) + ".")
    st.dataframe(table, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(table)))
    with st.popover("What the states mean"):
        for name in (lf.EVIDENCE, lf.NO_REPORTS, lf.SPARSE, lf.BELOW, lf.UNAVAILABLE, lf.NOT_APPLICABLE):
            st.markdown(f"**{name}**: {lf.STATE_NOTES[name]}")
    st.markdown("**Where your contacts were**")
    pick = st.radio("Group contacts by", list(lf.REGION_VIEWS.values()), horizontal=True, key="log_contacts_view")
    view = next(k for k, v in lf.REGION_VIEWS.items() if v == pick)
    by_region = lc.contact_direction_table(places, view)
    if by_region.empty:
        st.caption("No contact could be placed.")
    else:
        st.dataframe(by_region, hide_index=True, width="stretch")
    n = by_region.attrs
    if view == "sector":
        st.caption(f"{n['counted']} of the {n['total']} contacts can be placed in one direction: {n['counted'] - n['by_state']} by their own grid square and "
                   f"{n['by_state']} by their state, because the whole state lies in that direction from you. {n['between']} are between directions: "
                   "their state spreads over more than one, or they are placed only at the centre of their country, which can be hundreds of km from the station. "
                   + (f"{n['unplaced']} could not be placed at all." if n["unplaced"] else ""))
    else:
        st.caption("The continent comes from the log, or else from the callsign, so every contact counts here even when its place is not known exactly.")


def _clock(df, columns):
    """`df` with the time columns shown as clock times, for a table."""
    return df.assign(**{c: pd.to_datetime(df[c]).dt.strftime("%H:%M:%S") for c in columns if c in df})


def _box_evidence(cells, grid, log, places, spots, locs, home, band, slot, view, dest, min_km, rbn_ok, radius_km):
    """Everything behind one box: what it says, the WSPR window and what stands behind it, and the tables of transmitters, receivers, RBN spots and
    contacts."""
    row = cells[(cells["band"] == band) & (cells["slot"] == pd.Timestamp(slot))]
    if row.empty:
        st.caption("Pick a band and a box above.")
        return
    row = row.iloc[0]
    where = cells.attrs["where"]
    ev = lo.cell_evidence(grid, log, places, spots, locs, lambda a, b: load_nearby(home[0], home[1], radius_km, a, b), home, band, pd.Timestamp(slot), view,
                          dest, cells.attrs["min_km"], rbn_ok)
    start, end = ev["window"]
    b0, b1 = ev["bin"]
    cov = ev["coverage"]
    st.markdown(f"**{band}, {b0:%H:%M}\u2013{b1:%H:%M} UTC.** {row['text']} {lo.rbn_sentence(row['rbn_state'], int(row['rbn_n']), where, row['rbn_why'])}")
    st.caption(f"WSPR window: after {start:%d %b %H:%M} and up to {end:%H:%M} UTC, from transmitters within {lf.radius_text(radius_km)} of you. It shares "
               f"{row['shared_min']:.0f} of its minutes with the box before. Behind it: {cov['reports']} reports from {cov['transmitters']} transmitters, decoded by "
               f"{cov['receivers']} receivers at {cov['sites']} sites. The path in this box is {row['state']}: {lf.STATE_NOTES[row['state']]}")
    tx, rx, rbn, qso = ev["transmitters"], ev["receivers"], ev["rbn"], ev["qsos"]
    t1, t2, t3, t4 = st.tabs([f"WSPR transmitters near you ({len(tx)})", f"Receivers there ({len(rx)})", f"Your RBN spots ({len(rbn)})", f"Your contacts ({len(qso)})"])
    with t1:
        st.dataframe(_clock(tx, ["First report", "Last report"]).round({"Km from you": 0}), hide_index=True, width="stretch")
    with t2:
        st.caption("The WSPR stations in the destination, at the distance chosen, that decoded those transmitters in this window." if len(rx)
                   else "No WSPR station in the destination decoded them in this window.")
        st.dataframe(_clock(rx, ["First decode", "Last decode"]), hide_index=True, width="stretch")
    with t3:
        near = int((rbn["In the destination"] == "yes").sum()) if len(rbn) else 0
        st.caption((f"All the spots of you on this band in this box: {len(rbn)}, of which {near} from skimmers in the destination. Most spots are from skimmers near you, which "
                    "is why the shading and rings count only the distant ones.") if len(rbn)
                   else "RBN has no spot of you on this band in this box." if rbn_ok else lo.rbn_sentence(row["rbn_state"], int(row["rbn_n"]), where, row["rbn_why"]))
        st.dataframe(_clock(rbn, ["Time"]), hide_index=True, width="stretch")
    with t4:
        st.dataframe(_clock(qso, ["Time"]), hide_index=True, width="stretch")


def _destination_choices():
    """One list for the destination: all of them, a continent, or a compass direction, as [(key, label)]. A key is 'all', 'continent:EU' or 'sector:NE'."""
    return ([("all", "All destinations")] + [(f"continent:{k}", f"Continent: {v}") for k, v in lf.CONTINENT_NAMES.items() if k != "AN"]
            + [(f"sector:{s}", f"Direction: {lf.sector_label(s)}") for s in lf.SECTORS])


def _busiest_dx_continent(places):
    """The destination to open on: the continent outside North America with the most of your contacts, else all of them."""
    far = places[(places["continent"] != "") & (places["continent"] != "NA")].groupby("continent").size()
    return f"continent:{far.idxmax()}" if len(far) else "all"


LAYOUTS = {"dest": "By destination", "cards": "Band by band", "grid": "Grid"}


def _home_continent(call):
    """The continent your callsign belongs to (NA when it cannot be told), so the DX picture never treats your own continent as a destination."""
    from rbn_data import country_continent, country_location
    try:
        guess = country_location(call)
        return (country_continent(guess[2]) if guess else "") or "NA"
    except Exception:
        return "NA"


def _openings_section(grid, log, home, power, mode, zone, radius_km, skimmers, digest, home_cont="NA"):
    """How you used the openings. The default is *By destination*: one destination at a time (only those with a path in the nearby WSPR, an RBN skimmer or a
    contact get a tab, and the rest are named in a line), shown as a strip of the band you were on above a lane for each band. *Regional* is the last tab: the eight
    compass directions, band by band. Under More options the earlier views remain: *Band by band* (a card for each band you worked, with a lane for each distant
    continent) and *Grid* (a box for each band and time bin, read for one destination). All can be read as what WSPR showed or as an estimate for your station, and all
    are followed by 'look at one box', which shows the evidence behind a bar or box. Returns draw(spots, rbn_ok), which draws it all again: it is called once
    without RBN and again when the spots have been read; it returns the sentence for the row of findings."""
    places = lc.contact_places(log, home)
    with st.expander("More options"):
        show = st.radio("What the bars show", list(lh.DX_VIEWS.values()), horizontal=True, key="log_dx_view",
                        help="What WSPR showed: the stations that decoded WSPR transmitters near you, with nothing assumed about your station. "
                             "Estimate for my station: the ones whose reports, restated to your power, look strong enough to hear you.")
        layout = st.radio("View", list(LAYOUTS.values()), horizontal=True, key="log_openings_layout",
                          help="By destination: one destination at a time, with the band you were on above a lane for each band. Band by band: a card for each band you worked, with the "
                               "distant continents WSPR showed a path to, and your contacts, on one time axis. Grid: the earlier view, a box for each band and time bin for one destination.")
        reach = "dx"
        if layout == LAYOUTS["cards"]:
            shown = st.radio("Reach", list(lo.REACH.values()), horizontal=True, key="log_reach",
                             help="DX: the other continents, from the distance set below (3,000 miles by default). Regional: the eight compass directions "
                                  f"from you, for stations from {lo.REGIONAL_MIN_KM} km out to where DX begins, which is where most of a North American activation is worked.")
            reach = next(k for k, v in lo.REACH.items() if v == shown)
        distance = st.selectbox("At least this far away", list(lf.DISTANCE_CHOICES), index=list(lf.DISTANCE_CHOICES).index(lf.DEFAULT_DISTANCE),
                                format_func=lambda k: lf.DISTANCE_CHOICES[k][0], key="log_distance",
                                help="A station nearer than this is not counted as a destination, for the WSPR evidence, your contacts and the RBN skimmers alike.")
    metric_view = next(k for k, v in lh.DX_VIEWS.items() if v == show)
    min_km = lf.DISTANCE_CHOICES[distance][1]
    by_dest, cards = layout == LAYOUTS["dest"], layout == LAYOUTS["cards"]
    pick = None                                 # the tab chosen in the destination view: a continent code, or "regional"
    if by_dest:
        base = lo.band_timeline(grid, log, places, None, skimmers, home, min_km, lo.METRIC[metric_view], False, None, "dx", home_cont)
        tabs, _ = lo.destination_views(base)
        options = [v["code"] for v in tabs] + ["regional"]
        names = {v["code"]: f"{v['name']} · {lo.destination_badge(v)}" for v in tabs}
        names["regional"] = "Regional (by direction)"
        pick = st.segmented_control("Destination", options, default=options[0], format_func=names.get, key=f"log_dest_tab_{digest[:8]}_{'_'.join(options)}",
                                    label_visibility="collapsed",
                                    help="Only the destinations that have something to show are listed: a path in the nearby WSPR, an RBN skimmer there that spotted you, or a contact. "
                                         "Regional shows the eight compass directions instead of the other continents.") or options[0]
        view, dest = "continent", (None if pick == "regional" else pick)
        reach = "regional" if pick == "regional" else "dx"
    elif cards:
        lane_codes, lane_names, _, lane_word, _ = lo.lane_set(reach, home_cont)
        options = [("all", f"All {lane_word}s" if lane_word == "continent" else "All directions")] + [(c, lane_names[c][:1].upper() + lane_names[c][1:]) for c in lane_codes]
        choice = st.selectbox("Show", [k for k, _ in options], format_func=dict(options).get, key=f"log_card_dest_{reach}",
                              help="Every destination, or just one. Your own continent is not a DX destination." if reach == "dx" else "Every direction, or just one.")
        view, dest = "continent", (None if choice == "all" else choice)
    else:
        options = _destination_choices()
        default = _busiest_dx_continent(places)
        choice = st.selectbox("Destination", [k for k, _ in options], index=[k for k, _ in options].index(default), format_func=dict(options).get,
                              key=f"log_dest_{digest[:8]}", help="Where to look: a continent, or a compass direction from you (eight sectors of 45 degrees). "
                                                                  "It opens on the continent where you made the most DX contacts.")
        kind, _, code = choice.partition(":")
        view, dest = ("continent" if kind == "continent" else "sector"), (code or None)
    regional = reach == "regional"
    grid_slot, table_slot = st.empty(), st.empty()
    with st.expander("How to read this, and what it rests on"):
        explain_slot, words_slot = st.empty(), st.empty()
    bands = list(dict.fromkeys(grid["band"]))
    slots = sorted(grid["slot"].unique())
    lane_codes, lane_names = lo.lane_set(reach, home_cont)[:2] if (cards or by_dest) else ((), {})
    with st.expander("Details for one band and time: the stations, spots and contacts behind it"):
        cols = st.columns(3 if cards else 2)
        band = cols[0].selectbox("Band", bands, key="log_box_band")
        slot = cols[1].selectbox("Box (UTC)", slots, format_func=lambda t: f"{pd.Timestamp(t):%d %b %H:%M}Z", key="log_box_slot")
        if cards:
            ev_choice = cols[2].selectbox("Continent" if reach == "dx" else "Direction", ["all"] + list(lane_codes),
                                          format_func=lambda k: "All" if k == "all" else lane_names[k], key=f"log_box_cont_{reach}")
            ev_view, ev_dest = ("continent" if reach == "dx" else "sector"), (None if ev_choice == "all" else ev_choice)
        elif by_dest:
            ev_view, ev_dest = ("sector", None) if regional else ("continent", dest)           # the destination chosen above
        else:
            ev_view, ev_dest = view, dest
        box_slot = st.empty()
    ev_km = lo.REGIONAL_MIN_KM if (regional and (cards or by_dest)) else min_km

    def draw(spots, rbn_ok):
        metric = lo.METRIC[metric_view]
        headline = ""
        if by_dest and not regional:
            timeline = lo.band_timeline(grid, log, places, spots, skimmers, home, min_km, metric, rbn_ok, None, "dx", home_cont)
            tabs, empty = lo.destination_views(timeline)
            current = next((v for v in tabs if v["code"] == pick), None)
            if current is None:
                grid_slot.caption("Nothing to show for this destination.")
            else:
                note = lo.inside_limit_note(places, home_cont, min_km)
                extra = [v["name"] for v in tabs if v["code"] not in options]
                if extra:                          # a destination only the RBN spots found: it has no tab, so it is said here
                    note = (note + " " if note else "") + f"RBN skimmers in {', '.join(extra)} spotted you, though the nearby WSPR showed no path and you logged no contact there."
                grid_slot.html(lh.CSS + lh.destination_html(current, timeline, BAND_COLORS, empty, note))
                first = current["panels"][0]["lines"][0] if current["panels"] and current["panels"][0]["lines"] else None
                headline = f"{current['name']}, {first[0]}: {first[1]}" if first else ""
            table_slot.empty()
            explain_slot.html(lh.CSS + lh.band_cards_explain_html(timeline, grid))
            words_slot.empty()
        elif cards or (by_dest and regional):
            timeline = lo.band_timeline(grid, log, places, spots, skimmers, home, min_km, metric, rbn_ok, dest, reach, home_cont)
            grid_slot.html(lh.CSS + lh.with_id(lh.band_cards_html(timeline, zone), "sec-openings"))
            table_slot.empty()
            explain_slot.html(lh.CSS + lh.band_cards_explain_html(timeline, grid))
            words_slot.empty()
            headline = timeline["headline"]
        else:
            cells = lo.opening_cells(grid, log, places, spots, skimmers, home, view, dest, min_km, metric, rbn_ok)
            grid_slot.html(lh.CSS + lh.with_id(lh.openings_html(cells, grid, zone, metric_view), "sec-openings"))
            with table_slot.container():
                table = lo.openings_table(cells)
                if len(table):
                    st.dataframe(table, hide_index=True, width="stretch", height=min(300, 38 + 35 * len(table)))
                rbn = lo.rbn_line(cells)
                if rbn:
                    st.caption(rbn)
            explain_slot.html(lh.CSS + lh.openings_explain_html(cells, grid, metric_view))
            lines = lo.openings_summary(cells)
            words_slot.markdown("**In words**\n\n" + "\n".join(f"- {line}" for line in lines) if lines else "")
            headline = lo.openings_headline(cells)
        evidence = lo.opening_cells(grid, log, places, spots, skimmers, home, ev_view, ev_dest, ev_km, metric, rbn_ok)
        with box_slot.container():
            _box_evidence(evidence, grid, log, places, spots, skimmers, home, band, slot, ev_view, ev_dest, ev_km, rbn_ok, radius_km)
        return headline

    draw(None, False)
    with st.expander("Another view: the percent of stations that could have heard you"):
        st.html(lh.CSS + lh.conditions_html(grid, lc.conditions_notes(grid), power, mode, zone))
    with st.expander("What each box rests on: the time bins, the WSPR behind them and where your contacts were"):
        _foundations_section(grid, log, home, places)
    return draw


def _busiest_dx_band(log, bands):
    """The band with the most contacts outside North America, else the first."""
    dx = log[lc.dx_contacts_mask(log)].groupby("band").size()
    return int(bands.index(dx.idxmax())) if len(dx) and dx.idxmax() in bands else 0


def _default_band(bands, regions):
    """The index of the band to open on: the one with the most DX contacts, else the first."""
    dx = regions[~regions["region"].isin(lh.NEAR_REGIONS)].groupby("band")["contacts"].sum()
    return int(bands.index(dx.idxmax())) if len(dx) and dx.max() > 0 and dx.idxmax() in bands else 0


def _places_for(rows, digest, skimmers, grids=None):
    """Where the stations on one band were, looked up only for the ones not looked up before. Kept for this log, so each station is
    only looked up once however often you change band."""
    saved = st.session_state.get("log_places")
    if not saved or saved["digest"] != digest:
        saved = {"digest": digest, "places": pd.DataFrame(columns=["lat", "lon", "source", "level", "grid"]), "tried": set()}
    todo = [r for r in rows if r[0] not in saved["tried"]]
    if todo:
        bar = st.progress(0.0, text="Looking up where your contacts were…")
        found = load_contact_places(todo, skimmers, progress=lambda done, total: bar.progress(done / total, text=f"Looked up {done} of {total}…"), grids=grids)
        bar.empty()
        if len(found):
            saved["places"] = pd.concat([saved["places"], found]) if len(saved["places"]) else found
        saved["tried"] |= {r[0] for r in todo}
    st.session_state["log_places"] = saved
    return saved["places"]


def _prefetch_places(log, skimmers, digest):
    """Starts looking up where the stations of every band were, in the background and busiest band first, as soon as a log is loaded, so the
    contact map of each band is ready when you click it. The answers are saved by the lookup itself; nothing here touches the page."""
    if st.session_state.get("log_prefetch") == digest:
        return
    st.session_state["log_prefetch"] = digest
    jobs = [list(log[log["band"] == band].drop_duplicates("call")[["call", "state", "country"]].itertuples(index=False, name=None))
            for band in log["band"].value_counts().index]

    grids = _log_grids(log)

    def run():
        for rows in jobs:
            try:
                load_contact_places(rows, skimmers, workers=4, grids=grids)
            except Exception:
                pass
    threading.Thread(target=run, daemon=True, name="log-places").start()


def _view_points(home, spots, worked, locs):
    """The points both maps are framed on, so they show the same area."""
    points = []
    for spotter in spots["spotter"].unique():
        loc = skimmer_location(spotter, locs)
        if loc:
            points.append(great_circle(home, loc)[-1])
    for lat, lon in zip(worked["lat"], worked["lon"]):
        points.append(great_circle(home, (float(lat), float(lon)))[-1])
    return points


def _maps_section(log, result, spots, locs, home, label, who, tiles, units, digest, spots_url=None):
    """Two maps of one band, side by side and framed alike: the skimmers that spotted you, and the stations you worked. They open on the
    band with the most DX; placing that band's stations takes a few seconds the first time, and each band is only looked up once."""
    st.markdown(f"#### {MAPS_HEADING}")
    if spots_url:
        st.link_button("Open this activation on the My spots map", spots_url, icon=":material/open_in_new:",
                       help="Opens My spots in a new tab, on the day of this log and the hours of this session, with your callsign and RBN spots loaded.")
    st.caption("Skimmers only hear CW, so the maps start with your CW contacts. Where your contacts were is looked up in the background, so each band should be ready when you click it.")
    if result is not None:
        shown = set(result["bands"]["band"])
        bands = [b for b in lc.bands_top_down(log) if b in shown] or lc.bands_top_down(log)
        first = _default_band(bands, result["regions"])
    else:                       # no RBN to compare with: the stations you worked are still mapped, for every band of the log
        bands = lc.bands_top_down(log)
        first = _busiest_dx_band(log, bands)
    has_cw = bool((log["mode"] == "CW").any())
    c1, c2 = st.columns([3, 2])
    pick = c1.radio("Band", bands, index=first, horizontal=True, key="log_map_band_" + "_".join(bands), label_visibility="collapsed")
    cw_only = c2.checkbox("CW contacts only", value=has_cw and result is not None, key="log_map_cw",
                          help="Skimmers only hear CW, so the CW contacts are the ones to hold against the left map. Untick to see every contact.")
    mine = log[log["band"] == pick]
    shown_log = mine[mine["mode"] == "CW"] if cw_only else mine
    rows = list(shown_log.drop_duplicates("call")[["call", "state", "country"]].itertuples(index=False, name=None))
    places = _places_for(rows, digest, locs, _log_grids(log))
    worked = lc.where_worked(shown_log, places)
    worked = worked.assign(bands_worked=worked["call"].map(log.groupby("call")["band"].nunique()))
    t_lo, t_hi = mine["time"].min() - pd.Timedelta(minutes=10), mine["time"].max() + pd.Timedelta(minutes=10)
    heard = spots[(spots["band"] == pick) & (spots["time"] >= t_lo) & (spots["time"] <= t_hi)]
    view = _view_points(home, heard, worked, locs)
    left, right = st.columns(2)      # a one line title above each map and the notes below them, so the two maps start level
    left.markdown(f"**{HEARD_TITLE.format(band=pick)}**")
    right.markdown(f"**{WORKED_TITLE.format(band=pick)}**")
    left.iframe(build_map(heard, locs, home, label, who, False, tiles, units, None, title=f"{who} · RBN heard you on {pick}", view=view, show_legend=False)
                .get_root().render(), height=520)
    right.iframe(build_map(spots.iloc[0:0], locs, home, label, who, False, tiles, units, None, title=f"{who} · worked on {pick}",
                           contacts=worked if len(worked) else None, show_spots=False, contact_paths=False, view=view, show_legend=False)
                 .get_root().render(), height=520)
    missing = shown_log["call"].nunique() - worked["call"].nunique()
    left.caption(f"{heard['spotter'].nunique()} skimmers between {t_lo:%H:%M}Z and {t_hi:%H:%M}Z. Dots are coloured and sized by the best SNR."
                 if len(heard) else (f"No RBN spots on {pick} while you were working it." if result is not None
                                     else "The RBN spots are not available, so there is no skimmer map. The stations you worked are on the right."))
    right.caption(f"{worked['call'].nunique()} stations" + (f" ({missing} could not be placed)" if missing else "")
                  + ". Colour is the report they gave you, from weak (green) to strong (red), grey where the log has none. "
                    "A black ring marks a station that worked you on more than one band. Click one for the contacts. "
                    "Each is at the centre of its grid square, state or country.")


def _glance(park_cards, rep, spots, skimmers, home, headline, result):
    """The row of short findings under the tiles, each a link to its section, from what is known so far: who worked you on more than one band,
    who RBN heard you, the openings and the comparison with RBN. A finding that cannot be made yet or at all is left out."""
    items = []                  # the park or summit card follows this row at once, so it is not repeated here
    if len(rep):
        items.append(("Worked you on more than one band", lh.followers_headline(rep), "sec-hunters"))
    if spots is not None and len(spots):
        sk = lo.skimmer_table(spots, skimmers, home)
        bands = lc.bands_top_down(spots)
        text = f"{spots['spotter'].nunique()} RBN skimmers spotted you, on {', '.join(bands)}."
        if len(sk):
            far = sk.loc[sk["km"].idxmax()]
            text += f" The farthest was {far['who']}, {far['km']:,.0f} km ({far['km'] / 1.609344:,.0f} mi) away."
        items.append(("RBN and your contacts", text, "sec-session"))
    if headline:
        items.append(("Band openings", headline, "sec-openings"))
    if result is not None and pd.notna(result["overall"]["stronger_db"]):
        o = result["overall"]
        items.append(("Signal against WSPR stations near you", f"About {o['stronger_db']:+.0f} dB against a typical station, from {o['matches']} matches with "
                                                                f"{o.get('match_rx', o['matches'])} receiving stations.", "sec-signal"))
    return lh.glance_html(items)


def log_page():
    """The page."""
    if BANNER.exists():
        st.image(str(BANNER), width="stretch")
    else:
        st.title("FarField Lab")
    st.markdown('<p class="subtitle">Upload the log of a session and see it beside the skimmers that heard you and the WSPR stations around you.</p>',
                unsafe_allow_html=True)
    guide = st.container()
    skimmers, _ = skimmer_data()
    # The power sits beside the uploader and is set first: the work starts the moment a log is uploaded, so it has to be known by then. A log does not say it.
    power_box, file_box = st.columns([1, 3])
    power = power_box.number_input("Your power (watts)", min_value=1, max_value=1500, value=100, step=5, key="log_power",
                                   help="This page does not read the power from the log, so enter what you ran. Set it before you upload: the calculations start as soon as a log is "
                                        "loaded, and they use it to restate the WSPR stations' signals to your power. Changing it later works, but starts them again.")
    # No file-type filter on purpose: iPhones and iPads do not know .adi, so a filter greys out every log in the picker. A file that is not a log is caught below.
    file = file_box.file_uploader("Your log (ADIF file, .adi or .adif)", key="log_file",
                                  help="Most logging programs can export one. Contacts need a call, date, time and band. A file can be up to 5 MB, "
                                       "which is many thousands of contacts. The log is used for this visit only and is not saved or shared.")
    if file is not None:
        st.session_state["log_saved"] = (file.name, file.getvalue())
    saved = st.session_state.get("log_saved")
    with guide:
        page_guide("log")
    if saved is None:
        st.info(icon=":material/upload_file:", body="Upload an ADIF log to begin. Set your power above first if you ran something other than 100 W: "
                                                           "the calculations start as soon as a log is loaded and use it.")
        preview("log", "What you get: where the skimmers heard you on a band, beside the stations you worked on it. Here, a POTA activation on 20m.")
        return
    name, raw = saved
    if file is None:
        st.caption(f"Showing {name}. Upload another file to replace it.")
    if len(raw) > MAX_LOG_BYTES:
        st.error("That file is larger than 5 MB. Export just the day or two you want to look at.")
        return
    try:
        log = lc.parse_adif(raw.decode("utf-8", errors="replace"))
    except ValueError as exc:
        st.error(str(exc) + ("" if name.lower().endswith((".adi", ".adif")) else f" {name} does not look like an ADIF log (those end in .adi or .adif). Pick the exported log file."))
        return
    digest = hashlib.sha1(raw).hexdigest()
    read_slot = st.container()
    cw = log[log["mode"] == "CW"]
    summary, rep = lc.summary(log), lc.repeat_stations(log)
    call0, grid0 = lc.log_origin(log)

    _mixed_log_warning(log)
    with st.expander("Change the callsign, the place or the nearby radius", expanded=not call0):
        c1, c2, c3 = st.columns(3)
        call = c1.text_input("Your callsign", value=call0, key=f"log_call_{digest[:10]}",
                             help="Taken from the log. RBN spots are looked up under this callsign, exactly as it was sent (K5OHY/P is not K5OHY).").strip().upper()
        grid = c2.text_input("Where you operated (grid square)", value=grid0, key=f"log_grid_{digest[:10]}",
                             help="Taken from the log. Leave it empty to use where your callsign is registered.").strip()
        radius_km = c3.selectbox("Nearby WSPR stations", lf.RADIUS_CHOICES_KM, index=lf.RADIUS_CHOICES_KM.index(lf.DEFAULT_RADIUS_KM),
                                 key="log_radius_km", format_func=lf.radius_text,
                                 help="How far from you a WSPR transmitter counts as near you. The band conditions are worked out from the stations this close, so a smaller "
                                      "circle is more local and has fewer stations behind it. Changing it later works, but starts the calculations again.")
    if not call:
        st.warning("The log does not say which callsign it is for. Type yours above.")
        return
    try:
        lat, lon, label = _where(grid, call, skimmers)
    except RuntimeError as exc:
        st.error(str(exc))
        return
    with read_slot:
        _what_was_read(log, name, call, label)
    home = (lat, lon)
    units, tiles = st.session_state.get("units_in", "mi"), "Street"
    _prefetch_places(log, skimmers, digest)

    tiles_slot = st.empty()
    worked = lc.worked_summary(log)
    summary = dict(summary, states=len(worked["states"]) + len(worked["provinces"]))      # US states and Canadian provinces only, not a foreign station's region codes
    tiles_slot.html(lh.CSS + lh.tiles_html(summary, len(rep)) + lh.worked_tiles_html(worked))
    # The page is laid out in this order whatever order the work finishes in: who followed you, the session chart, the maps, the band
    # conditions, the progress of the RBN download, and last the comparison with RBN and the band conditions page. The log alone is drawn
    # first; the RBN spots are added to the chart, and the maps appear, when the spots have been read.
    glance_slot = st.empty()
    pota_slot, share_slot, followers_slot, worked_slot, highlights_slot, chart_slot, maps_slot, conditions_slot, space_slot, reports_slot, work, compare_slot = (st.container() for _ in range(12))
    home_cont = _home_continent(call)
    maps_hold = maps_slot.empty()
    if not cw.empty:
        maps_hold.caption("The maps appear here when the RBN spots have been read.")
    with followers_slot:
        st.html(lh.CSS + lh.with_id(lh.followers_html(log, summary), "sec-hunters"))
        if len(rep) > lh.LADDER_ROWS:
            rest_k = rep["k"].iloc[lh.LADDER_ROWS:]
            lo_k, hi_k = int(rest_k.min()), int(rest_k.max())
            with st.expander(f"Show the other {len(rest_k)} station{'s' if len(rest_k) != 1 else ''} "
                             f"(worked on {lo_k}{'' if lo_k == hi_k else f' to {hi_k}'} bands)"):
                st.html(lh.CSS + lh.ladder_rest_html(log))
    with worked_slot:
        shown_bands = lc.bands_top_down(log)
        st.html(lh.CSS + lh.worked_html(worked, shown_bands))
        if worked["n_entities"] > lh.ENTITY_ROWS:
            with st.expander(f"Show the other {worked['n_entities'] - lh.ENTITY_ROWS} countries"):
                st.html(lh.CSS + lh.worked_html(worked, shown_bands, rows=worked["n_entities"], first=lh.ENTITY_ROWS))
        still = lh.still_to_work_html(worked)
        if still:
            with st.expander("Still to work: continents, states, provinces and zones"):
                st.html(lh.CSS + still)
    with highlights_slot:
        hl_places = lc.contact_places(log, home)
        hl_first, hl_far, hl_hours = hl.first_by_continent(hl_places, home_cont), hl.farthest_by_band(hl_places), hl.new_by_hour(log)
        hl_html = lh.highlights_html(hl_first, hl_far, hl_hours, hl.highlight_lines(hl_first, hl_far, hl_hours))
        if hl_html:
            st.html(lh.CSS + hl_html)
        rate = hl.rate_chart(log, BAND_COLORS)
        if rate is not None:
            st.markdown("#### How fast the contacts came in")
            st.caption("Above, each bar is ten minutes and is as tall as the contacts you made in them, stacked by band; a triangle marks the first contact on each band. Below, the line is "
                       "the contacts an hour over the hour around each bar, counting only the time you were on the air; a pause of more than 30 minutes breaks it. Hover for the details.")
            st.altair_chart(rate, width="stretch")
            line = hl.rate_line(hl.best_stretch(log))
            if line:
                st.caption(line)
        timing_hold = st.empty()           # when RBN first and last spotted you on each band, added when the spots have been read
    days = sorted({f"{d:%Y%m%d}" for d in log["time"].dt.date})
    no_spots = pd.DataFrame({"spotter": [], "band": [], "snr": [], "time": pd.to_datetime([])})
    chart = chart_slot.empty()
    chart.html(lh.CSS + lh.with_id(lh.afternoon_html(log, no_spots), "sec-session"))
    speed_hold = chart_slot.empty()        # one line on how fast you sent, under the session chart, once the RBN spots have been read
    with pota_slot:         # a POTA log opens with how its park compares; the card is laid out above the rest and filled once the session chart is drawn
        park_cards = _pota_cards(log, call)
    with share_slot:
        with st.expander("Share this session: a picture and a short summary to post"):
            made = st.session_state.get("log_share")
            share_key = (digest, call, round(home[0], 3), round(home[1], 3), bool(park_cards))
            if not made or made["key"] != share_key:       # the picture and the text are made once for a log, not at every redraw
                facts = sc.share_facts(log, summary, worked, call, park_cards, rep, lc.contact_places(log, home), home)
                made = {"key": share_key, "facts": facts, "png": {}}
                st.session_state["log_share"] = made
            facts = made["facts"]
            shape = st.segmented_control("Shape", list(sc.FORMATS), default=sc.DEFAULT_FORMAT, key="log_share_format",
                                         format_func=lambda k: sc.FORMATS[k]["label"],
                                         help="Each shape is drawn for where you will post it, not cropped from another: landscape for X, Facebook and LinkedIn; square or "
                                              "portrait (4:5) for an Instagram or Facebook post; story (9:16) for an Instagram or TikTok story, with the text kept clear of "
                                              "the top and bottom where those apps put their buttons.") or sc.DEFAULT_FORMAT
            spec = sc.FORMATS[shape]
            picture = made["png"].setdefault(shape, sc.share_png(facts, shape))        # each shape is drawn once, the first time it is asked for
            st.image(picture, width="stretch" if shape == sc.DEFAULT_FORMAT else 480)
            pixels = f"{round(spec['size'][0] * sc.DPI)} \u00d7 {round(spec['size'][1] * sc.DPI)}"
            st.caption(f"{spec['label']}, {pixels}: for {spec['where']}.")
            stem = f"{call or 'log'}-session-{shape}".replace("/", "-")
            c1, c2 = st.columns(2)
            c1.download_button("Download PNG", picture, file_name=f"{stem}.png", mime="image/png", icon=":material/download:")
            c2.download_button("Download JPG (smaller)", lambda: sc.share_jpg(facts, shape), file_name=f"{stem}.jpg", mime="image/jpeg", icon=":material/download:",
                               help="The same picture as a JPEG: a smaller file, and what Instagram keeps whichever it is given. Made when you click.")
            st.caption("The summary, ready to copy (the copy button is at the top right of the box):")
            st.code(sc.share_text(facts), language=None)
            st.caption("Nothing here is saved or sent anywhere. The picture and the text are made on this page from your log.")
    glance_slot.html(lh.CSS + _glance(park_cards, rep, None, skimmers, home, "", None))
    mode, zone = lc.condition_mode(log), _visitor_timezone()
    draw_openings = None
    with conditions_slot:
        grid_of_conditions = _conditions(log, home, power, label, digest, radius_km) if len(days) <= MAX_DAYS else None
        if grid_of_conditions is not None and len(grid_of_conditions) > 0:
            draw_openings = _openings_section(grid_of_conditions, log, home, power, mode, zone, radius_km, skimmers, digest, home_cont)
    with reports_slot:      # who hears whom comes from the log alone, so it is drawn at once
        balance = lh.balance_html(lc.reports_balance(log))
        if balance:
            st.html(lh.CSS + balance)
    with space_slot:
        if len(days) <= MAX_DAYS:
            first_t, last_t = lc.space_span(log)
            weather = _space_history(str(first_t), str(last_t))
            weather_html = lh.space_weather_html(weather, log, lc.space_notes(weather, log["time"].min(), log["time"].max()))
            if weather_html:
                st.html(lh.CSS + weather_html)
    with work:
        if cw.empty:
            st.info(icon=":material/info:", body="There are no CW contacts in this log, so there is nothing to set beside the RBN spots. "
                                                 "The facts here come from the log alone.")
        if len(days) > MAX_DAYS and not cw.empty:
            st.warning(f"This log spans {len(days)} days. Each day is a large file to read, so only logs of up to {MAX_DAYS} days are compared. "
                       "Export a shorter stretch.")
            cw = cw.iloc[0:0]
        if cw.empty:
            spots, missing = no_spots, []
        else:
            spots, missing = _rbn_spots(digest, call, days)
    if len(spots):
        chart.html(lh.CSS + lh.with_id(lh.afternoon_html(log, spots), "sec-session"))
        speed = lh.speed_line(log, spots)
        if speed:
            speed_hold.markdown(f":material/speed: {speed}")
    timing = hl.rbn_timing(log, spots)
    if len(timing):
        with timing_hold.container():
            with st.expander("When RBN first and last spotted you on each band, beside your first and last contact"):
                st.caption("Times in UTC. A spot says a skimmer decoded you, a contact says you logged someone: the two are shown side by side, and neither says "
                           "when you were calling or listening.")
                show = timing.assign(**{c: timing[c].dt.strftime("%H:%M:%S") for c in ("first_contact", "last_contact", "first_spot", "last_spot")}).fillna("none")
                st.dataframe(show.rename(columns={"band": "Band", "first_contact": "First contact", "last_contact": "Last contact", "first_spot": "First RBN spot",
                                                  "last_spot": "Last RBN spot", "spots": "Spots"}), hide_index=True, width="stretch", height=min(300, 38 + 35 * len(show)))
    headline = ""
    if draw_openings is not None:   # the skimmers that spotted you are added to the openings, now the spots have been read (or are known to be missing)
        headline = draw_openings(spots, not cw.empty and len(missing) < len(days)) or ""
    glance_slot.html(lh.CSS + _glance(park_cards, rep, spots, skimmers, home, headline, None))
    result = None
    with work:
        if not cw.empty:
            if missing:
                when = lc.rbn_ready_message(missing, _visitor_timezone())
                names = ", ".join(f"{pd.Timestamp(d):%d %b}" for d in missing)
                if len(missing) < len(days):
                    st.caption(f"RBN has no file for {names} yet, so that part of the log is left out of the comparison. {when}")
            loaded = log[~log["time"].dt.strftime("%Y%m%d").isin(missing)]
            if loaded[loaded["mode"] == "CW"].empty:
                st.warning(f"RBN has no file for {names} yet. {when} The facts from the log alone are above.")
            elif spots.empty:
                st.warning(f"RBN has no spots for {call} on {'that day' if len(days) == 1 else 'those days'}. Check the callsign above: it must "
                           "match what you sent (a /P or /M counts). The facts here come from the log alone.")
            else:
                signature = _signature(raw, power, call, grid, spots, radius_km)
                held = st.session_state.get("log_result")
                result = held["result"] if held and held["signature"] == signature else None
                if result is None:
                    result = _run(loaded, spots, skimmers, home, power, label, radius_km)
                    if result is not None:
                        st.session_state["log_result"] = {"signature": signature, "result": result}
    with maps_hold.container():
        _maps_section(log, result, spots, skimmers, home, label, call, tiles, units, digest, lc.spots_link(call, grid, log))
    glance_slot.html(lh.CSS + _glance(park_cards, rep, spots, skimmers, home, headline, result))
    if result is None:
        return
    with compare_slot:
        shown = set(result["bands"].loc[result["bands"]["contacts"] >= 3, "band"])          # the bands that have a bar below
        table = lc.match_table(result["matches"])
        table = table[table["Band"].isin(shown)].reset_index(drop=True)
        st.html(lh.CSS + lh.signal_intro_html(lc.TYPICAL_OFFSET_DB, power, "CW", lh.signal_example(table), cond.MODES))
        st.html(lh.CSS + lh.band_table_html(result["bands"]))
        o = result["overall"]
        notes = [f"Estimated strength against a typical WSPR station near you: {o['stronger_db']:+.0f} dB, from {o['matches']} matches with {o.get('match_rx', o['matches'])} different receiving stations "
                 "(a station heard in two stretches of the log is a match in each; explained below)." if pd.notna(o["stronger_db"]) else None,
                 f"Strength spread between receivers: {o['spread_db']:.1f} dB." if o["matches"] > 2 else None]
        st.caption(" ".join(n for n in notes if n))
        if len(table):
            with st.expander(f"The receiving stations behind these bars ({len(table)})"):
                st.caption("One row for each band and receiving station. A station that was matched in more than one stretch of the log has more than one match.")
                st.dataframe(table, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(table)))
        st.caption(f"With fewer than {lc.MIN_MATCHES} matches a bar is striped, and it is a hint, not a score. "
                   "A log shows who worked you; RBN only shows who a skimmer decoded. "
                   "The S in each band row is the average report they gave you; many operators send a 9 out of habit, so it is a rough picture "
                   "of your station, not a measurement.")
