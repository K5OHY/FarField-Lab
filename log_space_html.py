"""The "Space weather during your session" card: a headline, four tiles (solar flux, magnetic activity, the strongest flare, daylight at the station), a timeline of Kp,
flares, daylight and the bands you logged, the flare in focus, what NOAA's scales say about readings like these, and a folded box of sources and coverage. The facts come
from log_space.facts; nothing here says what happened to a contact or a path."""
from html import escape

import pandas as pd

import log_space as ls

CSS = """<style>
.lc-card .sw-head{margin:0 0 4px;font-size:21px}.sw-sub{margin:0 0 10px;font-size:13.5px;opacity:.7}
.sw-line{margin:0 0 14px;padding:8px 12px;border-left:3px solid var(--a);background:rgba(240,160,32,.08);border-radius:0 8px 8px 0;font-size:14.5px}
.sw-tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:0 0 12px}
.sw-tile{border:1px solid var(--line);border-radius:12px;padding:11px 13px;background:var(--soft)}
.sw-tile .k{font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;opacity:.7}
.sw-tile .v{font-size:27px;font-weight:700;line-height:1.15;margin:3px 0}.sw-tile .v small{font-size:13px;font-weight:500;opacity:.75;margin-left:5px}
.sw-tile .n{font-size:12px;opacity:.72;line-height:1.35}
.sw-chip{display:inline-block;border-radius:99px;padding:1px 10px;font-size:12px;font-weight:700;margin:3px 0 4px;border:1px solid transparent}
.sw-chip.ok{background:rgba(47,191,138,.16);border-color:rgba(47,191,138,.55)}.sw-chip.warn{background:rgba(240,160,32,.18);border-color:rgba(240,160,32,.6)}
.sw-chip.bad{background:rgba(220,80,80,.18);border-color:rgba(220,80,80,.6)}.sw-chip.mute{background:rgba(128,128,128,.14);border-color:var(--line)}
.sw-box{border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--soft);margin:0 0 12px}
.sw-box h5{margin:0 0 8px;font-size:16px}
.sw-grid{display:grid;grid-template-columns:150px 1fr;gap:0 12px}.sw-row{display:contents}
.sw-lab{padding:8px 0;border-top:1px solid var(--line);font-size:13px;line-height:1.3}.sw-lab b{display:block;font-size:14px}.sw-lab small{opacity:.65}
.sw-plot{position:relative;border-top:1px solid var(--line);overflow:hidden}
.sw-tick{position:absolute;top:0;bottom:0;width:0;border-left:1px dashed rgba(128,128,128,.28)}
.sw-axis{position:relative;height:18px;font-size:12px;opacity:.75}.sw-axis span{position:absolute;transform:translateX(-50%);white-space:nowrap}
.sw-kp{position:absolute;bottom:0;border-radius:3px 3px 0 0;font-size:11.5px;font-weight:700;text-align:center;line-height:1.1;display:flex;align-items:flex-end;justify-content:center;padding-bottom:2px;color:#0b1420}
.sw-storm{position:absolute;left:0;right:0;border-top:1px dashed rgba(220,80,80,.75)}.sw-storm span{position:absolute;left:4px;top:-15px;font-size:11px;opacity:.85}
.sw-fl{position:absolute;border-radius:50%;transform:translate(-50%,-50%)}.sw-fn{position:absolute;transform:translate(-50%,0);font-size:11.5px;font-weight:700;white-space:nowrap;padding:0 6px;border-radius:99px;background:rgba(240,160,32,.25);border:1px solid rgba(240,160,32,.6)}
.sw-base{position:absolute;left:0;right:0;border-top:1px solid rgba(240,160,32,.55)}
.sw-day{position:absolute;top:0;bottom:0}.sw-day.night{background:rgba(70,90,150,.28)}.sw-day.twilight{background:rgba(150,110,170,.22)}.sw-day.daylight{background:rgba(240,190,60,.2)}
.sw-sun{position:absolute;bottom:3px;transform:translateX(-50%);font-size:11.5px;white-space:nowrap;padding:0 6px;border-radius:99px;background:rgba(0,0,0,.3);color:#fff}
.sw-run{position:absolute;height:15px;border-radius:5px;font-size:11px;font-weight:700;line-height:15px;text-align:center;overflow:hidden;white-space:nowrap}
.sw-focus{position:absolute;top:0;bottom:0;width:0;border-left:2px dashed #34c7d9;z-index:2}
.lc-card ul.sw-story{margin:0 0 10px;padding:0 0 0 18px;font-size:14px;line-height:1.5}.sw-story li{margin:3px 0}
.sw-sess{position:absolute;top:0;bottom:0;background:rgba(52,199,217,.17);border-left:1px solid rgba(52,199,217,.7);border-right:1px solid rgba(52,199,217,.7);z-index:1}
.sw-slab{position:absolute;top:2px;left:3px;font-size:11px;font-weight:700;color:#34c7d9;white-space:nowrap}
.sw-cme{position:absolute;width:9px;height:9px;background:#b07cff;transform:translate(-50%,-50%) rotate(45deg);border:1px solid rgba(0,0,0,.4)}
.sw-arrow{position:absolute;height:0;border-top:1.5px solid rgba(176,124,255,.75)}.sw-arrow::after{content:"";position:absolute;right:-1px;top:-5px;border-left:7px solid rgba(176,124,255,.95);border-top:4px solid transparent;border-bottom:4px solid transparent}
.sw-tag{position:absolute;font-size:11px;white-space:nowrap;padding:0 5px;border-radius:99px;background:rgba(128,128,128,.22);border:1px solid var(--line)}
.sw-2{display:grid;grid-template-columns:1fr 1.15fr;gap:12px;margin:0 0 12px}
.sw-big{font-size:26px;font-weight:700;margin:0 0 2px}.lc-card ul.sw-bul{list-style:none;margin:0;padding:0}.sw-bul li{margin:6px 0;font-size:14px;line-height:1.4}.sw-bul b{margin-right:4px}
.sw-foot{font-size:12px;opacity:.65;margin:8px 0 0}.sw-box details summary{cursor:pointer;font-weight:700;font-size:15px}.sw-box details ul{margin:8px 0 2px 18px;font-size:13px;line-height:1.45}
@media (max-width:820px){.sw-tiles{grid-template-columns:1fr 1fr}.sw-2{grid-template-columns:1fr}.sw-grid{grid-template-columns:96px 1fr}}
</style>"""

KP_COLOUR = ("rgba(47,191,138,.85)", "rgba(240,160,32,.9)", "rgba(220,80,80,.9)")
FLARE_COLOUR = {"X": "rgb(220,80,80)", "M": "rgb(240,160,32)"}
R_CHIP = {"R1": "warn", "R2": "warn", "R3": "bad", "R4": "bad", "R5": "bad"}


def _ticks(start, end):
    """The hours to mark, a few enough to read: every hour for a short stretch, every 2 or 3 hours for a long one."""
    hours = max(1, round((end - start).total_seconds() / 3600))
    step = 1 if hours <= 9 else 2 if hours <= 18 else 3 if hours <= 30 else 6
    t = start.ceil("h")
    while t <= end:
        if t.hour % step == 0:
            yield t
        t += pd.Timedelta(hours=1)


def _kp_chip(v):
    return "ok" if v < 3 else "warn" if v < 5 else "bad"


def _tiles(f, place):
    out = []
    flux = f["flux"]
    if flux is not None:
        days = sorted({t for t, _ in f["flux_days"]})
        note = (f"Latest daily solar flux, {f['flux_latest'][0]:%d %b}: the session's own day is not published yet" if f.get("flux_latest")
                else f"Daily solar flux, {', '.join(f'{d:%d %b}' for d in days)}")
        out.append(("Solar background", f"{flux:.0f}<small>F10.7 sfu</small>", f'<span class="sw-chip mute">{escape(ls.flux_label(flux))}</span>', note))
    else:
        out.append(("Solar background", "n/a", "", "The solar flux could not be read for these dates."))
    peak = f["kp_peak"]
    if peak:
        v = peak[1]
        out.append(("Geomagnetic activity", f"Kp {ls.kp_text(v)}", f'<span class="sw-chip {_kp_chip(v)}">{escape(ls.kp_label(v))}</span>', "Peak during your session. A storm starts at Kp 5."))
    else:
        out.append(("Geomagnetic activity", "n/a", "", "Kp could not be read for these dates."))
    focus = f["focus"]
    if f["flares"] is None:
        out.append(("Strongest flare", "n/a", "", "The flare list could not be read for these dates."))
    elif focus:
        chip = (f'<span class="sw-chip {R_CHIP[focus["level"]]}">{focus["level"]}-level</span>' if focus["level"] else '<span class="sw-chip mute">Below R1</span>')
        small = (ls.R_SCALE[focus["level"]][0] + " radio blackout level") if focus["level"] else "too small to affect HF"
        out.append(("Strongest flare", escape(focus["class"]), chip, f"Peak {focus['peak']:%H:%M} UTC · {small}"))
    else:
        out.append(("Strongest flare", "None", "", "No flare was listed for these hours."))
    word, sentence = ls.daylight_summary(f)
    rise = [t for t, k in f["events"] if k == "sunrise"]
    sets = [t for t, k in f["events"] if k == "sunset"]
    sun = " · ".join(([f"Sunrise {rise[0]:%H:%M}"] if rise else []) + ([f"Sunset {sets[0]:%H:%M}"] if sets else [])) + (" UTC" if rise or sets else "")
    out.append(("Daylight at your station", word, "", escape(sentence) + (f" {escape(sun)}." if sun else "")))
    html = ""
    for k, v, chip, note in out:
        html += f'<div class="sw-tile"><div class="k">{escape(k)}</div><div class="v">{v}</div>{chip}<div class="n">{note}</div></div>'
    return f'<div class="sw-tiles">{html}</div>'


def _timeline(f, colours):
    start, end = f["start"], f["end"]
    span = (end - start).total_seconds()
    left = lambda t: max(0.0, min(100.0, (pd.Timestamp(t) - start).total_seconds() / span * 100))
    ticks_t = list(_ticks(start, end))
    spans_days = (end - start) > pd.Timedelta(hours=30)
    grid = "".join(f'<i class="sw-tick" style="left:{left(t):.3f}%"></i>' for t in ticks_t)
    axis = "".join(f'<span style="left:{left(t):.3f}%">{t:%d %b %H:%M}</span>' if (spans_days and t.hour == 0) else f'<span style="left:{left(t):.3f}%">{t:%H:%M}</span>' for t in ticks_t)
    focus = f["focus"]
    focus_line = f'<i class="sw-focus" style="left:{left(focus["peak"]):.3f}%" title="{escape(focus["class"])} flare, peak {focus["peak"]:%H:%M} UTC"></i>' if focus else ""
    # magnetic activity: one bar for each three hours, as tall as the Kp is
    kp_h = 56
    kp = ""
    for t, v in f["kp"]:
        a, b = max(t, start), min(t + pd.Timedelta(hours=3), end)
        colour = KP_COLOUR[0 if v < 3 else 1 if v < 5 else 2]
        kp += (f'<i class="sw-kp" style="left:{left(a):.3f}%;width:calc({left(b) - left(a):.3f}% - 2px);height:{max(14.0, v / 9 * (kp_h - 6)):.1f}px;background:{colour}" '
               f'title="Kp {ls.kp_text(v)} ({ls.kp_label(v)}), the three hours from {t:%H:%M} UTC">Kp {ls.kp_text(v)}</i>')
    storm = f'<i class="sw-storm" style="top:{kp_h - 5 / 9 * (kp_h - 6) - 6:.1f}px"><span>Storm threshold · Kp 5</span></i>'
    # flares at their peak, the bigger ones labelled
    fl = f'<i class="sw-base" style="top:70%"></i>'
    if f["flares"] is None:
        fl += '<span style="position:absolute;left:8px;top:14px;font-size:12.5px;opacity:.75">Flare data is not available for these dates.</span>'
    elif not f["flares"]:
        fl += '<span style="position:absolute;left:8px;top:14px;font-size:12.5px;opacity:.75">No flares were listed for these hours.</span>'
    for t, c in f["flares"] or []:
        size = {"X": 16, "M": 13}.get(c[:1], 8)
        colour = FLARE_COLOUR.get(c[:1], "rgb(150,150,150)")
        fl += (f'<i class="sw-fl" style="left:{left(t):.3f}%;top:70%;width:{size}px;height:{size}px;background:{colour}" '
               f'title="{escape(c)} flare, peak {t:%H:%M} UTC' + (f", {ls.r_level(c)}" if ls.r_level(c) else ", below R1") + '"></i>')
        if c[:1] in ("M", "X"):
            x = left(t)
            anchor = "translate(0,0)" if x < 9 else "translate(-100%,0)" if x > 91 else "translate(-50%,0)"        # a label near an edge stays inside the plot
            fl += f'<span class="sw-fn" style="left:{x:.3f}%;top:2px;transform:{anchor}">{escape(c)} · {t:%H:%M}</span>'
    # daylight at the station
    day = "".join(f'<i class="sw-day {state}" style="left:{left(a):.3f}%;width:{left(b) - left(a):.3f}%" title="{state} at your station"></i>' for a, b, state in f["segments"])
    sun = "".join(f'<span class="sw-sun" style="left:{left(t):.3f}%">{"Sunrise" if kind == "sunrise" else "Sunset"} {t:%H:%M}</span>' for t, kind in f["events"])
    # the bands logged, one thin lane for each
    bands = []
    for band, *_ in f["runs"]:
        if band not in bands:
            bands.append(band)
    lanes = ""
    for band, a, b, n in f["runs"]:
        i = bands.index(band)
        width = max(left(b) - left(a), 0.9)
        h = pd.Timestamp(b)
        colour = colours.get(band, "#888888")
        ink = _ink(colour)
        lanes += (f'<i class="sw-run" style="left:{left(a):.3f}%;width:{width:.3f}%;top:{4 + i * 19}px;background:{colour};color:{ink}" '
                  f'title="{band}: {n} contact{"s" if n != 1 else ""}, {a:%H:%M} to {h:%H:%M} UTC">{band if width > 4 else ""}</i>')
    act_h = 8 + 19 * len(bands)

    def row(label, sub, body, h):
        return (f'<div class="sw-row"><div class="sw-lab" style="min-height:{h}px"><b>{label}</b><small>{sub}</small></div>'
                f'<div class="sw-plot" style="height:{h}px">{grid}{body}{focus_line}</div></div>')
    return ('<div class="sw-box"><h5>During your session</h5><div class="sw-grid">'
            + row("Magnetic activity", "Kp, 3-hour steps", kp + storm, kp_h)
            + row("Solar X-rays", "Flares at their peak", fl, 52)
            + row("Daylight", "At your station", day + sun, 40)
            + row("Logged activity", "Contacts on these bands", lanes, act_h)
            + f'<div></div><div class="sw-axis">{axis}</div></div><p class="sw-foot">Times are UTC. The dashed line marks the strongest flare.</p></div>')


def _ink(colour):
    h = str(colour).lstrip("#")
    if len(h) != 6:
        return "#fff"
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return "#000" if 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2] > 0.18 else "#fff"


def _story_box(story):
    """The days around your session: the sentences that tell what the sun did, and a chart of Kp, flares and the ejections NASA links to a storm, with your session shaded."""
    start, end = story["start"], story["end"]
    span = (end - start).total_seconds()
    left = lambda t: max(0.0, min(100.0, (pd.Timestamp(t) - start).total_seconds() / span * 100))
    ticks = []
    t = start.ceil("D")
    while t <= end:
        ticks.append(t)
        t += pd.Timedelta(days=1)
    grid = "".join(f'<i class="sw-tick" style="left:{left(t):.3f}%"></i>' for t in ticks)
    axis = "".join(f'<span style="left:{left(t):.3f}%">{t.day} {t:%b}</span>' for t in ticks)
    a, b = story["session"]
    sess = f'<i class="sw-sess" style="left:{left(a):.3f}%;width:{max(left(b) - left(a), 0.6):.3f}%" title="Your session, {a:%d %b %H:%M} to {b:%d %b %H:%M} UTC"></i>'
    kp_h = 72
    bars, labels = "", ""
    for t, v in story["kp"]:
        x0, x1 = left(max(t, start)), left(min(t + pd.Timedelta(hours=3), end))
        colour = KP_COLOUR[0 if v < 3 else 1 if v < 5 else 2]
        bars += (f'<i class="sw-kp" style="left:{x0:.3f}%;width:calc({x1 - x0:.3f}% - 1px);height:{max(3.0, v / 9 * (kp_h - 8)):.1f}px;background:{colour}" '
                 f'title="Kp {ls.kp_text(v)} ({ls.kp_label(v)}), the three hours from {t:%d %b %H:%M} UTC"></i>')
    for s in story["storms"]:
        x = left(s["peak_time"])
        anchor = "translate(0,0)" if x < 9 else "translate(-100%,0)" if x > 91 else "translate(-50%,0)"
        labels += (f'<span class="sw-fn" style="left:{x:.3f}%;top:2px;transform:{anchor};background:rgba(220,80,80,.2);border-color:rgba(220,80,80,.6)" '
                   f'title="Storm from {s["start"]:%d %b %H:%M} to {s["end"]:%d %b %H:%M} UTC">{escape(s["level"])} storm · Kp {ls.kp_text(s["peak_kp"])}</span>')
    storm_line = f'<i class="sw-storm" style="top:{kp_h - 5 / 9 * (kp_h - 8) - 2:.1f}px"></i>'
    fl = '<i class="sw-base" style="top:70%"></i>'
    if story["flares_unavailable"]:
        fl += '<span style="position:absolute;left:8px;top:14px;font-size:12.5px;opacity:.75">Flare data is not available for these days.</span>'
    last_label = -100.0
    for t, c in story["flares"]:
        size = 14 if c[:1] == "X" else 9
        fl += (f'<i class="sw-fl" style="left:{left(t):.3f}%;top:70%;width:{size}px;height:{size}px;background:{FLARE_COLOUR[c[:1]]}" '
               f'title="{escape(c)} flare, peak {t:%d %b %H:%M} UTC, {ls.r_level(c)}"></i>')
        if c[:1] == "X" and left(t) - last_label > 3.5:                  # a label too close to the one before is left off (the dot still has its hover text)
            x = last_label = left(t)
            anchor = "translate(0,0)" if x < 9 else "translate(-100%,0)" if x > 91 else "translate(-50%,0)"
            fl += f'<span class="sw-fn" style="left:{x:.3f}%;top:0;transform:{anchor}">{escape(c)}</span>'
    ce = ""
    cmes = story["cmes"]
    fastest = max((c for c in cmes if c.get("speed")), key=lambda c: c["speed"], default=None)
    shocks = {s["shock"] for s in story["storms"] if s.get("shock") is not None}
    for i, c in enumerate(cmes):
        y = 12 + (i % 4) * 9
        x0 = left(c["start"])
        for s in story["storms"]:
            if s["shock"] is not None and c in s["cmes"]:
                x1 = left(s["shock"])
                ce += f'<i class="sw-arrow" style="left:{x0:.3f}%;width:{max(x1 - x0, 0.3):.3f}%;top:{y}px"></i>'
        speed = f", about {c['speed']:,.0f} km/s" if c.get("speed") else ""
        ce += f'<i class="sw-cme" style="left:{x0:.3f}%;top:{y}px" title="CME launched {c["start"]:%d %b %H:%M} UTC{speed}"></i>'
    for sh in sorted(shocks):
        ce += f'<span class="sw-tag" style="left:{left(sh):.3f}%;top:2px;transform:translate(-100%,0)">shock reaches Earth {sh:%H:%M}</span>'
    if fastest is not None:
        ce += f'<span class="sw-tag" style="left:{left(fastest["start"]):.3f}%;top:44px;transform:translate(-50%,0)">fastest about {fastest["speed"]:,.0f} km/s</span>'
    if not cmes:
        if story["donki_state"] == "unavailable":
            why = "Ejections could not be read from NASA's DONKI just now."
        elif not story["storms"]:
            why = "No storm to link ejections to."
        else:
            why = "NASA's DONKI links no ejection to a storm in these days."
        ce += f'<span style="position:absolute;left:8px;top:14px;font-size:12.5px;opacity:.75">{why}</span>'

    def row(label, sub, body, h):
        return (f'<div class="sw-row"><div class="sw-lab" style="min-height:{h}px"><b>{label}</b><small>{sub}</small></div>'
                f'<div class="sw-plot" style="height:{h}px">{grid}{sess}{body}</div></div>')
    items = "".join(f"<li>{escape(x)}</li>" for x in story["sentences"])
    session_label = f'<span class="sw-slab" style="left:{left(a):.3f}%;top:{kp_h - 14}px">Your session</span>'
    return ('<div class="sw-box"><h5>The days around your session</h5>'
            + (f'<ul class="sw-story">{items}</ul>' if items else "")
            + '<div class="sw-grid">'
            + row("Magnetic activity", "Kp, 3-hour steps", bars + storm_line + labels + session_label, kp_h)
            + row("Flares", "M and X, at their peak", fl, 44)
            + (row("Ejections from the Sun", "CMEs NASA links to a storm", ce, 62) if story["storms"] else "")
            + f'<div></div><div class="sw-axis">{axis}</div></div>'
            + '<p class="sw-foot">Times are UTC.' + (" Purple diamonds are ejections at the moment they left the Sun, each with an arrow to the shock NASA links to the storm." if story["storms"] else "") + ' The shaded band is your session.</p></div>')


def _focus_box(f, colours):
    focus = f["focus"]
    if f["flares"] is None:
        return '<div class="sw-box"><h5>Flare in focus</h5><p class="sw-foot" style="margin:0">The flare list could not be read for these dates, so there is no flare to show.</p></div>'
    if not focus:
        return '<div class="sw-box"><h5>Flare in focus</h5><p class="sw-foot" style="margin:0">No flare was listed for these hours.</p></div>'
    level = focus["level"]
    chips = ""
    if focus["bands"]:
        chips += f'<span class="sw-chip ok">During logged {escape(focus["bands"][0])} activity</span> '
    else:
        chips += '<span class="sw-chip mute">Outside your logged activity</span> '
    chips += f'<span class="sw-chip mute">Station in {escape(focus["light"])}</span>'
    d = focus["detail"]
    when = f"Peak {focus['peak']:%H:%M} UTC"
    if d.get("begin") is not None and d.get("end") is not None:
        when += f" · {d['begin']:%H:%M} to {d['end']:%H:%M} UTC"
    level_text = (f"{level}-level · {ls.R_SCALE[level][0]}" if level else "below R1 · too small to affect HF")
    region = f" · active region {escape(str(d['region']))}" if d.get("region") else ""
    return (f'<div class="sw-box"><h5>Flare in focus</h5><div class="sw-big">{escape(focus["class"])} flare</div>'
            f'<div style="font-size:14px">{escape(when)}</div><div style="font-size:13px;opacity:.75;margin:2px 0 8px">{escape(level_text)}{region}</div>{chips}</div>')


def _means_box(f):
    items = "".join(f"<li><b>{escape(a)}</b>{escape(b)}</li>" for a, b in f["bullets"])
    return f'<div class="sw-box"><h5>What this means for HF</h5><ul class="sw-bul">{items}</ul></div>'


def _details(f, story=None):
    lines = []
    if f["kp"]:
        lines.append(f"<b>Magnetic activity:</b> {len(f['kp'])} three-hour Kp value{'s' if len(f['kp']) != 1 else ''} from GFZ Potsdam ({f['kp'][0][0]:%d %b %H:%M} to {f['kp'][-1][0] + pd.Timedelta(hours=3):%d %b %H:%M} UTC). "
                     "Kp is worldwide, so it says whether something unusual was going on, not what worked near you.")
    else:
        lines.append("<b>Magnetic activity:</b> not available for these dates.")
    if f["flux_days"]:
        lines.append("<b>Solar flux:</b> the observed daily 10.7 cm flux from GFZ Potsdam, " + ", ".join(f"{v:.0f} on {t:%d %b}" for t, v in f["flux_days"]) + ".")
    elif f.get("flux_latest"):
        lines.append(f"<b>Solar flux:</b> the flux for the session's own day is not published yet (it comes out later in the day), so this is the latest one, {f['flux_latest'][1]:.0f} on {f['flux_latest'][0]:%d %b}.")
    if f["flares"] is None:
        lines.append("<b>Flares:</b> not available. NOAA's own list reaches back about a month, and the NASA HEK service could not be read.")
    else:
        big = sum(1 for _, c in f["flares"] if c[:1] in ("M", "X"))
        lines.append(f"<b>Flares:</b> {len(f['flares'])} listed in these hours ({big} of class M or X), from {escape(f['flare_source'] or 'NOAA')}. A flare reported more than once is shown once, "
                     "with the class NOAA tied to an active region.")
    lat, lon = f["home"]
    lines.append(f"<b>Daylight:</b> the sun's height at {lat:.2f}, {lon:.2f} (where you operated): up above 0.83° below the horizon, twilight down to 6°, night below that.")
    if story:
        why = {"ok": "NASA's DONKI (api.nasa.gov) records which coronal mass ejections it links to each storm, the flare an ejection came with, and the interplanetary shock that reached Earth; the sentences say what NASA links and do not state a cause of their own. A storm here is any run of three-hour Kp values of 5 or more, whether or not DONKI lists it.",
               "partial": "NASA's DONKI could only be read in part just now, so some causes are missing from the story.",
               "unavailable": "NASA's DONKI could not be read just now, so the story says what the Kp shows and not why.",
               "not_needed": "There was no storm (Kp 5 or more) in these days, so NASA's DONKI was not asked for a cause."}[story["donki_state"]]
        extra = "" if story["own_key"] or story["donki_state"] in ("unavailable", "not_needed") else " The page is using NASA's shared demo key, which is limited to a few requests an hour; a key of its own removes the limit."
        lines.append(f"<b>The story:</b> three days before your session to two days after, from GFZ Potsdam's Kp. {why}{extra}")
    lines.append("<b>MUF:</b> not shown. A real MUF needs ionosonde measurements for the time of the session, and this page has no source for them; it is left out rather than guessed.")
    lines.append("<b>Times:</b> all UTC.")
    return '<div class="sw-box"><details><summary>Technical details and data coverage</summary><ul>' + "".join(f"<li>{x}</li>" for x in lines) + "</ul></details></div>"


def space_html(f, colours, story=None):
    """The card as HTML for st.html (with log_check_html.CSS), or '' when there are no facts."""
    if not f:
        return ""
    return (CSS + '<div class="lc"><div class="lc-card"><h4 class="sw-head">Space weather during your session</h4>'
            '<p class="sw-sub">The solar background, the magnetic field and the events that can affect HF, set beside the hours you were on the air.</p>'
            f'<div class="sw-line">{escape(f["headline"])}</div>' + _tiles(f, None) + (_story_box(story) if story else "") + _timeline(f, colours)
            + f'<div class="sw-2">{_focus_box(f, colours)}{_means_box(f)}</div>' + _details(f, story)
            + '<p class="sw-foot">Sources: GFZ Potsdam (Kp and solar flux), NOAA SWPC (flares, through NOAA or NASA\'s HEK for past dates). All times UTC.</p></div></div>')
