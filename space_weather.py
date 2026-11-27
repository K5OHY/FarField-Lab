"""Current space weather from NOAA's Space Weather Prediction Center (free public feeds), and a short plain-English reading of it
for HF operators. The numbers are global, not specific to any path: the WSPR picture on the Band conditions page is what is
actually working near you, and this explains the why and gives an early warning of change."""
from datetime import datetime, timedelta

import pandas as pd
import requests

from wspr_data import HEADERS

SWPC = "https://services.swpc.noaa.gov"
FEEDS = {
    "flux": "/products/summary/10cm-flux.json",
    "kp": "/products/noaa-planetary-k-index.json",
    "scales": "/products/noaa-scales.json",
    "wind": "/products/summary/solar-wind-speed.json",
    "field": "/products/summary/solar-wind-mag-field.json",
    "xray": "/json/goes/primary/xrays-6-hour.json",
    "flux30": "/products/10cm-flux-30-day.json",
    "solar_text": "/text/daily-solar-indices.txt",
    "geo_text": "/text/daily-geomagnetic-indices.txt",
}


def _get(name, timeout=12):
    resp = requests.get(SWPC + FEEDS[name], headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text if FEEDS[name].endswith(".txt") else resp.json()


def _rows(text):
    """The data rows of a NOAA daily text product, each as a list of tokens (comment and header lines are skipped)."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) > 4 and parts[0].isdigit() and len(parts[0]) == 4:
            out.append(parts)
    return out


GFZ = "https://kp.gfz-potsdam.de/app/json/"      # GFZ Potsdam's Kp and solar flux archive (CC BY 4.0): any past date
EVENTS = "/json/edited_events.json"              # SWPC's list of solar events, kept for about a month


def _gfz(index, start, end, timeout):
    resp = requests.get(GFZ, params={"start": f"{start:%Y-%m-%dT%H:%M:%SZ}", "end": f"{end:%Y-%m-%dT%H:%M:%SZ}", "index": index},
                        headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    return [(pd.Timestamp(t).tz_localize(None), float(v)) for t, v in zip(body["datetime"], body[index])]


def history(start, end, timeout=20):
    """Space weather over a past stretch of time (naive UTC `start` and `end`): 'kp' as (start of the 3 hours, Kp), 'flux' as (day, solar
    flux), and 'flares' as (time of the peak, class such as 'C2.1') from the X-ray events NOAA still lists. Each part is None when it could not
    be read; 'flares' is also None when the stretch is older than NOAA's list. Never raises."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    out = {"kp": None, "flux": None, "flares": None, "flare_details": {}, "flare_source": None, "flux_latest": None}
    try:
        out["kp"] = [(t, v) for t, v in _gfz("Kp", start.floor("D"), end.ceil("D"), timeout) if t + timedelta(hours=3) > start and t < end]
    except Exception:
        pass
    try:
        out["flux"] = [(t, v) for t, v in _gfz("Fobs", start.floor("D"), end.ceil("D"), timeout) if v > 0]
    except Exception:
        pass
    if out["flux"] is not None and not out["flux"]:                  # the day's flux is not out yet (it is measured at local noon in Canada and published later): the latest earlier one
        out["flux_latest"] = latest_flux(start, timeout)
    try:
        resp = requests.get(SWPC + EVENTS, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        events = resp.json()
        first = min(pd.Timestamp(e["begin_datetime"]) for e in events if e.get("begin_datetime"))
        if start > first + timedelta(days=1):                       # the list reaches back far enough to have seen this stretch
            seen, details = {}, {}
            for e in events:
                cls = e.get("particulars1") or ""
                if e.get("type") == "XRA" and cls[:1] in ("A", "B", "C", "M", "X") and e.get("max_datetime"):
                    peak = pd.Timestamp(e["max_datetime"]).floor("min")
                    if start <= peak <= end:
                        best = max(seen.get(peak, ""), cls, key=lambda c: (("ABCMX".index(c[:1])), float(c[1:] or 0)))   # two satellites report each flare
                        if best != seen.get(peak):
                            seen[peak] = best
                            details[peak] = {"begin": _stamp(e.get("begin_datetime")), "end": _stamp(e.get("end_datetime")), "region": str(e.get("region") or "").strip()}
            out["flares"] = sorted(seen.items())
            out["flare_details"] = details
            out["flare_source"] = "NOAA SWPC's list of solar events"
    except Exception:
        pass
    if out["flares"] is None:                                       # NOAA's own list only reaches back about a month: older days come from the HEK
        found = hek_flares(start, end, timeout)
        if found is not None:
            out["flares"], out["flare_details"] = found
            out["flare_source"] = "NASA's heliophysics event service (the HEK), carrying NOAA SWPC's flare list"
    return out


HEK = "https://www.lmsal.com/hek/her"           # NASA's heliophysics event service (run by Lockheed Martin's solar lab): free, no key, flares back many years
HEK_FEEDER = "SWPC"                              # the entries it carries from NOAA's own flare list, with NOAA's class and times


def _flare_rank(cls):
    return ("ABCMX".index(cls[:1]), float(cls[1:] or 0))


def merge_flares(rows):
    """One flare for each peak minute from a list of the same flare reported more than once, as the HEK does ((peak, class, begin, end, region) tuples, region 0 or
    empty when NOAA did not give one). Where the entries disagree about the class, the one NOAA tied to an active region wins, then the commonest class, then the
    lower class (a saturated reading can show a flare as far bigger than it was). Returns ([(peak, class)], {peak: {begin, end, region}}) in time order."""
    from collections import Counter
    groups = {}
    for peak, cls, begin, end, region in rows:
        groups.setdefault(pd.Timestamp(peak).floor("min"), []).append((cls, begin, end, str(region or "").strip()))
    flares, details = [], {}
    for peak, group in sorted(groups.items()):
        with_region = [g for g in group if g[3] not in ("", "0")] or group
        counts = Counter(g[0] for g in with_region)
        cls = max(counts, key=lambda c: (counts[c], -_flare_rank(c)[0], -_flare_rank(c)[1]))
        chosen = [g for g in with_region if g[0] == cls]
        begins, ends = [g[1] for g in chosen if g[1] is not None], [g[2] for g in chosen if g[2] is not None]
        flares.append((peak, cls))
        details[peak] = {"begin": min(begins) if begins else None, "end": max(ends) if ends else None, "region": next((g[3] for g in chosen if g[3] not in ("", "0")), "")}
    return flares, details


def hek_flares(start, end, timeout=30):
    """The flares whose peak fell between two naive UTC times, from NASA's HEK, as ([(peak, class)], details), or None when it could not be read. Only the dates are sent.
    A stretch that ended more than two days ago will not change, so its answer is kept on disk."""
    import json
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    key = f"{start:%Y%m%d%H}-{end:%Y%m%d%H}"
    settled = end < pd.Timestamp.now("UTC").tz_localize(None) - timedelta(days=2)
    try:
        import disk_cache
        raw = disk_cache.get_bytes("hekflares", key) if settled else None
        if raw is None:
            params = {"cosec": 2, "cmd": "search", "type": "column", "event_type": "fl", "event_coordsys": "helioprojective", "x1": -1200, "x2": 1200, "y1": -1200, "y2": 1200,
                      "event_starttime": f"{start - timedelta(hours=3):%Y-%m-%dT%H:%M:%S}", "event_endtime": f"{end + timedelta(hours=1):%Y-%m-%dT%H:%M:%S}",
                      "result_limit": 2000, "return": "event_starttime,event_peaktime,event_endtime,fl_goescls,frm_name,ar_noaanum"}
            resp = requests.get(HEK, params=params, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            result = resp.json()["result"]
            raw = json.dumps(result).encode("utf-8")
            if settled:
                disk_cache.put_bytes("hekflares", key, raw)
        rows = []
        for e in json.loads(raw):
            cls = (e.get("fl_goescls") or "").strip()
            if e.get("frm_name") != HEK_FEEDER or cls[:1] not in ("A", "B", "C", "M", "X") or not e.get("event_peaktime"):
                continue
            float(cls[1:] or 0)
            rows.append((pd.Timestamp(e["event_peaktime"]), cls, _stamp(e.get("event_starttime")), _stamp(e.get("event_endtime")), e.get("ar_noaanum")))
        flares, details = merge_flares(rows)
        keep = [(t, c) for t, c in flares if start <= t <= end]
        return keep, {t: details[t] for t, _ in keep}
    except Exception:
        return None


def latest_flux(before, timeout=20):
    """(day, flux) of the latest daily solar flux before a time, from GFZ Potsdam or else NOAA's 30 day list, or None. For a session on a day whose own flux is not published yet."""
    before = pd.Timestamp(before)
    try:
        found = [(t, v) for t, v in _gfz("Fobs", before.floor("D") - timedelta(days=6), before.floor("D"), timeout) if v > 0 and t < before.floor("D") + timedelta(days=1)]
        if found:
            return found[-1]
    except Exception:
        pass
    try:
        rows = [(pd.Timestamp(r["time_tag"]).floor("D"), float(r["flux"])) for r in _get("flux30", timeout) if r.get("flux")]
        rows = [(t, v) for t, v in rows if t <= before.floor("D")]
        return rows[-1] if rows else None
    except Exception:
        return None


def _stamp(text):
    """A time from NOAA's event list as a naive UTC timestamp, or None."""
    try:
        return pd.Timestamp(text).tz_localize(None) if text else None
    except Exception:
        return None


def flare_level(cls):
    """What a flare class means for HF, in NOAA's radio blackout scale: R1 (minor) for M1 to M4.9, R2 (moderate) from M5, R3 (strong) from X1, R4 (severe) from
    X10 and R5 (extreme) from X20; below M, 'too small to affect HF'. Empty for something that is not a flare class."""
    letter = (cls or "")[:1]
    try:
        n = float((cls or "")[1:] or 0)
    except ValueError:
        n = 0.0
    if letter == "X":
        return "R5, an extreme radio blackout" if n >= 20 else "R4, a severe radio blackout" if n >= 10 else "R3, a strong radio blackout"
    if letter == "M":
        return "R2, a moderate radio blackout" if n >= 5 else "R1, a minor radio blackout"
    return "too small to affect HF" if letter in ("A", "B", "C") else ""


def xray_class(flux):
    """The flare class of a GOES long-wavelength X-ray flux in W/m2, such as 'B6.6' or 'M1.2'."""
    if flux is None or not flux > 0:
        return None
    for letter, low in (("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7), ("A", 1e-8)):
        if flux >= low:
            return f"{letter}{flux / low:.1f}"
    return "A0.0"


def fetch():
    """The current readings, each None when its feed could not be read. Returns a dict, never raises."""
    out = dict.fromkeys(("flux", "kp", "a_index", "xray", "xray_max", "wind", "bz", "bt", "R", "S", "G", "ssn", "flux_week",
                         "flux_month"))
    out["times"] = {}
    try:
        row = _get("flux")[0]
        out["flux"], out["times"]["flux"] = float(row["flux"]), row.get("time_tag")
    except Exception:
        pass
    try:  # how the daily flux has been moving: the last 7 days against the whole 30
        values = [float(r["flux"]) for r in _get("flux30") if r.get("flux")]
        if len(values) >= 14:
            out["flux_week"], out["flux_month"] = sum(values[-7:]) / 7, sum(values) / len(values)
    except Exception:
        pass
    try:  # the sunspot number of the latest complete day
        rows = [r for r in _rows(_get("solar_text")) if float(r[3]) > 0]
        out["ssn"], out["times"]["ssn"] = float(rows[-1][4]), f"{rows[-1][0]}-{rows[-1][1]}-{rows[-1][2]}"
    except Exception:
        pass
    try:  # the mid-latitude A index of the latest complete day
        rows = [r for r in _rows(_get("geo_text")) if float(r[3]) >= 0]
        out["a_index"], out["times"]["a_index"] = float(rows[-1][3]), f"{rows[-1][0]}-{rows[-1][1]}-{rows[-1][2]}"
    except Exception:
        pass
    try:
        row = _get("kp")[-1]
        out["kp"], out["times"]["kp"] = float(row["Kp"]), row.get("time_tag")
    except Exception:
        pass
    try:
        now = _get("scales")["0"]
        for key in ("R", "S", "G"):
            out[key] = int(now[key]["Scale"])
    except Exception:
        pass
    try:
        row = _get("wind")[0]
        out["wind"], out["times"]["wind"] = float(row["proton_speed"]), row.get("time_tag")
    except Exception:
        pass
    try:
        row = _get("field")[0]
        out["bz"], out["bt"] = float(row["bz_gsm"]), float(row["bt"])
    except Exception:
        pass
    try:
        longwave = [r for r in _get("xray") if r.get("energy") == "0.1-0.8nm" and r.get("flux")]
        out["xray"] = longwave[-1]["flux"]
        out["xray_max"] = max(r["flux"] for r in longwave)
        out["times"]["xray"] = longwave[-1].get("time_tag")
    except Exception:
        pass
    return out


def _trend_text(week, month):
    """' Over the past week it has been rising (117 on average against 110 over 30 days).' or ''."""
    if week is None or month is None or abs(week - month) < 5:
        return ""
    way = "rising" if week > month else "falling"
    return f" Over the past week it has been {way} ({week:.0f} on average against {month:.0f} over 30 days)."


def _flux_sentence(flux):
    """What the solar flux says about the background: a tendency, not a forecast for any band. Which bands are open is for the
    MUF and the WSPR picture to say."""
    if flux < 70:
        mood = "very low, so the higher bands are unlikely to open widely and the lower bands tend to carry more of the traffic"
    elif flux < 90:
        mood = "low: openings on the higher bands tend to be limited, and the lower bands carry more of the traffic"
    elif flux < 120:
        mood = "fair: solar activity is modest, which tends to favour the middle bands over the highest ones"
    elif flux < 150:
        mood = "good: the higher bands are more likely to open when the sun is up on your path"
    elif flux < 200:
        mood = "very good: the highest bands open more often, and 6m may open now and then"
    else:
        mood = "excellent: the highest bands tend to open widely, with a better chance on 6m"
    return (f"Solar flux is {flux:.0f}, {mood}. Which bands are actually open also depends on the time of day, the season and "
            "your path, so check the MUF and the WSPR picture below.")


def _kp_sentence(kp):
    if kp < 2.5:
        return (f"The geomagnetic field is quiet (Kp {kp:.1f}), which is generally favourable for HF, including paths toward the "
                "north.")
    if kp < 4:
        return (f"The geomagnetic field is slightly unsettled (Kp {kp:.1f}): northern and polar paths may be a little weaker "
                "or flutter.")
    if kp < 5:
        return (f"The geomagnetic field is active (Kp {kp:.1f}): expect weaker, noisier paths toward the north and over "
                "the poles, and look south and east-west instead.")
    return (f"A geomagnetic storm is in progress (Kp {kp:.1f}): HF is likely degraded, especially at high latitudes and on "
            "the upper bands, and the low bands can be noisy.")


def _xray_sentence(xray, xray_max):
    cls, peak = xray_class(xray), xray_class(xray_max)
    big_now = xray is not None and xray >= 1e-5
    big_peak = xray_max is not None and xray_max >= 1e-5
    if big_now:
        strength = "strong" if xray >= 1e-4 else "moderate"
        return (f"A {strength} flare is in progress (X-ray {cls}): HF can fade out on the sunlit side of the Earth for "
                "minutes to an hour. Try the shaded side, or wait it out.")
    if big_peak:
        return (f"There was {'an' if peak[0] in 'XM' else 'a'} {peak} flare in the last 6 hours, but the X-ray level is back to {cls}, so any radio fade-out "
                "should have recovered.")
    return f"The X-ray level is {cls}, low: this reading shows no flare-related HF absorption right now."


def _wind_sentence(wind, bz, bt):
    parts = []
    if wind is not None and wind >= 600:
        parts.append(f"the solar wind is fast ({wind:.0f} km/s), which tends to disturb the field")
    elif wind is not None and wind >= 500:
        parts.append(f"the solar wind is elevated ({wind:.0f} km/s)")
    if bz is not None and bz <= -5:
        parts.append(f"the magnetic field points south (Bz {bz:.0f} nT), which lets the wind stir Earth's field")
    if not parts:
        return None
    return ("Watch for the field becoming unsettled in the next several hours to a day: " + ", and ".join(parts) + ".")


def interpret(data):
    """A few plain sentences about what the readings mean for HF, as a list of strings."""
    lines = []
    if data.get("flux") is not None:
        lines.append(_flux_sentence(data["flux"]) + _trend_text(data.get("flux_week"), data.get("flux_month")))
    if data.get("kp") is not None:
        lines.append(_kp_sentence(data["kp"]))
    if data.get("xray") is not None:
        lines.append(_xray_sentence(data["xray"], data.get("xray_max")))
    wind = _wind_sentence(data.get("wind"), data.get("bz"), data.get("bt"))
    if wind:
        lines.append(wind)
    scales = [f"{name}{data[key]}" for key, name in (("R", "radio blackout R"), ("S", "solar radiation storm S"),
                                                        ("G", "geomagnetic storm G")) if data.get(key)]
    if scales:
        lines.append("NOAA currently reports " + ", ".join(scales) + ".")
    if lines:
        lines.append("These are worldwide numbers, not your path. The WSPR picture below shows recently reported paths involving "
                     "stations near you; a band with few reports is not necessarily closed.")
    return lines


def when_text(iso, fmt):
    """A time from the feeds formatted with strftime `fmt` (like '%H:%M'), or '' when it cannot be read."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "")).strftime(fmt)
    except Exception:
        return ""


def readings(data):
    """The readings for the dashboard strip: a list of dicts with label, value, unit, a one-word reading, its tone ('good', 'ok',
    'warn', 'bad' or 'quiet') and a tooltip. Readings whose feed could not be read are left out."""
    out = []

    def add(label, value, unit, word, tone, help_):
        out.append({"label": label, "value": value, "unit": unit, "word": word, "tone": tone, "help": help_})

    flux = data.get("flux")
    if flux is not None:
        word, tone = (("Very low", "bad") if flux < 70 else ("Low", "warn") if flux < 90 else ("Fair", "warn") if flux < 120
                      else ("Good", "good") if flux < 150 else ("Very good", "good") if flux < 200 else ("Excellent", "good"))
        add("Solar flux", f"{flux:.0f}", "", word, tone, "The 10.7 cm radio flux, measured daily at noon in Penticton. Higher "
            "means better HF: about 70 is poor, 120 good, 150 or more very good.")
    ssn = data.get("ssn")
    if ssn is not None:
        word, tone = ("Low", "quiet") if ssn < 25 else ("Moderate", "ok") if ssn < 80 else ("High", "good") if ssn < 150 else ("Very high", "good")
        add("Sunspots", f"{ssn:.0f}", "", word, tone, "The sunspot number of the latest complete day. More spots usually means a "
            "more active sun and better HF.")
    kp = data.get("kp")
    if kp is not None:
        word, tone = (("Quiet", "good") if kp < 2.5 else ("Unsettled", "warn") if kp < 4 else ("Active", "warn") if kp < 5
                      else ("Storm", "bad"))
        add("Kp index", f"{kp:.1f}", "", word, tone, "How disturbed Earth's magnetic field is, 0 to 9, updated every 3 hours. "
            "Under 3 is quiet, 5 or more is a storm.")
    xray, peak = data.get("xray"), data.get("xray_max")
    if xray is not None:
        word, tone = (("Strong flare", "bad") if xray >= 1e-4 else ("Flare", "bad") if xray >= 1e-5
                      else ("Recovering", "warn") if peak is not None and peak >= 1e-5 else ("Low activity", "good"))
        add("X-ray", xray_class(xray), "", word, tone, "The flare level from the GOES satellite. A and B are quiet, C is minor, "
            "M can cause a brief radio fade-out, X a strong one.")
    wind, bz = data.get("wind"), data.get("bz")
    if wind is not None:
        word, tone = ("Calm", "good") if wind < 500 else ("Elevated", "warn") if wind < 600 else ("Fast", "bad")
        if tone == "good" and bz is not None and bz <= -5:
            word, tone = "Bz south", "warn"
        add("Solar wind", f"{wind:.0f}", "km/s", word, tone, "The speed of the wind reaching Earth. Around 400 is calm, 500 or "
            "more is elevated, 600 or more is fast. A strongly south (negative) Bz lets the wind stir Earth's field.")
    return out
