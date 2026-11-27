"""Space weather during a session, as the facts the page draws: Kp in three hour steps, flares at their peak, the sun at the station (sunrise, sunset, daylight) and the bands
the log shows, with the sentences that say it in words. The functions take tables and return plain values, so they can be tested with made-up data. Nothing here says what
happened to a particular contact or path: Kp, flux and flares are worldwide figures and the daylight is the sun's position at the station."""
import math
from datetime import timedelta

import numpy as np
import pandas as pd

import log_check as lc
import space_weather as sw

SUNRISE_DEG = -0.833        # the sun's centre this far below the horizon is the moment of sunrise or sunset
TWILIGHT_DEG = -6.0         # below this it is night; between the two it is twilight
RUN_GAP_MIN = 30            # a pause this long ends a stretch of activity on a band
NORTH = ("US East", "US Central", "US West", "Canada")

# NOAA's radio blackout scale, in the words NOAA gives for what each level can do to HF on the sunlit side of the Earth
R_SCALE = {
    "R1": ("minor", "weak or minor degradation of HF radio on the sunlit side of the Earth, with occasional loss of contact for a short time"),
    "R2": ("moderate", "a limited blackout of HF radio on the sunlit side, with loss of contact for tens of minutes"),
    "R3": ("strong", "a wide area blackout of HF radio on the sunlit side, with loss of contact for about an hour"),
    "R4": ("severe", "an HF blackout on most of the sunlit side for one to two hours"),
    "R5": ("extreme", "a complete HF blackout on the entire sunlit side for a number of hours"),
}


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the sun

def sun_elevation(lat, lon, times):
    """The sun's height above the horizon in degrees (the NOAA solar calculator's formulas, good to a few hundredths of a degree) at a place, east longitude positive, for
    one naive UTC time or an array of them."""
    t = pd.DatetimeIndex(np.atleast_1d(pd.to_datetime(times)))
    jd = (t - pd.Timestamp("2000-01-01 12:00")).total_seconds().to_numpy() / 86400.0 + 2451545.0
    c = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + c * (36000.76983 + c * 0.0003032)) % 360
    m = np.radians(357.52911 + c * (35999.05029 - 0.0001537 * c))
    e = 0.016708634 - c * (0.000042037 + 0.0000001267 * c)
    centre = np.sin(m) * (1.914602 - c * (0.004817 + 0.000014 * c)) + np.sin(2 * m) * (0.019993 - 0.000101 * c) + np.sin(3 * m) * 0.000289
    omega = np.radians(125.04 - 1934.136 * c)
    lam = np.radians(l0 + centre - 0.00569 - 0.00478 * np.sin(omega))
    eps = np.radians(23 + (26 + (21.448 - c * (46.815 + c * (0.00059 - c * 0.001813))) / 60) / 60 + 0.00256 * np.cos(omega))
    decl = np.arcsin(np.sin(eps) * np.sin(lam))
    y = np.tan(eps / 2) ** 2
    l0r = np.radians(l0)
    eqtime = 4 * np.degrees(y * np.sin(2 * l0r) - 2 * e * np.sin(m) + 4 * e * y * np.sin(m) * np.cos(2 * l0r) - 0.5 * y * y * np.sin(4 * l0r) - 1.25 * e * e * np.sin(2 * m))
    minutes = t.hour.to_numpy() * 60 + t.minute.to_numpy() + t.second.to_numpy() / 60
    hour_angle = np.radians(((minutes + eqtime + 4 * lon) % 1440) / 4 - 180)
    latr = math.radians(lat)
    cos_zenith = np.sin(latr) * np.sin(decl) + np.cos(latr) * np.cos(decl) * np.cos(hour_angle)
    out = 90 - np.degrees(np.arccos(np.clip(cos_zenith, -1, 1)))
    return out if np.ndim(times) else float(out[0])


def daylight_state(elevation):
    """'daylight', 'twilight' or 'night' for a sun height in degrees."""
    return "daylight" if elevation > SUNRISE_DEG else "twilight" if elevation > TWILIGHT_DEG else "night"


def daylight_segments(lat, lon, start, end, step_min=5):
    """[(start, end, state)] over a stretch of time: when the sun was up, low (twilight) or down at the place, in steps of `step_min` minutes."""
    times = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq=f"{step_min}min")
    if len(times) < 2:
        return []
    states = [daylight_state(v) for v in sun_elevation(lat, lon, times)]
    out, first = [], 0
    for i in range(1, len(times) + 1):
        if i == len(times) or states[i] != states[first]:
            out.append((times[first], times[min(i, len(times) - 1)], states[first]))
            first = i
    return out


def sun_events(lat, lon, start, end):
    """[(time, 'sunrise' or 'sunset')] between two naive UTC times, found to the minute."""
    times = pd.date_range(pd.Timestamp(start) - timedelta(minutes=1), pd.Timestamp(end), freq="1min")
    elev = sun_elevation(lat, lon, times) - SUNRISE_DEG
    out = []
    for i in range(1, len(times)):
        if elev[i - 1] <= 0 < elev[i]:
            out.append((times[i], "sunrise"))
        elif elev[i - 1] > 0 >= elev[i]:
            out.append((times[i], "sunset"))
    return [(t, k) for t, k in out if pd.Timestamp(start) <= t <= pd.Timestamp(end)]


# ------------------------------------------------------------------------------------------------------------------------------------------------------------ the log

def activity_runs(log, gap_min=RUN_GAP_MIN):
    """The stretches of logged activity on each band, the highest band first: [(band, first contact, last contact, contacts)]. A pause of more than `gap_min` minutes
    on a band ends a stretch."""
    out = []
    for band in lc.bands_top_down(log):
        times = log.loc[log["band"] == band, "time"].sort_values().tolist()
        first = prev = times[0]
        n = 1
        for t in times[1:]:
            if t - prev > timedelta(minutes=gap_min):
                out.append((band, first, prev, n))
                first, n = t, 0
            prev, n = t, n + 1
        out.append((band, first, prev, n))
    return out


def bands_active_at(runs, when, slack_min=5):
    """The bands with logged activity at a moment (within `slack_min` minutes of a stretch), highest first, without repeats."""
    seen = []
    for band, a, b, _ in runs:
        if a - timedelta(minutes=slack_min) <= when <= b + timedelta(minutes=slack_min) and band not in seen:
            seen.append(band)
    return seen


# ------------------------------------------------------------------------------------------------------------------------------------------------------- the readings

def kp_label(kp):
    """The word for a Kp, as NOAA names the levels: quiet below 3, unsettled at 3, active at 4, then a storm (G1 at 5 to G5 at 9)."""
    return "Quiet" if kp < 3 else "Unsettled" if kp < 4 else "Active" if kp < 5 else f"Storm G{min(int(kp) - 4, 5)}"


def kp_text(kp):
    return f"{kp:.0f}" if abs(kp - round(kp)) < 0.17 else f"{kp:.1f}"


def flux_label(flux):
    """A short word for the solar flux, from the same bands as the page's flux sentence."""
    return "Very low" if flux < 70 else "Low" if flux < 90 else "Fair" if flux < 120 else "Good" if flux < 150 else "Very good" if flux < 200 else "Excellent"


def flux_note(flux):
    """What the flux says about the background, as a tendency and no more."""
    if flux < 90:
        return "low, which tends to limit openings on the higher bands"
    if flux < 120:
        return "fair, a modest level of solar activity that tends to favour the middle bands over the highest"
    if flux < 150:
        return "good, which tends to open the higher bands when the sun is up on the path"
    return "high, which tends to open the highest bands more often"


def r_level(cls):
    """'R1' to 'R5' for a flare class on NOAA's radio blackout scale (M1 is R1, M5 R2, X1 R3, X10 R4, X20 R5), or '' for a smaller flare."""
    letter = (cls or "")[:1]
    try:
        n = float((cls or "")[1:] or 0)
    except ValueError:
        return ""
    if letter == "X":
        return "R5" if n >= 20 else "R4" if n >= 10 else "R3"
    if letter == "M":
        return "R2" if n >= 5 else "R1"
    return ""


def strongest_flare(flares):
    """The strongest of [(peak, class)] (the earliest of equals), or None."""
    return max(flares, key=lambda f: (sw._flare_rank(f[1]), -f[0].value)) if flares else None


# ------------------------------------------------------------------------------------------------------------------------------------------------------- the facts

def facts(log, wx, home):
    """Everything the page draws, as a dict, from a log, `space_weather.history` and the place (lat, lon), or None when there is no reading at all. Keys: start, end
    (the stretch drawn, an hour either side of the contacts), kp (steps touching it), kp_peak, flux (the mean over the session's days) and flux_days, flares (those in the
    stretch), focus (the strongest flare and what it overlapped), runs, segments, events, sun, contacts_by_light, headline and bullets."""
    kp_all, flux_all, flares_all = wx.get("kp"), wx.get("flux"), wx.get("flares")
    if kp_all is None and flux_all is None and flares_all is None:
        return None
    flux_all = list(flux_all or [])
    start, end = lc.space_span(log)
    first, last = log["time"].min(), log["time"].max()
    kp = [(t, v) for t, v in (kp_all or []) if t + timedelta(hours=3) > start and t < end]
    kp_session = [(t, v) for t, v in kp if t + timedelta(hours=3) > first and t < last]          # only the steps that touch the contacts themselves
    flux_days = [(t, v) for t, v in (flux_all or []) if first.normalize() <= t <= last]
    earlier = [(t, v) for t, v in flux_all if t < first.normalize()]
    latest = (earlier[-1] if earlier else wx.get("flux_latest")) if not flux_days else None       # the session's own day has no flux yet: the latest earlier one, said to be that
    flares = None if flares_all is None else [(t, c) for t, c in flares_all if start <= t <= end]
    runs = activity_runs(log)
    lat, lon = home
    segments = daylight_segments(lat, lon, start, end)
    contacts_light = {"daylight": 0, "twilight": 0, "night": 0}
    for t, v in zip(log["time"], sun_elevation(lat, lon, log["time"])):
        contacts_light[daylight_state(v)] += 1
    focus = None
    top = strongest_flare(flares)
    if top:
        peak, cls = top
        bands = bands_active_at(runs, peak)
        focus = {"peak": peak, "class": cls, "level": r_level(cls), "bands": bands, "light": daylight_state(sun_elevation(lat, lon, peak)),
                 "detail": (wx.get("flare_details") or {}).get(peak) or {}}
    out = {"start": start, "end": end, "kp": kp, "kp_peak": max(kp_session, key=lambda p: p[1]) if kp_session else None, "flux": (sum(v for _, v in flux_days) / len(flux_days)) if flux_days else (latest[1] if latest else None),
           "flux_days": flux_days, "flux_latest": latest, "flares": flares, "flare_source": wx.get("flare_source"), "flare_details": wx.get("flare_details") or {}, "focus": focus, "runs": runs,
           "segments": segments, "events": sun_events(lat, lon, start, end), "contacts_by_light": contacts_light, "home": (lat, lon), "contacts": len(log)}
    out["headline"] = headline(out)
    out["bullets"] = bullets(out)
    return out


def article(cls):
    """'an' before a class said with a vowel sound (A, M and X: 'an M2.1 flare') and 'a' before the rest ('a C4.9 flare')."""
    return "an" if (cls or " ")[:1] in "AMX" else "a"


def _clock(t, spans_days):
    return f"{t:%d %b %H:%M}" if spans_days else f"{t:%H:%M}"


def headline(f):
    """The one or two sentences over the card: how the magnetic field behaved and where the strongest flare fell against the logged activity."""
    span = (f["end"] - f["start"]) > timedelta(hours=30)
    parts = []
    peak = f["kp_peak"]
    if peak:
        t, v = peak
        if v < 3:
            parts.append(f"The magnetic field stayed quiet (Kp {kp_text(v)}{' or lower' if v > 0 else ''}).")
        else:
            rose = [(a, b) for a, b in f["kp"] if b >= 3]
            when = max(rose[0][0], f["start"]) if rose else t
            if rose and rose[0][0] <= f["start"] + timedelta(hours=1):
                parts.append(f"The magnetic field was {kp_label(v).lower() if v < 5 else 'stormy'} (Kp {kp_text(v)}) through your session.")
            else:
                parts.append(f"Magnetic activity rose to Kp {kp_text(v)} ({kp_label(v).lower()}) from {_clock(when, span)} UTC.")
    focus = f["focus"]
    if f["flares"] is None:
        parts.append("Flare data is not available for these dates.")
    elif focus and focus["level"]:
        if focus["bands"]:
            parts.append(f"{article(focus['class']).capitalize()} {focus['class']} flare peaked at {_clock(focus['peak'], span)} UTC during your logged {focus['bands'][0]} activity.")
        else:
            parts.append(f"{article(focus['class']).capitalize()} {focus['class']} flare peaked at {_clock(focus['peak'], span)} UTC, outside your logged activity.")
    else:
        parts.append("No flare reached M class (R1) in these hours.")
    return " ".join(parts)


def bullets(f):
    """The 'what this means for HF' lines, as (lead, text) pairs. They say what NOAA's scales say about readings like these; none says what happened to a contact."""
    out = []
    if f["flux"] is not None:
        which = f" (the latest daily reading, from {f['flux_latest'][0]:%d %b}; the day's own is not published yet)" if f.get("flux_latest") else ""
        out.append(("Solar flux:", f"{f['flux']:.0f} sfu{which} was {flux_note(f['flux'])}. Which bands were open also depended on the time of day, the season and the path."))
    peak = f["kp_peak"]
    if peak:
        v = peak[1]
        out.append(("Magnetic conditions:", f"{kp_label(v).lower() if v < 5 else 'a storm'} (Kp {kp_text(v)}), " + ("below storm level (Kp 5)." if v < 5 else "at or above storm level (Kp 5).")
                    + (" Disturbance can weaken HF paths that cross the polar regions." if v >= 3 else "")))
    focus = f["focus"]
    if f["flares"] is None:
        out.append(("Flare effects:", "not shown, because the flare list could not be read for these dates."))
    elif focus and focus["level"]:
        word, says = R_SCALE[focus["level"]]
        out.append(("Flare effects:", f"{article(focus['class'])} {focus['class']} flare is {focus['level']} ({word}) on NOAA's radio blackout scale: {says}. That is NOAA's general description, not a measurement of your paths."))
    else:
        out.append(("Flare effects:", "no flare reached R1 (M1) in these hours, so none was large enough to count on NOAA's radio blackout scale."))
    out.append(("Usable frequency:", "varies with route, distance and time; the openings above show what WSPR stations near you reported."))
    return out


def daylight_summary(f):
    """(headline word, sentence) for the daylight tile: how many of the contacts were made with the sun up at the station."""
    c, n = f["contacts_by_light"], max(f["contacts"], 1)
    up, low, down = c["daylight"], c["twilight"], c["night"]
    if up == f["contacts"]:
        return "Daylight", "All of your contacts were made with the sun up at your station."
    if down == f["contacts"]:
        return "Night", "All of your contacts were made with the sun well down at your station."
    parts = [f"{up} in daylight"] + ([f"{low} in twilight"] if low else []) + ([f"{down} at night"] if down else [])
    return "Mixed", f"Of your {f['contacts']} contacts, " + ", ".join(parts) + "."
