"""NASA's DONKI (Space Weather Database Of Notifications, Knowledge, Information): the geomagnetic storms, coronal mass ejections and flares of a stretch of days, with the links NASA
records between them (a storm linked to the CMEs that caused it, a CME linked to the flare it came with, the interplanetary shock that reached Earth; the flare itself is then found in NOAA's list by its time). The Log page uses it to say
why a storm happened. It needs a free NASA API key (api.nasa.gov) in `NASA_API_KEY`, in the environment or the app's secrets; without one NASA's shared DEMO_KEY is used, which is
limited to a few requests an hour, so a stretch that has ended is kept on disk and asked for once. Only dates and the key are sent; the key goes nowhere else."""
import json
import os
from datetime import timedelta

import pandas as pd
import requests

from wspr_data import HEADERS

BASE = "https://api.nasa.gov/DONKI"
TIMEOUT = 25
KINDS = ("GST", "CME")        # NASA's flare list (FLR) is not used: its endpoint does not answer, and the flares come from NOAA's list through the HEK, matched by the time in the ID NASA links to
_REFUSED = False          # a key NASA has refused is not tried again while the app runs


def _setting(name):
    value = os.environ.get(name)
    if not value:
        try:
            import streamlit as st
            value = st.secrets.get(name)
        except Exception:                      # no secrets file, which is the normal case on a computer
            value = None
    return (value or "").strip()


def api_key():
    """The NASA API key from the environment or the app's secrets, else NASA's shared DEMO_KEY."""
    return _setting("NASA_API_KEY") or "DEMO_KEY"


def key_in_use():
    """True when the app has a key of its own (not the shared demo one) that NASA has not refused."""
    return bool(_setting("NASA_API_KEY")) and not _REFUSED


def _stamp(text):
    """A DONKI time ('2024-05-10T15:00Z') as a naive UTC timestamp, or None."""
    try:
        return pd.Timestamp(str(text).replace("Z", "")).tz_localize(None) if text else None
    except Exception:
        return None


def id_time(activity_id):
    """The time an activity ID begins with ('2024-05-10T16:36:00-IPS-001' is 16:36 UTC on 10 May), or None. A shock's arrival is read this way."""
    return _stamp(str(activity_id or "")[:19])


def _fetch(kind, start, end):
    """The raw list DONKI gives for one kind of event over whole days, or None when it could not be read (no connection, a refused key, the request limit). A stretch that
    ended more than two days ago will not change, so its answer is kept on disk."""
    global _REFUSED
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    key = f"{kind}-{start:%Y%m%d}-{end:%Y%m%d}"
    settled = end < pd.Timestamp.now("UTC").tz_localize(None) - timedelta(days=2)
    try:
        import disk_cache
        raw = disk_cache.get_bytes("donki", key) if settled else None
        if raw is None:
            resp = requests.get(f"{BASE}/{kind}", params={"startDate": f"{start:%Y-%m-%d}", "endDate": f"{end:%Y-%m-%d}", "api_key": api_key()}, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code in (401, 403):
                _REFUSED = _REFUSED or bool(_setting("NASA_API_KEY"))
                return None
            if resp.status_code == 429:
                return None
            resp.raise_for_status()
            body = resp.json()
            if not isinstance(body, list):
                return None
            raw = json.dumps(body).encode("utf-8")
            if settled:
                disk_cache.put_bytes("donki", key, raw)
        return json.loads(raw)
    except Exception:
        return None


def parse_storms(raw):
    """[{id, start, kp: [(time, Kp)], max_kp, max_time, linked: [activity ids]}] from DONKI's geomagnetic storms."""
    out = []
    for e in raw or []:
        kp = sorted((_stamp(x.get("observedTime")), float(x["kpIndex"])) for x in e.get("allKpIndex") or [] if x.get("kpIndex") is not None and _stamp(x.get("observedTime")) is not None)
        top = max(kp, key=lambda p: p[1]) if kp else (None, None)
        out.append({"id": e.get("gstID"), "start": _stamp(e.get("startTime")), "kp": kp, "max_kp": top[1], "max_time": top[0], "linked": [x.get("activityID") for x in e.get("linkedEvents") or []]})
    return [s for s in out if s["start"] is not None]


def parse_cmes(raw):
    """[{id, start, speed, source, region, note, linked, arrivals}] from DONKI's CMEs: the speed is from the analysis NASA marks most accurate, and `arrivals` are the times
    its model gave for the shock reaching Earth (a prediction, not an observation)."""
    out = []
    for e in raw or []:
        analyses = e.get("cmeAnalyses") or []
        best = next((a for a in analyses if a.get("isMostAccurate")), analyses[0] if analyses else {})
        arrivals = sorted(t for t in (_stamp(m.get("estimatedShockArrivalTime")) for a in analyses for m in a.get("enlilList") or []) if t is not None)
        out.append({"id": e.get("activityID"), "start": _stamp(e.get("startTime")), "speed": best.get("speed"), "source": e.get("sourceLocation") or "",
                    "region": e.get("activeRegionNum"), "note": e.get("note") or "", "linked": [x.get("activityID") for x in e.get("linkedEvents") or []], "arrivals": arrivals})
    return [c for c in out if c["start"] is not None]


def events(start, end):
    """{'storms', 'cmes', 'own_key', 'storms_ok', 'cmes_ok', 'complete'} for the days from `start` to `end`, or None when neither the storms nor the CMEs could be read (the story then
    has no 'why'). CMEs are asked for from four days earlier, because an ejection leaves the Sun days before the storm it causes, so the cause of a storm is whole."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    storms_raw = _fetch("GST", start, end)
    cmes_raw = _fetch("CME", start - timedelta(days=4), end)
    if storms_raw is None and cmes_raw is None:
        return None
    return {"storms": parse_storms(storms_raw), "cmes": parse_cmes(cmes_raw), "own_key": key_in_use(),
            "storms_ok": storms_raw is not None, "cmes_ok": cmes_raw is not None, "complete": storms_raw is not None and cmes_raw is not None}
