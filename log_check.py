"""Log analysis: a contact log (ADIF) set beside the Reverse Beacon Network spots and the WSPR picture. Nothing here draws a page or
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
from geographiclib.geodesic import Geodesic

import conditions as cond
from compare_stats import locate as locate_skimmer
from rbn_data import country_continent, country_location, get_band, maidenhead_to_latlon
from session_report import BAND_ORDER, region_of
import log_foundations as lf

TYPICAL_OFFSET_DB = 10.0   # an ordinary 100 W station reads about this much above the page's figure on RBN (two known-power checks)
MIN_MATCHES = 8            # fewer matched skimmers than this and the strength is shown as a hint only
SHOW_MATCHES = 3           # fewer than this and no strength is shown at all
SPLIT_KM = 1500            # the strength of a band is also given for the skimmers nearer than this and for the ones farther, when each group has SPLIT_MIN of them
SPLIT_MIN = 2
HIGH_DB = 15               # a band that reads this far above the WSPR reference gets a note: more likely a better antenna than the stations on WSPR near you than a mistake in the data
SESSION_GAP_MIN = 30       # a pause this long on a band starts a new stretch
WINDOW_PAD_MIN = 5         # spots this long before the first contact and after the last still belong to the stretch
LOOKBACK_MIN = lf.WSPR_LOOKBACK_MIN   # the WSPR picture is built from the hour before the middle of the stretch
GAP_BAD, ACTUAL_LOW = 0.30, 0.30   # "worked but barely spotted": the page's chance is this much above the share spotted, which is low
NOTE_MIN_CONTACTS = 3       # a band with fewer CW contacts than this gets no note: two contacts say nothing (and it has no row in the table)
AGREE = 0.10               # the page's chance and the share spotted are within this of each other: close

_FIELD = re.compile(r"<([A-Za-z0-9_]+):(\d+)(?::[A-Za-z0-9_]+)?>")


def _base(call):
    return str(call).split("-")[0].upper()


def _rank(band):
    return BAND_ORDER.index(band) if band in BAND_ORDER else len(BAND_ORDER)


# ----------------------------------------------------------------------------------------------------- reading the log

def adif_coordinate(text):
    """A latitude or longitude from an ADIF LAT or LON field as signed decimal degrees, or None. ADIF writes 'N031 28.750' or 'W100 29.250' (a hemisphere letter, whole degrees,
    decimal minutes); a plain decimal such as '31.4792' or '-100.4875', which some programs write, is accepted too. Anything out of range is None."""
    t = str(text).strip().upper()
    m = re.match(r"^([NSEW])\s*(\d{1,3})\s+(\d{1,2}(?:\.\d+)?)$", t)
    if m:
        value = int(m.group(2)) + float(m.group(3)) / 60.0
        value = -value if m.group(1) in "SW" else value
        limit = 90 if m.group(1) in "NS" else 180
        return value if abs(value) <= limit and float(m.group(3)) < 60 else None
    try:
        value = float(t)
    except ValueError:
        return None
    return value if abs(value) <= 180 else None


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
                     "my_sota": (f.get("MY_SOTA_REF") or (f.get("MY_SIG_INFO", "") if f.get("MY_SIG", "").upper() == "SOTA" else "")).upper(),
                     "sota_ref": f.get("SOTA_REF", "").strip().upper(), "their_grid": f.get("GRIDSQUARE", "").strip().upper(),
                     "their_lat": adif_coordinate(f.get("LAT", "")), "their_lon": adif_coordinate(f.get("LON", "")),
                     "dxcc": f.get("DXCC", "").strip(), "cqz": f.get("CQZ", "").strip(), "ituz": f.get("ITUZ", "").strip(),
                     "my_pota": (f.get("MY_POTA_REF") or (f.get("MY_SIG_INFO", "") if f.get("MY_SIG", "").upper() == "POTA" else "")).upper(),
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
            **_park_counts(log),
            "summit_to_summit": int((_summits_of(log) != "").sum()), "summits": int(_summits_of(log).replace("", pd.NA).dropna().nunique()),
            "bands": bands_top_down(log)}


def _park_counts(log):
    """The park-to-park figures of the summary, counted the way the park map counts them: `park_to_park` is the contacts whose record names a park of the other station that
    is not one of the parks the log was made from, `parks` is how many different such parks (a two-fer names two), and `park_same` is the contacts that named the park the log
    was made from, which are not park to park and are not on the map."""
    if "pota_ref" not in log or not len(log):
        return {"park_to_park": 0, "parks": 0, "park_same": 0}
    own = set(pota_refs(log))
    others, contacts, same = set(), 0, 0
    for cell in log["pota_ref"]:
        refs = {r for r in _cell_refs(cell, "POTA") if POTA_REF.match(r)}
        if refs & own:
            same += 1
        far = refs - own
        if far:
            contacts += 1
            others |= far
    return {"park_to_park": contacts, "parks": len(others), "park_same": same}


def spots_link(call, grid, log, pad_min=10):
    """The web address of the My spots page opened on this session: your callsign, RBN as the source, the day (or days) of the log, the grid square when there is one
    and, for a log made on one UTC day, the UTC time window from `pad_min` minutes before the first contact to `pad_min` minutes after the last. `go=1` loads the spots at
    once. It is relative to the page it is shown on (./?...: My spots is the app's main page, so it has no path of its own), so it works on whichever site serves the app."""
    from urllib.parse import urlencode
    first, last = pd.Timestamp(log["time"].min()), pd.Timestamp(log["time"].max())
    q = {"call": call, "src": "rbn"}
    if grid:
        q["grid"] = grid
    d0, d1 = first.date(), last.date()
    q["date"] = f"{d0:%Y-%m-%d}" + (f"..{d1:%Y-%m-%d}" if d1 != d0 else "")
    if d0 == d1:
        pad = pd.Timedelta(minutes=pad_min)
        lo, hi = max(first - pad, first.normalize()), min(last + pad, first.normalize() + pd.Timedelta(hours=23, minutes=59))
        q["t0"], q["t1"] = f"{lo:%H:%M}", f"{hi:%H:%M}"
    q["go"] = "1"
    return "./?" + urlencode(q)


REACH_COLUMNS = ["rx", "lat", "lon", "km", "windows"]


def reach_points(grid, home, band, metric="good", slots=None, min_km=0.0):
    """Where the WSPR receivers that decoded the stations near you on `band` were, for a heat map of where the signal reached. One row for each receiving station:
    its place (found again from the distance and bearing the grid keeps, which came from its own position), its distance and `windows`, the number of half hours of the
    session in which it decoded WSPR near you (the heat). `metric` is 'heard' (it decoded WSPR near you) or 'good' (it also looked strong enough for your power);
    `slots` limits it to those half hours; `min_km` leaves out the receivers nearer than that."""
    rec = grid.attrs.get("receivers") if grid is not None else None
    if rec is None or len(rec) == 0:
        return pd.DataFrame(columns=REACH_COLUMNS)
    r = rec[rec["band"] == band]
    if metric == "good":
        r = r[r["verdict"] == "good"]
    if slots is not None:
        r = r[r["slot"].isin(set(pd.Timestamp(s) for s in slots))]
    r = r[r["km"] >= min_km]
    if r.empty:
        return pd.DataFrame(columns=REACH_COLUMNS)
    g = r.groupby("rx").agg(km=("km", "median"), bearing=("bearing", "first"), windows=("slot", "nunique")).reset_index()
    places = [Geodesic.WGS84.Direct(float(home[0]), float(home[1]), float(b), float(k) * 1000) for k, b in zip(g["km"], g["bearing"])]
    g["lat"], g["lon"] = [p["lat2"] for p in places], [p["lon2"] for p in places]
    return g[REACH_COLUMNS]


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


BALANCE_MIN = 10             # contacts with a report both ways needed before a band says anything about who hears whom
BALANCE_EQUAL_DB = 3.0       # within this many dB (half an S-unit) the two directions are called about equal
HABIT_SHARE = 0.9            # when this share of the reports were S9 both ways, they are habit and say little
DB_PER_S = 6.0               # one S-unit is 6 dB


def _balance_row(x, name):
    got, gave = x["got"], x["gave"]
    diff = float((got - gave).mean() * DB_PER_S)
    habit = float(((got == 9) & (gave == 9)).mean())
    if len(x) < BALANCE_MIN:
        reading = "too few reports to say"
    elif habit >= HABIT_SHARE:
        reading = "mostly S9 both ways, so this says little"
    elif abs(diff) < BALANCE_EQUAL_DB:
        reading = "about equal"
    else:
        reading = "they hear you stronger than you hear them" if diff > 0 else "you hear them stronger than they hear you"
    return {"band": name, "n": len(x), "got": float(got.mean()), "gave": float(gave.mean()), "diff_db": diff, "habit": habit, "reading": reading}


def reports_balance(log):
    """Who hears whom, from the reports in the log: for each band (and 'All bands' first), the contacts that carry an S report both ways, the
    average S they gave you (`got`) and you gave them (`gave`), the difference in dB (positive: they hear you stronger) and a plain reading.
    A band with fewer than BALANCE_MIN such contacts is not read, and neither is one whose reports are nearly all S9 both ways, because
    many operators send a 9 out of habit. Digital dB reports are left out. A difference can come from their station as easily as yours."""
    d = log.assign(got=log["rst_rcvd"].map(s_digit), gave=log["rst_sent"].map(s_digit)).dropna(subset=["got", "gave"])
    if d.empty:
        return pd.DataFrame(columns=["band", "n", "got", "gave", "diff_db", "habit", "reading"])
    rows = [_balance_row(d, "All bands")] + [_balance_row(d[d["band"] == b], b) for b in bands_top_down(d)]
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------------------- POTA and SOTA: how a place compares

POTA_REF = re.compile(r"^[A-Z0-9]{1,4}-\d{3,6}$")
SOTA_REF = re.compile(r"^[A-Z0-9]{1,4}/[A-Z]{2}-\d{3}$")
POTA_METRICS = (("total", "QSOs"), ("cw", "CW QSOs"), ("phone", "phone QSOs"), ("data", "data QSOs"))
_PHONE = ("SSB", "USB", "LSB", "AM", "FM")


def clean_sota(text):
    """A SOTA summit reference tidied (W7W/KG-O31, typed with a letter O, becomes W7W/KG-031), or an empty string when it is not one."""
    t = str(text).strip().upper()
    m = re.match(r"^([A-Z0-9]{1,4}/[A-Z]{2}-)([0-9O]{3})$", t)
    return (m.group(1) + m.group(2).replace("O", "0")) if m else (t if SOTA_REF.match(t) else "")


def _summits_of(log):
    """The summit each contact was made with (the other station's SOTA_REF, tidied), or an empty string."""
    return log["sota_ref"].map(clean_sota) if "sota_ref" in log else pd.Series("", index=log.index)


def _cell_refs(cell, program):
    out = set()
    for r in str(cell).split(","):
        r = clean_sota(r) if program == "SOTA" else r.strip().upper()
        if r:
            out.add(r)
    return out


def pota_refs(log):
    """The parks the log was made from (MY_POTA_REF, or MY_SIG_INFO when MY_SIG is POTA), most contacts first. A two-fer lists two."""
    counts = {}
    for cell in log["my_pota"]:
        for ref in _cell_refs(cell, "POTA"):
            if POTA_REF.match(ref):
                counts[ref] = counts.get(ref, 0) + 1
    return sorted(counts, key=lambda r: -counts[r])


def sota_refs(log):
    """The summits the log was made from (MY_SOTA_REF, or MY_SIG_INFO when MY_SIG is SOTA), most contacts first."""
    counts = {}
    if "my_sota" in log:
        for cell in log["my_sota"]:
            for ref in _cell_refs(cell, "SOTA"):
                counts[ref] = counts.get(ref, 0) + 1
    return sorted(counts, key=lambda r: -counts[r])


def pota_days(log, ref, program="POTA"):
    """The activations of one park or summit in the log, one per UTC day (the rule of both programs): date, contacts, and how many were CW, phone and data."""
    col = "my_sota" if program == "SOTA" else "my_pota"
    mine = log[log[col].map(lambda c: ref in _cell_refs(c, program))]
    mode = mine["mode"].str.upper()
    kind = mode.map(lambda m: "cw" if m == "CW" else "phone" if m in _PHONE else "data")
    day = mine["time"].dt.normalize()
    out = pd.DataFrame({"date": day, "kind": kind}).groupby(["date", "kind"]).size().unstack(fill_value=0)
    for k in ("cw", "phone", "data"):
        if k not in out:
            out[k] = 0
    out["total"] = out[["cw", "phone", "data"]].sum(axis=1)
    return out.reset_index()[["date", "total", "cw", "phone", "data"]]


def _who(call):
    """A callsign without its portable suffix (K5OHY/P is K5OHY): the longest part that has a digit."""
    parts = [p for p in str(call).upper().split("/") if any(c.isdigit() for c in p)] or [str(call).upper()]
    return max(parts, key=len)


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def pota_compare(log, ref, park, acts, call, stats=None, program="POTA"):
    """How the log's activations of a park (POTA) or a summit (SOTA) compare with every activation the program lists for it. `park` is the program's
    record of the place (or None), `acts` its activations (call, date, total, cw, phone, data; SOTA gives the total only). For each of the log's
    days: the program's count when that day is listed under the callsign (else the log's own), and the rank among the listed activations by
    QSOs (and, for POTA, CW, phone and data QSOs; 1 is the most; a tie shares a rank). Counts are what activators uploaded, so they can be out of date."""
    me = _who(call)
    sota = program == "SOTA"
    metrics = POTA_METRICS[:1] if sota else POTA_METRICS
    acts = acts.assign(who=acts["call"].map(_who)) if len(acts) else pd.DataFrame(columns=["call", "date", "total", "cw", "phone", "data", "who"])
    rows = []
    mine_listed = acts[acts["who"] == me].groupby("date")[["total", "cw", "phone", "data"]].sum().sort_index()
    for r in pota_days(log, ref, program).itertuples():
        ours = {"total": int(r.total), "cw": int(r.cw), "phone": int(r.phone), "data": int(r.data)}
        listed = r.date in mine_listed.index
        use = {k: int(mine_listed.at[r.date, k]) for k in ours} if listed else ours
        ranks = {}
        for key, _ in metrics:
            v = use[key]
            if v > 0:
                others = acts.drop(acts[(acts["who"] == me) & (acts["date"] == r.date)].index)       # everyone else's listed activations
                ranks[key] = (1 + int((others[key] > v).sum()), int((others[key] > 0).sum()) + 1)
        nth = (list(mine_listed.index).index(r.date) + 1) if listed else len(mine_listed) + 1
        rows.append({"date": r.date, "ours": ours, "listed": listed, "use": use, "ranks": ranks, "nth": nth})
    first = acts.sort_values("date").iloc[0] if len(acts) else None
    by_who = (acts.groupby("who").agg(activations=("date", "size"), qsos=("total", "sum"), cw=("cw", "sum")) if len(acts)
              else pd.DataFrame(columns=["activations", "qsos", "cw"]))
    standing = None
    if me in by_who.index:         # where you stand among everyone who has activated the place, by what is listed under your callsign
        mine = by_who.loc[me]
        standing = {k: (1 + int((by_who[k] > mine[k]).sum()), int((by_who[k] > 0).sum()), int(mine[k])) for k in ("qsos", "activations", "cw") if mine[k] > 0}
    p = park or {}
    where = ", ".join(x for x in (p.get("regionName"), p.get("associationName")) if x) if sota else p.get("locationName", "")
    return {"ref": ref, "name": p.get("name", ""), "kind": "Summit" if sota else p.get("parktypeDesc", ""), "where": where,
            "program": program, "noun": "summit" if sota else "park",
            "known": bool(park), "n_acts": len(acts), "n_activators": int(acts["who"].nunique()) if len(acts) else 0, "yours_listed": len(mine_listed),
            "first": (str(first["call"]), first["date"]) if first is not None else None, "rows": rows, "me": me,
            "my_totals": {d: int(t) for d, t in mine_listed["total"].items()}, "park": park or {}, "stats": stats, "standing": standing,
            "top_activators": by_who.sort_values(["qsos", "activations"], ascending=False).head(5),
            "top": acts.sort_values(["total", "date"], ascending=[False, True]).head(5)[["date", "call", "total", "cw", "phone", "data", "who"]]}


def pota_headline(card):
    """The one thing to say about a park or summit first: the log's best day there against every activation listed, and where you stand among the
    activators. Returns {'title', 'line', 'standing'} (standing may be empty), or None when no day of the log has a rank."""
    noun, program = card.get("noun", "park"), card.get("program", "POTA")
    rows = [r for r in card["rows"] if "total" in r["ranks"]]
    if not rows:
        return None
    best = min(rows, key=lambda r: (r["ranks"]["total"][0], -r["date"].value))     # the highest rank, the latest day when tied
    rank, n = best["ranks"]["total"]
    total = best["use"]["total"]
    name = card["name"] or card["ref"]
    others = [t for d, t in card["my_totals"].items() if d != best["date"]]
    mine = bool(others) and total > max(others)
    when = f"{best['date']:%d %b %Y}"
    if n == 2 and rank == 1:
        title, line = f"The biggest activation listed at {name}", f"{when}: {total:,} QSOs, more than the other activation {program} lists for this {noun}."
    elif n > 1 and rank == 1:
        title, line = f"The biggest activation listed at {name}", f"{when}: {total:,} QSOs, the most of any of the {n:,} activations {program} lists for this {noun}."
    elif n > 1 and rank <= max(round(n * 0.05), min(3, n // 2)):        # the top few, but never the bottom half of a short list
        title, line = f"The {_ordinal(rank)} biggest activation listed at {name}", f"{when}: {total:,} QSOs, the {_ordinal(rank)} most of the {n:,} activations {program} lists for this {noun}."
    elif n > 1 and mine:
        title, line = f"Your biggest activation at {name}", f"{when}: {total:,} QSOs, the {_ordinal(rank)} most of the {n:,} activations {program} lists for this {noun}."
    elif n > 1:
        title, line = f"Your activation at {name}", f"{when}: {total:,} QSOs, the {_ordinal(rank)} most of the {n:,} activations {program} lists for this {noun}."
    else:
        title, line = f"Your activation at {name}", f"{when}: {total:,} QSOs, the only activation {program} lists for this {noun}."
    if not best["listed"]:
        line += f" It is not on {program} yet, so this uses the QSOs in your log."
    standing, s = "", card.get("standing")
    if s and "qsos" in s:
        r, m, q = s["qsos"]
        acts = s["activations"][2] if "activations" in s else 0
        cw = s["cw"][2] if "cw" in s else 0
        body = f"{acts:,} activation{'s' if acts != 1 else ''} and {q:,} QSOs" + (f", {cw:,} of them CW" if cw else "") + "."
        standing = (f"You are its top activator of {m}: {body}" if r == 1 and m > 1 else f"You are its {_ordinal(r)} activator of {m} by QSOs: {body}")
    return {"title": title, "line": line, "standing": standing}


def pota_notes(card):
    """The comparison in plain words, as (lead, rest) pairs, one per activation in the log, with where you stand among the activators
    added when the headline does not carry it."""
    noun, program = card.get("noun", "park"), card.get("program", "POTA")
    notes = []
    for r in card["rows"]:
        use, ranks = r["use"], r["ranks"]
        text = ""
        if "total" in ranks:
            rank, n = ranks["total"]
            text = (f"That is more QSOs than the other activation listed for this {noun}." if rank == 1 and n == 2 else
                    f"That is the most QSOs of any of the {n:,} activations listed for this {noun}." if rank == 1 and n > 1 else
                    f"That is the {_ordinal(rank)} most QSOs of the {n:,} activations listed for this {noun}." if n > 1 else f"It is the only activation listed for this {noun}.")
        modes = [f"{use[k]:,} {label} ({_ordinal(ranks[k][0])} of {ranks[k][1]:,})" for k, label in POTA_METRICS[1:] if k in ranks]
        if modes:
            text += " By mode: " + ", ".join(modes) + "."
        if r["listed"]:
            text += f" This was your {_ordinal(r['nth'])} activation listed here."
            others = [t for d, t in card["my_totals"].items() if d != r["date"]]
            if others and use["total"] > max(others):
                text += " It is your biggest there."
            if r["ours"]["total"] != use["total"]:
                text += f" Your log has {r['ours']['total']:,} QSOs; {program} lists {use['total']:,}."
        else:
            text += f" {program} does not list this activation under {card['me']}, so the rank uses the {r['ours']['total']:,} QSOs in your log."
        notes.append((f"{r['date']:%d %b %Y}: {use['total']:,} QSOs.", text.strip()))
    head = pota_headline(card)
    if head is None and card.get("standing") and "qsos" in card["standing"]:
        r, m, q = card["standing"]["qsos"]
        notes.append((f"You are the {noun}'s {_ordinal(r)} activator of {m} by QSOs.", f"{q:,} QSOs listed under {card['me']}."))
    return notes



# ------------------------------------------------------------------------------------------------------------- what you worked

US_STATES = tuple("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
CA_PROVINCES = tuple("AB BC MB NB NL NS NT NU ON PE QC SK YT".split())
CONTINENT_NAMES = {"NA": "North America", "SA": "South America", "EU": "Europe", "AF": "Africa", "AS": "Asia", "OC": "Oceania"}
DXCC_ENTITIES = 340          # the number of current DXCC entities
CQ_ZONES = 40
_US_ENTITIES, _US_NAMES = {"291", "6", "110"}, ("United States", "Alaska", "Hawaii")     # the United States, Alaska and Hawaii: where STATE is a US state


def worked_entities(log):
    """The log with three columns added: `ent` (the DXCC entity worked: the DXCC number the log gives, else the country's name), `ent_name` and
    `ent_cont`. A log that has no DXCC numbers is filled in from the callsign, using the country list the page already has (cty.dat)."""
    d = log.copy()
    dxcc = d["dxcc"].fillna("").astype(str).str.strip() if "dxcc" in d else pd.Series("", index=d.index)
    names, conts = {}, {}
    for key in sorted(set(dxcc[dxcc != ""])):
        rows = d[dxcc == key]
        said = rows["country"][rows["country"] != ""].mode()
        loc = country_location(rows["call"].iloc[0])
        names[key] = said.iloc[0] if len(said) else (loc[2] if loc else f"DXCC {key}")
        cont = rows["cont"][rows["cont"] != ""].mode()
        conts[key] = cont.iloc[0] if len(cont) else (country_continent(names[key]) or "")
    taken = pd.Series(names).value_counts()
    for key in [k for k, v in names.items() if taken[v] > 1]:        # the log's country text can be the registered country, not the entity: Hawaii is not "United States"
        cty = pd.Series([(country_location(c) or (0, 0, ""))[2] for c in d.loc[dxcc == key, "call"].unique()]).replace("", pd.NA).dropna().mode()
        if len(cty):
            names[key] = cty.iloc[0]
    taken = pd.Series(names).value_counts()
    for key in [k for k, v in names.items() if taken[v] > 1]:        # still the same label: tell them apart by the DXCC number
        names[key] = f"{names[key]} (DXCC {key})"
    by_name = {v: k for k, v in names.items()}
    ent, ent_name, ent_cont = [], [], []
    for (_, row), key in zip(d.iterrows(), dxcc):
        if key:
            ent.append(key), ent_name.append(names[key]), ent_cont.append(conts[key])
            continue
        loc = country_location(row["call"])
        name = row["country"] or (loc[2] if loc else "Unknown")
        ent.append(by_name.get(name, name)), ent_name.append(name)
        ent_cont.append(row["cont"] or country_continent(name) or "")
    return d.assign(ent=ent, ent_name=ent_name, ent_cont=ent_cont)


def worked_summary(log):
    """What the log says about who was worked, from the log alone: the DXCC entities (with contacts and bands, those outside the continent with
    the most contacts first), the continents, the US states and Canadian provinces, the CQ and ITU zones, and the countries counted once per band.
    It is what is in this log, not what is confirmed."""
    d = worked_entities(log)
    g = d.groupby("ent")
    ents = pd.DataFrame({"name": g["ent_name"].first(), "cont": g["ent_cont"].first(), "contacts": g.size(),
                         "bands": g["band"].agg(lambda s: sorted(set(s), key=_rank))})
    home = ents.groupby("cont")["contacts"].sum().idxmax() if len(ents) else ""
    ents = ents.assign(away=ents["cont"] != home).sort_values(["away", "contacts", "name"], ascending=[False, False, True]).drop(columns="away")
    us = d["ent"].isin(_US_ENTITIES) | d["ent_name"].isin(_US_NAMES)
    ca = (d["ent"] == "1") | (d["ent_name"] == "Canada")
    states = set(d.loc[us, "state"]) & set(US_STATES)
    provinces = set(d.loc[ca, "state"]) & set(CA_PROVINCES)
    cqz = {int(z) for z in d["cqz"] if str(z).isdigit() and 1 <= int(z) <= CQ_ZONES} if "cqz" in d and (d["cqz"] != "").any() else None
    ituz = {int(z) for z in d["ituz"] if str(z).isdigit() and 1 <= int(z) <= 90} if "ituz" in d and (d["ituz"] != "").any() else None
    continents = {c for c in ents["cont"] if c in CONTINENT_NAMES}
    pairs = d.drop_duplicates(["ent", "band"])
    return {"ents": ents, "n_entities": len(ents), "home": home, "continents": continents,
            "missing_continents": [n for c, n in CONTINENT_NAMES.items() if c not in continents],
            "has_us": bool(us.any()), "states": sorted(states), "missing_states": [s for s in US_STATES if s not in states],
            "has_ca": bool(ca.any()), "provinces": sorted(provinces), "missing_provinces": [p for p in CA_PROVINCES if p not in provinces],
            "cq": sorted(cqz) if cqz is not None else None, "missing_cq": [z for z in range(1, CQ_ZONES + 1) if z not in cqz] if cqz is not None else None,
            "itu": len(ituz) if ituz is not None else None, "band_countries": len(pairs),
            "per_band": {b: int((pairs["band"] == b).sum()) for b in bands_top_down(d)}}


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
    if level == "grid":
        if str(source).startswith("grid square in the log"):
            return "Logged grid: the centre of its grid square"
        return f"Registered home location ({source}); where it operated is not confirmed. Shown as the centre of its grid square"
    return {"park": "Park or summit reference: the place of the park or summit the log names", "summit": "Park or summit reference: the place of the summit the log names",
            "area": f"Approximate: the centre of its call area ({source})", "state": f"Approximate: the centre of its state ({source})",
            "country": f"Approximate: the centre of its country ({source})"}.get(level, source)


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


def _per_skimmer(match, locs=None, home=None):
    """One value for each skimmer from the matches of a band: the median of how far its RBN reports sat from the estimate (`diff`), the matches it was in and, when `locs` and
    `home` are given, its distance from you in km (NaN when its place is not known). A skimmer matched with three WSPR stations (or heard at two sites of one callsign) is one
    skimmer, so it counts once in the middle result and in the number of stations."""
    if match is None or len(match) == 0:
        return pd.DataFrame(columns=["diff", "n", "km"])
    base = match["rx"].map(_base)
    g = match.assign(b=base).groupby("b").agg(diff=("diff", "median"), n=("diff", "size"))
    km = {}
    if locs is not None and home is not None:
        for rx, b in zip(match["rx"], base):
            if b not in km or np.isnan(km[b]):
                place = locate_skimmer(rx, locs)
                km[b] = Geodesic.WGS84.Inverse(home[0], home[1], float(place[0]), float(place[1]))["s12"] / 1000 if place else float("nan")
    g["km"] = g.index.map(lambda b: km.get(b, float("nan")))
    return g


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
    power_by_band = {}       # the power each band was worked out for (it differs by band only when the log has a PowerPlan)
    on_sets, spot_sets = {}, {}     # the distinct skimmers on the band, and that spotted you, for each band and region
    for band, first, last, _ in stretches(own):
        t0, t1 = first - pd.Timedelta(minutes=WINDOW_PAD_MIN), last + pd.Timedelta(minutes=WINDOW_PAD_MIN)
        g = spots[(spots["band"] == band) & (spots["time"] >= t0) & (spots["time"] <= t1)]
        spotted_by_band.setdefault(band, set()).update(g["b"])
        mid = t0 + (t1 - t0) / 2
        wspr = wspr_for(mid - timedelta(minutes=LOOKBACK_MIN), mid)
        power_then = lf.power_at(power_w, mid)               # a power that changed during the log is the power at the middle of this stretch
        power_by_band.setdefault(band, power_then)
        res = cond.analyze(wspr, home, power_then, mode, mid.to_pydatetime(), LOOKBACK_MIN, antenna_db, 3.0) if len(wspr) else None
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
        mb = match[match["band"] == band]
        per = _per_skimmer(mb, locs, home)                   # one value for each skimmer, so one with several matches does not count several times
        m = per["diff"]
        offset = float(m.median()) - TYPICAL_OFFSET_DB if len(m) >= SHOW_MATCHES else float("nan")
        near, far = per[per["km"] < SPLIT_KM]["diff"], per[per["km"] >= SPLIT_KM]["diff"]
        note, tone = _note(n_cw, page, actual)
        got = own.loc[own["band"] == band, "rst_rcvd"].map(s_digit)
        rows.append({"band": band, "contacts": n_cw, "other": int(all_counts[band]) - n_cw, "skimmers": len(spotted_by_band.get(band, ())),
                     "report": float(got.mean()) if got.notna().any() else float("nan"),
                     "page": page, "spotted": actual, "listening": n_listen, "stronger_db": offset, "matches": len(mb), "match_rx": len(per),
                     "near_db": float(near.median()) - TYPICAL_OFFSET_DB if len(near) >= SPLIT_MIN else float("nan"), "near_n": len(near),
                     "far_db": float(far.median()) - TYPICAL_OFFSET_DB if len(far) >= SPLIT_MIN else float("nan"), "far_n": len(far),
                     "q1": float(m.quantile(0.25)) - TYPICAL_OFFSET_DB if len(m) >= SHOW_MATCHES else float("nan"),
                     "q3": float(m.quantile(0.75)) - TYPICAL_OFFSET_DB if len(m) >= SHOW_MATCHES else float("nan"),
                     "thin": 0 < len(m) < MIN_MATCHES, "note": note, "tone": tone, "no_picture": band in no_picture})
    bands = pd.DataFrame(rows)
    page, actual, n_listen = _agg(solid)
    every = match.assign(b=match["rx"].map(_base)).groupby(["band", "b"])["diff"].median() if len(match) else pd.Series(dtype=float)       # one value for each skimmer on each band
    offset = float(every.median()) - TYPICAL_OFFSET_DB if len(every) >= SHOW_MATCHES else float("nan")
    thin_cells = cells[~cells.index.isin(solid.index)]
    thin_listen = int(thin_cells["listening"].sum())
    overall = {"page": page, "spotted": actual, "listening": n_listen, "stronger_db": offset, "matches": len(match), "match_rx": int(match["rx"].map(_base).nunique()),
               "spread_db": float(every.std()) if len(every) > 2 else float("nan"),
               "thin_listening": thin_listen, "thin_spotted": int(thin_cells["spotted"].sum()),
               "typical_offset_db": TYPICAL_OFFSET_DB}
    return {"bands": bands, "regions": _regions(log, mode, cells, solid, on_sets, spot_sets), "overall": overall, "matches": match, "cells": cells,
            "power_by_band": power_by_band}


MATCH_COLUMNS = ["Band", "Receiving station", "Matches", "RBN report (dB)", "Estimated from WSPR (dB)", "Above (+) or below (-) the estimate (dB)"]


def match_table(match):
    """The receiving stations behind the strength comparison, one row for each band and station: how many matched stretches it appears in, the
    median RBN report, the median estimate made for it from the WSPR near you (restated to your power) and the difference with the reference offset
    (TYPICAL_OFFSET_DB) taken off, as in the bars. Highest band first, then the station with the most matches."""
    if match is None or len(match) == 0:
        return pd.DataFrame(columns=MATCH_COLUMNS)
    g = match.groupby(["band", "rx"]).agg(n=("diff", "size"), obs=("obs", "median"), adj=("adj", "median"), diff=("diff", "median")).reset_index()
    g["_r"] = g["band"].map(_rank)
    g = g.sort_values(["_r", "n", "rx"], ascending=[False, False, True])
    return pd.DataFrame({"Band": g["band"], "Receiving station": g["rx"], "Matches": g["n"].astype(int), "RBN report (dB)": g["obs"].round(1),
                         "Estimated from WSPR (dB)": g["adj"].round(1), "Above (+) or below (-) the estimate (dB)": (g["diff"] - TYPICAL_OFFSET_DB).round(1)}).reset_index(drop=True)


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


# ------------------------------------------------------------------------------------------------- band conditions while you were on the air

CONDITIONS_SLOT_MIN = lf.DEFAULT_BIN_MIN     # one box of the picture (30 minutes unless a page asks for 15)
CONDITIONS_GAP_H = 4         # a pause this long in the log starts a new picture
MIN_PICTURE_RECEIVERS = 20   # fewer WSPR receivers than this behind a box and it is shown as too thin to say
FETCH_CHUNK_H = 5            # WSPR is fetched this many hours at a time, so a long activation stays well under the row limit
DX_MILES = 3000              # a receiver or skimmer this far from you or farther counts as DX
DX_KM = DX_MILES * 1.609344
US_ABROAD = "US stations overseas"
CONDITION_BANDS = ("160m", "80m", "60m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m")     # the bands the DX picture looks at, worked or not
STEADY_SPREAD = 0.10         # a band whose share stayed within this (10 points) of itself all evening is called steady
BIG_CHANGE = 0.15            # a band has risen or fallen by this much (15 points) between the start and the end of the activation
_MODE_OF = {"CW": "CW", "SSB": "SSB", "USB": "SSB", "LSB": "SSB", "AM": "SSB", "FM": "SSB", "FT8": "FT8", "FT4": "FT8"}


def condition_mode(log):
    """The mode the conditions picture is worked out for: the one most of the contacts were made in, as the conditions page knows it
    (CW, SSB or FT8), and CW when that is something else."""
    counts = log["mode"].map(lambda m: _MODE_OF.get(str(m).upper(), "CW")).value_counts()
    return str(counts.index[0]) if len(counts) else "CW"


def condition_panels(log, bin_min=CONDITIONS_SLOT_MIN):
    """The first and last bin (half hour unless `bin_min` says 15) of each stretch of activity in the log, as a list of (first, last), cut at
    pauses of CONDITIONS_GAP_H hours."""
    slots = pd.Series(sorted(lf.bin_floor(log["time"], bin_min).unique()))
    new = (slots.diff() > pd.Timedelta(hours=CONDITIONS_GAP_H)).cumsum()
    return [(g.iloc[0], g.iloc[-1]) for _, g in slots.groupby(new)]


def dx_contacts_mask(log):
    """The contacts outside North America, by the continent the log gives (or, with none, by the country)."""
    cont, country = log["cont"].fillna(""), log["country"].fillna("")
    return ((cont != "") & (cont != "NA")) | ((cont == "") & (country != "") & ~country.isin(_NORTH_AMERICA))


def conditions_grid(log, wspr_for, home, power_w, mode=None, antenna_db=0.0, bin_min=CONDITIONS_SLOT_MIN, radius_km=None):
    """How open each band looked while you were on the air: one row per panel, bin (30 minutes, or 15 with `bin_min`) and band with the number of
    WSPR receivers heard near you, how many of them a signal like yours would have reached (the conditions page's 'good'), their share (nan when
    fewer than MIN_PICTURE_RECEIVERS stand behind it) and the contacts you made on that band in that bin. The DX columns count the receivers
    DX_MILES or more from you: `dx_heard` heard WSPR near you, `dx_good` of them would also have heard a signal like yours, `dx_regions`
    says where those are, and `dx_contacts` counts your contacts outside North America. `rbn_far` starts at 0 (see add_rbn_far). Each bin
    uses the hour of WSPR spots up to its end, as the conditions page does, so neighbouring bins share part of that hour: `window_start` and
    `window_end` are the exact bounds of it and `shared_min` how much of it the bin before used as well. `wspr_tx`, `wspr_sites` and
    `wspr_reports` count the transmitters, receiving sites and reports in that window, and `state` is what the box can say (see
    log_foundations.cell_state). `wspr_for(start, end)` gives the WSPR spots between two times; `radius_km` is the radius they were fetched
    within, kept with the evidence so the page can say it."""
    mode = mode or condition_mode(log)
    worked_bands = bands_top_down(log)
    bands = worked_bands + [b for b in sorted(CONDITION_BANDS, key=_rank, reverse=True) if b not in worked_bands]      # the bands you did not work follow
    step = timedelta(minutes=bin_min)
    log = log.assign(slot=lf.bin_floor(log["time"], bin_min))
    made = log.groupby(["slot", "band"]).size()
    made_dx = log[dx_contacts_mask(log)].groupby(["slot", "band"]).size()
    rows, receiver_rows = [], []
    seen_tx, seen_rx, n_reports, farthest = set(), set(), 0, 0.0
    for panel, (first, last) in enumerate(condition_panels(log, bin_min)):
        start, end = first - timedelta(minutes=LOOKBACK_MIN), last + step
        frames, t = [], start
        while t < end:
            t2 = min(t + timedelta(hours=FETCH_CHUNK_H), end)
            part = wspr_for(t, t2)
            if len(part):
                frames.append(part[part["band"].isin(bands)])
            t = t2
        wspr = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if len(wspr):
            seen_tx |= set(wspr["tx"])
            seen_rx |= set(wspr["rx"])
            n_reports += len(wspr)
        for slot in pd.date_range(first, last, freq=f"{bin_min}min"):
            window = lf.wspr_window(slot, bin_min)
            shared = lf.shared_minutes(lf.wspr_window(slot - step, bin_min), window) if slot > first else 0.0
            behind = {}
            if len(wspr):
                inside = wspr[(wspr["time"] > window[0]) & (wspr["time"] <= window[1])]
                behind = {band: lf.coverage(g) for band, g in inside.groupby("band")}
            res = (cond.analyze(wspr, home, lf.power_at(power_w, slot), mode, window[1].to_pydatetime(), LOOKBACK_MIN,
                                antenna_db, 3.0) if len(wspr) else None)
            rec = res["receivers"] if res is not None else pd.DataFrame()
            if len(rec):
                farthest = max(farthest, float(rec["km"].max()))
                receiver_rows.append(rec[["band", "rx", "km", "bearing", "region", "verdict", "adj", "margin", "reports"]].assign(panel=panel, slot=slot))
            for band in bands:
                receivers = good = dx_heard = dx_good = 0
                dx_regions, dx_regions_heard = {}, {}
                if res is not None and not res["bands"].empty and band in res["bands"].index:
                    receivers, good = int(res["bands"].loc[band, "Receivers"]), int(res["bands"].loc[band, "Good"])
                if len(rec):
                    far = rec[(rec["band"] == band) & (rec["km"] >= DX_KM)]
                    far = far.assign(region=far["region"].replace({"US East": US_ABROAD, "US Central": US_ABROAD, "US West": US_ABROAD}))   # a US callsign this far away is overseas
                    strong = far[far["verdict"] == "good"]
                    dx_heard, dx_good = int(len(far)), int(len(strong))
                    dx_regions = {str(k): int(v) for k, v in strong.groupby("region").size().items()}
                    dx_regions_heard = {str(k): int(v) for k, v in far.groupby("region").size().items()}
                share = good / receivers if receivers >= MIN_PICTURE_RECEIVERS else float("nan")
                cov = behind.get(band) or lf.coverage(None)
                rows.append({"panel": panel, "slot": slot, "band": band, "receivers": receivers, "good": good, "share": share,
                             "contacts": int(made.get((slot, band), 0)), "dx_heard": dx_heard, "dx_good": dx_good, "dx_regions": dx_regions,
                             "dx_contacts": int(made_dx.get((slot, band), 0)), "rbn_far": 0, "dx_regions_heard": dx_regions_heard,
                             "worked": band in worked_bands, "wspr_tx": cov["transmitters"], "wspr_sites": cov["sites"],
                             "wspr_reports": cov["reports"], "window_start": window[0], "window_end": window[1], "shared_min": shared,
                             "state": lf.cell_state(reports=cov["reports"], transmitters=cov["transmitters"], receivers=cov["receivers"], reaching=good)})
    out = pd.DataFrame(rows, columns=["panel", "slot", "band", "receivers", "good", "share", "contacts", "dx_heard", "dx_good", "dx_regions",
                                      "dx_contacts", "rbn_far", "dx_regions_heard", "worked", "wspr_tx", "wspr_sites", "wspr_reports",
                                      "window_start", "window_end", "shared_min", "state"])
    if len(out):    # a band you did not work with no WSPR at all has nothing to show
        out = out[out["worked"] | (out.groupby("band")["receivers"].transform("max") > 0)].reset_index(drop=True)
    out.attrs["evidence"] = {"transmitters": len(seen_tx), "receivers": len(seen_rx), "reports": n_reports, "farthest_km": farthest,
                             "radius_km": radius_km}
    out.attrs["bin_min"] = bin_min
    out.attrs["mode"], out.attrs["power_w"], out.attrs["home"] = mode, power_w, tuple(home)
    receivers = pd.concat(receiver_rows, ignore_index=True) if receiver_rows else pd.DataFrame(
        columns=["band", "rx", "km", "bearing", "region", "verdict", "adj", "margin", "reports", "panel", "slot"])
    receivers["sector"] = receivers["bearing"].map(lf.sector_of)
    receivers["continent"] = receivers["region"].map(lf.continent_of_region)
    out.attrs["receivers"] = receivers          # one row for each receiver in each box and band: where it was, and whether it looked strong enough
    return out


COVERAGE_COLUMNS = ["Band", "Box (UTC)", "WSPR window (UTC)", "Shared with the box before (min)", "Transmitters", "Receivers", "Receiving sites", "Reports",
                    "What it can say"]


def coverage_table(grid):
    """What each box of the conditions grid rests on, as a table for the page: the box and the exact WSPR window behind it, how much of that
    window the box before used too, how many transmitters, receivers and receiving sites reported in it, and the state the box is in (see
    log_foundations.cell_state). Bands you worked come first, highest band first, each in time order."""
    if grid is None or grid.empty or "state" not in grid.columns:
        return pd.DataFrame(columns=COVERAGE_COLUMNS)
    step = pd.Timedelta(minutes=grid.attrs.get("bin_min", CONDITIONS_SLOT_MIN))
    many = grid["panel"].nunique() > 1
    when = (lambda t: f"{t:%d %b %H:%M}") if many else (lambda t: f"{t:%H:%M}")
    d = grid.assign(_not_worked=~grid["worked"].astype(bool), _rank=-grid["band"].map(_rank)).sort_values(["_not_worked", "_rank", "panel", "slot"])
    dash = "\u2013"
    return pd.DataFrame({
        "Band": d["band"].tolist(),
        "Box (UTC)": [f"{when(t)}{dash}{t + step:%H:%M}" for t in d["slot"]],
        "WSPR window (UTC)": [f"{when(a)}{dash}{b:%H:%M}" for a, b in zip(d["window_start"], d["window_end"])],
        "Shared with the box before (min)": d["shared_min"].round().astype(int).tolist(),
        "Transmitters": d["wspr_tx"].astype(int).tolist(), "Receivers": d["receivers"].astype(int).tolist(),
        "Receiving sites": d["wspr_sites"].astype(int).tolist(), "Reports": d["wspr_reports"].astype(int).tolist(),
        "What it can say": d["state"].tolist()}, columns=COVERAGE_COLUMNS)


PRECISE_SOURCES = ("grid", "coords", "park", "summit", "home")      # a contact placed by one of these is at a known place (a station's HamQTH home is its own 4 character grid); a call area, a state or a country is only a centre, which can be hundreds of km away
AREA_SECTOR_MIN_KM = 2500                          # a call area (Kinki, a Brazilian state) is a region's centre, off by a few hundred km: far enough away that is too little to change the sector it is in
ROUGH_MARGIN_KM = 1500                             # a centre placed farther than this beyond the farthest known place is certainly farther (a small country's centre is wrong by far less)


def farthest_contact(places, band=None):
    """The farthest contact, from contact_places' table (all bands, or one `band`). A contact placed by a grid, a park or a summit is at a known place, so the farthest of
    those is the answer when there is one. A contact placed only by its state or country is at a centre that can be hundreds of km from the station, so it is never
    allowed to win by a few km over another, and when nothing better is known every contact at the same distance is named (two stations in Japan are both at the centre
    of Japan, so neither is 'the' farthest). Returns None for no placed contact, else a dict: `call` (the first), `calls` (all at that distance), `bands` (their bands),
    `place` (the country, else the continent), `km`, `band` and `approx`. A contact placed only by country that is farther than the farthest precise one comes as `rough`
    (the same dict) when it is farther by less than ROUGH_MARGIN_KM, so the page can say so without letting it take the answer; when it is farther by more than that
    it is the answer itself (`approx` True) with the farthest precise one as `precise`."""
    d = places[places["c_km"].notna()] if places is not None and len(places) else None
    if d is None or d.empty:
        return None
    if band is not None:
        d = d[d["band"] == band]
        if d.empty:
            return None

    def pick(g, approx):
        top = g.loc[g["c_km"].idxmax()]
        tied = g[(g["c_km"] - top["c_km"]).abs() < 1.0] if approx else g.loc[[top.name]]
        calls = list(dict.fromkeys(tied["call"]))
        return {"call": str(top["call"]), "calls": calls, "bands": list(dict.fromkeys(tied["band"])), "band": str(top["band"]),
                "place": top["country"] or lf.CONTINENT_NAMES.get(top["continent"], ""), "km": float(top["c_km"]), "approx": approx}

    precise, rough = d[d["c_source"].isin(PRECISE_SOURCES)], d[~d["c_source"].isin(PRECISE_SOURCES)]
    best = pick(precise, False) if len(precise) else None
    if len(rough):
        far_rough = pick(rough, True)
        if best is None:
            return far_rough
        if far_rough["km"] > best["km"] + ROUGH_MARGIN_KM:
            far_rough["precise"] = best            # a country's centre is not wrong by this much, so it is certainly farther: it leads, said to be rough, with the best known place beside it
            return far_rough
        if far_rough["km"] > best["km"]:
            best["rough"] = far_rough              # farther, but by less than a centre can be wrong: said beside the precise one, which keeps the place
    return best


def park_to_park(log, ref, ref_places=None, program="POTA"):
    """The contacts made from the park (or summit) `ref` with another activator, one row for each park (or summit) of theirs that the log names: `ref`, `name`, `lat`, `lon`
    (NaN when the place of that park is not known), `contacts`, `stations`, `calls`, `bands`, `first` and `last` (times), and `by_band` ({band: {contacts, calls, first, last}}, highest band first). Only a contact whose log record carries the other
    station's park reference is here: the log is the only place that says it was park to park, so a contact the logging program did not mark is not found. Most contacts
    first. `attrs` has `with_ref` (contacts that name another park or summit, each counted once even when it names two), `total` (the contacts made from `ref`), `same` (contacts
    that named `ref` itself, which are not park to park and are left off the map) and `unplaced` (parks with no known place)."""
    ref_places = ref_places if ref_places is not None else (getattr(log, "attrs", {}).get("ref_places") or {})
    sota = program == "SOTA"
    mine_col, valid = ("my_sota", SOTA_REF) if sota else ("my_pota", POTA_REF)
    cols = ["ref", "name", "lat", "lon", "contacts", "stations", "calls", "bands", "first", "last", "by_band"]
    empty = pd.DataFrame(columns=cols)
    empty.attrs.update(with_ref=0, total=0, unplaced=0, same=0)
    if mine_col not in log:
        return empty
    theirs = _summits_of(log) if sota else (log["pota_ref"] if "pota_ref" in log else pd.Series("", index=log.index))
    rows, total, same, named = [], 0, 0, 0
    for call, band, time, mine, other in zip(log["call"], log["band"], log["time"], log[mine_col], theirs):
        if ref not in _cell_refs(mine, program):
            continue
        total += 1
        refs = [r for r in sorted(_cell_refs(other, program)) if valid.match(r)]
        same += int(ref in refs)
        far = [r for r in refs if r != ref]
        named += int(bool(far))
        for r in far:
            rows.append((r, call, band, time))
    if not rows:
        empty.attrs.update(total=total, same=same)
        return empty
    d = pd.DataFrame(rows, columns=["ref", "call", "band", "time"])
    out = []
    for r, g in d.groupby("ref"):
        place = ref_places.get(r)
        out.append({"ref": r, "name": (place[2] if place and len(place) > 2 else ""), "lat": float(place[0]) if place else float("nan"),
                    "lon": float(place[1]) if place else float("nan"), "contacts": len(g), "stations": int(g["call"].nunique()),
                    "calls": list(dict.fromkeys(g.sort_values("time")["call"])), "bands": sorted(g["band"].unique(), key=_rank), "first": g["time"].min(), "last": g["time"].max(),
                    "by_band": {b: {"contacts": len(h), "calls": list(dict.fromkeys(h.sort_values("time")["call"])), "first": h["time"].min(), "last": h["time"].max()}
                                for b, h in sorted(g.groupby("band"), key=lambda kv: _rank(kv[0]))}})
    table = pd.DataFrame(out, columns=cols).sort_values(["contacts", "ref"], ascending=[False, True]).reset_index(drop=True)
    table.attrs.update(with_ref=named, total=total, unplaced=int(table["lat"].isna().sum()), same=same)
    return table


def contact_dx_calls(log):
    """The stations that need a place looked up beyond the log: no usable grid square, no park or summit place, and outside North America (those are placed by the log's
    state). A contact's country is the log's, else the one its callsign gives."""
    refs = log.attrs.get("ref_places") or {}
    calls = []
    pota = log["pota_ref"] if "pota_ref" in log else [""] * len(log)
    sota = log["sota_ref"] if "sota_ref" in log else [""] * len(log)
    for call, grid, country, pc, sc in zip(log["call"], log["their_grid"], log["country"], pota, sota):
        if lf.grid_point(grid) is not None or _reference_point(pc, sc, refs)[0] is not None:
            continue
        name = country or (country_location(call) or (0, 0, ""))[2]
        if name and name not in _NORTH_AMERICA:
            calls.append(call)
    return sorted(set(calls))


def contact_references(log):
    """The parks and summits the other stations were at (the POTA_REF and SOTA_REF of a contact; a two-fer lists two), as (set of POTA references, set of SOTA references),
    so their places can be looked up."""
    pota = set()
    for cell in log["pota_ref"] if "pota_ref" in log else []:
        for ref in str(cell).split(","):
            ref = ref.strip().upper()
            if POTA_REF.match(ref):
                pota.add(ref)
    return pota, {s for s in (_summits_of(log) if "sota_ref" in log else []) if s}


def _reference_point(pota_cell, sota_cell, ref_places):
    """The place of the first park (then the summit) of a contact that is known in `ref_places`, as ((lat, lon), 'park' or 'summit'), else (None, '')."""
    for ref in str(pota_cell).split(","):
        ref = ref.strip().upper()
        if ref in ref_places:
            return tuple(ref_places[ref][:2]), "park"
    summit = clean_sota(sota_cell) if sota_cell else ""
    if summit and summit in ref_places:
        return tuple(ref_places[summit][:2]), "summit"
    return None, ""


def contact_places(log, home, ref_places=None):
    """Where each contact was, as columns added to the log. The place comes from the contact's own grid square when the log gives a valid one
    (the 6 character grid when there is one), read for each contact, so a station that moved is placed where it was each time; failing that, for a contact with another
    park or summit, from that park or summit's own place (`ref_places`, or the log's `attrs['ref_places']`, {reference: (lat, lon)}); failing that
    the centre of its state (North America), then the centre of its country by its callsign. `c_source` says which ('grid', 'coords' (the station's own LAT and LON in the log), 'park', 'summit', 'home' (a station
    outside North America placed by its HamQTH callbook home, from `attrs['call_places']`), 'area' (the same, by its call area), 'state', 'country' or '' when it could not be placed), `c_approx` is True for the last two, `c_km` and `c_bearing` are the distance and the bearing from
    `home` to the place, `sector` is the compass sector of that bearing and `continent` comes from the log's CONT field, else from the callsign.
    `sector_whole` is the sector the contact can be counted in: the sector of its grid, park or summit, or, for a contact placed only by its state, the sector
    the whole state lies in (None when the state spreads over more than one, and for a country's centre); `sector_basis` says 'grid', 'coords', 'park', 'summit', 'home', 'area' or 'state'. A call area counts in a sector only when it is AREA_SECTOR_MIN_KM or more away."""
    ref_places = ref_places if ref_places is not None else (getattr(log, "attrs", {}).get("ref_places") or {})
    call_places = getattr(log, "attrs", {}).get("call_places") or {}
    pota_cells = log["pota_ref"] if "pota_ref" in log else pd.Series("", index=log.index)
    sota_cells = log["sota_ref"] if "sota_ref" in log else pd.Series("", index=log.index)
    if "their_lat" in log and "their_lon" in log:                       # the other station's own coordinates, when the log carries them (ADIF LAT and LON)
        coords = [(round(float(a), 5), round(float(b), 5)) if a == a and b == b and a is not None and b is not None else None for a, b in zip(log["their_lat"], log["their_lon"])]
    else:
        coords = [None] * len(log)
    keys = list(zip(log["call"], log["state"], log["their_grid"], log["cont"], log["country"], pota_cells, sota_cells, coords))
    found = {}
    for key in set(keys):
        call, state, grid, cont, country, pota_cell, sota_cell, logged = key
        point, source = lf.grid_point(grid), "grid"
        if point is None and logged is not None:
            point, source = logged, "coords"
        if point is None and ref_places:
            point, source = _reference_point(pota_cell, sota_cell, ref_places)
            point = point or None
        guess = country_location(call)
        if point is None and call in call_places:            # a station outside North America with no grid in the log: its HamQTH home, else its call area
            found_at = call_places[call]
            if found_at["source"] == "home":
                from conditions import latlon_to_maidenhead
                point, source = maidenhead_to_latlon(latlon_to_maidenhead(found_at["lat"], found_at["lon"])[:4]), "home"     # only the centre of its 4 character grid, as for every other home
            else:
                point, source = (found_at["lat"], found_at["lon"]), "area"
        if point is None and state in STATE_CENTRES and country in _NORTH_AMERICA:
            point, source = STATE_CENTRES[state], "state"
        if point is None and guess:
            point, source = (guess[0], guess[1]), "country"
        continent = cont if cont in lf.CONTINENT_NAMES else (country_continent(guess[2]) if guess else "") or ""
        if point is None:
            found[key] = (np.nan, np.nan, "", False, np.nan, np.nan, None, continent, None, "")
            continue
        inv = Geodesic.WGS84.Inverse(home[0], home[1], float(point[0]), float(point[1]))
        bearing = inv["azi1"] % 360
        sector = lf.sector_of(bearing)
        far_area = source == "area" and inv["s12"] / 1000 >= AREA_SECTOR_MIN_KM
        whole, basis = (sector, source) if source in PRECISE_SOURCES or far_area else ((lf.state_sector(state, home), "state") if source == "state" else (None, ""))
        found[key] = (float(point[0]), float(point[1]), source, source not in PRECISE_SOURCES, inv["s12"] / 1000, bearing, sector, continent, whole if whole else None,
                      basis if whole else "")
    cols = ["c_lat", "c_lon", "c_source", "c_approx", "c_km", "c_bearing", "sector", "continent", "sector_whole", "sector_basis"]
    return log.assign(**{c: [found[k][i] for k in keys] for i, c in enumerate(cols)})


def contact_direction_table(places, view="sector"):
    """How many contacts were in each region, from contact_places' output. In the 'sector' view a contact counts when it can be pinned to one
    sector: it has its own grid, or its state lies wholly in that sector as seen from you. A contact placed only at the centre of a state that
    spreads over several sectors, or at the centre of a country, is between sectors and is counted apart, because that centre can be hundreds
    of km from the station. In the 'continent' view every contact counts, because a continent is known from the callsign even when the
    place is not. Returns a table of Region, Contacts and, in the sector view, how many of those were placed by their state."""
    if view == "continent":
        names = places["continent"].map(lambda c: lf.region_of_point(None, c, "continent"))
        order = list(lf.CONTINENT_NAMES.values())
        counted, by_state = names.notna(), pd.Series(False, index=places.index)
    else:
        names = places["sector_whole"].map(lambda s: lf.sector_label(s) if isinstance(s, str) else None)
        order = [lf.sector_label(s) for s in lf.SECTORS]
        counted, by_state = names.notna(), names.notna() & (places["sector_basis"] == "state")
    rows = [{"Region": r, "Contacts": int((counted & (names == r)).sum()), "Placed by state only": int((by_state & (names == r)).sum())} for r in order]
    out = pd.DataFrame(rows, columns=["Region", "Contacts", "Placed by state only"])
    out = out[out["Contacts"] > 0].reset_index(drop=True)
    if view == "continent":
        out = out.drop(columns=["Placed by state only"])
    out.attrs.update(counted=int(counted.sum()), by_state=int(by_state.sum()), unplaced=int((places["c_source"] == "").sum()), total=len(places),
                     between=int((~counted & (places["c_source"] != "")).sum()))
    return out


def add_rbn_far(grid, spots, locs, home):
    """The grid with `rbn_far` filled in: for each half hour and band, how many different skimmers DX_MILES or more from you spotted you.
    `locs` is the skimmer list (callsign to place); a skimmer it does not know is not counted."""
    carried, bin_min = dict(grid.attrs), grid.attrs.get("bin_min", CONDITIONS_SLOT_MIN)
    grid = grid.assign(rbn_far=0)
    grid.attrs.update(carried)
    if spots is None or spots.empty or grid.empty:
        return grid
    far = {}
    for spotter in spots["spotter"].unique():
        place = locate_skimmer(spotter, locs)
        if place and Geodesic.WGS84.Inverse(home[0], home[1], float(place[0]), float(place[1]))["s12"] / 1000 >= DX_KM:
            far[spotter] = _base(spotter)
    s = spots[spots["spotter"].isin(far)]
    if s.empty:
        return grid
    s = s.assign(slot=lf.bin_floor(s["time"], bin_min), who=s["spotter"].map(far))
    counts = s.groupby(["slot", "band"])["who"].nunique()
    out = grid.assign(rbn_far=[int(counts.get((slot, band), 0)) for slot, band in zip(grid["slot"], grid["band"])])
    out.attrs.update(carried)
    return out


def _join(names):
    return ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]


def _slot_windows(slots, step_min=CONDITIONS_SLOT_MIN):
    """Runs of half hours that follow one another, as [(first, last)]: scattered half hours are separate windows, not one long opening."""
    runs = []
    for s in sorted(slots):
        if runs and s - runs[-1][1] == timedelta(minutes=step_min):
            runs[-1][1] = s
        else:
            runs.append([s, s])
    return [tuple(r) for r in runs]


def dx_notes(grid, power_w, max_lines=9, view="estimate"):
    """The DX picture in plain words, as (lead, rest) pairs, band by band: in how many half hours WSPR stations DX_MILES or more away decoded WSPR near
    you ('observed') or looked strong enough to hear a signal like yours ('estimate'), where they were, and what you did on the band by comparison.
    Bands you did not work come after the ones you did. These are facts about the half hours, not advice: a log cannot say why you were on a band."""
    if grid.empty or "dx_good" not in grid.columns:
        return []
    observed = view == "observed"
    metric, regs_col = ("dx_heard", "dx_regions_heard") if observed else ("dx_good", "dx_regions")
    if regs_col not in grid.columns:
        regs_col = "dx_regions"
    when = (lambda t: f"{t:%d %b %H:%M}Z") if grid["panel"].nunique() > 1 else (lambda t: f"{t:%H:%M}Z")
    power = f"{power_w:g} W"
    miles = f"{DX_MILES:,}"
    evidence, plain = [], []
    for band, d in grid.groupby("band"):
        d = d.sort_values(["panel", "slot"])
        n, is_worked = int(d["contacts"].sum()), (bool(d["worked"].iloc[0]) if "worked" in d else True)
        ev = d[d[metric] >= 1]
        if len(ev) and (len(ev) >= 2 or int(ev[metric].max()) >= 2):
            evidence.append((is_worked, len(ev), n, band, d, ev))
        elif is_worked and n >= 5:
            plain.append((n, band, d))
    notes = []
    rbn_note = lambda d: (f" RBN skimmers over {miles} miles from you spotted you on it, first in the half hour from {when(d[d['rbn_far'] > 0]['slot'].min())}."
                          if (d["rbn_far"] > 0).any() else "")
    outside = lambda d: (f", and {int(d['dx_contacts'].sum())} {'was' if int(d['dx_contacts'].sum()) == 1 else 'were'} outside North America"
                         if d["dx_contacts"].sum() else "")
    thin = lambda d: " WSPR coverage on this band was thin." if int(d["receivers"].max()) < MIN_PICTURE_RECEIVERS else ""
    for is_worked, _, n, band, d, ev in sorted(evidence, key=lambda x: (not x[0], -x[1], -x[2])):
        lo, hi = int(ev[metric].min()), int(ev[metric].max())
        regions = {}
        for r in ev[regs_col]:
            for k, v in r.items():
                regions[k] = max(regions.get(k, 0), v)
        top = [k for k, _ in sorted(regions.items(), key=lambda kv: -kv[1])[:3]]
        said = f"{lo} to {hi}" if lo != hi else f"{hi}"
        where = f", in {_join(top)}." if top else "."
        tag = "" if is_worked else " (not worked)"
        plural = "s" if hi != 1 else ""
        if observed:
            lead = f"{band}{tag}: distant WSPR stations decoded transmitters near you in {len(ev)} of {len(d)} half hours."
            text = f"{said} WSPR station{plural} over {miles} miles away decoded WSPR near you{where}"
        else:
            lead = f"{band}{tag}: estimated DX paths for {power} in {len(ev)} of {len(d)} half hours."
            text = f"{said} WSPR station{plural} over {miles} miles away looked strong enough to hear {power}{where}"
            heard_med, good_med = float(d["dx_heard"].median()), float(d["dx_good"].median())
            if heard_med >= 10 and good_med <= 1:
                text += (f" {int(d['dx_heard'].min())} to {int(d['dx_heard'].max())} WSPR stations over {miles} miles away decoded WSPR on {band}, "
                         f"but most looked too weak for {power}.")
        if is_worked:
            inside = int(d.loc[d[metric] >= 1, "contacts"].sum())
            text += (f" You made {n} contact{'s' if n != 1 else ''} on {band}, "
                     + ("all of them" if inside == n else "none of them" if inside == 0 else f"{inside} of them")
                     + f" in half hours with {'distant WSPR reports' if observed else 'DX evidence'}" + outside(d) + ".")
            worked = d[d["contacts"] > 0]
            if len(worked):
                before, after = (ev["slot"] < worked["slot"].min()).any(), (ev["slot"] > worked["slot"].max()).any()
                if before and after:
                    text += " Some of the evidence came before your first contact there and some after your last."
                elif after:
                    text += " Some of the evidence came after your last contact there."
                elif before:
                    text += " Some of the evidence came before your first contact there."
            text += rbn_note(d)
        notes.append((lead, text))
    for n, band, d in sorted(plain, key=lambda x: -x[0]):
        heard, strong = int((d["dx_heard"] > 0).sum()), d[d[metric] >= 1]
        if len(strong):
            lead = f"{band}: little distant WSPR." if observed else f"{band}: little estimated DX for {power}."
            text = (f"Only the half hour from {when(strong['slot'].iloc[0])} had one: {int(strong[metric].iloc[0])} WSPR station over {miles} miles away "
                    + ("decoded WSPR near you." if observed else f"looked strong enough to hear {power}."))
        elif observed:
            lead = f"{band}: no distant WSPR reports."
            text = f"No WSPR stations over {miles} miles away reported on {band}."
        else:
            lead = f"{band}: no estimated DX paths for {power}."
            text = (f"{heard} half hour{'s' if heard != 1 else ''} had WSPR stations over {miles} miles away that decoded WSPR, but none looked strong enough."
                    if heard else f"No WSPR stations over {miles} miles away reported on {band}.")
        notes.append((lead, f"{text}{thin(d)} You made {n} contacts on {band}{outside(d)}.{rbn_note(d)}"))
    return notes[:max_lines]


def space_span(log):
    """The stretch of time the space weather is shown for: from an hour before the first contact to an hour after the last."""
    return log["time"].min().floor("h") - timedelta(hours=1), log["time"].max().ceil("h") + timedelta(hours=1)


def _pc(x):
    return f"{x * 100:.0f}%"


def conditions_notes(grid, max_lines=6):
    """What the picture says in plain words, as a list of (lead, rest) pairs. Every line compares a band with itself, or states what a box
    says, because bands differ in how many far receivers they have and so cannot be fairly set side by side."""
    g = grid[grid["share"].notna()]
    if g.empty:
        return []
    notes = []
    when = (lambda t: f"{t:%d %b %H:%M}Z") if g["panel"].nunique() > 1 else (lambda t: f"{t:%H:%M}Z")     # the date too when the log has several days
    # bands that stayed wide open the whole time they could be judged
    steady = [b for b, d in g.groupby("band") if len(d) >= 4 and d["share"].min() >= 0.9]
    steady = sorted(steady, key=lambda b: _rank(b), reverse=True)
    if steady:
        names = ", ".join(steady[:-1]) + (" and " if len(steady) > 1 else "") + steady[-1]
        notes.append((f"{names} stayed above 90% the whole time.", "Nearly every station that heard WSPR near you would have heard a signal like yours."))
    # the bands you spent most contacts on: were you there when it looked best?
    totals = grid.groupby("band")["contacts"].sum().sort_values(ascending=False)
    for band in totals.index[:3]:
        n = int(totals[band])
        d = g[g["band"] == band]
        worked = d[d["contacts"] > 0]
        if n < 5 or worked.empty or len(d) < 3 or band in steady:      # too few boxes to say anything, or already called wide open
            continue
        avg = float(np.average(worked["share"], weights=worked["contacts"]))
        top = d.loc[d["share"].idxmax()]
        if d["share"].max() - d["share"].min() < STEADY_SPREAD:
            notes.append((f"{band} stayed steady.", f"It sat at about {_pc(avg)} the whole time you were on it ({n} contacts)."))
        elif top["share"] - avg >= BIG_CHANGE:
            notes.append((f"{band} was higher at other times.", f"It averaged {_pc(avg)} during your {n} contacts and reached {_pc(top['share'])} in the "
                                                                f"half hour from {when(top['slot'])}. The receivers heard can change over a session."))
        else:
            notes.append((f"{band} averaged {_pc(avg)} during your contacts.", f"That is {n} contacts. The session peak was {_pc(top['share'])}."))
    # bands that rose or fell, in the longest stretch of activity
    if len(g):
        panel = g.groupby("panel").size().idxmax()
        moves = []
        for band, d in g[g["panel"] == panel].sort_values("slot").groupby("band"):
            if len(d) >= 4:
                start, end = float(d["share"].iloc[:2].mean()), float(d["share"].iloc[-2:].mean())
                if abs(end - start) >= BIG_CHANGE:
                    moves.append((abs(end - start), band, start, end))
        for _, band, start, end in sorted(moves, reverse=True)[:2]:
            notes.append((f"{band} was {'improving' if end > start else 'fading'}:", f"from about {_pc(start)} at the start to about {_pc(end)} by the end."))
    return notes[:max_lines]
