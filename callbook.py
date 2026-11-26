"""Where a station is, for stations the log gives no grid square for and that are outside North America (North America is placed by the log's state, as before).

Two kinds of answer come from HamQTH.com's public data service (data provided by HamQTH.com):

  'area'  the call's own region, from HamQTH's DXCC tables: Kinki or Kanto, not just 'Japan'; a state of Brazil or Australia; an oblast of Russia. It needs no
          account. It is a region's centre, so it is a rough place, a good deal better than the centre of a country.
  'home'  the station's own home position from the HamQTH callbook, when the person running the app has put a HamQTH API key in the app's settings (the secret is
          called HAMQTH_API_KEY). It is only ever shown as the centre of its 4 character grid square, like every other station's home. Without the key nothing here
          changes except that this is skipped.

The key is sent in a header to HamQTH and nowhere else: never in an address, a message, a log line or a saved file. A portable callsign (EA8/DF4UE, W1AW/P) is placed by
the area of the whole callsign, because a callbook entry is the operator's home, not where the portable station was.

Nothing here raises: a call that cannot be found is simply left out, and the caller falls back to the centre of the country. Answers are saved in the disk cache (an
area for good, a home for the cache's usual life), and a miss is remembered for an hour so the same call is not asked twice."""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

import disk_cache

API = "https://www.hamqth.com/api/v2"
HEADERS = {"User-Agent": "FarField-Lab (personal project)", "Accept": "application/json"}
TIMEOUT = 12
ATTRIBUTION = "Station locations: data provided by HamQTH.com"
_CALL = re.compile(r"^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,4}[A-Z](/[A-Z0-9]{1,4})?$|^[A-Z0-9]{1,4}/[A-Z0-9]{3,8}(/[A-Z0-9]{1,4})?$")

_RECENT = {}                  # call -> (answer, when): kept for an hour
RECENT_SECONDS = 3600
_KEY_REFUSED = False          # a key HamQTH has said is not valid is not tried again while the app runs, so the user is not locked out for trying


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
    """The HamQTH API key from the environment or the app's secrets ('' when there is none)."""
    return _setting("HAMQTH_API_KEY")


def key_in_use():
    """True when a key is set and has not been refused, so the callbook will be asked."""
    return bool(api_key()) and not _KEY_REFUSED


def plausible(call):
    """True when `call` looks like an amateur callsign, so nothing else is ever sent to the service."""
    return bool(_CALL.match(str(call).strip().upper()))


def _get(path, params=None, auth=False):
    """One request. Returns (status code, parsed JSON or None). The key goes only in the Authorization header."""
    headers = dict(HEADERS)
    if auth:
        headers["Authorization"] = "Bearer " + api_key()
    try:
        resp = requests.get(f"{API}/{path}", params=params, headers=headers, timeout=TIMEOUT)
    except requests.RequestException:
        return 0, None
    try:
        return resp.status_code, (resp.json() if resp.content else None)
    except ValueError:
        return resp.status_code, None


def _number(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def area_of(call):
    """The call's own region from HamQTH's DXCC tables, as {'lat', 'lon', 'source': 'area', 'where': 'Japan (Kinki)'}, or None."""
    status, data = _get("dxcc", {"callsign": call})
    if status != 200 or not isinstance(data, dict):
        return None
    lat, lon = _number(data.get("lat")), _number(data.get("lon"))
    if lat is None or lon is None:
        entity = data.get("entity") or {}
        lat, lon = _number(entity.get("lat")), _number(entity.get("lon"))
    if lat is None or lon is None:
        return None
    details = [p.strip() for p in str(data.get("details") or "").split(",") if p.strip()]
    place = details[0] if details else ""                                  # the country (or entity) and, when the second part names a region (it has a bracket), the region: never
    if len(details) > 1 and "(" in details[1]:                             # the licence class or a name that HamQTH sometimes adds after them
        place += ", " + details[1]
    return {"lat": lat, "lon": lon, "source": "area", "where": place or str((data.get("entity") or {}).get("name") or "")}


def home_of(call):
    """The station's home from the HamQTH callbook, as {'lat', 'lon', 'source': 'home', 'where': grid}, or None. Needs a key; a refused key is remembered."""
    global _KEY_REFUSED
    status, data = _get(f"callbook/{call}", {"app": "FarField-Lab"}, auth=True)
    if status in (401, 403):
        _KEY_REFUSED = True                              # revoked or mistyped: do not keep asking
        return None
    if status != 200 or not isinstance(data, dict):
        return None
    loc = data.get("location") or {}
    lat, lon = _number(loc.get("lat")), _number(loc.get("lon"))
    if lat is None or lon is None:
        return None
    return {"lat": lat, "lon": lon, "source": "home", "where": str(loc.get("grid") or "")}


def _saved(kind, call):
    hit = disk_cache.get_frame(kind, call)
    if hit and len(hit[0]):
        row = hit[0].iloc[0]
        return {"lat": float(row["lat"]), "lon": float(row["lon"]), "source": str(row["source"]), "where": "" if pd.isna(row["where"]) else str(row["where"])}
    return None


def _save(kind, call, found):
    disk_cache.put_frame(kind, call, pd.DataFrame([found]))


def locate(call):
    """The best place HamQTH gives for one callsign: the callbook home when there is a key and the call is not portable, else the call's area; None when neither is
    known or the service cannot be reached."""
    call = str(call).strip().upper()
    if not plausible(call):
        return None
    portable = "/" in call
    if key_in_use() and not portable:
        saved = _saved("hqhome", call)
        if saved:
            return saved
    area = _saved("hqarea", call)
    recent = _RECENT.get(call)
    if not area and recent and time.time() - recent[1] < RECENT_SECONDS:
        return recent[0]
    if key_in_use() and not portable:
        home = home_of(call)
        if home:
            _save("hqhome", call, home)
            _RECENT[call] = (home, time.time())
            return home
    if not area:
        area = area_of(call)
        if area:
            _save("hqarea", call, area)
    _RECENT[call] = (area, time.time())
    return area


def load_places(calls, workers=8):
    """{call: {'lat', 'lon', 'source', 'where'}} for every call HamQTH can place; calls it cannot are left out. A few requests run at once. Never raises."""
    calls = list(dict.fromkeys(str(c).strip().upper() for c in calls if str(c).strip()))
    if not calls:
        return {}

    def one(call):
        try:
            return call, locate(call)
        except Exception:
            return call, None

    with ThreadPoolExecutor(max_workers=min(workers, len(calls))) as pool:
        found = list(pool.map(one, calls))
    return {call: place for call, place in found if place}
