"""The Log analysis page: upload a contact log (ADIF) and the callsign, place and days come from the log. The RBN spots and the WSPR stations
near you are fetched, and the log is set beside them."""
import hashlib
import threading

import pandas as pd
import streamlit as st

import log_check as lc
import log_check_html as lh
import share_card as sc
import space_weather as sw
from compare_stats import locate as skimmer_location
from data_sources import download_rbn_day, load_contact_places, load_nearby, load_pota_park, load_rbn_listening, load_sota_summit, skimmer_data
from maps import build_map, great_circle, park_map
from rbn_data import lookup_callsign_location, maidenhead_to_latlon
from ui_common import BANNER, KM_PER_MILE, page_guide, preview
from wspr_data import WsprError

RADIUS_KM = 300 * KM_PER_MILE   # the WSPR stations counted as "near you", as on the Band conditions page
MAX_LOG_BYTES = 5_000_000
MAX_DAYS = 4                    # each day is a large file to read, so a log is limited to a few days
MAPS_HEADING = "Maps for CW: where RBN heard you, and who you worked"
HEARD_TITLE, WORKED_TITLE = "Where RBN heard you on {band}", "Stations you worked on {band}"


def _signature(raw, power, call, grid, spots):
    """What a finished comparison was made from, so a new file, power, callsign, place or spots start again."""
    return (hashlib.sha1(raw).hexdigest(), float(power), call, grid, len(spots), str(spots["time"].min()), str(spots["time"].max()))


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


def _what_was_read(log, name):
    """How many contacts were read from the file, and how many records were left out and why."""
    n, seen = len(log), log.attrs.get("records", len(log))
    if seen == n:
        st.caption(f"Read {n} contacts from {name}.")
        return
    why = [f"{k} without a usable {what}" for k, what in ((log.attrs.get("no_time", 0), "date or time"), (log.attrs.get("no_band", 0), "band")) if k]
    st.caption(f"Read {n} of the {seen} records in {name}. {seen - n} left out: {', '.join(why)}.")


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


def _conditions(log, home, power, label, digest):
    """The grid of how open each band looked while you were on the air, kept for this log, power and place. It needs only WSPR, so it works
    on the day of the activation, before RBN has published its file."""
    key = (digest, float(power), round(home[0], 3), round(home[1], 3))
    held = st.session_state.get("log_conditions")
    if held and held["key"] == key:
        return held["grid"]
    with st.status(f"Looking at how open each band was near {label}…", expanded=True) as status:
        try:
            st.write("Fetching the WSPR stations within 300 miles of you for the hours of the activation…")
            grid = lc.conditions_grid(log, lambda a, b: load_nearby(home[0], home[1], RADIUS_KM, a, b), home, power)
        except (WsprError, RuntimeError) as exc:
            status.update(label="Could not work out the band conditions", state="error")
            st.error(str(exc))
            return None
        status.update(label="Band conditions worked out", state="complete", expanded=False)
    st.session_state["log_conditions"] = {"key": key, "grid": grid}
    return grid


def _default_band(bands, regions):
    """The index of the band to open on: the one with the most DX contacts, else the first."""
    dx = regions[~regions["region"].isin(lh.NEAR_REGIONS)].groupby("band")["contacts"].sum()
    return int(bands.index(dx.idxmax())) if len(dx) and dx.max() > 0 and dx.idxmax() in bands else 0


def _regions_section(result):
    """A band by region: pick a band, see each region's contacts, skimmers and the page's figure. It opens on the band with the most DX."""
    shown = result["bands"][result["bands"]["contacts"] >= 3]      # the bands that have a row in the table above
    bands, regions = list(shown["band"]), result["regions"]
    if not bands or regions.empty:
        return
    st.markdown("#### A band by region")
    pick = st.radio("Band", bands, index=_default_band(bands, regions), horizontal=True, key="log_region_band_" + "_".join(bands),
                    label_visibility="collapsed")
    st.html(lh.CSS + lh.regions_html(regions, pick))


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


def _maps_section(log, result, spots, locs, home, label, who, tiles, units, digest):
    """Two maps of one band, side by side and framed alike: the skimmers that spotted you, and the stations you worked. They open on the
    band with the most DX; placing that band's stations takes a few seconds the first time, and each band is only looked up once."""
    st.markdown(f"#### {MAPS_HEADING}")
    st.caption("Skimmers only hear CW, so the maps start with your CW contacts. Where your contacts were is looked up in the background, so each band should be ready when you click it.")
    shown = set(result["bands"]["band"])
    bands = [b for b in lc.bands_top_down(log) if b in shown] or lc.bands_top_down(log)
    first = _default_band(bands, result["regions"])
    c1, c2 = st.columns([3, 2])
    pick = c1.radio("Band", bands, index=first, horizontal=True, key="log_map_band_" + "_".join(bands), label_visibility="collapsed")
    cw_only = c2.checkbox("CW contacts only", value=True, key="log_map_cw",
                          help="Skimmers only hear CW, so the CW contacts are the ones to hold against the left map. Untick to see every contact.")
    mine = log[log["band"] == pick]
    shown_log = mine[mine["mode"] == "CW"] if cw_only else mine
    rows = list(shown_log.drop_duplicates("call")[["call", "state", "country"]].itertuples(index=False, name=None))
    places = _places_for(rows, digest, locs, _log_grids(log))
    worked = lc.where_worked(shown_log, places)
    worked = worked.assign(bands_worked=worked["call"].map(log.groupby("call")["band"].nunique()))
    lo, hi = mine["time"].min() - pd.Timedelta(minutes=10), mine["time"].max() + pd.Timedelta(minutes=10)
    heard = spots[(spots["band"] == pick) & (spots["time"] >= lo) & (spots["time"] <= hi)]
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
    left.caption(f"{heard['spotter'].nunique()} skimmers between {lo:%H:%M}Z and {hi:%H:%M}Z. Dots are coloured and sized by the best SNR."
                 if len(heard) else f"No RBN spots on {pick} while you were working it.")
    right.caption(f"{worked['call'].nunique()} stations" + (f" ({missing} could not be placed)" if missing else "")
                  + ". Colour is the report they gave you, from weak (green) to strong (red), grey where the log has none. "
                    "A black ring marks a station that worked you on more than one band. Click one for the contacts. "
                    "Each is at the centre of its grid square, state or country.")


def log_page():
    """The page."""
    if BANNER.exists():
        st.image(str(BANNER), width="stretch")
    else:
        st.title("FarField Lab")
    st.markdown('<p class="subtitle">Upload the log of a session and see it beside the skimmers that heard you and the WSPR stations '
                'around you. The callsign, the place and the days come from the log.</p>', unsafe_allow_html=True)
    guide = st.container()
    skimmers, _ = skimmer_data()
    # The power comes first: the work starts the moment a log is uploaded, so it has to be known by then. A log does not say it.
    power_box, _ = st.columns([1, 3])
    power = power_box.number_input("Your power (watts)", min_value=1, max_value=1500, value=100, step=5, key="log_power",
                                   help="This page does not read the power from the log, so enter what you ran. Set it before you upload: the calculations start as soon as a log is "
                                        "loaded, and they use it to restate the WSPR stations' signals to your power. Changing it later works, but starts them again.")
    file = st.file_uploader("Your log (ADIF file)", type=["adi", "adif"], key="log_file",
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
        st.error(str(exc))
        return
    digest = hashlib.sha1(raw).hexdigest()
    _what_was_read(log, name)
    st.caption(":material/info: Your contacts, the spots that heard you and the estimated conditions are different things. A band with no reports can just mean nobody was listening.")
    cw = log[log["mode"] == "CW"]
    summary, rep = lc.summary(log), lc.repeat_stations(log)
    call0, grid0 = lc.log_origin(log)

    _mixed_log_warning(log)
    c1, c2 = st.columns(2)
    call = c1.text_input("Your callsign", value=call0, key=f"log_call_{digest[:10]}",
                         help="Taken from the log. RBN spots are looked up under this callsign, exactly as it was sent (K5OHY/P is not K5OHY).").strip().upper()
    grid = c2.text_input("Where you operated (grid square)", value=grid0, key=f"log_grid_{digest[:10]}",
                         help="Taken from the log. Leave it empty to use where your callsign is registered.").strip()
    if not call:
        st.warning("The log does not say which callsign it is for. Type yours above.")
        return
    try:
        lat, lon, label = _where(grid, call, skimmers)
    except RuntimeError as exc:
        st.error(str(exc))
        return
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
    pota_slot, share_slot, followers_slot, worked_slot, chart_slot, maps_slot, conditions_slot, space_slot, reports_slot, work, compare_slot = (st.container() for _ in range(11))
    maps_hold = maps_slot.empty()
    if not cw.empty:
        maps_hold.caption("The maps appear here when the RBN spots have been read.")
    with followers_slot:
        st.html(lh.CSS + lh.followers_html(log, summary))
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
    days = sorted({f"{d:%Y%m%d}" for d in log["time"].dt.date})
    no_spots = pd.DataFrame({"spotter": [], "band": [], "snr": [], "time": pd.to_datetime([])})
    chart = chart_slot.empty()
    chart.html(lh.CSS + lh.afternoon_html(log, no_spots))
    with pota_slot:         # a POTA log opens with how its park compares; the card is laid out above the rest and filled once the session chart is drawn
        park_cards = _pota_cards(log, call)
    with share_slot:
        with st.expander("Share this session: a picture and a short summary to post"):
            facts = sc.share_facts(log, summary, worked, call, park_cards, rep)
            picture = sc.share_png(facts)
            st.image(picture, width="stretch")
            st.download_button("Download the picture (PNG)", picture, file_name=f"{call or 'log'}-session.png".replace("/", "-"), mime="image/png")
            st.caption("The summary, ready to copy (the copy button is at the top right of the box):")
            st.code(sc.share_text(facts), language=None)
            st.caption("Nothing here is saved or sent anywhere. The picture and the text are made on this page from your log.")
    mode, zone = lc.condition_mode(log), _visitor_timezone()
    with conditions_slot:
        grid_of_conditions = _conditions(log, home, power, label, digest) if len(days) <= MAX_DAYS else None
        has_picture = grid_of_conditions is not None and len(grid_of_conditions) > 0
        view = "estimate"
        if has_picture:
            chosen = st.radio("The DX picture", list(lh.DX_VIEWS.values()), horizontal=True, key="log_dx_view", label_visibility="collapsed",
                              help="What WSPR showed: the stations over 3,000 miles away that decoded WSPR transmitters near you, with nothing assumed about your station. "
                                   "Estimate for my station: the ones whose reports, restated to your power, look strong enough to hear you.")
            view = next(k for k, v in lh.DX_VIEWS.items() if v == chosen)
        dx_slot = st.empty()
        if has_picture:
            dx_slot.html(lh.CSS + lh.dx_windows_html(grid_of_conditions, lc.dx_notes(grid_of_conditions, power, view=view), power, mode, zone, view))
            regions_html = lh.dx_regions_html(grid_of_conditions, view)
            if regions_html:
                st.html(lh.CSS + regions_html)
            with st.expander("Another view: the percent of stations that could have heard you"):
                st.html(lh.CSS + lh.conditions_html(grid_of_conditions, lc.conditions_notes(grid_of_conditions), power, mode, zone))
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
        chart.html(lh.CSS + lh.afternoon_html(log, spots))
        if has_picture:     # the skimmers far away that spotted you are added to the DX picture
            with_rbn = lc.add_rbn_far(grid_of_conditions, spots, skimmers, home)
            dx_slot.html(lh.CSS + lh.dx_windows_html(with_rbn, lc.dx_notes(with_rbn, power, view=view), power, mode, zone, view))
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
                signature = _signature(raw, power, call, grid, spots)
                held = st.session_state.get("log_result")
                result = held["result"] if held and held["signature"] == signature else None
                if result is None:
                    result = _run(loaded, spots, skimmers, home, power, label)
                    if result is not None:
                        st.session_state["log_result"] = {"signature": signature, "result": result}
    if result is None:
        maps_hold.empty()
        return
    with maps_hold.container():
        _maps_section(log, result, spots, skimmers, home, label, call, tiles, units, digest)
    with compare_slot:
        st.markdown("#### The comparison with RBN and the band conditions page")
        st.html(lh.CSS + lh.band_table_html(result["bands"]))
        o = result["overall"]
        notes = [f"Page and skimmers: in regions with at least {lc.cond.THIN} WSPR receivers, the page's chance averaged {lh.pct(o['page'])} "
                 f"and {lh.pct(o['spotted'])} of the {o['listening']} skimmers on the band spotted you." if o["listening"] else None,
                 f"Regions with too few WSPR receivers (greyed on the Band conditions page): {o['thin_spotted']} of {o['thin_listening']} "
                 "skimmers on the band spotted you." if o["thin_listening"] else None,
                 f"Estimated strength against a typical WSPR station near you: {o['stronger_db']:+.0f} dB, from {o['matches']} matched receivers "
                 "(explained below)." if pd.notna(o["stronger_db"]) else None,
                 f"Strength spread between receivers: {o['spread_db']:.1f} dB." if o["matches"] > 2 else None]
        st.caption(" ".join(n for n in notes if n))
        _regions_section(result)
        st.caption(f"\"Stronger than a typical WSPR station\" sets the skimmers' reports against the WSPR stations near you, restated to your power. "
                   f"Skimmers and WSPR receivers are different equipment, so an ordinary station reads about {lc.TYPICAL_OFFSET_DB:.0f} dB higher "
                   "on RBN than on the Band conditions page (found from two checks of stations whose power is known), and that is taken off. "
                   f"With fewer than {lc.MIN_MATCHES} matched receivers a bar is striped, and it is a hint, not a score. The percentages "
                   "compare the page's chance for each region with the share of skimmers on the band that spotted you, which is lower, because "
                   "a skimmer has to be tuned to you and decode you. A log shows who worked you; RBN only shows who a skimmer decoded. "
                   "The S in each band row is the average report they gave you; many operators send a 9 out of habit, so it is a rough picture "
                   "of your station, not a measurement.")
