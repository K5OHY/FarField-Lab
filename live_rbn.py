"""Today's RBN spots, from the live collector (collector/rbn_service.py) when one has been set up.

RBN's daily file does not exist until the UTC day is over, so today's spots have to come from somewhere else. The collector listens to RBN's live
feed all day on a small always-on machine and answers "the spots of this callsign today". This module asks it. With no collector set up (no
address in the settings) nothing here does anything, and the app works as it always has.

The address is LIVE_RBN_URL, in the environment or in Streamlit's secrets; LIVE_RBN_KEY is the key, if the collector has one.
"""
import os
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

TIMEOUT = 25


def _setting(name):
    value = os.environ.get(name)
    if not value:
        try:
            value = st.secrets.get(name)
        except Exception:                      # no secrets file, which is the normal case on a computer
            value = None
    return (value or "").strip()


def base_url():
    return _setting("LIVE_RBN_URL").rstrip("/")


def _headers():
    key = _setting("LIVE_RBN_KEY")
    return {"X-Api-Key": key, "Accept-Encoding": "gzip"} if key else {"Accept-Encoding": "gzip"}


@st.cache_data(show_spinner=False, ttl=60)
def _healthy(url):
    """Whether the collector at `url` answers and is connected to the feed. Looked at once a minute, so a page redraw costs nothing."""
    try:
        r = requests.get(url + "/health", timeout=8)
        return r.ok and bool(r.json().get("connected"))
    except Exception:
        return False


def available():
    """True when a collector is set up and working, so today can be offered."""
    url = base_url()
    return bool(url) and _healthy(url)


def today():
    return datetime.now(timezone.utc).date()


def fetch(call, day):
    """(spots, note) for `call` on the UTC day `day`: the spots as a table like the daily file's (spotter, freq, band, dx, mode, snr, time,
    speed, tx_mode), and a sentence about what may be missing, or None when the whole day so far was collected."""
    url = base_url()
    if not url:
        raise RuntimeError("Today's spots are not available: no live collector is set up.")
    try:
        r = requests.get(f"{url}/spots", params={"call": call, "date": f"{day:%Y-%m-%d}"}, headers=_headers(), timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"The live collector did not answer ({type(exc).__name__}). Try again in a minute, or paste your spots from reversebeacon.net.") from exc
    if not r.ok:
        try:
            why = r.json().get("error", "")
        except ValueError:
            why = ""
        raise RuntimeError(f"The live collector said no ({r.status_code}{': ' + why if why else ''}).")
    body = r.json()
    df = pd.DataFrame(body["rows"], columns=body["columns"]).rename(columns={"callsign": "spotter", "db": "snr", "date": "time"})
    df["snr"] = pd.to_numeric(df["snr"], errors="coerce")
    df["freq"] = pd.to_numeric(df["freq"], errors="coerce")
    df["time"] = pd.to_datetime(df["time"])
    return df, coverage_note(body, day)


def _hm(stamp):
    return stamp[11:16]


def coverage_note(body, day):
    """What may be missing from a day collected live: spots from before the collector began that day, and any breaks in its connection.
    None when the day so far was collected without a break."""
    if not body.get("covered"):
        return f"The live collector has no record of {day:%d %b}, so there may be spots missing."
    parts = []
    if body.get("collected_from"):
        parts.append(f"the live collector only began listening at {_hm(body['collected_from'])} UTC, so spots before that are missing")
    gaps = body.get("gaps") or []
    if gaps:
        shown = ", ".join(f"{_hm(a)}–{_hm(b)}" for a, b in gaps[:4]) + (f" and {len(gaps) - 4} more" if len(gaps) > 4 else "")
        parts.append(f"it lost its connection to RBN between {shown} UTC, so spots are missing then")
    if not parts:
        return None
    return f"Spots for {day:%d %b} come from RBN's live feed: " + "; ".join(parts) + ". The complete list is in RBN's daily file the next day."
