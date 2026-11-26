"""A picture and a short text for sharing a Log analysis, made from the log's own numbers and, for a POTA log, how its park compares. Nothing here
reads the network, and nothing is saved: the picture and the text are built on the page for the person who uploaded the log to post as they like.
They state only what the log and POTA's list say, in plain words.

With the places of the contacts the picture is a map: your station, a path to each place a contact was and a diamond there, all in the colour of the
band (a place worked on several bands has a diamond for each), and, beside the map, how many contacts there were on each band. Each place is the centre of
the contact's own grid square when the log gives one, else of its state, else of its country."""
import io
import math
import textwrap
from functools import lru_cache

import numpy as np
from matplotlib import patheffects
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

import log_check as lc
import maps as mp
import world_map as wm
from rbn_data import country_location
from ui_common import BAND_COLORS

SITE = "farfieldlab.streamlit.app"
BG, PANEL, FG, MUTED, TEAL, AMBER, BLUE, GREEN = "#0e1117", "#161b24", "#e8ecf3", "#9aa5b8", "#20b2aa", "#e6a117", "#6f8cff", "#4caf50"
SIZE = (12.0, 6.3)       # inches: with DPI, a 2400 by 1260 picture, the shape social sites show best, sharp on a large or high-density screen
DPI = 200
# The shapes social sites want, each drawn for its own shape and not cropped from another. Sizes are in inches at DPI, so twice the usual pixel size: a square
# is 2160 by 2160 and shows at 1080 by 1080. A story keeps its text clear of the top and bottom (inches), where the apps cover the picture with their own buttons.
FORMATS = {
    "landscape": {"label": "Landscape", "where": "X, Facebook, LinkedIn", "size": SIZE},
    "square": {"label": "Square", "where": "Instagram, Facebook", "size": (10.8, 10.8)},
    "portrait": {"label": "Portrait", "where": "Instagram feed (4:5)", "size": (10.8, 13.5)},
    "story": {"label": "Story", "where": "Instagram, TikTok, Reels (9:16)", "size": (10.8, 19.2), "safe_top": 2.6, "safe_bottom": 3.3},
}
DEFAULT_FORMAT = "landscape"
MIN_LON_SPAN, MIN_LAT_SPAN = 40.0, 25.0     # the map never zooms in closer than this, so a local session still looks like a map


def _dates(log):
    a, z = log["time"].min(), log["time"].max()
    if a.date() == z.date():
        return f"{a:%d %b %Y}"
    if (a.year, a.month) == (z.year, z.month):
        return f"{a:%d}–{z:%d %b %Y}"
    return f"{a:%d %b} – {z:%d %b %Y}"


def _clip(text, n):
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _wrap(text, width, lines):
    """`text` wrapped to `width` characters and at most `lines` lines; when it is longer, the last line ends in an ellipsis instead of stopping mid-sentence."""
    wrapped = textwrap.wrap(text, width)
    if len(wrapped) <= lines:
        return wrapped or [""]
    keep = wrapped[:lines]
    last = keep[-1] if len(keep[-1]) < width else keep[-1][:width - 1]
    keep[-1] = last.rstrip(" .,;:") + chr(8230)
    return keep


PLAIN_NAMES = {"Fed. Rep. of Germany": "Germany", "European Russia": "Russia", "Asiatic Russia": "Russia", "Kaliningrad": "Russia", "Hawaii": "Hawaii",
               "Rep. of Korea": "South Korea", "Rep. of the Congo": "Congo", "Dem. Rep. of the Congo": "Congo", "Slovak Republic": "Slovakia"}


def _country(call, named):
    """The country of a contact for the map: the log's own name for it, else the one its callsign belongs to, in plain words (the DXCC list says
    'Fed. Rep. of Germany')."""
    if isinstance(named, str) and named.strip():
        return named.strip()
    found = country_location(call)
    return PLAIN_NAMES.get(found[2], found[2]) if found else ""


def map_facts(places, home):
    """What the map needs, from lc.contact_places' table and the station's (lat, lon): the station, and one point for each place a contact was, with how
    many contacts and how many different stations were there, the bands worked there and how many on each (busiest first), a call, the country and the distance. Also the farthest
    contact, one entry for each contact (where and on which band) and how many contacts could be placed. None when there is no place to draw."""
    if places is None or home is None:
        return None
    d = places[places["c_source"] != ""].dropna(subset=["c_lat", "c_lon"])
    if d.empty:
        return None
    d = d.assign(plat=d["c_lat"].round(2), plon=d["c_lon"].round(2))
    points = []
    for (lat, lon), g in d.groupby(["plat", "plon"]):
        first = g.iloc[0]
        counts = g["band"].value_counts()
        points.append({"lat": float(lat), "lon": float(lon), "n": int(len(g)), "stations": int(g["call"].nunique()), "km": float(g["c_km"].max()), "bands": list(counts.index),
                       "band_n": {b: int(n) for b, n in counts.items()},
                       "band_calls": {b: g[g["band"] == b]["call"].value_counts().to_dict() for b in counts.index}, "call": str(first["call"]), "country": _country(first["call"], first["country"])})
    far = lc.farthest_contact(d)
    return {"home": (float(home[0]), float(home[1])), "points": points, "placed": int(len(d)), "total": int(len(places)),
            "farthest": {"call": far["call"], "calls": far["calls"], "country": far["place"] if far["approx"] else _country(far["call"], d[d["call"] == far["call"]]["country"].iloc[0]),
                         "km": far["km"], "band": far["band"], "approx": far["approx"]},
            "contacts": [(float(r.plat), float(r.plon), str(r.band)) for r in d.itertuples()]}


PURPLE, ORANGE = "#c792ea", "#ff8a65"


def _hm(minutes):
    """A length of time in plain words: '47 min', '2 h', '1 h 52 m'."""
    minutes = int(round(minutes))
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h} h" if m == 0 else f"{h} h {m:02d} m"


def _compact(minutes):
    """A length of time short enough for a big number: '47m', '2h', '1h 52m'."""
    minutes = int(round(minutes))
    h, m = divmod(minutes, 60)
    return f"{m}m" if h == 0 else f"{h}h" if m == 0 else f"{h}h {m:02d}m"


def on_air(summary):
    """The time on the air, from lc.summary: the total of the stretches between contacts, with any pause of more than 30 minutes counted as time off the air
    (so a break in the middle of a long day is not counted as operating), and how fast the contacts came in that time. `span` says how long it was from the
    first contact to the last, but only when a long break makes that much longer (15 minutes and 10 percent or more), so a break does not make a long, slow
    day look like a short, fast one. A log holds contacts, so this is logged time. None when there is no time to count (one contact)."""
    hours = summary.get("on_air_hours") or 0
    if hours * 60 < 1:
        return None
    minutes = hours * 60
    rate = summary.get("per_hour")
    rate = None if rate is None or rate != rate else int(round(rate))
    elapsed = (summary["last"] - summary["first"]).total_seconds() / 60
    differs = elapsed - minutes >= 15 and elapsed - minutes >= 0.1 * elapsed
    return {"text": _hm(minutes), "minutes": minutes, "rate": rate, "elapsed": _hm(elapsed) if differs else ""}


def card_numbers(facts):
    """The numbers on the picture: the four in the text (contacts, DXCC entities, bands, states or continents) and, when there is time to count, the time on the
    air and the contacts an hour."""
    out = list(facts["numbers"])
    oa = facts.get("on_air")
    if oa:
        out.append((_compact(oa["minutes"]), f"on air of {oa['elapsed']}" if oa["elapsed"] else "on the air", PURPLE))
        if oa["rate"] is not None:
            out.append((f"{oa['rate']}", "contacts / hour", ORANGE))
    return out


def share_facts(log, summary, worked, call, cards=None, rep=None, places=None, home=None):
    """What goes on the picture and into the text: the callsign and dates, a title and subtitle (the park headline for a POTA log), four numbers,
    up to three plain lines (the standing at the park, the DX countries, who followed across bands) and, with `places` (lc.contact_places) and
    `home`, the map of where the contacts were."""
    contacts = int(summary["contacts"])
    numbers = [(f"{contacts:,}", "contacts", BLUE), (f"{worked['n_entities']:,}", "DXCC entities", TEAL), (f"{len(summary['bands'])}", "bands", AMBER)]
    numbers.append((f"{len(worked['states'])}", "US states", GREEN) if worked["has_us"] else (f"{len(worked['continents'])}", "continents", GREEN))
    title = subtitle = ""
    lines = []
    head = lc.pota_headline(cards[0]) if cards else None
    if head:
        title, subtitle = head["title"], head["line"]
        if head["standing"]:
            lines.append(head["standing"])
    elif cards:
        title = f"Activation of {cards[0]['name'] or cards[0]['ref']}"
    if not title:
        title = f"{contacts:,} contacts on {len(summary['bands'])} bands"
        subtitle = f"{summary['stations']:,} stations worked, {worked['n_entities']:,} DXCC entities."
    away = worked["ents"][worked["ents"]["cont"] != worked["home"]]
    if len(away):
        names = list(away["name"])
        lines.append("DX: " + (", ".join(names[:3]) + (f" and {len(names) - 3} more countries." if len(names) > 3 else ".")))
    if rep is not None and len(rep):
        top = rep.iloc[0]
        lines.append(f"{len(rep):,} stations worked on 2 or more bands, {rep.index[0]} on {int(top['k'])}.")
    counts = log["band"].value_counts()
    hunters = None
    if rep is not None and len(rep):                                  # the top hunter is the station worked on the most bands (ties: the most contacts)
        top = rep.iloc[0]
        hunters = {"n": int(len(rep)), "top": str(rep.index[0]), "k": int(top["k"]), "bands": sorted(top["bands"], key=lc._rank, reverse=True)}
    return {"call": call or "", "dates": _dates(log), "title": title, "subtitle": subtitle, "numbers": numbers, "lines": lines[:3],
            "bands": [(b, int(counts[b])) for b in lc.bands_top_down(log)], "hunters": hunters, "on_air": on_air(summary), "map": map_facts(places, home)}


def share_text(facts):
    """The summary as plain text to paste into a post or an email."""
    head = " · ".join(x for x in (facts["call"], facts["dates"]) if x)
    parts = [head, facts["title"]] + ([facts["subtitle"]] if facts["subtitle"] else [])
    parts.append(" · ".join(f"{value} {label}" for value, label, _ in facts["numbers"]))
    oa = facts.get("on_air")
    if oa:
        parts.append(f"{oa['text']} on the air" + (f" · {oa['rate']} contacts an hour" if oa["rate"] is not None else "")
                     + (f" (out of {oa['elapsed']} between the first and last contact)" if oa["elapsed"] else ""))
    parts += facts["lines"]
    parts.append(f"Made with FarField Lab ({SITE})")
    return "\n".join(parts)


@lru_cache(maxsize=1)
def _world_image():
    """The whole world as an 8-bit RGB picture (1800 by 3600, north up, 0.1 degree a pixel) in the app's dark map colours, with the coasts picked out."""
    grid, _ = wm._land_grid()
    gy, gx = np.gradient(grid)
    edge = np.clip(np.hypot(gx, gy) * 5.0, 0, 1)[..., None]
    rgb = wm.OCEAN + (wm.LAND - wm.OCEAN) * grid[..., None]
    rgb = rgb + (wm.COAST - rgb) * edge * 0.85
    return (np.clip(rgb, 0, 1) * 255).astype(np.uint8)


def _paths(m):
    """The great-circle path from the station to every place a contact was, for each band worked there, with longitudes unwrapped (so a path to Asia
    runs on across the Pacific); where each place's diamond goes (the end of a path); and the bounds of all of it."""
    home = m["home"]
    ends, lines = {}, []
    for lat, lon, band in m["contacts"]:
        if (lat, lon, band) in ends:
            continue
        path = mp.great_circle(home, (lat, lon))
        ends[(lat, lon, band)] = path[-1]
        lines.append((band, [p[1] for p in path], [p[0] for p in path]))
    lons = [x for _, xs, _ in lines for x in xs] + [home[1]]
    lats = [y for _, _, ys in lines for y in ys] + [home[0]]
    return lines, ends, (min(lons), max(lons), min(lats), max(lats))


def _extent(bounds, box, size=SIZE):
    """The map's edges (west, east, south, north) so that the paths and places fill `box` (x0, x1, y0, y1, as fractions of the frame, `size` inches across)
    at one scale in both directions, whatever the shape of the data, and the rest of the frame is more map."""
    w, e, s, n = bounds
    lon_span, lat_span = max(e - w, MIN_LON_SPAN), max(n - s, MIN_LAT_SPAN)
    fx0, fx1, fy0, fy1 = box
    per_inch = max(lon_span / ((fx1 - fx0) * size[0]), lat_span / ((fy1 - fy0) * size[1]))
    sx, sy = per_inch * size[0], per_inch * size[1]                       # degrees across the whole frame, each way
    cx, cy = (w + e) / 2, (s + n) / 2
    x0, y0 = cx - (fx0 + fx1) / 2 * sx, cy - (fy0 + fy1) / 2 * sy
    y0 = min(max(y0, -90), 90 - sy)
    return x0, x0 + sx, y0, y0 + sy


def _draw_world(fig, m, rect=(0, 0, 1, 1), size=SIZE, box=(0.31, 0.97, 0.10, 0.90)):
    """The map filling `rect` (x, y, width, height as fractions of the picture; `size` inches across): the dark world, a faint grid, a path to each place in
    its band's colour, a diamond for each station (or for each band, at a crowded place) round its place in the band's colour, and your station. There are no country names: the fanned diamonds show how many stations are at a place, and a name over a crowd of paths is clutter. With no `m` it is the world and
    nothing on it."""
    lines, ends, bounds = _paths(m) if m else ([], {}, (-165.0, 165.0, -55.0, 78.0))
    x0, x1, y0, y1 = _extent(bounds, box, size)
    ax = fig.add_axes(list(rect))
    ax.axis("off")                                                        # (which also hides the axes' own background, so the sea is painted below)
    ax.axhspan(-1000, 1000, facecolor=_hex(wm.OCEAN), edgecolor="none", zorder=-1)       # a wide log makes the frame taller than the world is: the rest is open sea, not an empty strip
    image = _world_image()
    for offset in range(-720, 721, 360):
        if offset + 180 > x0 and offset - 180 < x1:
            ax.imshow(image, extent=[offset - 180, offset + 180, -90, 90], origin="upper", interpolation="antialiased", aspect="auto", zorder=0)
    for lon in range(int(math.floor(x0 / 30) * 30), int(x1) + 31, 30):
        ax.plot([lon, lon], [-400, 400], color="#ffffff", alpha=0.05, linewidth=0.5, zorder=1)
    for lat in range(-300, 301, 30):
        ax.plot([x0 - 720, x1 + 720], [lat, lat], color="#ffffff", alpha=0.05, linewidth=0.5, zorder=1)
    for band, xs, ys in lines:                                            # a soft glow under each path, then the path itself
        colour = _lighten(BAND_COLORS.get(band, "#3388ff"))
        ax.plot(xs, ys, color=colour, linewidth=3.6, alpha=0.10, solid_capstyle="round", zorder=2)
        ax.plot(xs, ys, color=colour, linewidth=1.1, alpha=0.8, solid_capstyle="round", zorder=3)
    ring = 0.0045 * (x1 - x0)                                             # several stations or bands at one place: a diamond for each, fanned round the place
    for p in sorted(m["points"] if m else [], key=lambda q: -len(q["bands"])):
        items = _fan(p)
        k = len(items)
        radius = ring * (1.0 if k <= 4 else 0.5 + 0.25 * k)               # more diamonds need a wider ring, so they do not sit on each other
        for i, (band, n) in enumerate(items):
            ey, ex = ends[(p["lat"], p["lon"], band)]                       # a path's end is (latitude, longitude)
            if k > 1:
                angle = -math.pi / 2 + 2 * math.pi * i / k
                ex, ey = ex + radius * math.cos(angle), ey + radius * math.sin(angle)
            ax.scatter([ex], [ey], marker="D", s=24 + 8 * math.sqrt(n), color=BAND_COLORS.get(band, "#3388ff"),
                       edgecolors="#ffffff", linewidths=0.7, zorder=6)
    if m:
        hx, hy = m["home"][1], m["home"][0]
        ax.scatter([hx], [hy], marker="o", s=520, color=TEAL, alpha=0.18, zorder=7)
        ax.scatter([hx], [hy], marker="*", s=330, color="#ffffff", edgecolors=TEAL, linewidths=1.2, zorder=9)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    return ax


FAN_MAX = 8        # a place with up to this many stations (each on each band) gets a diamond for each, so five stations are not mistaken for one


def _fan(p):
    """The diamonds to draw at one place, as (band, contacts): one for each station on each band when there are only a few (so five stations show as five, spread round
    the place), else one for each band, as a crowded place such as a state's centre would be a heap of overlapping diamonds."""
    each = [(band, n) for band in p["bands"] for n in sorted((p.get("band_calls") or {}).get(band, {}).values(), reverse=True)]
    if 1 < len(each) <= FAN_MAX:
        return each
    return [(band, p["band_n"][band]) for band in p["bands"]]


def _lighten(hex_colour, amount=0.45):
    """A colour mixed part of the way to white, so a band's path shows on the dark map."""
    return "#" + "".join(f"{int(round((c + (1 - c) * amount) * 255)):02x}" for c in _rgb(hex_colour))


def _hex(rgb):
    """A colour given as 0 to 1 red, green, blue as a '#rrggbb' string."""
    return "#" + "".join(f"{int(round(float(c) * 255)):02x}" for c in rgb)


def _rgb(hex_colour):
    h = hex_colour.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def _farthest_text(far):
    """The share card's line about the farthest contact: named with its distance when its place is known, and, when only its country is known, the country with the stations
    in it and a distance said to be about so much."""
    if far.get("approx"):
        calls = far["calls"]
        who = " and ".join(calls) if len(calls) <= 2 else ", ".join(calls[:2]) + f" and {len(calls) - 2} more"
        return f"Farthest: {far['country'] or 'a far country'} ({who}), about {_fmt_km(far['km'])} on {far['band']}."
    place = f", {far['country']}" if far["country"] else ""
    return f"Farthest: {far['call']}{place}, {_fmt_km(far['km'])} on {far['band']}."


def _fmt_km(km):
    return f"{km:,.0f} km ({km / 1.609344:,.0f} mi)"


def _flat_card(fig, facts):
    """The picture when there is no map to draw: the numbers across the middle and the lines under them."""
    title = _wrap(facts["title"], 44, 2)
    fig.text(0.04, 0.925, "FARFIELD LAB · LOG ANALYSIS", color=TEAL, fontsize=10, fontweight="bold", va="center")
    who = " · ".join(x for x in (facts["call"], facts["dates"]) if x)
    fig.text(0.96, 0.925, who, color=FG, fontsize=15, fontweight="bold", va="center", ha="right")
    fig.text(0.04, 0.80 if len(title) == 1 else 0.82, chr(10).join(title), color=FG, fontsize=27, fontweight="bold", va="top", linespacing=1.15)
    sub = _wrap(facts["subtitle"], 100, 2) if facts["subtitle"] else []
    if sub:
        fig.text(0.04, 0.63 if len(title) == 1 else 0.60, chr(10).join(sub), color=MUTED, fontsize=14, va="top", linespacing=1.3)
    numbers = card_numbers(facts)
    n = len(numbers)
    gap = 0.02
    width = (0.92 - gap * (n - 1)) / n
    big = 34 if n <= 4 else 26
    for i, (value, label, colour) in enumerate(numbers):
        x = 0.04 + i * (width + gap)
        fig.add_artist(Rectangle((x, 0.29), width, 0.2, transform=fig.transFigure, facecolor=PANEL, edgecolor="#2a3140", linewidth=1))
        fig.text(x + 0.018, 0.425, value, color=colour, fontsize=big, fontweight="bold", va="center")
        fig.text(x + 0.018, 0.33, label, color=MUTED, fontsize=12 if n <= 4 else 10, va="center")
    for i, line in enumerate(facts["lines"]):
        fig.text(0.04, 0.225 - i * 0.058, _clip(line, 104), color=FG, fontsize=14, va="center")
    fig.text(0.04, 0.04, "Made with FarField Lab", color=MUTED, fontsize=10, va="center")
    fig.text(0.96, 0.04, SITE, color=MUTED, fontsize=10, va="center", ha="right")


def _map_card(fig, facts, m):
    """The picture with a map: the contact map fills it, and a panel down the left carries the names, the four numbers, the plain lines, the farthest
    contact and the key to the colours."""
    _draw_world(fig, m)
    fig.add_artist(Rectangle((0.018, 0.04), 0.262, 0.92, transform=fig.transFigure, facecolor="#0b1119", edgecolor="#2a3140", linewidth=1, alpha=0.86, zorder=20))
    t = dict(zorder=21)
    fig.text(0.03, 0.925, "FARFIELD LAB · LOG ANALYSIS", color=TEAL, fontsize=8.5, fontweight="bold", va="center", **t)
    who = " · ".join(x for x in (facts["call"], facts["dates"]) if x)
    fig.text(0.03, 0.885, who, color=FG, fontsize=12.5, fontweight="bold", va="center", **t)
    title = _wrap(facts["title"], 23, 3)
    y = 0.845
    fig.text(0.03, y, chr(10).join(title), color=FG, fontsize=16, fontweight="bold", va="top", linespacing=1.15, **t)
    y -= 0.044 * len(title) + 0.02
    sub = _wrap(facts["subtitle"], 38, 2 if len(title) == 3 else 3) if facts["subtitle"] else []
    if sub:
        fig.text(0.03, y, chr(10).join(sub), color=MUTED, fontsize=9.5, va="top", linespacing=1.3, **t)
        y -= 0.03 * len(sub)
    y -= 0.025
    numbers = card_numbers(facts)
    rows = math.ceil(len(numbers) / 2)
    tile_w, tile_h, gap = 0.114, (0.09 if rows <= 2 else 0.07), 0.008      # three rows of tiles are lower, to leave the same room for the text under them
    value_pt, label_pt, value_dy, label_dy = (18, 8, 0.034, 0.073) if rows <= 2 else (15, 7.5, 0.027, 0.057)
    for i, (value, label, colour) in enumerate(numbers):
        x = 0.03 + (i % 2) * (tile_w + gap)
        top = y - (i // 2) * (tile_h + gap)
        fig.add_artist(Rectangle((x, top - tile_h), tile_w, tile_h, transform=fig.transFigure, facecolor=PANEL, edgecolor="#2a3140", linewidth=0.8, zorder=21))
        fig.text(x + 0.01, top - value_dy, value, color=colour, fontsize=value_pt, fontweight="bold", va="center", **t)
        fig.text(x + 0.01, top - label_dy, label, color=MUTED, fontsize=label_pt, va="center", **t)
    y -= rows * tile_h + (rows - 1) * gap + 0.014
    hun = facts.get("hunters")
    if hun:                                                              # who came back on another band, and the top hunter with the bands they worked
        height = 0.094
        fig.add_artist(Rectangle((0.03, y - height), 0.232, height, transform=fig.transFigure, facecolor=PANEL, edgecolor="#2a3140", linewidth=0.8, zorder=21))
        fig.text(0.04, y - 0.034, f"{hun['n']:,}", color=AMBER, fontsize=18, fontweight="bold", va="center", **t)
        fig.text(0.04, y - 0.071, chr(10).join(("stations worked on", "2 or more bands")), color=MUTED, fontsize=7.5, va="center", linespacing=1.2, **t)
        fig.add_artist(Rectangle((0.148, y - height + 0.012), 0.0007, height - 0.024, transform=fig.transFigure, facecolor="#2a3140", edgecolor="none", zorder=21))
        fig.text(0.158, y - 0.015, "TOP HUNTER", color=MUTED, fontsize=6.5, fontweight="bold", va="center", **t)
        fig.text(0.158, y - 0.037, hun["top"], color=FG, fontsize=12, fontweight="bold", va="center", **t)
        fig.text(0.158, y - 0.057, f"worked on {hun['k']} bands", color=MUTED, fontsize=7.5, va="center", **t)
        chip_w = min(0.027, (0.100 - 0.002 * (len(hun["bands"]) - 1)) / len(hun["bands"]))
        for i, band in enumerate(hun["bands"]):
            x = 0.158 + i * (chip_w + 0.002)
            fig.add_artist(Rectangle((x, y - 0.090), chip_w, 0.018, transform=fig.transFigure, facecolor=BAND_COLORS.get(band, "#3388ff"), edgecolor="#ffffff", linewidth=0.4, zorder=21))
            if chip_w >= 0.02:
                fig.text(x + chip_w / 2, y - 0.081, band, color="#ffffff", fontsize=6, fontweight="bold", va="center", ha="center",
                         path_effects=[patheffects.withStroke(linewidth=1.4, foreground="#000000")], **t)
        y -= height + 0.03
    else:
        y -= 0.026
    lines = [x for x in facts["lines"] if not (hun and "worked on 2 or more bands" in x)]      # the hunters block says it, so the line is not said twice
    far = m["farthest"]
    if far["km"] >= lc.DX_KM or not lines:                              # the farthest contact comes first, so it is the last line to be dropped when there is no room
        lines.insert(0, _farthest_text(far))
    floor = 0.278                                                       # the band counts start below this; a line that would reach it is left out
    for line in lines:
        wrapped = _wrap(line, 40, 2)
        height = 0.03 * len(wrapped)
        if y - height < floor:
            break
        fig.text(0.03, y, chr(10).join(wrapped), color=FG, fontsize=9, va="top", linespacing=1.25, **t)
        y -= height + 0.012
    bands = facts.get("bands") or []
    if bands:
        fig.text(0.03, 0.262, "CONTACTS BY BAND", color=MUTED, fontsize=7.5, fontweight="bold", va="center", **t)
        per_col = max(math.ceil(len(bands) / 2), 5) if len(bands) > 5 else len(bands)
        peak = max(n for _, n in bands)
        for i, (band, n) in enumerate(bands):
            col, row = divmod(i, per_col)
            x, top = 0.03 + col * 0.125, 0.238 - row * 0.0245
            fig.add_artist(Rectangle((x, top - 0.012), 0.009, 0.018, transform=fig.transFigure, facecolor=BAND_COLORS.get(band, "#3388ff"), edgecolor="none", zorder=21))
            fig.text(x + 0.014, top - 0.003, band, color=FG, fontsize=8.5, fontweight="bold", va="center", **t)
            fig.add_artist(Rectangle((x + 0.054, top - 0.008), 0.044 * n / peak, 0.009, transform=fig.transFigure, facecolor=BAND_COLORS.get(band, "#3388ff"),
                                     edgecolor="none", alpha=0.9, zorder=21))
            fig.text(x + 0.119, top - 0.003, f"{n:,}", color=FG, fontsize=8.5, va="center", ha="right", **t)
    fig.text(0.03, 0.052, SITE, color=TEAL, fontsize=8.5, fontweight="bold", va="center", **t)


def _tall_card(fig, facts, m, size, safe_top=0.0, safe_bottom=0.0):
    """The picture for a square, portrait or story shape: the contact map on top and a panel underneath with the callsign and date, the title, the four
    numbers, the top hunter, the farthest contact and the contacts on each band. Everything is placed in inches, so one layout serves every height.
    A world map is about half as tall as it is wide, so the map is only as tall as the data needs (never more than the world's shape allows); any room
    that is left over is clear background below the panel. In a story nothing is drawn within `safe_top` inches of the top or `safe_bottom` inches of the
    bottom except the map's own sea and land, because the apps put their buttons there."""
    W, H = size
    content_h = 6.0                                                    # the panel: header, title, numbers, top hunter and band counts
    bounds = _paths(m)[2] if m else (-165.0, 165.0, -55.0, 78.0)
    per_inch = max(bounds[1] - bounds[0], MIN_LON_SPAN) / (0.9 * W)    # degrees of longitude an inch of map has to cover
    map_h = max(min(H - safe_top - safe_bottom - content_h, 165.0 / per_inch), 3.0)
    panel_top = safe_top + map_h                                       # inches down from the top of the picture
    X = lambda v: v / W
    Y = lambda v: 1 - v / H
    t = dict(zorder=21)
    _draw_world(fig, m, rect=(0, Y(panel_top), 1, map_h / H), size=(W, map_h), box=(0.05, 0.95, 0.07, 0.93))
    if safe_top > 0:                                                    # the map fades in from the clear top of a story, with no hard edge
        steps = 24
        for i in range(steps):
            fig.add_artist(Rectangle((0, Y(safe_top + (i + 1) * 0.05)), 1, 0.05 / H, transform=fig.transFigure, facecolor=BG, edgecolor="none",
                                     alpha=1 - i / steps, zorder=19))
    fig.add_artist(Rectangle((0, 0), 1, Y(panel_top), transform=fig.transFigure, facecolor="#0b1119", edgecolor="#2a3140", linewidth=1.2, zorder=20))
    pad = 0.45
    fig.text(X(pad), Y(panel_top + 0.4), "FARFIELD LAB · LOG ANALYSIS", color=TEAL, fontsize=11, fontweight="bold", va="center", **t)
    who = " · ".join(x for x in (facts["call"], facts["dates"]) if x)
    fig.text(X(W - pad), Y(panel_top + 0.4), who, color=FG, fontsize=16, fontweight="bold", va="center", ha="right", **t)
    y = panel_top + 0.85
    title = _wrap(facts["title"], 40, 2)
    fig.text(X(pad), Y(y), chr(10).join(title), color=FG, fontsize=24, fontweight="bold", va="top", linespacing=1.15, **t)
    y += 0.40 * len(title) + 0.08
    sub = _wrap(facts["subtitle"], 92, 2) if facts["subtitle"] else []
    if sub:
        fig.text(X(pad), Y(y), chr(10).join(sub), color=MUTED, fontsize=12, va="top", linespacing=1.3, **t)
        y += 0.22 * len(sub) + 0.2
    numbers = card_numbers(facts)
    gap, per_row = (0.14 if len(numbers) <= 4 else 0.11), len(numbers)
    tw, th = (W - 2 * pad - (per_row - 1) * gap) / per_row, 0.95
    value_pt, label_pt = (26, 10.5) if len(numbers) <= 4 else (21, 8.5)
    for i, (value, label, colour) in enumerate(numbers):
        x = pad + i * (tw + gap)
        fig.add_artist(Rectangle((X(x), Y(y + th)), tw / W, th / H, transform=fig.transFigure, facecolor=PANEL, edgecolor="#2a3140", linewidth=0.9, zorder=21))
        fig.text(X(x + 0.14), Y(y + 0.36), value, color=colour, fontsize=value_pt, fontweight="bold", va="center", **t)
        fig.text(X(x + 0.14), Y(y + 0.75), label, color=MUTED, fontsize=label_pt, va="center", **t)
    y += th + 0.22
    half = (W - 2 * pad - 0.25) / 2
    hun = facts.get("hunters")
    bottom = min(y + 2.1, H - safe_bottom - 0.8)                         # the row of the top hunter, the lines and the band counts ends here, above the address
    ly = y
    if hun:
        fig.add_artist(Rectangle((X(pad), Y(y + 1.0)), half / W, 1.0 / H, transform=fig.transFigure, facecolor=PANEL, edgecolor="#2a3140", linewidth=0.9, zorder=21))
        fig.text(X(pad + 0.18), Y(y + 0.38), f"{hun['n']:,}", color=AMBER, fontsize=26, fontweight="bold", va="center", **t)
        fig.text(X(pad + 0.18), Y(y + 0.78), chr(10).join(("stations worked on", "2 or more bands")), color=MUTED, fontsize=9, va="center", linespacing=1.2, **t)
        fig.add_artist(Rectangle((X(pad + 1.95), Y(y + 0.9)), 0.012 / W, 0.8 / H, transform=fig.transFigure, facecolor="#2a3140", edgecolor="none", zorder=21))
        fig.text(X(pad + 2.15), Y(y + 0.18), "TOP HUNTER", color=MUTED, fontsize=8.5, fontweight="bold", va="center", **t)
        fig.text(X(pad + 2.15), Y(y + 0.43), hun["top"], color=FG, fontsize=16, fontweight="bold", va="center", **t)
        fig.text(X(pad + 2.15), Y(y + 0.65), f"worked on {hun['k']} bands", color=MUTED, fontsize=9, va="center", **t)
        room = half - 2.15 - 0.15
        chip = min(0.5, (room - 0.04 * (len(hun["bands"]) - 1)) / len(hun["bands"]))
        for i, band in enumerate(hun["bands"]):
            x = pad + 2.15 + i * (chip + 0.04)
            fig.add_artist(Rectangle((X(x), Y(y + 0.93)), chip / W, 0.2 / H, transform=fig.transFigure, facecolor=BAND_COLORS.get(band, "#3388ff"),
                                     edgecolor="#ffffff", linewidth=0.4, zorder=21))
            if chip >= 0.34:
                fig.text(X(x + chip / 2), Y(y + 0.83), band, color="#ffffff", fontsize=7.5, fontweight="bold", va="center", ha="center",
                         path_effects=[patheffects.withStroke(linewidth=1.6, foreground="#000000")], **t)
        ly = y + 1.2
    lines = [x for x in facts["lines"] if not (hun and "worked on 2 or more bands" in x)]
    if m:
        far = m["farthest"]
        if far["km"] >= lc.DX_KM or not lines:                          # the farthest contact comes first, so it is the last line to be dropped
            lines.insert(0, _farthest_text(far))
    for line in lines:
        wrapped = _wrap(line, 46, 2)
        height = 0.2 * len(wrapped)
        if ly + height > bottom:
            break
        fig.text(X(pad), Y(ly), chr(10).join(wrapped), color=FG, fontsize=11, va="top", linespacing=1.25, **t)
        ly += height + 0.1
    bands = facts.get("bands") or []
    if bands:
        bx = pad + half + 0.25
        fig.text(X(bx), Y(y + 0.1), "CONTACTS BY BAND", color=MUTED, fontsize=9, fontweight="bold", va="center", **t)
        per_col = max(math.ceil(len(bands) / 2), 6) if len(bands) > 6 else len(bands)
        cols = math.ceil(len(bands) / per_col)
        col_w = half / cols
        peak = max(n for _, n in bands)
        for i, (band, n) in enumerate(bands):
            col, row = divmod(i, per_col)
            x, top = bx + col * col_w, y + 0.42 + row * 0.27
            fig.add_artist(Rectangle((X(x), Y(top + 0.17)), 0.17 / W, 0.17 / H, transform=fig.transFigure, facecolor=BAND_COLORS.get(band, "#3388ff"), edgecolor="none", zorder=21))
            fig.text(X(x + 0.25), Y(top + 0.085), band, color=FG, fontsize=11, fontweight="bold", va="center", **t)
            bar = (col_w - 1.45) * n / peak
            fig.add_artist(Rectangle((X(x + 0.95), Y(top + 0.12)), bar / W, 0.08 / H, transform=fig.transFigure, facecolor=BAND_COLORS.get(band, "#3388ff"),
                                     edgecolor="none", alpha=0.9, zorder=21))
            fig.text(X(x + col_w - 0.1), Y(top + 0.085), f"{n:,}", color=FG, fontsize=11, va="center", ha="right", **t)
    fig.text(X(pad), Y(H - safe_bottom - 0.45), SITE, color=TEAL, fontsize=13, fontweight="bold", va="center", **t)


def _render(facts, fmt, image_format):
    """The picture for one format, as bytes of `image_format` ('png' or 'jpeg')."""
    spec = FORMATS[fmt]
    fig = Figure(figsize=spec["size"], dpi=DPI)
    fig.patch.set_facecolor(BG)
    m = facts.get("map")
    if fmt == "landscape":
        _map_card(fig, facts, m) if m else _flat_card(fig, facts)
    else:
        _tall_card(fig, facts, m, spec["size"], spec.get("safe_top", 0.0), spec.get("safe_bottom", 0.0))
    buf = io.BytesIO()
    fig.savefig(buf, format=image_format, facecolor=BG, dpi=DPI, **({"pil_kwargs": {"quality": 92}} if image_format == "jpeg" else {}))
    return buf.getvalue()


def share_png(facts, fmt=DEFAULT_FORMAT):
    """The summary as a PNG for a social site: `fmt` is one of FORMATS (landscape 2400 by 1260, square 2160 by 2160, portrait 2160 by 2700, story 2160 by 3840).
    With a map the contact map is the picture and the numbers sit beside or under it; with none, the landscape picture is the numbers alone."""
    return _render(facts, fmt, "png")


def share_jpg(facts, fmt=DEFAULT_FORMAT):
    """The same picture as a JPEG, which is smaller and what Instagram stores whichever it is given."""
    return _render(facts, fmt, "jpeg")
