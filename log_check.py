"""Log check: a contact log (ADIF) set beside the Reverse Beacon Network spots and the WSPR picture. Nothing here draws a page or
asks the network; the functions take tables and return tables, so they can be tested with made-up data.

What is compared, band by band, for the stretches of the log where you were on a band:
  * how many contacts you made, and how many different skimmers spotted you in the same time;
  * what the Band conditions page would have said for the regions around the world (its chance of being heard), against the share
    of the skimmers that were listening in those regions and did spot you;
  * how strong the skimmers reported you, against the WSPR stations near you at the same power. Skimmers and WSPR receivers are
    different equipment, so the answer is given as "stronger than a typical station", using the typical offset in
    TYPICAL_OFFSET_DB, which comes from the checks in docs/METHODOLOGY.md. It is a rough hint, not a score.
"""
import io
import re
import zipfile
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import conditions as cond
from rbn_data import get_band, maidenhead_to_latlon
from session_report import BAND_ORDER, region_of

TYPICAL_OFFSET_DB = 10.0   # an ordinary 100 W station reads about this much above the page's figure on RBN (two known-power checks)
MIN_MATCHES = 8            # fewer matched receivers than this and the strength is shown as a hint only
SHOW_MATCHES = 3           # fewer than this and no strength is shown at all
SESSION_GAP_MIN = 30       # a pause this long on a band starts a new stretch
WINDOW_PAD_MIN = 5         # spots this long before the first contact and after the last still belong to the stretch
LOOKBACK_MIN = 60          # the WSPR picture is built from the hour before the middle of the stretch
GAP_BAD, ACTUAL_LOW = 0.30, 0.30   # "worked but barely spotted": the page's chance is this much above the share spotted, which is low
NOTE_MIN_CONTACTS = 3       # a band with fewer CW contacts than this gets no note: two contacts say nothing (and it has no row in the table)
AGREE = 0.10               # the page's chance and the share spotted are within this of each other: close

_FIELD = re.compile(r"<([A-Za-z0-9_]+):(\d+)(?::[A-Za-z0-9_]+)?>")


def _base(call):
    return str(call).split("-")[0].upper()


def _rank(band):
    return BAND_ORDER.index(band) if band in BAND_ORDER else len(BAND_ORDER)


# ----------------------------------------------------------------------------------------------------- reading the log

def _fields(record):
    """The fields of one ADIF record. A value is as long as its length says, so '<' inside a value is not a problem."""
    out, pos = {}, 0
    while True:
        m = _FIELD.search(record, pos)
        if not m:
            return out
        n = int(m.group(2))
        out[m.group(1).upper()] = record[m.end():m.end() + n].strip()
        pos = m.end() + n


def _when(date, time):
    """A naive UTC timestamp from ADIF's YYYYMMDD and HHMM or HHMMSS, or None."""
    time = (time + "000000")[:6] if len(time) in (4, 6) else None
    try:
        return pd.Timestamp(f"{date[:4]}-{date[4:6]}-{date[6:8]} {time[:2]}:{time[2:4]}:{time[4:6]}") if time and len(date) == 8 else None
    except ValueError:
        return None


def parse_adif(text):
    """The contacts in an ADIF file as a table: call, time (UTC), band, mode, state, country, cont, pota_ref, and the reports
    (rst_sent: what you gave them, rst_rcvd: what they gave you). Raises ValueError
    when there are no contacts in it. Contacts without a call, a date, a time or a band are left out; log.attrs says how many records the
    file had (records) and how many were left out for want of a usable date or time (no_time) or band (no_band)."""
    parts = re.split(r"<eoh>", text, maxsplit=1, flags=re.IGNORECASE)
    body = parts[1] if len(parts) == 2 else text
    rows, seen, no_time, no_band = [], 0, 0, 0
    for record in re.split(r"<eor>", body, flags=re.IGNORECASE):
        f = _fields(record)
        if "CALL" not in f:
            continue
        seen += 1
        when = _when(f.get("QSO_DATE", ""), f.get("TIME_ON", ""))
        if when is None:
            no_time += 1
            continue
        band = f.get("BAND", "").lower()
        if band not in BAND_ORDER:
            try:
                band = get_band(float(f["FREQ"]) * 1000)   # ADIF gives the frequency in MHz, get_band wants kHz
            except (KeyError, ValueError):
                band = "unknown"
        if band == "unknown":
            no_band += 1
            continue
        mode = f.get("MODE", "").upper()
        if mode == "MFSK" and f.get("SUBMODE"):
            mode = f["SUBMODE"].upper()
        rows.append({"call": f["CALL"].upper(), "time": when, "band": band, "mode": mode, "state": f.get("STATE", "").upper(),
                     "country": f.get("COUNTRY", ""), "cont": f.get("CONT", "").upper(), "pota_ref": f.get("POTA_REF", ""),
                     "rst_sent": f.get("RST_SENT", ""), "rst_rcvd": f.get("RST_RCVD", ""),
                     "station": (f.get("STATION_CALLSIGN") or f.get("OPERATOR") or "").upper(), "my_grid": f.get("MY_GRIDSQUARE", "")})
    if not rows:
        raise ValueError("No contacts with a call, a date, a time and a band were found in that file.")
    log = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
    log.attrs.update(records=seen, no_time=no_time, no_band=no_band)    # how many records the file had and how many were left out
    return log


RBN_FILE_DELAY_MIN = 2     # RBN builds a UTC day's history file at 00:02 UTC the next day (seen on the files of 16 to 19 Nov 2026)


def rbn_ready_message(days, tz_name=None):
    """Why a day of the log has no RBN file yet and when it will have one, in a sentence. `days` are YYYYMMDD strings (the latest one decides
    the time); `tz_name` is the visitor's time zone (such as America/Chicago), used to say the time where they are as well as in UTC."""
    last = pd.Timestamp(max(days))
    ready = last + pd.Timedelta(days=1, minutes=RBN_FILE_DELAY_MIN)
    when = f"{ready:%H:%M} UTC on {ready:%d %b}"
    try:
        local = ready.tz_localize(timezone.utc).astimezone(ZoneInfo(tz_name)) if tz_name else None
    except Exception:   # an unknown zone name: say it in UTC only
        local = None
    here = f" ({local:%a %d %b, %I:%M %p}".replace(" 0", " ") + f" {local:%Z})" if local is not None else ""
    return (f"RBN makes each UTC day's file just after the day ends, so {last:%d %b} will be ready after {when}{here}. "
            "Come back then, and this log will be compared.")


def origin_counts(log, column):
    """The different values of a log column (station for callsigns, my_grid for grid squares) with the contacts made under each, most
    first. Grids are compared by their first four characters, because two squares of one park are the same place."""
    if column not in log:
        return []
    values = log[column][log[column] != ""]
    if column == "my_grid":
        values = values.str[:4].str.upper()
    return [(str(v), int(n)) for v, n in values.value_counts().items()]


def log_origin(log):
    """(callsign, grid) the log says it was made with: the most common station callsign and the most common grid square of the operator,
    or an empty string for either when the log does not carry it (some logging programs leave them out)."""
    def common(column):
        values = log[column][log[column] != ""] if column in log else []
        return str(values.mode().iloc[0]) if len(values) else ""
    return common("station"), common("my_grid")


# ------------------------------------------------------------------------------------------------- facts from the log alone

def best_hour(times):
    """(contacts, start) for the busiest stretch of 60 minutes that starts at a contact."""
    t = np.sort(pd.to_datetime(times).to_numpy().astype("datetime64[ns]").astype("int64"))
    ends = np.searchsorted(t, t + 3600 * 10 ** 9, side="left")
    i = int(np.argmax(ends - np.arange(len(t))))
    return int(ends[i] - i), pd.Timestamp(t[i])


def summary(log):
    """The headline numbers of a log."""
    t = log["time"].sort_values()
    gaps = t.diff().dropna().dt.total_seconds()
    on_air = gaps[gaps <= SESSION_GAP_MIN * 60]       # the pauses of more than half an hour are time off the air, not slow operating
    per_hour = len(on_air) / (on_air.sum() / 3600) if on_air.sum() > 0 else float("nan")
    n_best, start_best = best_hour(t)
    states = log.loc[log["state"] != "", "state"].nunique()
    return {"contacts": len(log), "stations": int(log["call"].nunique()), "states": int(states),
            "countries": int(log.loc[log["country"] != "", "country"].nunique()), "first": t.iloc[0], "last": t.iloc[-1],
            "per_hour": per_hour, "on_air_hours": float(on_air.sum() / 3600), "median_gap_s": float(gaps.median()) if len(gaps) else float("nan"),
            "longest_gap_min": float(gaps.max() / 60) if len(gaps) else float("nan"), "best_hour": n_best, "best_hour_start": start_best,
            "park_to_park": int(log["pota_ref"].ne("").sum()), "parks": int(log.loc[log["pota_ref"] != "", "pota_ref"].nunique())}


def band_rates(log):
    """One row per band: contacts, first and last contact, and contacts per hour while on the band."""
    g = log.groupby("band")["time"].agg(contacts="size", first="min", last="max")
    minutes = (g["last"] - g["first"]).dt.total_seconds() / 60
    g["per_hour"] = np.where(minutes >= 5, g["contacts"] / minutes.clip(lower=1) * 60, np.nan)
    return g.loc[sorted(g.index, key=_rank)]


def repeat_stations(log):
    """Stations worked on more than one band: call, the bands (in band order), contacts. Most contacts and bands first."""
    bands = log.groupby("call")["band"].agg(lambda s: sorted(set(s), key=_rank))
    rep = pd.DataFrame({"bands": bands, "contacts": log.groupby("call").size()}).sort_index()
    rep["k"] = rep["bands"].map(len)
    return rep[rep["k"] > 1].sort_values(["k", "contacts"], ascending=False, kind="stable")      # ties stay in callsign order


def same_band_repeats(log):
    """How many stations were worked more than once on the same band."""
    return int((log.groupby(["call", "band"]).size() > 1).sum())


def stretches(log, gap_min=SESSION_GAP_MIN):
    """The stretches of the log on each band: a list of (band, first contact, last contact, contacts), in time order. A pause of
    more than gap_min minutes on a band starts a new stretch."""
    out = []
    for band, g in log.groupby("band"):
        t = g["time"].sort_values()
        new = (t.diff() > pd.Timedelta(minutes=gap_min)).cumsum()
        for _, part in t.groupby(new):
            out.append((band, part.iloc[0], part.iloc[-1], len(part)))
    return sorted(out, key=lambda s: s[1])


def bands_top_down(log):
    """The bands of a log from the highest frequency down, so 10m comes first and 40m after it."""
    return sorted(log["band"].unique(), key=_rank, reverse=True)


# ------------------------------------------------------------------------------------------------------------ signal reports

def s_digit(rst):
    """The S (strength) digit of a report: 579 gives 7 and 59 gives 9. A digital report in dB, or anything else, gives nan."""
    r = str(rst).strip()
    if r.isdigit() and len(r) in (2, 3) and r[0] in "12345" and r[1] != "0":
        return float(r[1])
    return float("nan")


def report_summary(log):
    """What the reports in a log say: the average S they gave you and you gave them, how many carried a usable report, and how many
    were S9. Operators often give a 9 out of habit, so this is a rough picture of the station, not a measurement."""
    got, gave = log["rst_rcvd"].map(s_digit), log["rst_sent"].map(s_digit)
    return {"received": float(got.mean()) if got.notna().any() else float("nan"),
            "sent": float(gave.mean()) if gave.notna().any() else float("nan"),
            "n": int(got.notna().sum()), "s9": int((got == 9).sum()), "weakest": float(got.min()) if got.notna().any() else float("nan")}


# ------------------------------------------------------------------------------------------------------- where the contacts were

# Rough centres of the states and provinces, used only for a contact the lookups could not place.
STATE_CENTRES = {
    "AL": (32.8, -86.8), "AK": (64.0, -152.0), "AZ": (34.3, -111.7), "AR": (34.9, -92.4), "CA": (37.2, -119.4), "CO": (39.0, -105.5),
    "CT": (41.6, -72.7), "DE": (39.0, -75.5), "DC": (38.9, -77.0), "FL": (28.6, -82.4), "GA": (32.7, -83.4), "HI": (20.8, -156.3),
    "ID": (44.4, -114.6), "IL": (40.0, -89.2), "IN": (39.9, -86.3), "IA": (42.1, -93.5), "KS": (38.5, -98.4), "KY": (37.5, -85.3),
    "LA": (31.0, -92.0), "ME": (45.3, -69.2), "MD": (39.0, -76.8), "MA": (42.3, -71.8), "MI": (44.3, -85.4), "MN": (46.3, -94.3),
    "MS": (32.7, -89.7), "MO": (38.4, -92.5), "MT": (47.0, -109.6), "NE": (41.5, -99.8), "NV": (39.3, -116.6), "NH": (43.7, -71.6),
    "NJ": (40.1, -74.7), "NM": (34.4, -106.1), "NY": (42.9, -75.5), "NC": (35.5, -79.4), "ND": (47.5, -100.5), "OH": (40.3, -82.8),
    "OK": (35.6, -97.5), "OR": (44.0, -120.5), "PA": (40.9, -77.8), "RI": (41.7, -71.5), "SC": (33.9, -80.9), "SD": (44.4, -100.2),
    "TN": (35.9, -86.4), "TX": (31.5, -99.3), "UT": (39.3, -111.7), "VT": (44.0, -72.7), "VA": (37.5, -78.8), "WA": (47.4, -120.5),
    "WV": (38.6, -80.6), "WI": (44.6, -89.9), "WY": (43.0, -107.5), "PR": (18.2, -66.5),
    "ON": (50.0, -85.0), "QC": (52.0, -71.0), "BC": (54.0, -125.0), "AB": (55.0, -115.0), "SK": (54.0, -106.0), "MB": (54.5, -98.0),
    "NS": (45.0, -63.0), "NB": (46.5, -66.0), "NL": (53.0, -60.0), "PE": (46.4, -63.3), "YT": (64.0, -135.0), "NT": (64.0, -120.0),
    "NU": (70.0, -90.0)}
_NORTH_AMERICA = ("", "United States", "Canada", "USA", "Hawaii", "Alaska", "Puerto Rico")


def snap_to_grid4(lat, lon):
    """The centre of the 4 character grid square (about 100 by 70 miles) a point is in. Other people's home positions are shown no
    more exactly than this."""
    from conditions import latlon_to_maidenhead
    grid = latlon_to_maidenhead(lat, lon)[:4]
    return (*maidenhead_to_latlon(grid), grid)


def finish_place(found, state="", country=""):
    """Turns a lookup result (lat, lon, grid, source) into where to show a contact: {'lat', 'lon', 'source', 'level'} or None.
    level is 'grid' (the centre of its 4 character grid square, from an exact lookup), 'state' (the state's centre, used when the
    lookup could only name the country) or 'country' (the centre of the country)."""
    approximate = found is not None and str(found[3]).startswith("center of")
    if found is not None and not approximate:
        lat, lon, grid = snap_to_grid4(found[0], found[1])
        return {"lat": lat, "lon": lon, "source": str(found[3]).split(" (")[0], "level": "grid", "grid": grid}
    if state.upper() in STATE_CENTRES and country in _NORTH_AMERICA:
        lat, lon = STATE_CENTRES[state.upper()]
        return {"lat": lat, "lon": lon, "source": f"centre of {state.upper()}", "level": "state", "grid": ""}
    if found is not None:
        return {"lat": found[0], "lon": found[1], "source": str(found[3]).split(" (")[0], "level": "country", "grid": ""}
    return None


def place_note(level, source):
    """How a contact's place was found, in words for the map popup."""
    return {"grid": f"centre of its grid square ({source})", "state": f"centre of the state ({source})",
            "country": f"centre of the country ({source})"}.get(level, source)


def where_worked(log, places):
    """The log's contacts with a position, as a table: the contact's columns plus lat, lon, level, place and s (the S digit they
    gave you). `places` is a table indexed by call with lat, lon, level and source."""
    j = log.merge(places[["lat", "lon", "level", "source"]], left_on="call", right_index=True, how="inner")
    j["place"] = [place_note(lv, src) for lv, src in zip(j["level"], j["source"])]
    j["s"] = j["rst_rcvd"].map(s_digit)
    return j.reset_index(drop=True)


def region_table(worked, spots, locs):
    """Where contacts were and where skimmers were, region by region: contacts, stations worked and skimmers that spotted you."""
    from session_report import REGION_ORDER
    region = {}
    for call, place in locs.items():
        region.setdefault(_base(call), region_of(_base(call), place))
    c = worked.assign(region=[region_of(call, (la, lo)) for call, la, lo in zip(worked["call"], worked["lat"], worked["lon"])])
    k = spots.assign(region=spots["spotter"].map(lambda x: region.get(_base(x)))).dropna(subset=["region"])
    out = pd.DataFrame({"contacts": c.groupby("region").size(), "stations": c.groupby("region")["call"].nunique(),
                        "skimmers": k.groupby("region")["spotter"].apply(lambda x: x.map(_base).nunique())}).fillna(0).astype(int)
    return out.loc[[r for r in REGION_ORDER if r in out.index]]


DX_FIRST = ["Europe", "Africa", "Asia", "Oceania", "South America", "Mexico, Caribbean & Central America", "Canada", "US West", "US Central",
            "US East", "Other"]
NEAR_REGIONS = ("Canada", "US West", "US Central", "US East", "Other")   # anything else is DX for this table


def contact_region(call, state=""):
    """The region a contact is in: where in the US (from its state), Canada, or the country group the callsign belongs to."""
    return region_of(call, STATE_CENTRES.get(str(state).upper()))


# ------------------------------------------------------------------------------------------- the skimmers that were listening

def listening_from_zip(raw, start, end):
    """Every skimmer that spotted anyone between two times, as a table (band, slot of 15 minutes, base callsign). A skimmer that
    spotted somebody in a slot was on the air and listening on that band then, whether or not it heard you."""
    seen = set()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = next((n for n in z.namelist() if n.endswith(".csv")), None)
        if name is None:
            raise RuntimeError("No CSV file found in the RBN ZIP archive")
        with z.open(name) as f:
            for chunk in pd.read_csv(f, chunksize=500_000, usecols=["callsign", "band", "date"]):
                chunk = chunk.dropna()
                when = pd.to_datetime(chunk["date"])
                keep = (when >= start) & (when <= end)
                chunk, when = chunk[keep], when[keep]
                seen.update(zip(chunk["band"], when.dt.floor("15min"), chunk["callsign"].map(_base)))
    return pd.DataFrame(list(seen), columns=["band", "slot", "b"])


# ------------------------------------------------------------------------------------------------------------- the comparison

def _agg(cells):
    """Pooled page chance and share spotted over a table of (band, region) cells."""
    listening = cells["listening"].sum()
    if not len(cells) or listening == 0:
        return float("nan"), float("nan"), 0
    return float(np.average(cells["chance"], weights=cells["listening"])), float(cells["spotted"].sum() / listening), int(listening)


def _note(contacts, page, actual):
    """A short label for a band, or '' and a tone."""
    if np.isnan(page) or np.isnan(actual) or contacts < NOTE_MIN_CONTACTS:
        return "", "neutral"
    if actual <= ACTUAL_LOW and page - actual >= GAP_BAD:
        return "Worked, barely spotted", "warn"
    if abs(page - actual) <= AGREE:
        return "Page and skimmers close", "good"
    return "", "neutral"


def compare(log, spots, wspr_for, listening, locs, home, power_w, mode="CW", antenna_db=0.0):
    """Sets the log beside the spots and the WSPR picture, band by band.

    log        the contacts (parse_adif); only those in `mode` are compared, since RBN hears CW (and RTTY), but the others are counted
    spots      your spots from RBN: spotter, band, snr, time
    wspr_for   function(start, end) -> the WSPR spots of the stations near you in that time (conditions.fetch_nearby's table)
    listening  the skimmers that were listening (listening_from_zip), or None
    locs       the skimmer locations {callsign: (lat, lon)}
    Returns {'bands': table with one row per band, highest band first, 'regions': a table with one row per band and region, 'overall':
    dict, 'matches': the receivers matched for strength, 'cells': the band and region cells for each stretch}."""
    own = log[log["mode"] == mode]
    region_of_base = {}
    for call, place in locs.items():
        region_of_base.setdefault(_base(call), region_of(_base(call), place))
    spots = spots.assign(b=spots["spotter"].map(_base))
    spots = spots.assign(region=spots["b"].map(region_of_base))
    listening = None if listening is None or listening.empty else listening.assign(region=listening["b"].map(region_of_base)).dropna(subset=["region"])
    cells, matches, spotted_by_band, no_picture = [], [], {}, set()
    on_sets, spot_sets = {}, {}     # the distinct skimmers on the band, and that spotted you, for each band and region
    for band, first, last, _ in stretches(own):
        t0, t1 = first - pd.Timedelta(minutes=WINDOW_PAD_MIN), last + pd.Timedelta(minutes=WINDOW_PAD_MIN)
        g = spots[(spots["band"] == band) & (spots["time"] >= t0) & (spots["time"] <= t1)]
        spotted_by_band.setdefault(band, set()).update(g["b"])
        mid = t0 + (t1 - t0) / 2
        wspr = wspr_for(mid - timedelta(minutes=LOOKBACK_MIN), mid)
        res = cond.analyze(wspr, home, power_w, mode, mid.to_pydatetime(), LOOKBACK_MIN, antenna_db, 3.0) if len(wspr) else None
        if res is None or res["bands"].empty or band not in res["bands"].index:
            no_picture.add(band)
            continue
        rec = res["receivers"][res["receivers"]["band"] == band].copy()
        rec["b"] = rec["rx"].map(_base)
        seen = g.groupby("b")["snr"].median().rename("obs")
        j = rec.merge(seen, left_on="b", right_index=True)
        j["band"] = band
        matches.append(j[["band", "rx", "adj", "obs"]])
        if listening is None:
            continue
        lst = listening[(listening["band"] == band) & (listening["slot"] >= t0.floor("15min") - pd.Timedelta(minutes=15))
                        & (listening["slot"] <= t1.floor("15min"))]
        for region, grp in lst.groupby("region"):
            on_sets.setdefault((band, region), set()).update(grp["b"])
        for region, grp in g.groupby("region"):
            spot_sets.setdefault((band, region), set()).update(grp["b"])
        n_listen, n_spot = lst.groupby("region")["b"].nunique(), g.groupby("region")["b"].nunique()
        for region in n_listen.index:
            chance, n_rx = res["chance"].loc[band].get(region, np.nan), int(res["regions_n"].loc[band].get(region, 0))
            nl = int(n_listen[region])
            cells.append({"band": band, "region": region, "chance": chance, "wspr_receivers": n_rx, "listening": nl,
                          "spotted": min(int(n_spot.get(region, 0)), nl)})
    cells = pd.DataFrame(cells, columns=["band", "region", "chance", "wspr_receivers", "listening", "spotted"])
    solid = cells[(cells["wspr_receivers"] >= cond.THIN) & cells["chance"].notna()]
    match = pd.concat(matches, ignore_index=True) if matches else pd.DataFrame(columns=["band", "rx", "adj", "obs"])
    match["diff"] = match["obs"] - match["adj"]
    counts, all_counts = own.groupby("band").size(), log.groupby("band").size()
    rows = []
    for band in bands_top_down(log):
        n_cw = int(counts.get(band, 0))
        page, actual, n_listen = _agg(solid[solid["band"] == band])
        m = match[match["band"] == band]["diff"]
        offset = float(m.median()) - TYPICAL_OFFSET_DB if len(m) >= SHOW_MATCHES else float("nan")
        note, tone = _note(n_cw, page, actual)
        got = own.loc[own["band"] == band, "rst_rcvd"].map(s_digit)
        rows.append({"band": band, "contacts": n_cw, "other": int(all_counts[band]) - n_cw, "skimmers": len(spotted_by_band.get(band, ())),
                     "report": float(got.mean()) if got.notna().any() else float("nan"),
                     "page": page, "spotted": actual, "listening": n_listen, "stronger_db": offset, "matches": len(m),
                     "thin": 0 < len(m) < MIN_MATCHES, "note": note, "tone": tone, "no_picture": band in no_picture})
    bands = pd.DataFrame(rows)
    page, actual, n_listen = _agg(solid)
    offset = float(match["diff"].median()) - TYPICAL_OFFSET_DB if len(match) >= SHOW_MATCHES else float("nan")
    thin_cells = cells[~cells.index.isin(solid.index)]
    thin_listen = int(thin_cells["listening"].sum())
    overall = {"page": page, "spotted": actual, "listening": n_listen, "stronger_db": offset, "matches": len(match),
               "spread_db": float(match["diff"].std()) if len(match) > 2 else float("nan"),
               "thin_listening": thin_listen, "thin_spotted": int(thin_cells["spotted"].sum()),
               "typical_offset_db": TYPICAL_OFFSET_DB}
    return {"bands": bands, "regions": _regions(log, mode, cells, solid, on_sets, spot_sets), "overall": overall, "matches": match, "cells": cells}


def _regions(log, mode, cells, solid, on_sets, spot_sets):
    """One row per band and region: the contacts (all modes, and how many were in `mode`), the distinct stations worked, the distinct
    skimmers on the band and how many of them spotted you, how many WSPR receivers the page's figure rests on (at most, in any stretch)
    and the page's chance (nan when no stretch had enough receivers). DX regions come first."""
    c = log.assign(region=[contact_region(call, state) for call, state in zip(log["call"], log["state"])])
    contacts = c.groupby(["band", "region"]).agg(contacts=("call", "size"), stations=("call", "nunique"))
    cw = c[c["mode"] == mode].groupby(["band", "region"]).size()
    wspr = cells.groupby(["band", "region"])["wspr_receivers"].max() if len(cells) else pd.Series(dtype=float)
    page = {}
    for key, d in solid.groupby(["band", "region"]):
        page[key] = float(np.average(d["chance"], weights=d["listening"])) if d["listening"].sum() else float("nan")
    order = {r: i for i, r in enumerate(DX_FIRST)}
    rows = []
    for band, region in sorted(set(contacts.index) | set(on_sets), key=lambda k: (-_rank(k[0]), order.get(k[1], len(order)))):
        key = (band, region)
        on = len(on_sets.get(key, ()))
        rows.append({"band": band, "region": region, "contacts": int(contacts["contacts"].get(key, 0)), "cw": int(cw.get(key, 0)),
                     "stations": int(contacts["stations"].get(key, 0)), "on_band": on, "spotted": min(len(spot_sets.get(key, ())), on),
                     "wspr_receivers": int(wspr.get(key, 0)), "page": page.get(key, float("nan"))})
    return pd.DataFrame(rows, columns=["band", "region", "contacts", "cw", "stations", "on_band", "spotted", "wspr_receivers", "page"])
