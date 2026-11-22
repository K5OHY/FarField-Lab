"""A picture and a short text for sharing a Log analysis, made from the log's own numbers and, for a POTA log, how its park compares. Nothing here
reads the network, and nothing is saved: the picture and the text are built on the page for the person who uploaded the log to post as they like.
They state only what the log and POTA's list say, in plain words."""
import io
import textwrap

from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

import log_check as lc

SITE = "farfieldlab.streamlit.app"
BG, PANEL, FG, MUTED, TEAL, AMBER, BLUE, GREEN = "#0e1117", "#161b24", "#e8ecf3", "#9aa5b8", "#20b2aa", "#e6a117", "#6f8cff", "#4caf50"
SIZE = (12.0, 6.3)       # inches at 100 dpi: a 1200 by 630 picture, the shape social sites show best


def _dates(log):
    a, z = log["time"].min(), log["time"].max()
    if a.date() == z.date():
        return f"{a:%d %b %Y}"
    if (a.year, a.month) == (z.year, z.month):
        return f"{a:%d}–{z:%d %b %Y}"
    return f"{a:%d %b} – {z:%d %b %Y}"


def _clip(text, n):
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def share_facts(log, summary, worked, call, cards=None, rep=None):
    """What goes on the picture and into the text: the callsign and dates, a title and subtitle (the park headline for a POTA log), four numbers,
    and up to three plain lines (the standing at the park, the DX countries, who followed across bands)."""
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
    return {"call": call or "", "dates": _dates(log), "title": title, "subtitle": subtitle, "numbers": numbers, "lines": lines[:3]}


def share_text(facts):
    """The summary as plain text to paste into a post or an email."""
    head = " · ".join(x for x in (facts["call"], facts["dates"]) if x)
    parts = [head, facts["title"]] + ([facts["subtitle"]] if facts["subtitle"] else [])
    parts.append(" · ".join(f"{value} {label}" for value, label, _ in facts["numbers"]))
    parts += facts["lines"]
    parts.append(f"Made with FarField Lab ({SITE})")
    return "\n".join(parts)


def share_png(facts):
    """The summary as a 1200 by 630 picture, as PNG bytes."""
    fig = Figure(figsize=SIZE, dpi=100)
    fig.patch.set_facecolor(BG)
    fig.text(0.04, 0.925, "FARFIELD LAB · LOG ANALYSIS", color=TEAL, fontsize=10, fontweight="bold", va="center")
    who = " · ".join(x for x in (facts["call"], facts["dates"]) if x)
    fig.text(0.96, 0.925, who, color=FG, fontsize=15, fontweight="bold", va="center", ha="right")
    title = textwrap.wrap(facts["title"], 44)[:2] or [""]
    fig.text(0.04, 0.80 if len(title) == 1 else 0.82, "\n".join(title), color=FG, fontsize=27, fontweight="bold", va="top", linespacing=1.15)
    sub = textwrap.wrap(facts["subtitle"], 100)[:2]
    if sub:
        fig.text(0.04, 0.63 if len(title) == 1 else 0.60, "\n".join(sub), color=MUTED, fontsize=14, va="top", linespacing=1.3)
    n = len(facts["numbers"])
    gap = 0.02
    width = (0.92 - gap * (n - 1)) / n
    for i, (value, label, colour) in enumerate(facts["numbers"]):
        x = 0.04 + i * (width + gap)
        fig.add_artist(Rectangle((x, 0.29), width, 0.2, transform=fig.transFigure, facecolor=PANEL, edgecolor="#2a3140", linewidth=1))
        fig.text(x + 0.018, 0.425, value, color=colour, fontsize=34, fontweight="bold", va="center")
        fig.text(x + 0.018, 0.33, label, color=MUTED, fontsize=12, va="center")
    for i, line in enumerate(facts["lines"]):
        fig.text(0.04, 0.225 - i * 0.058, _clip(line, 104), color=FG, fontsize=14, va="center")
    fig.text(0.04, 0.04, "Made with FarField Lab", color=MUTED, fontsize=10, va="center")
    fig.text(0.96, 0.04, SITE, color=MUTED, fontsize=10, va="center", ha="right")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    return buf.getvalue()
