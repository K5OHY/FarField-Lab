"""The story behind the space weather of a session: the days around it, the geomagnetic storms in them (from Kp, a fact), why each happened when NASA's DONKI records a cause
(coronal mass ejections linked to the storm, the flare one came with, the shock that reached Earth), and where the session fell against them. The functions take tables and return
plain values, so they can be tested with made-up data. The 'why' is NASA's: the sentences say "DONKI links the storm to ..." and never state a cause of their own; with no DONKI they
say what the Kp shows and that the cause could not be read."""
from datetime import timedelta

import pandas as pd

import donki
import log_space as ls
import space_weather as sw

STORM_KP = 5.0
DAYS_BEFORE, DAYS_AFTER, MAX_DAYS = 3, 2, 9
G_NAMES = {1: "minor", 2: "moderate", 3: "strong", 4: "severe", 5: "extreme"}


def window(log):
    """(start, end) of the days drawn: three whole days before the first contact and through two days after the last, those shortened (before first, then after) for a log of many
    days, but never so far that the session itself is cut."""
    first, last = log["time"].min(), log["time"].max()
    session_days = (last.floor("D") - first.floor("D")).days + 1
    room = max(0, MAX_DAYS - session_days)
    before = min(DAYS_BEFORE, room)
    after = min(DAYS_AFTER, room - before)
    return first.floor("D") - timedelta(days=before), last.floor("D") + timedelta(days=1 + after)


def g_level(kp):
    """NOAA's geomagnetic storm level for a Kp: 'G1' at 5 up to 'G5' at 9."""
    return f"G{min(max(int(kp) - 4, 1), 5)}"


def kp_storms(kp):
    """The runs of three-hour steps at Kp 5 or more, as [{start, end, peak_kp, peak_time, level}]: a storm is what the Kp shows, whatever caused it."""
    out, run = [], []
    for t, v in sorted(kp or []):
        if v >= STORM_KP and (not run or t - run[-1][0] <= timedelta(hours=3)):
            run.append((t, v))
            continue
        if run:
            out.append(run)
        run = [(t, v)] if v >= STORM_KP else []
    if run:
        out.append(run)
    merged = []
    for r in out:                                          # a dip below Kp 5 of less than twelve hours inside one disturbance does not end it
        if merged and r[0][0] - (merged[-1][-1][0] + timedelta(hours=3)) < timedelta(hours=12):
            merged[-1] = merged[-1] + r
        else:
            merged.append(r)
    storms = []
    for r in merged:
        peak = max(r, key=lambda p: p[1])
        storms.append({"start": r[0][0], "end": r[-1][0] + timedelta(hours=3), "peak_kp": peak[1], "peak_time": peak[0], "level": g_level(peak[1])})
    return storms


def _is(activity_id, kind):
    return f"-{kind}-" in str(activity_id or "")


def resolve_flares(found, rows):
    """{activity id: {class, peak, begin}} for the flare IDs NASA links CMEs to, found in NOAA's list (`rows`: dicts with class, peak, begin) by the time the ID begins with, which is
    the flare's start: the match is the flare that began within ten minutes of it, the strongest if more than one."""
    out = {}
    for c in (found or {}).get("cmes", []):
        for i in c["linked"]:
            t = donki.id_time(i) if _is(i, "FLR") else None
            near = [r for r in rows if t is not None and r.get("begin") is not None and abs(r["begin"] - t) <= timedelta(minutes=10)]
            if near:
                out[i] = max(near, key=lambda r: sw._flare_rank(r["class"]))
    return out


def attach_causes(storms, found, flare_by_id=None):
    """Each storm with what DONKI links to it: `cmes` (the CMEs, earliest first), `flare` (the strongest flare linked to any of them), `shock` (when the interplanetary shock reached
    Earth, read from the linked event) and `donki` (NASA's own record of the storm), or None for the cause when `found` (donki.events) is None or has no record of it."""
    cmes = {c["id"]: c for c in (found or {}).get("cmes", [])}
    flares = flare_by_id or {}
    for s in storms:
        s.update({"cmes": [], "flare": None, "shock": None, "donki": None})
        if not found:
            continue
        match = [g for g in found["storms"] if s["start"] - timedelta(hours=12) <= g["start"] <= s["end"]]
        if not match:
            continue
        g = max(match, key=lambda g: g["max_kp"] or 0)
        s["donki"] = g
        s["cmes"] = sorted((cmes[i] for i in g["linked"] if _is(i, "CME") and i in cmes), key=lambda c: c["start"])
        shocks = sorted(donki.id_time(i) for i in g["linked"] if _is(i, "IPS") and donki.id_time(i) is not None)
        s["shock"] = shocks[0] if shocks else None
        linked = [flares[i] for c in s["cmes"] for i in c["linked"] if _is(i, "FLR") and i in flares]
        s["flare"] = max(linked, key=lambda f: sw._flare_rank(f["class"])) if linked else None
    return storms


# ------------------------------------------------------------------------------------------------------------------------------------------------------------- sentences

def _day(t):
    return f"{t.day} {t:%b}"


def _when(t):
    return f"{t:%H:%M} UTC on {_day(t)}"


def _span(delta):
    hours = abs(delta.total_seconds()) / 3600
    if hours < 1.5:
        return "about an hour"
    if hours < 36:
        return f"about {round(hours)} hours"
    days = round(hours / 24)
    return f"about {days} day{'s' if days != 1 else ''}"


def _sentences(story, log):
    out = []
    flares = [(t, c) for t, c in story["flares_all"] if c[:1] in ("M", "X")]
    big = [(t, c) for t, c in flares if c[:1] == "X"]
    if flares:
        top = ls.strongest_flare(flares)
        text = f"Flares in these days: {len(big)} of class X and {len(flares) - len(big)} of class M; the strongest was {ls.article(top[1])} {top[1]}, peaking at {_when(top[0])}"
        level = ls.r_level(top[1])
        out.append(text + (f" ({level}, {ls.R_SCALE[level][0]} on NOAA's radio blackout scale)." if level else "."))
    elif story["flares_all"]:
        out.append("No flare in these days reached M class (R1).")
    elif story["flares_unavailable"]:
        out.append("The flare list could not be read for these days.")
    first, last = log["time"].min(), log["time"].max()
    session_kp = [v for t, v in story["kp"] if t + timedelta(hours=3) > first and t < last]
    storms = story["storms"]
    if not storms:
        peak = max((v for _, v in story["kp"]), default=None)
        if peak is not None:
            out.append(f"There was no geomagnetic storm (Kp 5 or more) in these {story['days']} days; Kp peaked at {ls.kp_text(peak)}.")
        return out
    for s in storms:
        para = []                                          # one paragraph for each storm: what it was, why, and where the session fell
        level = G_NAMES[int(s["level"][1])]
        para.append(f"A geomagnetic storm began at {_when(s['start'])} and reached Kp {ls.kp_text(s['peak_kp'])} ({s['level']}, {level}) at {_when(s['peak_time'])}.")
        if story["donki_state"] == "unavailable" or not story["storms_ok"]:
            para.append("What caused it could not be read from NASA's DONKI just now.")
        elif s["donki"] is None:
            para.append("NASA's DONKI has no record of this storm, so its cause is not given here.")
        elif not s["cmes"] and not story["cmes_ok"]:
            para.append("NASA's DONKI lists the storm, but the ejections linked to it could not be read just now.")
        elif not s["cmes"]:
            para.append("NASA's DONKI records the storm but links no coronal mass ejection to it.")
        else:
            cmes = s["cmes"]
            regions = sorted({str(c["region"]) for c in cmes if c["region"]})
            first_c, last_c = cmes[0]["start"], cmes[-1]["start"]
            span = f"on {_day(first_c)}" if first_c.date() == last_c.date() else f"between {_day(first_c)} and {_day(last_c)}"
            text = (f"NASA's DONKI links it to {len(cmes)} coronal mass ejection{'s' if len(cmes) != 1 else ''} (clouds of solar plasma) that left the Sun {span}"
                    + (f", from active region {regions[0]}" if len(regions) == 1 else "") + ".")
            speeds = [(c["speed"], c) for c in cmes if c.get("speed")]
            if speeds:
                speed, fastest = max(speeds, key=lambda p: p[0])
                text += f" The fastest, about {speed:,.0f} km/s, left at {_when(fastest['start'])}"
                linked = [f for f in (story["donki_flares"].get(i) for i in fastest["linked"] if _is(i, "FLR")) if f]
                top = max(linked, key=lambda f: sw._flare_rank(f["class"])) if linked else None
                text += f", with {ls.article(top['class'])} {top['class']} flare that peaked at {top['peak']:%H:%M} UTC." if top else "."
            para.append(text)
            if s["shock"] is not None:
                para.append(f"The shock from those ejections reached Earth near {_when(s['shock'])}.")
        if last < s["start"]:
            para.append(f"Your last contact was {_span(s['start'] - last)} before the storm began.")
        elif first > s["end"]:
            para.append(f"Your first contact was {_span(first - s['end'])} after the storm ended.")
        else:
            top = max(session_kp) if session_kp else None
            para.append("You were on the air while the storm was under way" + (f": Kp was up to {ls.kp_text(top)} during your session." if top is not None else "."))
        out.append(" ".join(para))
    return out


def needs_donki(history, log):
    """True when the days around the session hold a storm (Kp 5 or more), the only case in which a cause is asked of NASA: a quiet stretch needs no request."""
    start, end = window(log)
    kp = [(t, v) for t, v in (history.get("kp") or []) if start - timedelta(hours=3) < t < end]
    return bool(kp_storms(kp))


def build(log, history, found, asked=True):
    """The story's facts, as a dict, from a log, `space_weather.history` over `window(log)` and `donki.events` (None when NASA could not be read): start, end, days, kp,
    storms (with their causes), flares (the M and X ones to draw), flares_all, session, donki_state ('ok', 'partial' or 'unavailable'), cmes (the ones linked to a storm,
    to draw) and sentences. None when the Kp could not be read at all (there is no story without it)."""
    start, end = window(log)
    kp = [(t, v) for t, v in (history.get("kp") or []) if start - timedelta(hours=3) < t < end]
    if not kp:
        return None
    flares_all = None if history.get("flares") is None else [(t, c) for t, c in history["flares"] if start <= t <= end]
    details = history.get("flare_details") or {}
    rows = [{"class": c, "peak": t, "begin": (details.get(t) or {}).get("begin")} for t, c in (flares_all or [])]
    by_id = resolve_flares(found, rows)
    storms = attach_causes(kp_storms(kp), found, by_id)
    story = {"start": start, "end": end, "days": max(1, round((end - start).total_seconds() / 86400)), "kp": kp, "storms": storms,
             "flares_all": flares_all or [], "flares_unavailable": flares_all is None, "session": (log["time"].min(), log["time"].max()),
             "donki_state": "not_needed" if not asked else "unavailable" if found is None else "ok" if found.get("complete") else "partial",
             "storms_ok": bool(found and found.get("storms_ok")), "cmes_ok": bool(found and found.get("cmes_ok")), "donki_flares": by_id,
             "own_key": bool(found and found.get("own_key"))}
    story["flares"] = [(t, c) for t, c in story["flares_all"] if c[:1] in ("M", "X")]
    seen = {}
    for s in storms:
        for c in s["cmes"]:
            seen.setdefault(c["id"], c)
    story["cmes"] = list(seen.values())
    story["sentences"] = _sentences(story, log)
    return story
