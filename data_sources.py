"""Getting spots and skimmer locations: the RBN daily download and pasted rows, WSPR from wspr.live, and the skimmer list."""
import time
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests
import streamlit as st

import disk_cache
import example_data
from conditions import fetch_nearby
from log_check import _NORTH_AMERICA, finish_place, listening_from_zip
from wspr_data import HEADERS
from rbn_data import country_location, get_band, load_skimmers, lookup_callsign_location, maidenhead_to_latlon, refresh_skimmer_cache
from wspr_data import clean_callsign, fetch_listening, fetch_wspr_spots, grid_from_spots, latest_tx_grid


# ----------------------------------------------------------------- data loading

def rbn_day_zip(date):
    """The bytes of one day's RBN history file (date as YYYYMMDD), from the disk cache or downloaded."""
    raw = disk_cache.get_bytes("rbnzip", date)  # a day's file never changes once published, and it serves every callsign
    if raw is None:
        resp = requests.get(f"https://data.reversebeacon.net/rbn_history/{date}.zip", timeout=180)
        if resp.status_code == 404:
            raise RuntimeError(f"RBN has no data file for {date} yet. Try an earlier date.")
        resp.raise_for_status()
        raw = resp.content
        disk_cache.put_bytes("rbnzip", date, raw)
    return raw


@st.cache_data(show_spinner=False, ttl=3600)
def download_rbn_day(date, callsign):
    """Download one day of RBN history and keep only spots of `callsign` (streamed, never written to disk)."""
    raw = rbn_day_zip(date)

    with zipfile.ZipFile(BytesIO(raw)) as z:
        name = next((n for n in z.namelist() if n.endswith(".csv")), None)
        if name is None:
            raise RuntimeError("No CSV file found in the RBN ZIP archive")
        with z.open(name) as f:
            parts = [c[c["dx"] == callsign] for c in pd.read_csv(f, chunksize=500_000)]

    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    df = df.rename(columns={"callsign": "spotter", "db": "snr", "date": "time"})
    df["snr"] = pd.to_numeric(df["snr"], errors="coerce")
    df["freq"] = pd.to_numeric(df["freq"], errors="coerce")
    df["time"] = pd.to_datetime(df["time"])
    if "band" not in df.columns:
        df["band"] = df["freq"].apply(get_band)
    return df


# A row copied from the RBN spots page:
#   K1RA-4  K5OHY  DM81wx  1443 mi  14073.0  CW  CQ  7 dB  25 wpm  1908z 26 Sep  94 seconds ago
PASTE_ROW_RE = re.compile(
    r"^\W*(?P<spotter>[A-Z0-9/-]+)\s+(?P<dx>[A-Z0-9/-]+)\s+(?:[A-R]{2}\d{2}\w*\s+)?"
    r"(?:[\d,.]+\s*(?:mi|km)\s+)?(?P<freq>\d+\.\d+)\s+(?P<tx>\S+)\s+(?P<kind>\S+)\s+(?P<snr>-?\d+)\s*dB\b"
    r"(?:.*?\b(?P<speed>\d+)\s*wpm\b)?.*?(?P<time>\d{4})z\s+(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]{3})",
    re.IGNORECASE,
)


def parse_pasted_data(text):
    """Parse rows copied from the RBN spots web page (header lines and trailing 'seen' column are ignored)."""
    year = datetime.now(timezone.utc).year
    rows, unread = [], []
    for line in filter(None, (l.strip() for l in text.splitlines())):
        m = PASTE_ROW_RE.match(line)
        if not m:
            if "spotter" not in line.lower():  # the copied header row is expected, anything else isn't
                unread.append(line)
            continue
        try:
            when = datetime.strptime(f"{year} {m['time']}z {m['day']} {m['month'].title()}", "%Y %H%Mz %d %b")
            speed = float(m["speed"]) if m["speed"] else float("nan")
            rows.append([m["spotter"].upper(), m["dx"].upper(), float(m["freq"]), float(m["snr"]), when, speed, m["tx"].upper(), m["kind"].upper()])
        except ValueError:
            unread.append(line)
    if not rows:
        raise RuntimeError("Couldn't read any spot rows from the pasted text."
                           + (f" The first line I couldn't read was: {unread[0][:120]!r}" if unread else ""))
    df = pd.DataFrame(rows, columns=["spotter", "dx", "freq", "snr", "time", "speed", "tx_mode", "mode"])   # the names the daily file uses
    df["band"] = df["freq"].apply(get_band)
    return df


@st.cache_data(show_spinner=False, ttl=3600)
def skimmer_data():
    """Check hourly whether the skimmer list is stale (it only re-downloads if >24h old), so a
    long-running server keeps itself up to date. Returns (skimmers, status message)."""
    _, msg = refresh_skimmer_cache()
    return load_skimmers(), msg


def resolve_home(callsign, grid_override, skimmers, spot_grid=None):
    """Return (lat, lon, label) for the map pin. In order: the grid typed in, the grid the station's own WSPR spots report (`spot_grid`),
    then a lookup of the callsign. The lookup ends at the centre of the country, which can be hundreds of km off, so it is the last resort."""
    if grid_override.strip():
        grid = grid_override.strip()
        lat, lon = maidenhead_to_latlon(grid)
        return lat, lon, f"{grid[:2].upper()}{grid[2:]} (manual)"
    if spot_grid:
        lat, lon = maidenhead_to_latlon(spot_grid)
        return lat, lon, f"{spot_grid} from your WSPR spots"
    found = lookup_callsign_location(callsign, skimmers)
    if not found:
        raise RuntimeError(
            f"Couldn't find a location for {callsign}. Enter your grid square in the sidebar to place the pin.")
    lat, lon, grid, source = found
    if "approximate" in source:
        st.warning(f"No exact location found for {callsign}, so the pin is at the {source}. "
                   "Enter your grid square in the sidebar for an accurate map.")
    return lat, lon, f"{grid or f'{lat:.2f}, {lon:.2f}'} via {source}"


SETTLED_HOURS = 1  # wspr.live has everything for a period within minutes; an hour on is long past any late reports


def _settled(end):
    """True when a period ended long enough ago that nothing more will arrive for it, so what was fetched can be reused."""
    return pd.Timestamp(end) <= pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None)) - pd.Timedelta(hours=SETTLED_HOURS)


def load_wspr(tx_call, start, end):
    """WSPR spots from wspr.live. A period that has ended is remembered, because it will not change and wspr.live allows the whole
    site only 20 requests a minute. A period that reaches into the last hour is always fetched fresh, so a test you have only just
    sent is there."""
    key = f"{clean_callsign(tx_call)}|{pd.Timestamp(start):%Y-%m-%d %H:%M:%S}|{pd.Timestamp(end):%Y-%m-%d %H:%M:%S}"
    settled = _settled(end)
    if settled:
        hit = disk_cache.get_frame("wspr", key)
        if hit:
            return hit[0], bool(hit[1].get("truncated"))
    spots, truncated = fetch_wspr_spots(tx_call, start, end)
    if settled and len(spots.columns):
        disk_cache.put_frame("wspr", key, spots, {"truncated": bool(truncated)})
    return spots, truncated


@st.cache_data(show_spinner=False, ttl=60)
def load_listening(band, start, end):
    """Which receivers were decoding on `band` in each slot. Remembered for a minute because the screen redraws often. The
    saved examples carry their own copy, so they work without asking wspr.live."""
    saved = example_data.listening(band, start, end)
    if saved is not None:
        return saved
    key = f"{band}|{pd.Timestamp(start):%Y-%m-%d %H:%M:%S}|{pd.Timestamp(end):%Y-%m-%d %H:%M:%S}"
    settled = _settled(end)
    if settled:
        hit = disk_cache.get_frame("listening", key)
        if hit:
            return hit[0], bool(hit[1].get("truncated"))
    listening, truncated = fetch_listening(band, start, end)
    if settled and len(listening.columns):
        disk_cache.put_frame("listening", key, listening, {"truncated": bool(truncated)})
    return listening, truncated


def load_nearby(lat, lon, radius_km, start, end):
    """WSPR spots from every transmitter within `radius_km` of a point, as the Band conditions page uses them. Like load_wspr, a period
    that has ended is remembered on disk, because it will not change and wspr.live allows the whole site only 20 requests a minute."""
    key = f"{lat:.3f}|{lon:.3f}|{radius_km:.0f}|{pd.Timestamp(start):%Y-%m-%d %H:%M:%S}|{pd.Timestamp(end):%Y-%m-%d %H:%M:%S}"
    settled = _settled(end)
    if settled:
        hit = disk_cache.get_frame("nearby", key)
        if hit:
            return hit[0]
    spots, _ = fetch_nearby(lat, lon, radius_km, pd.Timestamp(start).to_pydatetime(), pd.Timestamp(end).to_pydatetime())
    if settled and len(spots.columns):
        disk_cache.put_frame("nearby", key, spots)
    return spots


@st.cache_data(show_spinner=False, ttl=3600)
def load_rbn_listening(days, start, end):
    """The skimmers that spotted anyone between two times: (band, slot of 15 minutes, callsign). `days` are the YYYYMMDD files to read."""
    frames = [listening_from_zip(rbn_day_zip(d), start, end) for d in days]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["band", "slot", "b"])


POTA_API = "https://api.pota.app"


def load_pota_park(ref):
    """POTA's record of a park, every activation listed for it, and its totals, from POTA's public data service: (park dict or None,
    activations as a table of call, date, total, cw, phone, data, and the totals dict or None). Only the park reference is sent. Raises
    RuntimeError when POTA cannot be reached (the totals alone failing is not an error: they are left out)."""
    def ask(url, params=None, timeout=20):
        for attempt in (1, 2):                    # one retry: a connection that is reset once usually works the second time
            try:
                resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
                resp.raise_for_status()
                return resp
            except requests.RequestException:
                if attempt == 2:
                    raise

    try:
        park = ask(f"{POTA_API}/park/{ref}")
        acts = ask(f"{POTA_API}/park/activations/{ref}", {"count": "all"}, 30)
        info, rows = (park.json() if park.content else None), (acts.json() or [])
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"POTA could not be reached ({exc.__class__.__name__}).") from exc
    try:
        totals = ask(f"{POTA_API}/park/stats/{ref}").json()
        totals = totals if isinstance(totals, dict) and "contacts" in totals else None
    except (requests.RequestException, ValueError):
        totals = None
    table = pd.DataFrame({"call": [str(r.get("activeCallsign", "")) for r in rows],
                          "date": pd.to_datetime([str(r.get("qso_date", "")) for r in rows], format="%Y%m%d", errors="coerce"),
                          "total": [int(r.get("totalQSOs") or 0) for r in rows], "cw": [int(r.get("qsosCW") or 0) for r in rows],
                          "phone": [int(r.get("qsosPHONE") or 0) for r in rows], "data": [int(r.get("qsosDATA") or 0) for r in rows]})
    return (info if isinstance(info, dict) and info.get("reference") else None), table.dropna(subset=["date"]).reset_index(drop=True), totals


SOTA_API = "https://api2.sota.org.uk/api"


def load_sota_summit(ref):
    """SOTA's record of a summit and every activation listed for it, from SOTA's public data service: (summit dict or None, activations as a table of
    call, date, total, cw, phone, data (SOTA gives the QSOs of an activation, not the modes, so the mode columns are 0), and None). Only the
    summit reference is sent. Raises RuntimeError when SOTA cannot be reached."""
    def ask(url):
        for attempt in (1, 2):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=30)
                resp.raise_for_status()
                return resp
            except requests.RequestException:
                if attempt == 2:
                    raise

    try:
        summit = ask(f"{SOTA_API}/summits/{ref}").json()
        rows = ask(f"{SOTA_API}/activations/{ref}").json() or []
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f"SOTA could not be reached ({exc.__class__.__name__}).") from exc
    dates = pd.to_datetime([str(r.get("activationDate", "")) for r in rows], utc=True, errors="coerce")
    table = pd.DataFrame({"call": [str(r.get("ownCallsign", "")) for r in rows], "date": dates.tz_localize(None).normalize() if len(rows) else pd.to_datetime([]),
                          "total": [int(r.get("qsos") or 0) for r in rows]}).assign(cw=0, phone=0, data=0)
    return (summit if isinstance(summit, dict) and summit.get("summitCode") else None), table.dropna(subset=["date"]).reset_index(drop=True), None


_REF_PLACES = {}              # park or summit reference -> (lat, lon, name) or None: kept for as long as the app runs, so a reference is asked for once


def load_reference_places(pota_refs=(), sota_refs=(), workers=8):
    """Where the parks and summits are, for contacts made with another activator: {reference: (lat, lon, name)}, from POTA's and SOTA's public data services, one small request
    for each reference (only the reference is sent). A reference that cannot be found or reached is left out, and nothing here raises, so a contact is then placed by its
    state or country as before."""
    from concurrent.futures import ThreadPoolExecutor

    def ask(ref, kind):
        if ref in _REF_PLACES:
            return ref, _REF_PLACES[ref]
        url = f"{POTA_API}/park/{ref}" if kind == "POTA" else f"{SOTA_API}/summits/{ref}"
        point = None
        for attempt in (1, 2):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
                data = resp.json() if resp.content else None
                if isinstance(data, dict) and data.get("latitude") is not None and data.get("longitude") is not None:
                    point = (float(data["latitude"]), float(data["longitude"]), str(data.get("name") or data.get("summitName") or data.get("title") or ""))
                break
            except (requests.RequestException, ValueError, TypeError):
                if attempt == 2:
                    return ref, None                      # not remembered: it may work next time
        _REF_PLACES[ref] = point
        return ref, point

    jobs = [(r, "POTA") for r in dict.fromkeys(pota_refs)] + [(r, "SOTA") for r in dict.fromkeys(sota_refs)]
    if not jobs:
        return {}
    with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
        found = list(pool.map(lambda job: ask(*job), jobs))
    return {ref: point for ref, point in found if point}


_RECENT = {}                  # callsign -> (answer, when it was asked): misses and guesses are kept for an hour, so a band is never asked twice
RECENT_SECONDS = 3600


def _found(call, skimmers):
    """One callsign's lookup (lat, lon, grid, source), from the disk cache when an exact answer was saved, else asked of the
    FCC and HamDB. Only exact answers are saved on disk: a guess at the country's centre should be asked again next time. Whatever was
    answered, a miss included, is remembered in memory for an hour, so the lookups started in the background are not repeated."""
    hit = disk_cache.get_frame("callloc", call)
    if hit and len(hit[0]):
        row = hit[0].iloc[0]
        return float(row["lat"]), float(row["lon"]), None if pd.isna(row["grid"]) else row["grid"], str(row["source"])
    recent = _RECENT.get(call)
    if recent and time.time() - recent[1] < RECENT_SECONDS:
        return recent[0]
    found = lookup_callsign_location(call, skimmers)
    if found is not None and not str(found[3]).startswith("center of"):
        disk_cache.put_frame("callloc", call, pd.DataFrame([{"lat": found[0], "lon": found[1], "grid": found[2], "source": found[3]}]))
    _RECENT[call] = (found, time.time())
    return found


def _place_without_lookup(call, state, country, dx_places=None):
    """A contact the FCC and HamDB cannot know about (the log says it is outside North America), or None. It is placed from `dx_places` ({call: {'lat', 'lon', 'source',
    'where'}} from callbook.load_places) when that has it: its HamQTH home as the centre of its 4 character grid square, or its call area; failing that at the centre of
    its country. Asking the FCC and HamDB about a European callsign only costs the time of two failed requests."""
    known = (dx_places or {}).get(call)
    if known and known["source"] == "home":
        return finish_place((known["lat"], known["lon"], None, "HamQTH callbook"), state, country)
    if known:
        return {"lat": known["lat"], "lon": known["lon"], "source": "HamQTH call area" + (f", {known['where']}" if known.get("where") else ""), "level": "area", "grid": ""}
    guess = country_location(call)
    return finish_place((guess[0], guess[1], None, f"center of {guess[2]}") if guess else None, state, country)


def _place_from_log_grid(call, state, country, grids):
    """A contact placed from the grid square the log itself gives (the centre of its 4 character square, so a street is never drawn), or None."""
    from rbn_data import maidenhead_to_latlon
    grid = str((grids or {}).get(call, "")).strip()
    if len(grid) < 4:
        return None
    for size in (8, 6, 4):
        if len(grid) >= size:
            try:
                lat, lon = maidenhead_to_latlon(grid[:size])
            except ValueError:
                continue
            return finish_place((lat, lon, grid[:size], "grid square in the log"), state, country)
    return None


def load_contact_places(rows, skimmers, progress=None, workers=6, grids=None, dx_places=None):
    """Where each station in a log was, as a table indexed by call (lat, lon, level, source, grid). `rows` is a list of
    (call, state, country). Exact answers are shown at the centre of the 4 character grid square, a miss falls back to the centre of
    the state in the log, and a call that cannot be placed at all is left out. Stations the log puts outside North America are placed at
    the centre of their country without a lookup. `grids` maps a call to the grid square the log gives it: such a contact is placed from that, with no
    lookup at all. `dx_places` is callbook.load_places' answer for the stations outside North America. A few lookups run at once; `progress(done, total)` is called as they finish."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    done, out = 0, {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for call, state, country in rows:
            from_log = _place_from_log_grid(call, state, country, grids)
            if from_log:
                out[call] = from_log
                done += 1
            elif country in _NORTH_AMERICA:
                futures[pool.submit(_found, call, skimmers)] = (call, state, country)
            else:
                placed = _place_without_lookup(call, state, country, dx_places)
                if placed:
                    out[call] = placed
                done += 1
        if progress and done:
            progress(done, len(rows))
        for future in as_completed(futures):
            call, state, country = futures[future]
            try:
                placed = finish_place(future.result(), state, country)
            except Exception:
                placed = finish_place(None, state, country)
            if placed:
                out[call] = placed
            done += 1
            if progress:
                progress(done, len(rows))
    table = pd.DataFrame.from_dict(out, orient="index", columns=["lat", "lon", "source", "level", "grid"]) if out else pd.DataFrame(
        columns=["lat", "lon", "source", "level", "grid"])
    table.index.name = "call"
    return table
