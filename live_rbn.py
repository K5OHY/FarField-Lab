"""Today's RBN spots, from a live collector (collector/rbn_service.py).

RBN's daily file does not exist until the UTC day is over, so today's spots have to come from somewhere else. A collector listens to RBN's
live feed all day and answers "the spots of this callsign today". This module gets them in one of two ways:

* from a collector somewhere else (an always-on machine; see collector/SETUP.md), when its address is set: LIVE_RBN_URL, in the environment
  or in Streamlit's secrets, and LIVE_RBN_KEY, the key, if it has one;
* from a collector inside the app itself, when the app is running on your own computer and no address is set. The first time, the sidebar asks
  for your own callsign to log in to the feed with (nothing connects until you give it), and remembers it. It keeps what it hears in a small file
  in the local app-data folder, so it has the spots from the time the app was started (the page says so). Set LIVE_RBN_LOCAL=0 to switch that
  off, or LIVE_RBN_CALL to give the callsign without being asked.

With neither, nothing here does anything, and the app works as it always has.
"""
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from ui_common import running_locally

TIMEOUT = 25
STARTING_SECONDS = 30      # a collector that has only just been started counts as there while it is still connecting


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


# ---------------------------------------------------------------- the collector inside the app

def _service():
    """The collector's own module (collector/rbn_service.py), loaded when it is first needed."""
    folder = str(Path(__file__).resolve().parent / "collector")
    if folder not in sys.path:
        sys.path.insert(0, folder)
    import rbn_service
    return rbn_service


def _db_path():
    """Where the inside collector keeps its spots: the local app-data folder, never the project folder (which may be synced to a cloud
    drive, and a file written to all day would be synced all day)."""
    custom = os.environ.get("LIVE_RBN_DB")
    if custom:
        return Path(custom)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "FarFieldLab" / "live_rbn.db"


class _Inside:
    """The collector running inside this app: one for the whole app, however many pages and visitors, started when a callsign is known."""

    def __init__(self):
        self.lock = threading.Lock()
        self.store = None
        self.collector = None
        self.call = ""

    def ensure(self, call):
        """Make sure a collector is listening. One that is already running is left alone, whatever callsign is on the page: it logs in
        once, as the callsign it was started with, and a callsign looked up later does not restart it (that would break the day's record)."""
        with self.lock:
            if self.collector is not None and self.collector.is_alive():
                return self
            svc = _service()
            if self.store is None:
                path = _db_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                self.store = svc.Store(path)
                self.store.prune()
            self.collector = svc.Collector(self.store, call)
            self.collector.start()
            self.call = call
        return self


@st.cache_resource(show_spinner=False)
def _inside():
    return _Inside()


def _local_enabled():
    """True when the app is on your own computer, no collector elsewhere has been named, and it has not been switched off."""
    return running_locally() and not base_url() and _setting("LIVE_RBN_LOCAL").lower() not in ("0", "false", "no", "off")


def _call_file():
    """The callsign confirmed for the live feed is kept beside the spots: on this computer only, outside the project folder."""
    return _db_path().with_name("live_call.txt")


def _saved_call():
    try:
        return _call_file().read_text(encoding="utf-8").strip().upper()
    except OSError:
        return ""


def _valid(call):
    try:
        return bool(_service().CALL_RE.match(call))
    except Exception:
        return False


def _local_call():
    """The callsign to log in with: LIVE_RBN_CALL if set, else the one the person confirmed in the sidebar. Empty if neither: the app never
    guesses one (a callsign typed on a page may be someone else's, looked up). Only used to start the collector, so looking up another
    callsign afterwards does not change it."""
    call = (_setting("LIVE_RBN_CALL") or _saved_call()).strip().upper()
    return call if _valid(call) else ""


def _confirm():
    """The sidebar's Start button: keep the callsign that was typed, if it is one."""
    ss = st.session_state
    call = (ss.get("live_call_in") or "").strip().upper()
    if not _valid(call):
        ss["live_call_error"] = "That does not look like a callsign."
        return
    ss.pop("live_call_error", None)
    try:
        path = _call_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(call, encoding="utf-8")
    except OSError:
        ss["live_call_error"] = "Could not save it on this computer."


def _local_ready():
    """True when a collector inside the app is listening (or has only just been started and is still connecting)."""
    if not _local_enabled():
        return False
    inside = _inside()
    if inside.collector is None or not inside.collector.is_alive():
        call = _local_call()
        if not call:
            return False
        try:
            inside.ensure(call)
        except Exception:
            return False
    collector = inside.collector
    return collector.is_alive() and (collector.connected or time.time() - collector.started < STARTING_SECONDS)


def status_line():
    """A sentence for the sidebar about the collector inside the app, or None when there is none (not on your own computer, a collector
    elsewhere is in use, or it is switched off)."""
    if not _local_enabled():
        return None
    if not _local_ready():
        return None
    collector = _inside().collector
    if not collector.connected:
        return "Connecting to RBN's live feed to collect today's spots."
    since = datetime.fromtimestamp(collector.started, timezone.utc)
    return f"Collecting today's RBN spots for {collector.call} while this app is open (since {since:%H:%M} UTC)."


def sidebar():
    """What the sidebar shows about today's spots when the app is on your own computer: the one-time question (your own callsign, to log in
    with) until it is answered, then a line saying the collector is running and since when. Nothing when there is no collector here."""
    if not _local_enabled():
        return
    inside = _inside()
    running = inside.collector is not None and inside.collector.is_alive()
    if not running and not _local_call():
        st.caption(":material/sensors: To show today's spots, this app can listen to RBN's live feed while it is open. It logs in with your own callsign.")
        st.session_state.setdefault("live_call_in", st.session_state.get("callsign_in", ""))
        st.text_input("Your callsign for the live feed", key="live_call_in", max_chars=14)
        st.button("Start collecting today's spots", key="live_call_go", on_click=_confirm, width="stretch")
        if st.session_state.get("live_call_error"):
            st.caption(st.session_state["live_call_error"])
        return
    line = status_line()
    if line:
        st.caption(f":material/sensors: {line}")


# ---------------------------------------------------------------- asking for the spots

def available():
    """True when a collector is set up and working, so today can be offered."""
    url = base_url()
    if url:
        return _healthy(url)
    return _local_ready()


def today():
    return datetime.now(timezone.utc).date()


def _frame(body):
    """The collector's answer as a table like the daily file's: spotter, freq, band, dx, mode, snr, time, speed, tx_mode."""
    df = pd.DataFrame(body["rows"], columns=body["columns"]).rename(columns={"callsign": "spotter", "db": "snr", "date": "time"})
    df["snr"] = pd.to_numeric(df["snr"], errors="coerce")
    df["freq"] = pd.to_numeric(df["freq"], errors="coerce")
    df["time"] = pd.to_datetime(df["time"])
    return df


def fetch(call, day):
    """(spots, note) for `call` on the UTC day `day`: the spots as a table like the daily file's (spotter, freq, band, dx, mode, snr, time,
    speed, tx_mode), and a sentence about what may be missing, or None when the whole day so far was collected."""
    url = base_url()
    if url:
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
    elif _local_enabled() and _inside().store is not None:
        body = _service().spots_answer(_inside().store, call.upper(), day)
    else:
        raise RuntimeError("Today's spots are not available: no live collector is set up.")
    return _frame(body), coverage_note(body, day)


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
