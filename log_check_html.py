"""The look of the Log check tab: HTML and SVG built from the tables in log_check.py. Colors are fixed mid-tones that read on both the
light and the dark theme, and every block of text takes the page's own color, so nothing here follows the theme by hand."""
from html import escape

import numpy as np
import pandas as pd

from log_check import BALANCE_MIN, CONTINENT_NAMES, DX_FIRST, DX_MILES, DXCC_ENTITIES, CQ_ZONES, HABIT_SHARE, NEAR_REGIONS, bands_top_down, pota_notes

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
.lc-d{position:absolute;z-index:3;width:10px;height:10px;transform:rotate(45deg);background:currentColor;border:1.5px solid Canvas;margin-left:-5px}
.lc-kl{position:absolute;z-index:3;font-size:12.5px;font-weight:700;white-space:nowrap}
.lc-ph{font-size:12.5px;font-weight:650;opacity:.75;margin:10px 0 6px 74px}
.lc-chart + .lc-chart{margin-top:14px}
.lc-axis{position:relative;height:22px;margin-left:74px}.lc-axis span{position:absolute;top:2px;transform:translateX(-50%);font-size:12px;opacity:.65}
.lc-lad{display:grid;grid-template-columns:118px repeat(var(--k),1fr);align-items:center}
.lc-lad .cl .n{font-weight:500;font-size:11px;opacity:.55;margin-left:6px}
.lc-lad .hd{font-size:12px;opacity:.65;text-align:center;padding-bottom:4px}
.lc-lad .cl{font-size:12.5px;font-weight:650;padding:3px 0 3px 8px;height:30px;line-height:24px}
.lc-lad .cd{position:relative;height:30px;display:flex;align-items:center;justify-content:center}
.lc-lad .zb{background:var(--lane)}
.lc-lad .cd.ln:before{content:"";position:absolute;left:0;right:0;top:50%;height:2px;margin-top:-1px;background:var(--a);opacity:.75}
.lc-lad .cd.l0:before{left:50%}.lc-lad .cd.l1:before{right:50%}
.lc-lad .cd i{position:relative;width:13px;height:13px;border-radius:50%;background:var(--b);border:2.2px solid var(--a)}
.lc-cgw{overflow-x:auto;margin-top:8px}
.lc-cg{display:grid;grid-template-columns:42px repeat(var(--k),minmax(0,1fr));gap:4px;align-items:stretch;min-width:calc(42px + var(--k) * 44px)}
.lc-cg.dense .th span{display:none}.lc-cg.dense .th b{font-size:10.5px}.lc-cg.dense .cell .p{font-size:11.5px}
.lc-cg.dense .cell em{font-size:9px;padding:0 4px 0 3px;right:1px;bottom:1px}
.lc-cg .th{text-align:center;line-height:1.2}.lc-cg .th b{display:block;font-size:12.5px}.lc-cg .th span{font-size:10.5px;opacity:.6}
.lc-cg .bl{display:flex;align-items:center;font-weight:700;font-size:13.5px}
.lc-cg .cell{position:relative;height:48px;border-radius:8px;display:flex;align-items:center;justify-content:center;border:1px solid var(--line)}
.lc-cg .cell .p{font-size:15px;font-weight:700}
.lc-cg .cell.few{background:repeating-linear-gradient(135deg,transparent 0 5px,rgba(128,128,128,.28) 5px 6px)}.lc-cg .cell.few .p{opacity:.45;font-weight:500}
.lc-cg .cell em{position:absolute;right:3px;bottom:2px;font-style:normal;font-size:10.5px;font-weight:700;background:Canvas;color:CanvasText;border-radius:99px;padding:0 6px 0 4px;display:flex;align-items:center;gap:3px;border:1px solid var(--line)}
.lc-cg .cell em i{display:inline-block;width:7px;height:7px;background:var(--a);transform:rotate(45deg);border:1px solid Canvas}
.lc-ramp{display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin:12px 0 4px;font-size:12px;opacity:.8}
.lc-ramp b{display:inline-block;width:130px;height:9px;border-radius:6px;background:linear-gradient(90deg,rgba(32,178,170,.15),rgba(32,178,170,.95));vertical-align:middle;margin:0 6px}
.lc-says{margin:12px 0 0;padding-left:20px}.lc-says li{margin:6px 0;font-size:14px}
.lc-dx .cell{height:auto;min-height:66px;padding:5px 2px;flex-direction:column;gap:3px;background:transparent}.lc-dx .cell .p{line-height:1}
.lc-dx .cell.s3{background:rgba(32,178,170,.88)}.lc-dx .cell.s3 .p{color:#04201e}
.lc-dx .cell.s1{background:rgba(32,178,170,.40)}
.lc-dx .cell.none .p{opacity:.35;font-weight:500}
.lc-dx .m{display:flex;flex-wrap:wrap;gap:3px;align-items:center;justify-content:center;min-height:15px}
.lc-dx .cell em{position:static}.lc-dx .cell em.st{color:var(--a);padding:0 4px}
.lc-dx .cell em u{display:inline-block;width:3px;height:3px;border-radius:50%;background:Canvas;border:2px solid #3b82f6;box-sizing:content-box}
.lc-cg .grp{grid-column:1/-1;font-size:12px;font-weight:600;opacity:.7;margin:8px 0 0}
.lc-key{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:10px 0 0;font-size:12px;opacity:.85}
.lc-key .sw{display:inline-flex;align-items:center;gap:6px}.lc-key .sw b{display:inline-block;width:22px;height:13px;border-radius:4px;border:1px solid var(--line)}
.lc-reg{border-collapse:collapse;width:100%;font-size:13.5px}.lc-reg td,.lc-reg th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}
.lc-reg th{font-weight:600;font-size:12px;opacity:.7}.lc-reg small{opacity:.65}
.lc-kp{position:absolute;bottom:6px;border-radius:2px 2px 0 0}.lc-storm{position:absolute;left:0;right:0;height:0;border-top:1px dashed rgb(230,120,40);opacity:.8}
.lc-fl{position:absolute;top:50%;border-radius:50%;border:1px solid Canvas}.lc-kq{position:absolute;bottom:6px;background:var(--a);border-radius:1.5px 1.5px 0 0}
.lc-card a{color:inherit;text-decoration:underline}
.lc-hero{border:1px solid var(--line);border-left:6px solid rgb(32,178,170);border-radius:14px;padding:16px 20px;margin:0 0 12px}
.lc-hero .k{font-size:11px;font-weight:700;letter-spacing:.08em;opacity:.65}.lc-hero h3{margin:2px 0 6px;font-size:24px;line-height:1.2}
.lc-hero p{margin:0;font-size:15px}.lc-hero p.s{margin-top:6px;font-weight:600}
.lc-reg .dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:rgb(32,178,170);margin-right:6px}.lc-reg .no{opacity:.35}
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


def _tile(number, color, label, small, unit="", title=""):
    return (f'<div class="lc-tile"' + (f' title="{escape(title)}"' if title else "") + f'><div class="n" style="color:var({color})">{number}{f"<small>{unit}</small>" if unit else ""}</div>'
            f'<div class="l">{label}</div><div class="s">{small}</div></div>')


RATE_NOTE = ("Contacts divided by the time between them, counting only gaps of 30 minutes or less, so a break is not counted as slow operating. "
             "It is an estimate: a log does not say when you were actually on the air.")


def tiles_html(s, repeats):
    """Four tiles: contacts, the estimated active rate, the bands worked, and the stations that came back on another band."""
    where = f"{s['stations']} stations"
    if s["states"]:
        where += f" · {s['states']} states or provinces"
    bands = s["bands"]
    span = bands[0] if len(bands) == 1 else f"{bands[0]} down to {bands[-1]}"
    return ('<div class="lc"><div class="lc-tiles">'
            + _tile(s["contacts"], "--b", "contacts", escape(where))
            + _tile("–" if np.isnan(s["per_hour"]) else f"{s['per_hour']:.0f}", "--t", "estimated active rate",
                    f"busiest hour {s['best_hour']} contacts, from {s['best_hour_start']:%H:%M}Z" + (" · pauses over 30 min not counted" if s["on_air_hours"] else ""),
                    "" if np.isnan(s["per_hour"]) else "/ hour", RATE_NOTE)
            + _tile(len(bands), "--a", "bands worked", escape(span))
            + _tile(repeats, "--g", "came back on another band", "stations worked on 2 or more bands")
            + '</div></div>')


ENTITY_ROWS = 12      # the countries shown at first; the rest are under a 'Show more' box


def worked_tiles_html(w):
    """A second row of tiles: DXCC entities, continents, US states and CQ zones, each against the whole it is part of."""
    n = w["n_entities"]
    away = int((w["ents"]["cont"] != w["home"]).sum())
    tiles = [_tile(n, "--b", "DXCC entities worked", f"{away} outside {escape(CONTINENT_NAMES.get(w['home'], 'your continent'))}" if away else "all on your continent",
                   f"of {DXCC_ENTITIES}", "")]
    seen = len(w["continents"])
    tiles.append(_tile(seen, "--t", "continents", "all six: WAC" if seen == 6 else "missing " + escape(", ".join(w["missing_continents"])), "of 6"))
    if w["has_us"]:
        miss = w["missing_states"]
        tiles.append(_tile(len(w["states"]), "--a", "US states", ("all 50: WAS" if not miss else f"missing {', '.join(miss)}" if len(miss) <= 6 else f"{len(miss)} to go")
                           + (f" · {len(w['provinces'])} Canadian provinces" if w["has_ca"] else ""), "of 50"))
    if w["cq"] is not None:
        tiles.append(_tile(len(w["cq"]), "--g", "CQ zones", f"{w['itu']} ITU zones" if w["itu"] is not None else "", f"of {CQ_ZONES}"))
    return '<div class="lc" style="margin-top:12px"><div class="lc-tiles">' + "".join(tiles) + "</div></div>"


def _ent_rows(w, bands, first, rows):
    out = []
    for key, r in w["ents"].iloc[first:first + rows].iterrows():
        dots = "".join(f'<td>{"&#9679;" if b in r["bands"] else "<span class=\"no\">&middot;</span>"}</td>' for b in bands)
        out.append(f'<tr><td><b>{escape(str(r["name"]))}</b> <small>{escape(str(r["cont"]))}</small></td><td>{int(r["contacts"])}</td>{dots}</tr>')
    return "".join(out)


def worked_html(w, bands, rows=ENTITY_ROWS, first=0):
    """The countries worked, with the contacts and a dot for each band, those outside the home continent first; `first` and `rows` pick the stretch
    of the list shown (the rest wait under a 'Show more' box)."""
    head = "<tr><th>Country</th><th>Contacts</th>" + "".join(f"<th>{escape(b)}</th>" for b in bands) + "</tr>"
    table = f'<div class="lc-cgw"><table class="lc-reg">{head}{_ent_rows(w, bands, first, rows)}</table></div>'
    if first:
        return '<div class="lc">' + table + "</div>"
    counts = " · ".join(f"{escape(b)} {n}" for b, n in w["per_band"].items())
    return ('<div class="lc"><div class="lc-card"><h4>What you worked</h4>'
            f'<p class="sub">{w["n_entities"]} DXCC entities in this log, those outside {escape(CONTINENT_NAMES.get(w["home"], "your continent"))} first. A dot means the country was '
            'worked on that band. This is what the log says, not what is confirmed by LoTW or the ARRL.</p>' + table
            + f'<p class="sub" style="margin-top:8px"><b>{w["band_countries"]} band-countries</b> (each country counted once per band): {counts}.</p></div></div>')


def still_to_work_html(w):
    """What is still missing, for the stretch of the log: continents, US states, Canadian provinces and CQ zones. Empty when nothing is missing."""
    items = []
    if w["missing_continents"]:
        items.append(f"<li><b>Continents ({len(w['missing_continents'])}):</b> {escape(', '.join(w['missing_continents']))}</li>")
    if w["has_us"] and w["missing_states"]:
        items.append(f"<li><b>US states ({len(w['missing_states'])}):</b> {escape(', '.join(w['missing_states']))}</li>")
    if w["has_ca"] and w["missing_provinces"]:
        items.append(f"<li><b>Canadian provinces and territories ({len(w['missing_provinces'])}):</b> {escape(', '.join(w['missing_provinces']))}</li>")
    if w["missing_cq"]:
        items.append(f"<li><b>CQ zones ({len(w['missing_cq'])}):</b> {escape(', '.join(str(z) for z in w['missing_cq']))}</li>")
    return '<div class="lc"><ul class="lc-says">' + "".join(items) + "</ul></div>" if items else ""


def _teal(share):
    """A teal that deepens with the share of receivers that would hear you."""
    return f"rgba(32,178,170,{0.12 + 0.80 * float(share) ** 1.6:.2f})"


def _local_time(s, tz_name):
    """The time of a slot in the visitor's time zone, as HH:MM, or an empty string when there is none or it is not a zone."""
    from zoneinfo import ZoneInfo
    try:
        return f"{pd.Timestamp(s).tz_localize('UTC').astimezone(ZoneInfo(tz_name)):%H:%M}" if tz_name else ""
    except Exception:
        return ""


def _evidence_line(grid):
    """How much WSPR the DX picture rests on, so a thin picture looks thin: the reports, the transmitters near you, the stations that decoded
    them and how far away the farthest was."""
    ev = grid.attrs.get("evidence") or {}
    if not ev.get("reports"):
        return ""
    far = round(ev["farthest_km"] / 1.609344, -2)
    thin = " That is few transmitters, so the picture is thin." if ev["transmitters"] < 5 else ""
    return (f'<p class="sub"><b>The evidence:</b> {ev["reports"]:,} WSPR reports from {ev["transmitters"]} transmitter{"s" if ev["transmitters"] != 1 else ""} within 300 miles of you, decoded by '
            f'{ev["receivers"]:,} stations as far away as {far:,.0f} miles.{thin}</p>')


def _runs_text(slots, stamp):
    """The half hours in `slots` as windows ('13:30-15:00, 18:00-20:30'): half hours that do not follow each other are separate windows."""
    from log_check import _slot_windows
    step = pd.Timedelta(minutes=30)
    runs = _slot_windows(slots)
    text = ", ".join(f"{stamp(a)}&ndash;{stamp(b + step)}" for a, b in runs[:3])
    return text + (f", and {len(runs) - 3} more" if len(runs) > 3 else "")


DX_VIEWS = {"estimate": "Estimate for my station", "observed": "What WSPR showed"}


def dx_windows_html(grid, notes, power_w, mode="CW", tz_name=None, view="estimate"):
    """When DX was there while you were on the air: a box for each band and half hour. In the 'observed' view it counts the WSPR stations
    DX_MILES or more away that decoded WSPR transmitters near you; in the 'estimate' view, those that looked strong enough to hear a signal like
    yours. Your contacts (diamond), contacts outside North America (star) and skimmers that far away that spotted you (a ring) sit on top, and
    the lines that say it in words follow. Bands you did not work come after the ones you did."""
    miles = f"{DX_MILES:,}"
    observed = view == "observed"
    first = grid.drop_duplicates("band")
    flags = dict(zip(first["band"], first["worked"])) if "worked" in first else {b: True for b in first["band"]}
    all_bands = [b for b in first["band"] if flags[b]] + [b for b in first["band"] if not flags[b]]
    panels = []
    for panel, d in grid.groupby("panel"):
        slots = sorted(d["slot"].unique())
        by = {(r.band, r.slot): r for r in d.itertuples()}
        head = "<div></div>" + "".join(f'<div class="th"><b>{pd.Timestamp(s):%H:%M}</b>'
                                       + (f"<span>{_local_time(s, tz_name)} local</span>" if _local_time(s, tz_name) else "") + "</div>" for s in slots)
        cells, in_group = [], False
        for b in all_bands:
            if not flags[b] and not in_group:
                cells.append('<div class="grp">Bands you did not work</div>')
                in_group = True
            cells.append(f'<div class="bl">{escape(b)}</div>')
            for s in slots:
                r = by[(b, s)]
                n = r.dx_heard if observed else r.dx_good
                kind = "s3" if n >= 3 else "s1" if n >= 1 else ("few" if (not observed and r.dx_heard > 0) else "none")
                marks = (f'<em><i></i>{r.contacts}</em>' if r.contacts else "") + ('<em class="st" title="a contact outside North America">&#9733;</em>' if r.dx_contacts else "") \
                    + ('<em title="a skimmer that far away spotted you"><u></u></em>' if r.rbn_far else "")
                tip = (f"{b} {pd.Timestamp(s):%H:%M}Z: {r.dx_heard} WSPR stations over {miles} miles decoded WSPR near you; {r.contacts} contacts" if observed else
                       f"{b} {pd.Timestamp(s):%H:%M}Z: {r.dx_good} WSPR stations over {miles} miles estimated strong enough for {power_w:g} W; {r.dx_heard} that far "
                       f"decoded WSPR near you; {r.contacts} contacts")
                cells.append(f'<div class="cell {kind}" title="{escape(tip)}"><span class="p">{n if n else "&ndash;"}</span>'
                             f'<span class="m">{marks}</span></div>')
        title = f'<p class="sub" style="margin:14px 0 0"><b>{pd.Timestamp(slots[0]):%a %d %b}</b> (UTC)</p>' if grid["panel"].nunique() > 1 else ""
        dense = " dense" if len(slots) > 10 else ""
        panels.append(title + f'<div class="lc-cgw"><div class="lc-cg lc-dx{dense}" style="--k:{len(slots)}">{head}{"".join(cells)}</div></div>')
    says = ("<ul class=\"lc-says\">" + "".join(f"<li><b>{escape(lead)}</b> {escape(rest)}</li>" for lead, rest in notes) + "</ul>") if notes else ""
    if observed:
        heading = "Band conditions while you were on the air: what WSPR showed"
        intro = (f'<p class="sub">What WSPR showed. Each box counts the WSPR stations over {miles} miles from you that decoded WSPR transmitters near you in the hour up to '
                 'the end of that half hour. Nothing is assumed about your power or mode. It counts different stations, not reports. '
                 '(A WSPR station here is a receiver, not an RBN skimmer.)</p>')
        reading = ('<p class="sub"><b>How to read it:</b> read across a row to follow a band over time. A dash means no station that far decoded WSPR near you. '
                   'Bands have different numbers of stations, so use the counts to compare hours, not to rank bands.</p>')
        key = ('<div class="lc-key"><span class="sw"><b style="background:rgba(32,178,170,.88)"></b>3 or more decoded WSPR</span>'
               '<span class="sw"><b style="background:rgba(32,178,170,.40)"></b>1 or 2</span><span class="sw"><b></b>none that far</span></div>')
        caveat = ('<p class="sub" style="margin-top:10px">This is what was decoded, with no estimate in it. WSPR only covers stations within 300 miles of you, and a band with few '
                  'transmitters there has thin evidence. ')
    else:
        heading = f"Band conditions while you were on the air: estimate for {power_w:g} W"
        intro = (f'<p class="sub">An estimate of when a signal like yours could have reached more than {miles} miles. Each box counts the WSPR stations over {miles} miles '
                 f'from you that decoded WSPR transmitters near you in the hour up to the end of that half hour and looked strong enough to hear {power_w:g} W using '
                 f'{escape(mode)} (their reports restated to your power, with 3 dB to spare). It counts different stations, not reports. '
                 '(A WSPR station here is a receiver, not an RBN skimmer.)</p>')
        reading = ('<p class="sub"><b>How to read it:</b> read across a row to follow a band over time. A dash means no station that far looked strong enough; '
                   'a striped box means stations that far decoded WSPR, but none looked strong enough. Bands have different numbers of stations, so use the counts to '
                   'compare hours, not to rank bands.</p>')
        key = ('<div class="lc-key"><span class="sw"><b style="background:rgba(32,178,170,.88)"></b>3 or more look strong enough</span>'
               '<span class="sw"><b style="background:rgba(32,178,170,.40)"></b>1 or 2</span>'
               '<span class="sw"><b style="background:repeating-linear-gradient(135deg,transparent 0 5px,rgba(128,128,128,.4) 5px 6px)"></b>decoded WSPR, none strong enough</span>'
               '<span class="sw"><b></b>no reports that far</span></div>')
        caveat = ('<p class="sub" style="margin-top:10px">"Strong enough" is an estimate: each station\'s WSPR reports are restated to your power and compared with what the mode needs, '
                  'assuming an ordinary antenna. It tends to run high, so use it to compare bands and hours, not to promise a contact. WSPR only covers stations within 300 miles '
                  'of you, and a band with few of them has thin evidence. ')
    return (f'<div class="lc"><div class="lc-card"><h4>{escape(heading)}</h4>' + intro + reading + _evidence_line(grid) + "".join(panels) + key
            + '<div class="lc-key"><span class="sw"><span style="display:inline-block;width:8px;height:8px;background:var(--a);transform:rotate(45deg)"></span> contacts in that half hour</span>'
              '<span class="sw"><span style="color:var(--a);font-weight:700">&#9733;</span> a contact outside North America</span>'
              f'<span class="sw"><span style="display:inline-block;width:3px;height:3px;border-radius:50%;background:Canvas;border:2px solid #3b82f6"></span> an RBN skimmer over {miles} miles away spotted you</span></div>'
            + says + caveat
            + 'RBN has far fewer skimmers than WSPR has receivers, especially outside North America and Europe: a ring is proof you were heard that far, but no ring says nothing. '
              'These lines say what was seen in the data, not what you should have done.</p></div></div>')


def dx_regions_html(grid, view="estimate"):
    """Where DX reached, by band: for each band and region, the most WSPR stations over DX_MILES away in one half hour (those that decoded WSPR near you
    in the 'observed' view, those that looked strong enough for you in the 'estimate' view) and the windows in which there were any. Half hours that do
    not follow each other are separate windows. Empty when there was nothing to show."""
    observed = view == "observed"
    col = "dx_regions_heard" if observed and "dx_regions_heard" in grid.columns else "dx_regions"
    seen = {k for d in grid[col] for k in d}
    if not seen:
        return ""
    regions = [r for r in DX_FIRST if r in seen] + sorted(seen - set(DX_FIRST))
    many = grid["panel"].nunique() > 1
    stamp = (lambda t: f"{t:%d %b %H:%M}") if many else (lambda t: f"{t:%H:%M}")
    rows = []
    for band in list(grid.drop_duplicates("band")["band"]):
        d = grid[grid["band"] == band].sort_values("slot")
        tds = []
        for reg in regions:
            hits = [(s, r[reg]) for s, r in zip(d["slot"], d[col]) if r.get(reg, 0) > 0]
            if hits:
                best = max(n for _, n in hits)
                tds.append(f'<td><span class="dot" style="opacity:{0.35 + 0.65 * min(best / 3, 1):.2f}"></span>{best} <small>{_runs_text([s for s, _ in hits], stamp)}</small></td>')
            else:
                tds.append('<td><span class="no">&ndash;</span></td>')
        n, x = int(d["contacts"].sum()), int(d["dx_contacts"].sum())
        mine = f"{n}" if n else '<span class="no">not worked</span>'
        rows.append(f"<tr><td><b>{escape(band)}</b></td>{''.join(tds)}<td>{mine}" + (f" <small>({x} outside North America)</small>" if x else "") + "</td></tr>")
    what = "decoded WSPR transmitters near you" if observed else "looked strong enough to hear you"
    return ('<div class="lc"><div class="lc-card"><h4>Where DX reached, by band</h4>'
            f'<p class="sub">The most WSPR stations over {DX_MILES:,} miles away that {what} in one half hour, by region, with the windows in which there were any (UTC). '
            'Half hours that do not follow each other are listed as separate windows.</p><div class="lc-cgw"><table class="lc-reg"><tr><th>Band</th>'
            + "".join(f"<th>{escape(r)}</th>" for r in regions) + "<th>Your contacts</th></tr>" + "".join(rows) + "</table></div></div></div>")


def conditions_html(grid, notes, power_w, mode="CW", tz_name=None):
    """The picture of how open each band looked while you were on the air: a box for each band and half hour, shaded by the share of nearby
    WSPR receivers that would have heard you, with your contacts on top, and the lines that say it in words. `tz_name` (the visitor's time
    zone) adds the local time under each UTC time."""
    from zoneinfo import ZoneInfo
    all_bands = list(grid.drop_duplicates("band")["band"])
    panels = []
    for panel, d in grid.groupby("panel"):
        slots = sorted(d["slot"].unique())
        by = {(r.band, r.slot): r for r in d.itertuples()}
        bands = [b for b in all_bands if d.loc[d["band"] == b, "contacts"].sum() > 0 or d.loc[d["band"] == b, "share"].notna().any()]   # no empty rows

        def local(s):
            try:
                return f"{pd.Timestamp(s).tz_localize('UTC').astimezone(ZoneInfo(tz_name)):%H:%M}" if tz_name else ""
            except Exception:
                return ""
        head = "<div></div>" + "".join(f'<div class="th"><b>{pd.Timestamp(s):%H:%M}</b>' + (f"<span>{local(s)} local</span>" if local(s) else "") + "</div>"
                                       for s in slots)
        cells = []
        for b in bands:
            cells.append(f'<div class="bl">{escape(b)}</div>')
            for s in slots:
                r = by[(b, s)]
                pill = f'<em><i></i>{r.contacts}</em>' if r.contacts else ""
                if np.isnan(r.share):
                    cells.append(f'<div class="cell few" title="{escape(b)} {pd.Timestamp(s):%H:%M}Z: only {r.receivers} WSPR stations, too few to say; '
                                 f'{r.contacts} contacts"><span class="p">&ndash;</span>{pill}</div>')
                else:
                    cells.append(f'<div class="cell" style="background:{_teal(r.share)}" title="{escape(b)} {pd.Timestamp(s):%H:%M}Z: {r.good} of {r.receivers} '
                                 f'WSPR stations would hear you; {r.contacts} contacts"><span class="p">{pct(r.share)}</span>{pill}</div>')
        title = f'<p class="sub" style="margin:14px 0 0"><b>{pd.Timestamp(slots[0]):%a %d %b}</b> (UTC)</p>' if grid["panel"].nunique() > 1 else ""
        dense = " dense" if len(slots) > 10 else ""
        panels.append(title + f'<div class="lc-cgw"><div class="lc-cg{dense}" style="--k:{len(slots)}">{head}{"".join(cells)}</div></div>')
    says = ("<ul class=\"lc-says\">" + "".join(f"<li><b>{escape(lead)}</b> {escape(rest)}</li>" for lead, rest in notes) + "</ul>") if notes else ""
    return ('<div class="lc"><div class="lc-card"><h4>How open each band looked: percent of stations that could hear you</h4>'
            f'<p class="sub">An estimate for your station at {power_w:g} W using {escape(mode)}. Each box is the percentage of the stations that decoded WSPR near you on '
            'that band that would also have decoded a signal like yours, in the hour up to the end of each half hour. Your contacts are the amber diamonds.</p>'
            + '<p class="sub"><b>How to read it:</b> read across each row to follow that band over time. Different bands have different numbers of '
              'stations behind them, so the percentages of different bands are not comparable with each other.</p>'
            + "".join(panels)
            + '<div class="lc-ramp"><span>fewer<b></b>more stations would hear you</span><span>hatched: too few WSPR stations to say</span>'
              '<span><span style="display:inline-block;width:8px;height:8px;background:var(--a);transform:rotate(45deg)"></span> contacts in that half hour</span></div>'
            + says
            + '<p class="sub" style="margin-top:10px">An estimate from WSPR transmitters within 300 miles of you, restated to your power. Use it to compare a band with itself over time '
              'and one hour with another. It is not an exact chance of a contact (the percentages run high), and bands cannot be fairly compared with each other: '
              'a band with many distant stations, such as 20m, tends to show a lower share.</p>'
            '</div></div>')


def balance_html(bal):
    """Who hears whom, by band: the average S they gave you and you gave them, the difference in dB, and a plain reading. Empty when no
    contact carries a report both ways."""
    if bal.empty:
        return ""
    rows = []
    for r in bal.itertuples():
        diff = f"{r.diff_db:+.0f} dB" if r.n >= BALANCE_MIN and r.habit < HABIT_SHARE else "&ndash;"
        label = f"<b>{escape(r.band)}</b>"
        rows.append(f"<tr><td>{label}</td><td>{r.n}</td><td>S{r.got:.1f}</td><td>S{r.gave:.1f}</td><td>{diff}</td><td>{escape(r.reading)}</td></tr>")
    return ('<div class="lc"><div class="lc-card"><h4>Do they hear you as well as you hear them?</h4>'
            '<p class="sub">From the reports in your log. A report is the S in RST (579 is S7); one S-unit is about 6 dB. A positive difference means the stations '
            'you worked gave you stronger reports than you gave them. Many operators send a 9 out of habit, and a difference can come from their antenna, their noise or their '
            'habits as easily as from your station, so this is a rough picture, not a measurement. A band needs at least '
            f'{BALANCE_MIN} contacts with a report both ways before it says anything.</p>'
            '<div class="lc-cgw"><table class="lc-reg"><tr><th>Band</th><th>Contacts with reports both ways</th><th>They gave you</th><th>You gave them</th>'
            '<th>Difference</th><th>Reading</th></tr>' + "".join(rows) + "</table></div></div></div>")


KP_COLOURS = ("rgb(76,175,80)", "rgb(230,161,23)", "rgb(210,80,80)")


def space_weather_html(wx, log, notes):
    """The space weather over the session: Kp in 3 hour steps, the flares at their peak, and your contacts in the same hours, with the lines
    that say it in words. Empty when nothing could be read."""
    from log_check import space_span
    if not (wx.get("kp") or wx.get("flux") or wx.get("flares")):
        return ""
    start, end = space_span(log)
    minutes = (end - start).total_seconds() / 60
    left = lambda t: max(0.0, min(100.0, (t - start).total_seconds() / 60 / minutes * 100))
    ticks_t = list(_ticks(start, end))
    ticks = "".join(f'<i class="lc-tick" style="left:{left(t):.3f}%"></i>' for t in ticks_t)
    axis = "".join(f'<span style="left:{left(t):.3f}%">{t:%H:%M}Z</span>' for t in ticks_t)
    kp = ""
    for t, v in wx.get("kp") or []:
        a, b = max(t, start), min(t + pd.Timedelta(hours=3), end)
        colour = KP_COLOURS[0 if v < 3 else 1 if v < 5 else 2]
        kp += (f'<i class="lc-kp" style="left:{left(a):.3f}%;width:calc({left(b) - left(a):.3f}% - 2px);height:{max(3.0, v / 9 * 44):.1f}px;background:{colour}" '
               f'title="Kp {v:.1f}, the three hours from {t:%H:%M}Z"></i>')
    flares = ""
    for t, c in wx.get("flares") or []:
        size = {"X": 12, "M": 9}.get(c[:1], 5)
        colour = {"X": "rgb(210,80,80)", "M": "rgb(230,161,23)"}.get(c[:1], "rgb(140,140,140)")
        flares += (f'<i class="lc-fl" style="left:{left(t):.3f}%;width:{size}px;height:{size}px;margin:{-size / 2:.1f}px 0 0 {-size / 2:.1f}px;background:{colour}" '
                   f'title="{c} flare, peak {t:%H:%M}Z"></i>')
    slot = log.assign(slot=log["time"].dt.floor("30min")).groupby("slot").size()
    top = max(int(slot.max()), 1) if len(slot) else 1
    bars = "".join(f'<i class="lc-kq" style="left:{left(t):.3f}%;width:calc({30 / minutes * 100:.3f}% - 1px);height:{max(2.0, n / top * 30):.1f}px" '
                   f'title="{n} contacts, {t:%H:%M}Z"></i>' for t, n in slot.items())
    lane = lambda label, body, h: (f'<div class="lc-lane"><div class="lc-lab" style="padding-top:{h // 2 - 8}px"><b>{label}</b></div>'
                                   f'<div class="lc-plot" style="height:{h}px">{ticks}{body}</div></div>')
    says = ("<ul class=\"lc-says\">" + "".join(f"<li><b>{escape(a)}</b> {escape(b)}</li>" for a, b in notes) + "</ul>") if notes else ""
    storm = f'<i class="lc-storm" style="top:{50 - 5 / 9 * 44:.1f}px" title="Kp 5: a geomagnetic storm"></i>'
    return ('<div class="lc"><div class="lc-card"><h4>Space weather during your session</h4>'
            '<p class="sub">Kp is the worldwide measure of magnetic disturbance (0 is calm, 5 and above is a storm), shown in three-hour steps; the dots are solar flares at '
            'their peak (grey C, amber M, red X). Your contacts are along the bottom. These are worldwide figures: they say whether something unusual was going on, '
            'not what worked near you. Times are UTC.</p>'
            '<div class="lc-chart">' + lane("Kp", kp + storm, 56) + lane("Flares", flares, 30) + lane("Contacts", bars, 40)
            + f'<div class="lc-axis">{axis}</div></div>' + says + '</div></div>')


def _pota_date(text):
    try:
        return f"{pd.Timestamp(text):%d %b %Y}"
    except Exception:
        return ""


def park_facts_html(card):
    """About the park, from POTA's record of it: what it is and where, who first activated and first hunted it, how many stations have hunted
    it, the totals, and a link to its own website. Empty when POTA has no record of the park."""
    p, totals = card["park"], card.get("stats") or {}
    if not p:
        return ""
    where = ", ".join(x for x in (card["kind"], card["where"], f"grid {p['grid6']}" if p.get("grid6") else "") if x)
    facts = [escape(where)] if where else []
    if p.get("firstActivator"):
        facts.append(f"First activated by <b>{escape(str(p['firstActivator']))}</b>, {_pota_date(p.get('firstActivationDate'))}")
    if p.get("firstHunter"):
        facts.append(f"First hunted by <b>{escape(str(p['firstHunter']))}</b>, {_pota_date(p.get('firstHuntDate'))}")
    if p.get("uniqueHunters"):
        facts.append(f"{int(p['uniqueHunters']):,} different stations have hunted it")
    if totals.get("contacts"):
        facts.append(f"{int(totals['contacts']):,} contacts logged there in all; {int(totals['activations'])} of {int(totals['attempts'])} activations "
                     "reached the 10 QSOs POTA needs")
    site = str(p.get("website") or "")
    if site.startswith(("http://", "https://")):
        facts.append(f'<a href="{escape(site, quote=True)}" target="_blank" rel="noopener noreferrer">the park\'s own website</a>')
    return ('<div class="lc"><div class="lc-card"><h4>About the park</h4><ul class="lc-says">' + "".join(f"<li>{f}</li>" for f in facts) + "</ul></div></div>") if facts else ""


def summit_facts_html(card):
    """About the summit, from SOTA's record of it: where it is, how high, its points, who first activated it (from the list), and a link to its
    page on the SOTA website. Empty when SOTA has no record of the summit."""
    p = card["park"]
    if not p:
        return ""
    facts = []
    if card["where"]:
        facts.append(escape(card["where"]))
    if p.get("altM"):
        facts.append(f"{int(p['altM']):,} m ({int(p.get('altFt') or 0):,} ft) high" + (f" \u00b7 grid {escape(str(p['locator']))}" if p.get("locator") else ""))
    if p.get("points") is not None:
        facts.append(f"{int(p['points'])} points" + (f" plus {int(p['bonusPoints'])} bonus" if p.get("bonusPoints") else ""))
    if card["first"]:
        facts.append(f"First activation listed: <b>{escape(card['first'][0])}</b>, {card['first'][1]:%d %b %Y}")
    facts.append(f'<a href="https://www.sota.org.uk/Summit/{escape(card["ref"], quote=True)}" target="_blank" rel="noopener noreferrer">this summit on the SOTA website</a>')
    return '<div class="lc"><div class="lc-card"><h4>About the summit</h4><ul class="lc-says">' + "".join(f"<li>{f}</li>" for f in facts) + "</ul></div></div>"


def pota_banner_html(card):
    """The headline of the park or summit card, large: the best day of the log against every activation listed, and where you stand among its
    activators. Empty when no day of the log has a rank."""
    from log_check import pota_headline
    h = pota_headline(card)
    if h is None:
        return ""
    label = f"{card.get('program', 'POTA')} {card.get('noun', 'park').upper()} "
    return ('<div class="lc"><div class="lc-hero"><div class="k">' + escape(label + card["ref"]) + f'</div><h3>{escape(h["title"])}</h3><p>{escape(h["line"])}</p>'
            + (f'<p class="s">{escape(h["standing"])}</p>' if h["standing"] else "") + "</div></div>")


def pota_html(card):
    """How a park or summit compares: a few counts, one line for each activation in the log and for everything under your callsign, and two short
    tables: the top activators and the biggest activations. SOTA lists QSOs only, so its tables have no mode columns."""
    noun, program = card.get("noun", "park"), card.get("program", "POTA")
    modes = program == "POTA"
    tiles = ('<div class="lc-tiles">' + _tile(f"{card['n_acts']:,}", "--b", f"activations at this {noun}", f"listed by {program}")
             + _tile(f"{card['n_activators']:,}", "--t", "activators", "different stations")
             + _tile(f"{card['yours_listed']:,}", "--a", "your activations here", f"listed under {escape(card['me'])}") + "</div>")
    says = ("<ul class=\"lc-says\">" + "".join(f"<li><b>{escape(a)}</b> {escape(b)}</li>" for a, b in pota_notes(card)) + "</ul>") if card["rows"] else ""
    act = card["top_activators"]
    rows_a = "".join(f"<tr><td>{escape(str(who))}" + (" <small>(you)</small>" if who == card["me"] else "")
                     + f"</td><td>{int(r.activations):,}</td><td>{int(r.qsos):,}</td>" + (f"<td>{int(r.cw):,}</td>" if modes else "") + "</tr>" for who, r in act.iterrows())
    table_a = (f'<p class="sub" style="margin-top:12px"><b>The {noun}\'s top activators</b> (by QSOs listed)</p><div class="lc-cgw"><table class="lc-reg"><tr><th>Station</th>'
               '<th>Activations</th><th>QSOs</th>' + ("<th>CW QSOs</th>" if modes else "") + '</tr>' + rows_a + "</table></div>") if len(act) else ""
    top = card["top"]
    rows = "".join(f"<tr><td>{r.date:%d %b %Y}</td><td>{escape(r.call)}" + (" <small>(you)</small>" if r.who == card["me"] else "")
                   + f"</td><td>{r.total:,}</td>" + (f"<td>{r.cw:,}</td><td>{r.phone:,}</td><td>{r.data:,}</td>" if modes else "") + "</tr>" for r in top.itertuples())
    table = (f'<p class="sub" style="margin-top:12px"><b>The biggest activations listed for this {noun}</b></p><div class="lc-cgw"><table class="lc-reg"><tr><th>Date</th><th>Station</th>'
             '<th>QSOs</th>' + ("<th>CW</th><th>Phone</th><th>Data</th>" if modes else "") + '</tr>' + rows + "</table></div>") if len(top) else ""
    return (f'<div class="lc"><div class="lc-card"><h4>How this {noun} compares: ' + escape(f"{card['ref']} {card['name']}".strip()) + "</h4>"
            f'<p class="sub">Counts from {program}\'s public activation list, as the activators uploaded them, so they can be out of date. '
            f'An activation is one UTC day at the {noun}. Ranks are by QSOs, with the most first; a tie shares a rank.</p>' + tiles + says + table_a + table + '</div></div>')


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


MIN_SKIMMERS = 3      # fewer skimmers than this in a region and no share is shown, as the page shows no figure under 3 WSPR receivers


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
        if 0 < r.on_band < MIN_SKIMMERS:
            shared = (f'<span class="dim" title="Only {r.on_band} skimmer{"s" if r.on_band != 1 else ""} on the band in this region, too few for a '
                      f'share: a few skimmers cannot say whether the path was open">too few skimmers</span>')
        elif r.on_band:
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


def _panel_html(part, spots, rep, follow, title, marked, follow_bands=None):
    """One chart: a lane for each band used in `part`. `marked` is a one-item list that remembers whether the follower's label is drawn;
    `follow_bands` is how many bands the follower was worked on in the whole log."""
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
                                     f'worked you on {follow_bands or part.loc[part["call"] == follow, "band"].nunique()} bands</span>')
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
        charts.append(_panel_html(part, spots, rep, follow, title, marked, int(log.loc[log["call"] == follow, "band"].nunique()) if follow else None))
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


LADDER_ROWS = 12      # the stations shown at first; the rest are under a "Show more" box


def ladder_html(rep, bands, rows=LADDER_ROWS, first=0):
    """A dot for each band a repeat station was worked on, joined by a line, with the number of bands beside the callsign. Shows `rows`
    stations from number `first` on."""
    cells = ['<div class="hd" style="text-align:left;padding-left:8px">station · bands</div>' + "".join(f'<div class="hd">{b}</div>' for b in bands)]
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


def ladder_rest_html(log, first=LADDER_ROWS):
    """The stations of the ladder after the first `first`, for a 'Show more' box under it."""
    from log_check import repeat_stations
    rep = repeat_stations(log)
    return '<div class="lc">' + ladder_html(rep, bands_top_down(log), rows=len(rep), first=first) + "</div>"


def followers_html(log, summary, rows=LADDER_ROWS):
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
    if summary.get("summit_to_summit"):
        facts.append(_fact("Summit to summit", f"<b>{summary['summit_to_summit']} contacts</b> with {summary['summits']} summit{'s' if summary['summits'] != 1 else ''}."))
    dupes = same_band_repeats(log)
    if dupes:
        facts.append(_fact("Worked twice on a band", f"{dupes} station{'s were' if dupes != 1 else ' was'} logged more than once on the same band."))
    ladder = ladder_html(rep, bands_top_down(log), rows) if len(rep) else '<p class="muted">Nobody was worked on more than one band.</p>'
    return ('<div class="lc"><div class="lc-card"><h4>Who followed you</h4>'
            f'<p class="sub">{followers_headline(rep)}</p>'
            f'<div class="lc-two"><div>{ladder}</div><div class="lc-facts">{"".join(facts)}</div></div></div></div>')
