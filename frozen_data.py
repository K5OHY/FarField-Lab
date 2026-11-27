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
