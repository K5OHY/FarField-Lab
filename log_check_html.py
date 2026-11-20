"""The look of the Log check tab: HTML and SVG built from the tables in log_check.py. Colors are fixed mid-tones that read on both the
light and the dark theme, and every block of text takes the page's own color, so nothing here follows the theme by hand."""
from html import escape

import numpy as np
import pandas as pd

from log_check import NEAR_REGIONS, bands_top_down

BLUE, TEAL, AMBER = "#5B8CFF", "#19B5AE", "#F0A020"

CSS = """<style>
.lc{--b:#5B8CFF;--t:#19B5AE;--a:#F0A020;--g:#2FBF8A;--w:#F26B2A;--lane:rgba(128,128,128,.14);--line:rgba(128,128,128,.30);--soft:rgba(128,128,128,.07);line-height:1.45}
.lc *{box-sizing:border-box}
.lc .muted{opacity:.68}
.lc-tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:4px 0 14px}
.lc-tile{border:1px solid var(--line);border-radius:14px;padding:12px 14px;background:var(--soft)}
.lc-tile .n{font-size:32px;font-weight:750;letter-spacing:-.02em;line-height:1.05}.lc-tile .n small{font-size:14px;font-weight:600;opacity:.65;margin-left:4px}
.lc-tile .l{font-weight:600;margin-top:2px}.lc-tile .s{font-size:12.5px;opacity:.68;margin-top:2px}
.lc-card{border:1px solid var(--line);border-radius:16px;padding:16px 18px;margin:12px 0;background:var(--soft)}
.lc-card h4{margin:0 0 2px;font-size:17px}.lc-card .sub{font-size:13px;opacity:.68;margin:0 0 10px}
.lc-legend{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12.5px;opacity:.78;margin:0 0 10px}
.lc-legend i{display:inline-block;width:11px;height:11px;vertical-align:-2px;margin-right:5px;border-radius:3px}
.lc-legend i.pg{border-radius:50%;border:2.5px solid var(--a)}.lc-legend i.ac{border-radius:50%;background:var(--t)}
.lc-legend i.dia{width:9px;height:9px;border-radius:0;transform:rotate(45deg);margin-right:7px;background:currentColor}
.lc-bh,.lc-brow{display:grid;grid-template-columns:44px minmax(100px,1.1fr) 76px minmax(150px,1.6fr) minmax(120px,1.2fr) 190px;gap:14px;align-items:center}
.lc-bh{font-size:11.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;opacity:.65;padding-bottom:8px;border-bottom:1px solid var(--line)}
.lc-brow{padding:10px 0;border-bottom:1px solid var(--line)}.lc-brow:last-child{border-bottom:0}
.lc-bname{font-size:18px;font-weight:750}
.lc-cont{display:grid;grid-template-columns:1fr auto;align-items:center;gap:2px 8px}
.lc-cont .bar{grid-column:1/-1;height:9px;background:var(--lane);border-radius:9px;overflow:hidden}.lc-cont .bar i{display:block;height:100%;background:var(--b);border-radius:9px}
.lc-cont small{grid-column:1/-1;font-size:11.5px;opacity:.7}
.lc-rh,.lc-rr{display:grid;grid-template-columns:minmax(160px,1.5fr) 96px 78px 110px 100px minmax(120px,1.2fr) 96px;gap:12px;align-items:center}
.lc-rh{font-size:11.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;opacity:.65;padding-bottom:8px;border-bottom:1px solid var(--line)}
.lc-rr{padding:9px 0;border-bottom:1px solid var(--line);font-size:14px}.lc-rr:last-child{border-bottom:0}
.lc-rr .rn{font-weight:650}.lc-rr .rn em{font-style:normal;font-size:10.5px;font-weight:700;letter-spacing:.06em;color:var(--a);border:1px solid var(--a);border-radius:99px;padding:1px 6px;margin-left:7px}
.lc-rr .dim{opacity:.55}.lc-rr small{opacity:.65}
.lc-share{display:grid;grid-template-columns:1fr 40px;align-items:center;gap:8px}.lc-share div{height:8px;background:var(--lane);border-radius:8px;overflow:hidden}.lc-share i{display:block;height:100%;background:var(--t);border-radius:8px}
.lc-cont b,.lc-sk b{font-size:17px}.lc-cont span,.lc-sk span{font-size:12px;opacity:.68}.lc-sk{display:flex;flex-direction:column;line-height:1.15}
.lc-dumb{position:relative;height:38px}
.lc-dumb:before{content:"";position:absolute;left:0;right:0;top:11px;height:2px;background:var(--lane);border-radius:2px}
.lc-dumb .g50{position:absolute;left:50%;top:5px;width:1px;height:14px;background:var(--line)}
.lc-dumb .gap{position:absolute;top:10px;height:4px;border-radius:4px;background:linear-gradient(90deg,var(--a),var(--t));opacity:.6}
.lc-dumb u{position:absolute;top:12px;width:14px;height:14px;border-radius:50%;transform:translate(-50%,-50%);text-decoration:none}
.lc-dumb .pg{border:3px solid var(--a);background:Canvas}.lc-dumb .ac{background:var(--t)}
.lc-dumb .cap{position:absolute;left:0;top:23px;font-size:12px;opacity:.78;white-space:nowrap}.lc-dumb .cap s{text-decoration:none;color:var(--a);font-weight:700}.lc-dumb .cap strong{color:var(--t)}
.lc-dumb.none{font-size:12.5px;opacity:.6;line-height:38px}
.lc-str{display:grid;grid-template-columns:1fr 62px;align-items:center;gap:10px}
.lc-sbar{position:relative;height:10px;background:var(--lane);border-radius:9px}.lc-sbar i{position:absolute;top:0;height:100%;border-radius:9px}
.lc-sbar .pos{background:var(--b)}.lc-sbar .neg{background:var(--a)}
.lc-sbar .thin{opacity:.6;background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.55) 0 3px,transparent 3px 6px)}
.lc-sbar .z{position:absolute;top:-3px;width:2px;height:16px;background:currentColor;opacity:.5}.lc-str b{font-size:14px;text-align:right}
.lc-str.none{font-size:12.5px;opacity:.6}
.lc-note{font-size:12.5px;font-weight:600;padding:4px 10px;border-radius:99px;justify-self:start;border:1px solid var(--line)}
.lc-note.good{color:var(--g);border-color:var(--g)}.lc-note.warn{color:var(--w);border-color:var(--w)}
.lc-swim{overflow-x:auto}.lc-chart{min-width:640px}
.lc-lane{display:grid;grid-template-columns:70px 1fr;gap:4px;margin-bottom:8px}
.lc-lab{padding-top:34px;text-align:right;padding-right:6px}.lc-lab b{display:block;font-size:14px;line-height:1.1}.lc-lab span{font-size:11px;opacity:.6}
.lc-plot{position:relative;height:88px;background:var(--lane);border-radius:8px;overflow:hidden}
.lc-mid{position:absolute;left:4px;right:4px;top:56px;height:1.5px;background:var(--line)}
.lc-tick{position:absolute;top:0;bottom:0;width:0;border-left:1px dashed var(--line)}
.lc-b{position:absolute;border-radius:2.5px;background:var(--b)}.lc-b.rep{background:var(--a)}
.lc-s{position:absolute;border-radius:1.5px;background:var(--t);opacity:.55}
.lc-d{position:absolute;width:10px;height:10px;transform:rotate(45deg);background:currentColor;border:1.5px solid Canvas;margin-left:-5px}
.lc-kl{position:absolute;font-size:12.5px;font-weight:700;white-space:nowrap}
.lc-ph{font-size:12.5px;font-weight:650;opacity:.75;margin:10px 0 6px 74px}
.lc-chart + .lc-chart{margin-top:14px}
.lc-axis{position:relative;height:22px;margin-left:74px}.lc-axis span{position:absolute;top:2px;transform:translateX(-50%);font-size:12px;opacity:.65}
.lc-lad{display:grid;grid-template-columns:100px repeat(var(--k),1fr);align-items:center}
.lc-lad .cl .n{font-weight:500;font-size:11px;opacity:.55;margin-left:6px}
.lc-lad .hd{font-size:12px;opacity:.65;text-align:center;padding-bottom:4px}
.lc-lad .cl{font-size:12.5px;font-weight:650;padding:3px 0 3px 8px;height:30px;line-height:24px}
.lc-lad .cd{position:relative;height:30px;display:flex;align-items:center;justify-content:center}
.lc-lad .zb{background:var(--lane)}
.lc-lad .cd.ln:before{content:"";position:absolute;left:0;right:0;top:50%;height:2px;margin-top:-1px;background:var(--a);opacity:.75}
.lc-lad .cd.l0:before{left:50%}.lc-lad .cd.l1:before{right:50%}
.lc-lad .cd i{position:relative;width:13px;height:13px;border-radius:50%;background:var(--b);border:2.2px solid var(--a)}
.lc-two{display:grid;grid-template-columns:minmax(280px,1.05fr) 1fr;gap:20px;align-items:start}
.lc-facts{display:grid;gap:10px}.lc-fact{border:1px solid var(--line);border-radius:12px;padding:10px 13px}
.lc-fact .h{font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;opacity:.65}.lc-fact .b{font-size:14.5px;margin-top:2px}
.lc-fact.warn{border-color:var(--w)}.lc-fact.warn .h{color:var(--w);opacity:1}
@media (max-width:820px){.lc-rh{display:none}.lc-rr{grid-template-columns:1fr 1fr}.lc-rr .rn{grid-column:1/-1}.lc-rr [data-l]:before{content:attr(data-l) ": ";opacity:.6}
.lc-tiles{grid-template-columns:repeat(2,1fr)}.lc-two{grid-template-columns:1fr}
.lc-bh{display:none}.lc-brow{grid-template-columns:48px 1fr;grid-template-areas:"n c" "n d" ". s" ". t";gap:6px 12px}
.lc-bname{grid-area:n}.lc-cont{grid-area:c}.lc-sk{display:none}.lc-dumb{grid-area:d}.lc-str{grid-area:s}.lc-note{grid-area:t}}
</style>"""


def pct(x):
    return f"{x * 100:.0f}%"


def _tile(number, color, label, small, unit=""):
    return (f'<div class="lc-tile"><div class="n" style="color:var({color})">{number}{f"<small>{unit}</small>" if unit else ""}</div>'
            f'<div class="l">{label}</div><div class="s">{small}</div></div>')


def tiles_html(s, overall, repeats):
    """Four tiles: contacts, rate, strength against a typical station (once the comparison has been run), repeat stations."""
    where = f"{s['stations']} stations"
    if s["states"]:
        where += f" · {s['states']} states or provinces"
    if overall is None:
        strength = _tile("–", "--a", "vs a typical WSPR station", "worked out from the RBN comparison below")
    elif np.isnan(overall["stronger_db"]):
        strength = _tile("–", "--a", "vs a typical WSPR station", f"too few receivers matched ({overall['matches']})")
    else:
        strength = _tile(f"{overall['stronger_db']:+.0f}", "--a", f"{'stronger' if overall['stronger_db'] >= 0 else 'weaker'} than a typical WSPR station",
                         f"{overall['matches']} matched receivers · an estimate", "dB")
    return ('<div class="lc"><div class="lc-tiles">'
            + _tile(s["contacts"], "--b", "contacts", escape(where))
            + _tile("–" if np.isnan(s["per_hour"]) else f"{s['per_hour']:.0f}", "--t", "contacts per hour on the air",
                    f"busiest hour {s['best_hour']} contacts, from {s['best_hour_start']:%H:%M}Z" + (" · pauses over 30 min not counted" if s["on_air_hours"] else ""),
                    "" if np.isnan(s["per_hour"]) else "/ hour")
            + strength
            + _tile(repeats, "--g", "came back on another band", "stations worked on 2 or more bands")
            + '</div></div>')


def band_table_html(bands, min_contacts=3):
    """One row per band: contacts, skimmers, the page's chance against the share spotted, and strength against a typical station. A band
    with fewer than `min_contacts` contacts is left out of the rows and named underneath, because one contact says nothing."""
    few = bands[bands["contacts"] < min_contacts]
    bands = bands[bands["contacts"] >= min_contacts]
    top = max(int(bands["contacts"].max()), 1) if len(bands) else 1
    rows = []
    for r in bands.itertuples():
        zero = 15 / 35 * 100
        if np.isnan(r.page) or np.isnan(r.spotted):
            why = "no WSPR picture" if r.no_picture else "too few regions with WSPR"
            dumb = f'<div class="lc-dumb none">{why}</div>'
        else:
            lo, hi = sorted((r.page * 100, r.spotted * 100))
            dumb = (f'<div class="lc-dumb" title="Page said {pct(r.page)}, skimmers that spotted you {pct(r.spotted)} '
                    f'(of {r.listening} on the band)"><em class="g50"></em><em class="gap" style="left:{lo:.1f}%;width:{hi - lo:.1f}%"></em>'
                    f'<u class="pg" style="left:{r.page * 100:.1f}%"></u><u class="ac" style="left:{r.spotted * 100:.1f}%"></u>'
                    f'<span class="cap">page <s>{pct(r.page)}</s> &rarr; spotted <strong>{pct(r.spotted)}</strong></span></div>')
        if np.isnan(r.stronger_db):
            strength = f'<div class="lc-str none">{"too few matches" if r.matches else "no matches"}</div>'
        else:
            pos = (np.clip(r.stronger_db, -15, 20) + 15) / 35 * 100
            left, width = (zero, pos - zero) if r.stronger_db >= 0 else (pos, zero - pos)
            strength = (f'<div class="lc-str" title="{r.matches} skimmers that spotted you were also heard by WSPR stations near you">'
                        f'<div class="lc-sbar"><em class="z" style="left:{zero:.1f}%"></em>'
                        f'<i class="{"pos" if r.stronger_db >= 0 else "neg"}{" thin" if r.thin else ""}" style="left:{left:.1f}%;width:{width:.1f}%"></i></div>'
                        f'<b>{r.stronger_db:+.1f} dB</b></div>')
        report = (f'<span title="The average S in the reports they gave you on this band">report S{r.report:.1f}</span>'
                  if not np.isnan(r.report) else "")
        extra = getattr(r, "other", 0)
        other = f'<small title="Contacts in other modes are in the log but RBN cannot hear them, so they are not compared">+{extra} other mode{"s" if extra != 1 else ""}</small>' if extra else ""
        note = f'<div class="lc-note {r.tone}">{escape(r.note)}</div>' if r.note else "<div></div>"
        rows.append(f'<div class="lc-brow"><div class="lc-bname">{r.band}</div>'
                    f'<div class="lc-cont"><div class="bar"><i style="width:{r.contacts / top * 100:.1f}%"></i></div><b>{r.contacts}</b><span>CW contacts</span>{other}</div>'
                    f'<div class="lc-sk"><b>{r.skimmers}</b><span>skimmers</span>{report}</div>{dumb}{strength}'
                    f'{note}</div>')
    return ('<div class="lc"><div class="lc-card"><h4>Band by band</h4>'
            '<p class="sub">What you worked, who heard you, what the Band conditions page predicted, and how strong you were.</p>'
            '<div class="lc-legend"><span><i class="pg"></i>what the page said (chance)</span>'
            '<span><i class="ac"></i>share of skimmers on the band that spotted you</span>'
            '<span>bar: stronger (blue) or weaker (amber) than a typical station at your power; striped means few matches</span></div>'
            '<div class="lc-bh"><div>Band</div><div>Contacts</div><div>Skimmers</div><div>Page vs spotted</div><div>Strength vs typical</div><div></div></div>'
            + "".join(rows)
            + (f'<p class="sub" style="margin-top:10px">Not shown, with fewer than {min_contacts} CW contacts: '
               + ", ".join(f"{r.band} ({r.contacts} CW" + (f", {r.other} other" if getattr(r, "other", 0) else "") + ")" for r in few.itertuples()) + ".</p>" if len(few) else "")
            + '</div></div>')


def regions_html(regions, band):
    """One band by region: the contacts, stations worked, the skimmers on the band and how many spotted you, and what the Band conditions
    page said. DX regions come first and are tagged. A region with fewer than three WSPR receivers behind it has no page figure."""
    d = regions[regions["band"] == band]
    d = d[(d["contacts"] > 0) | (d["on_band"] > 0)]
    if d.empty:
        return '<div class="lc"><p class="muted">Nothing to show for this band.</p></div>'
    rows = []
    for r in d.itertuples():
        dx = r.region not in NEAR_REGIONS
        tag = "<em>DX</em>" if dx else ""
        contacts = f"{r.contacts}" + (f' <small>({r.cw} CW)</small>' if r.cw != r.contacts else "")
        if r.on_band:
            share = r.spotted / r.on_band
            shared = f'<div class="lc-share"><div><i style="width:{share * 100:.0f}%"></i></div><b>{share * 100:.0f}%</b></div>'
        else:
            shared = '<span class="dim">no skimmers on the band</span>'
        if np.isnan(r.page):
            page = f'<span class="dim" title="Fewer than 3 WSPR receivers in this region, so the page has no figure ({r.wspr_receivers} here)">greyed</span>'
        else:
            page = f'{pct(r.page)} <small>({r.wspr_receivers} WSPR rx)</small>'
        rows.append(f'<div class="lc-rr"><div class="rn">{escape(r.region)}{tag}</div><div data-l="Contacts">{contacts}</div>'
                    f'<div data-l="Stations">{r.stations}</div><div data-l="Skimmers on the band">{r.on_band}</div>'
                    f'<div data-l="Spotted you">{r.spotted}</div><div data-l="Share spotted">{shared}</div><div data-l="Page said">{page}</div></div>')
    return ('<div class="lc"><div class="lc-card"><h4>' + escape(band) + ' by region</h4>'
            '<p class="sub">Contacts are all modes; the skimmers and the page are for CW. Skimmers are counted once each across the whole log.</p>'
            '<div class="lc-rh"><div>Region</div><div>Contacts</div><div>Stations</div><div>Skimmers on the band</div><div>Spotted you</div>'
            '<div>Share spotted</div><div>Page said</div></div>' + "".join(rows) + '</div></div>')


def _ticks(t0, t1):
    span = (t1 - t0).total_seconds() / 60
    step = 15 if span <= 90 else 30 if span <= 200 else 60
    t = t0.ceil(f"{step}min")
    while t <= t1:
        yield t
        t += pd.Timedelta(minutes=step)


UP, DOWN, GAP = 50, 26, 2.5           # pixels: room above a lane's line for blocks, room below it for spots, space between blocks
PANEL_GAP_H = 4                       # a pause this long in the log starts a new chart, so a log over several days is not squeezed into one
SLOTS = (2, 3, 5, 10, 15, 30, 60)     # minutes a block can stack over; the shortest one that keeps a block readable is used
MIN_BLOCK_PX, LANE_PX = 5, 820        # a block is at least about this many pixels wide on a lane about this wide


def _slot_minutes(span_min):
    for m in SLOTS:
        if m / max(span_min, 1) * LANE_PX >= MIN_BLOCK_PX:
            return m
    return SLOTS[-1]


def _panels(log):
    """The log cut into stretches of activity, wherever there is a pause of PANEL_GAP_H hours or more."""
    t = log["time"]
    return [g for _, g in log.groupby((t.diff() > pd.Timedelta(hours=PANEL_GAP_H)).cumsum())]


def _panel_html(part, spots, rep, follow, title, marked):
    """One chart: a lane for each band used in `part`. `marked` is a one-item list that remembers whether the follower's label is drawn."""
    bands = bands_top_down(part)
    span = ((part["time"].max() - part["time"].min()).total_seconds() / 60) + 12
    step = _slot_minutes(span)
    freq = f"{step}min"
    t0, t1 = part["time"].min().floor(freq) - pd.Timedelta(minutes=6), part["time"].max().ceil(freq) + pd.Timedelta(minutes=6)
    minutes = (t1 - t0).total_seconds() / 60
    slot = part.assign(slot=part["time"].dt.floor(freq))
    tallest = max(int(slot.groupby(["band", "slot"]).size().max()), 1)
    up = UP if tallest <= 4 else min(104, 11 * tallest)     # a lane grows when a slot holds many contacts
    mid, height = up + 6, up + 6 + DOWN + 6
    bh = max(3.0, min(12.0, (up - GAP * (tallest - 1)) / tallest))
    gap = GAP if bh > 4 else 1.0
    sp = pd.Series(dtype=int)
    if spots is not None and len(spots):
        k = spots[(spots["time"] >= t0) & (spots["time"] <= t1) & spots["band"].isin(bands)]
        sp = k.assign(slot=k["time"].dt.floor(freq)).groupby(["band", "slot"]).size()
    mx = max(int(sp.max()), 1) if len(sp) else 1
    left = lambda t: (t - t0).total_seconds() / 60 / minutes * 100
    width = f"max(3px, calc({step / minutes * 100:.4f}% - 1.4px))"
    ticks = "".join(f'<i class="lc-tick" style="left:{left(t):.3f}%"></i>' for t in _ticks(t0, t1))
    lanes = []
    for band in bands:
        n = int((part["band"] == band).sum())
        parts = [f'<div class="lc-mid" style="top:{mid}px"></div>', ticks]
        if len(sp) and band in sp.index.get_level_values(0):
            for t, c in sp[band].items():
                parts.append(f'<i class="lc-s" style="left:{left(t):.3f}%;width:{width};top:{mid + 3}px;height:{max(2, c / mx * DOWN):.1f}px" '
                             f'title="{c} RBN spots on {band}, {t:%H:%M}Z"></i>')
        for t, g in slot[slot["band"] == band].groupby("slot"):
            for j, r in enumerate(g.sort_values("time").itertuples()):
                top = mid - 3 - (j + 1) * bh - j * gap
                came_back = r.call in rep
                parts.append(f'<i class="lc-b{" rep" if came_back else ""}" style="left:{left(t):.3f}%;width:{width};top:{top:.1f}px;height:{bh:.1f}px" '
                             f'title="{escape(r.call)} · {band} · {r.time:%H:%M}Z{" · came back on another band" if came_back else ""}"></i>')
                if follow and r.call == follow:
                    parts.append(f'<i class="lc-d" style="left:{left(t) + step / 2 / minutes * 100:.3f}%;top:{top - 13:.1f}px" title="{escape(follow)}"></i>')
                    if not marked[0]:
                        parts.append(f'<span class="lc-kl" style="left:calc({left(t):.3f}% + 14px);top:{top - 15:.1f}px">{escape(follow)}: '
                                     f'{part.loc[part["call"] == follow, "band"].nunique()} bands here</span>')
                        marked[0] = True
        lanes.append(f'<div class="lc-lane"><div class="lc-lab" style="padding-top:{mid - 22}px"><b>{band}</b><span>{n} contact{"s" if n != 1 else ""}</span></div>'
                     f'<div class="lc-plot" style="height:{height}px">{"".join(parts)}</div></div>')
    axis = "".join(f'<span style="left:{left(t):.3f}%">{t:%H:%M}Z</span>' for t in _ticks(t0, t1))
    return (f'<div class="lc-chart"><div class="lc-ph">{title} · blocks stack in {step} minute slots</div>{"".join(lanes)}'
            f'<div class="lc-axis">{axis}</div></div>')


def afternoon_html(log, spots):
    """The session as one chart for each stretch of activity (a pause of four hours or more starts another). One lane per band: above
    its line, one block for each contact, stacked in short time slots (amber for a station that came back on another band); below it,
    the RBN spots in the same slots. Times are UTC. Built of positioned boxes, not SVG, because the page sanitizer removes SVG."""
    rep, follow, marked = set(repeat_calls(log)), pick_follower(log), [False]
    panels = _panels(log)
    charts = []
    for part in panels:
        a, z = part["time"].min(), part["time"].max()
        title = (f"{a:%a %d %b}, {a:%H:%M}Z to {z:%H:%M}Z" if a.date() == z.date() else f"{a:%a %d %b} {a:%H:%M}Z to {z:%a %d %b} {z:%H:%M}Z")
        charts.append(_panel_html(part, spots, rep, follow, title, marked))
    legend = ('<div class="lc-legend"><span><i style="background:var(--b)"></i>one block = one contact (stacked in short time slots)</span>'
              '<span><i style="background:var(--a)"></i>that station came back on another band</span>'
              '<span><i style="background:var(--t);opacity:.55"></i>RBN spots below the line (same slots)</span>'
              + (f'<span><i class="dia"></i>{escape(follow)}</span>' if follow else "") + '</div>')
    return ('<div class="lc"><div class="lc-card"><h4>The session</h4><p class="sub">Your contacts and the spots, band by band, in time order (UTC)'
            + (f"; the log has {len(panels)} stretches of activity, each drawn on its own" if len(panels) > 1 else "") + '.</p>'
            + legend + f'<div class="lc-swim">{"".join(charts)}</div></div></div>')


def repeat_calls(log):
    """The calls worked on more than one band."""
    k = log.groupby("call")["band"].nunique()
    return list(k[k > 1].index)


def pick_follower(log):
    """The station that came back on the most bands, if it was three or more; it gets a line through the chart."""
    k = log.groupby("call")["band"].nunique().sort_values(ascending=False)
    return k.index[0] if len(k) and k.iloc[0] >= 3 else None


def ladder_html(rep, bands, rows=24, first=0):
    """A dot for each band a repeat station was worked on, joined by a line, with the number of bands beside the callsign. Shows `rows`
    stations from number `first` on."""
    cells = ["<div></div>" + "".join(f'<div class="hd">{b}</div>' for b in bands)]
    for i, (call, r) in enumerate(rep.iloc[first:first + rows].iterrows()):
        idx = [bands.index(b) for b in r["bands"] if b in bands]
        lo, hi = min(idx), max(idx)
        z = " zb" if i % 2 == 0 else ""
        row = [f'<div class="cl{z}">{escape(call)}<span class="n" title="worked on {r["k"]} bands">{r["k"]}</span></div>']
        for j, b in enumerate(bands):
            cls = "cd" + z + (" ln" if lo <= j <= hi else "") + (" l0" if j == lo else "") + (" l1" if j == hi else "")
            dot = f'<i title="{escape(call)} · {b}"></i>' if j in idx else ""
            row.append(f'<div class="{cls}">{dot}</div>')
        cells.append("".join(row))
    return f'<div class="lc-lad" style="--k:{len(bands)}">' + "".join(cells) + "</div>"


def _fact(head, body, tone=""):
    return f'<div class="lc-fact {tone}"><div class="h">{head}</div><div class="b">{body}</div></div>'


_NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


def followers_headline(rep):
    """One sentence on how many stations worked you on how many bands: '8 stations worked you on three bands; another 25 on two.'"""
    if not len(rep):
        return "Nobody was worked on more than one band."
    parts = []
    for i, (k, n) in enumerate(rep["k"].value_counts().sort_index(ascending=False).items()):
        word = _NUMBER_WORDS.get(int(k), str(k))
        parts.append(f"{n} station{'s' if n != 1 else ''} worked you on {word} bands" if i == 0 else f"another {n} on {word}")
    return "; ".join(parts) + "."


def ladder_rest_html(log, first=24):
    """The stations of the ladder after the first `first`, for a 'Show all' box under it."""
    from log_check import repeat_stations
    rep = repeat_stations(log)
    return '<div class="lc">' + ladder_html(rep, bands_top_down(log), rows=len(rep), first=first) + "</div>"


def followers_html(log, summary, rows=24):
    """The ladder of the stations worked on more than one band, the most bands first, beside a few notes written from the log."""
    from log_check import repeat_stations, same_band_repeats
    rep = repeat_stations(log)
    facts = []
    far = log[(log["cont"] != "") & (log["cont"] != "NA")]
    if len(far):
        names = ", ".join(f"<b>{escape(r.call)}</b> ({r.band})" for r in far.head(6).itertuples())
        facts.append(_fact("Outside North America", names + (f" and {len(far) - 6} more" if len(far) > 6 else "")))
    facts.append(_fact("Busiest stretch", f"<b>{summary['best_hour']} contacts</b> in the hour from {summary['best_hour_start']:%H:%M}Z. "
                                        f"Longest quiet gap: {summary['longest_gap_min']:.1f} minutes."))
    if summary["park_to_park"]:
        facts.append(_fact("Park to park", f"<b>{summary['park_to_park']} contacts</b> with {summary['parks']} park{'s' if summary['parks'] != 1 else ''}."))
    dupes = same_band_repeats(log)
    if dupes:
        facts.append(_fact("Worked twice on a band", f"{dupes} station{'s were' if dupes != 1 else ' was'} logged more than once on the same band."))
    ladder = ladder_html(rep, bands_top_down(log), rows) if len(rep) else '<p class="muted">Nobody was worked on more than one band.</p>'
    return ('<div class="lc"><div class="lc-card"><h4>Who followed you</h4>'
            f'<p class="sub">{followers_headline(rep)}</p>'
            f'<div class="lc-two"><div>{ladder}</div><div class="lc-facts">{"".join(facts)}</div></div></div></div>')
