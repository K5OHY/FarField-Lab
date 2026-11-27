"""Saved copies of the real RBN and WSPR data behind the example logs, so an example opens at once, shows the same thing every time and does not wait on the Reverse
Beacon Network or wspr.live. `build_log_examples.py` makes the files in `examples/log/`; `data_sources` asks this module first for the three things the Log page reads:
the spots of one callsign on one RBN day, the skimmers that were listening in a stretch, and the WSPR spots from transmitters near a place in a stretch. Each answer is
the one the live service gave, cut to the times asked for, and a question the saved data does not cover (another callsign, another place, another day) returns None and
goes to the live service as it always did. The data is history, so it does not change."""
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

DIR = Path(__file__).resolve().parent / "examples" / "log"
SLOT = "15min"                     # the length of a slot in the table of who was listening (data_sources.load_rbn_listening)


@lru_cache(maxsize=1)
def _entries():
    """[(key, meta)] for every saved example that has its saved data, in file order."""
    found = []
    for path in sorted(DIR.glob("*.frozen.json")):
        key = path.name[:-len(".frozen.json")]
        if (DIR / f"{key}_spots.csv.gz").exists() and (DIR / f"{key}_listening.csv.gz").exists() and (DIR / f"{key}_nearby.csv.gz").exists():
            found.append((key, json.loads(path.read_text(encoding="utf-8"))))
    return found


@lru_cache(maxsize=24)
def _frame(key, kind):
    time_col = "slot" if kind == "listening" else "time"
    return pd.read_csv(DIR / f"{key}_{kind}.csv.gz", parse_dates=[time_col], keep_default_na=False, na_values=[""])


def available():
    """The keys of the examples that carry saved data."""
    return [key for key, _ in _entries()]


def _open_example():
    """The key of the example log the visitor opened on the page, or None (outside a page, or a log of their own)."""
    try:
        import streamlit as st
        return st.session_state.get("log_example")
    except Exception:
        return None


def spots(day, callsign):
    """The spots of `callsign` on one RBN day (YYYYMMDD), as data_sources.download_rbn_day returns them, or None when no saved example holds them. Two examples can be cut
    from one day of one callsign (a day with two antennas), each with only its own stretch of spots, so the example that is open is asked first."""
    chosen = _open_example()
    for key, meta in sorted(_entries(), key=lambda e: e[0] != chosen):
        if meta["call"] == callsign and day in meta["days"]:
            frame = _frame(key, "spots")
            return frame[frame["time"].dt.strftime("%Y%m%d") == day].reset_index(drop=True)
    return None


def listening(days, start, end):
    """The (band, slot, b) table of skimmers that spotted anyone between `start` and `end`, as data_sources.load_rbn_listening returns it, or None when no saved example
    covers every day and the whole stretch."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    for key, meta in _entries():
        if set(days) <= set(meta["days"]) and pd.Timestamp(meta["listening_start"]) <= start and end <= pd.Timestamp(meta["listening_end"]):
            frame = _frame(key, "listening")
            keep = (frame["slot"] >= start.floor(SLOT)) & (frame["slot"] <= end)
            return frame[keep].reset_index(drop=True)[["band", "slot", "b"]]
    return None


def nearby(lat, lon, radius_km, start, end):
    """The WSPR spots from transmitters within `radius_km` of a place between two times (both ends included, as the live query does), or None when no saved example was
    made for this place and radius and holds the whole stretch."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    for key, meta in _entries():
        if (round(meta["lat"], 3), round(meta["lon"], 3), round(float(meta["radius_km"]))) != (round(lat, 3), round(lon, 3), round(float(radius_km))):
            continue
        if any(pd.Timestamp(a) <= start and end <= pd.Timestamp(b) for a, b in meta["nearby_covered"]):
            frame = _frame(key, "nearby")
            return frame[(frame["time"] >= start) & (frame["time"] <= end)].reset_index(drop=True)
    return None


# ------------------------------------------------------------------------------------------------------------------------------------------------------------ lookups
# The slow part of opening an example was not the RBN or WSPR data but the lookups the page makes about it: where each station worked was (FCC, HamDB and HamQTH, a request for
# each), the park or summit record (POTA, SOTA), the space weather (GFZ, NOAA, the HEK) and, for a storm, NASA. What the page derives from each is saved here, in
# `<key>.lookups.json.gz`, as {name: [{"args": [...], "value": ...}]}, and handed back only for the same arguments while that example is open, so a real log never gets one.
# What is saved is what the page keeps from a lookup (a station's place as the centre of its 4 character grid square, a park's public record, public space weather), not
# what the services answered: a HamQTH, FCC or HamDB reply is a person's record and none of it is kept.
import gzip
from io import StringIO

LOOKUP_NAMES = ("places", "dx_places", "reference_places", "pota_park", "sota_summit", "space_history", "donki_events")


def _enc(obj):
    """A value as plain JSON: a time, a tuple and a table are tagged so `_dec` can give them back as they were."""
    if isinstance(obj, pd.Timestamp):
        return {"__ts__": obj.isoformat()}
    if isinstance(obj, tuple):
        return {"__tuple__": [_enc(x) for x in obj]}
    if isinstance(obj, pd.DataFrame):
        dates = [c for c in obj.columns if str(obj[c].dtype).startswith("datetime")]
        return {"__df__": obj.to_json(orient="split", date_format="iso", index=True), "dates": dates, "index_name": obj.index.name}
    if isinstance(obj, dict):
        return {"__dict__": [[_enc(k), _enc(v)] for k, v in obj.items()]}          # keys may be times or tuples, which JSON object keys cannot be
    if isinstance(obj, (list, set)):
        return [_enc(x) for x in obj]
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):                   # a numpy number
        return obj.item()
    return obj


def _dec(obj):
    if isinstance(obj, dict):
        if "__ts__" in obj:
            return pd.Timestamp(obj["__ts__"])
        if "__tuple__" in obj:
            return tuple(_dec(x) for x in obj["__tuple__"])
        if "__df__" in obj:
            frame = pd.read_json(StringIO(obj["__df__"]), orient="split", convert_dates=False, dtype=False)
            for c in obj.get("dates") or []:
                frame[c] = pd.to_datetime(frame[c])
            frame.index.name = obj.get("index_name")
            return frame
        if "__dict__" in obj:
            return {_dec(k): _dec(v) for k, v in obj["__dict__"]}
    if isinstance(obj, list):
        return [_dec(x) for x in obj]
    return obj


def _norm(args):
    """Arguments in a form that compares the same whether they came from a file or from the page."""
    return json.dumps(_enc(list(args)), sort_keys=True, default=str)


def save_lookups(key, lookups, directory=None):
    """Writes {name: [(args tuple, value), ...]} as `<key>.lookups.json.gz` in `examples/log/` (or `directory`)."""
    body = {name: [{"args": _enc(list(args)), "value": _enc(value)} for args, value in entries] for name, entries in lookups.items()}
    with gzip.open((directory or DIR) / f"{key}.lookups.json.gz", "wt", encoding="utf-8") as f:
        json.dump(body, f)
    _lookups.cache_clear()


@lru_cache(maxsize=12)
def _lookups(key):
    path = DIR / f"{key}.lookups.json.gz"
    if not path.exists():
        return {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        body = json.load(f)
    return {name: [(_norm(_dec(e["args"])), e["value"]) for e in entries] for name, entries in body.items()}


def lookup(name, *args):
    """What the page derived from a lookup when the open example was made, for the same arguments, or None (no example open, no such lookup, other arguments: the page then
    looks it up as it always did). A copy is returned, so the page cannot change what is saved."""
    key = _open_example()
    if not key:
        return None
    wanted = _norm(args)
    for saved_args, value in _lookups(key).get(name, []):
        if saved_args == wanted:
            return _dec(json.loads(json.dumps(value)))
    return None


# ------------------------------------------------------------------------------------------------------------------------------------------------------------ results
# The two long calculations on a log (how open each band looked from the WSPR near the station, and the comparison of the skimmers with it) take most of the time an example takes to open,
# and their inputs are saved and never change, so their results are saved too, for the power and place the example was made with. They are tables with notes attached
# that JSON would only approximate, so they are kept as Python pickles in `<key>.results.pkl.gz`: files made by `build_log_examples.py` and read only from this repository's own folder.
import copy
import pickle


def save_results(key, results, directory=None):
    """Writes {name: [(args tuple, object), ...]} as `<key>.results.pkl.gz`."""
    body = {name: [(_norm(args), obj) for args, obj in entries] for name, entries in results.items()}
    with gzip.open((directory or DIR) / f"{key}.results.pkl.gz", "wb") as f:
        pickle.dump(body, f)
    _results.cache_clear()


@lru_cache(maxsize=12)
def _results(key):
    path = DIR / f"{key}.results.pkl.gz"
    if not path.exists():
        return {}
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


def result(name, *args):
    """A saved calculation for the same arguments (the power, place and radius it was made with) while that example is open, or None: the page then calculates it as it always did.
    A copy is returned, so the page cannot change what is saved."""
    key = _open_example()
    if not key:
        return None
    wanted = _norm(args)
    for saved_args, obj in _results(key).get(name, []):
        if saved_args == wanted:
            return copy.deepcopy(obj)
    return None
