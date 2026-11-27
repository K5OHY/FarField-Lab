"""What stood out in a CW session, worked out from the log alone (and, for the timing of RBN spots, from the spots of your own call).

Nothing here scores or judges. Each piece says what the log shows: when each other continent first answered, the farthest contact on each band, how many
and when RBN first and last spotted you on each band next to your first and last contact there. The times are logged
times: a log holds contacts, so it cannot say when you were listening, calling or resting."""
import pandas as pd

import log_check as lc
import log_foundations as lf
from log_openings import unsupported_claims


def _hm(minutes):
    minutes = int(round(minutes))
    h, m = divmod(minutes, 60)
    return f"{m} min" if h == 0 else f"{h} h" if m == 0 else f"{h} h {m:02d} m"


def first_by_continent(places, home_cont="NA"):
    """When each other continent first answered: one row for each continent you worked that is not your own, the one worked first at the top.
    Columns: code, name, call, band, time, since (minutes after the first contact of the log) and stations (different calls worked there in all)."""
    cols = ["code", "name", "call", "band", "time", "since", "stations"]
    if places is None or len(places) == 0:
        return pd.DataFrame(columns=cols)
    d = places[places["continent"].isin(lf.CONTINENT_NAMES) & (places["continent"] != (home_cont or "NA")) & (places["continent"] != "AN")].sort_values("time")
    start = places["time"].min()
    rows = []
    for code, g in d.groupby("continent", sort=False):
        first = g.iloc[0]
        rows.append({"code": code, "name": lf.CONTINENT_NAMES[code], "call": first["call"], "band": first["band"], "time": first["time"],
                     "since": (first["time"] - start).total_seconds() / 60, "stations": int(g["call"].nunique())})
    return pd.DataFrame(rows, columns=cols).sort_values("time").reset_index(drop=True)


def farthest_by_band(places):
    """The farthest contact on each band, highest band first (see log_check.farthest_contact: one placed by a grid, a park or a summit wins; one placed only by its state
    or country does not, and when nothing better is known the stations at the same distance are all named). Columns: band, call (the first), calls (every contact at that
    distance), place (the country, else the continent), km, approx (True when only a centre is known, so the distance is a rough one), time, and rough_place, rough_km and
    rough_calls for a contact placed only by country that was farther than the precise one (else empty)."""
    cols = ["band", "call", "calls", "place", "km", "approx", "time", "rough_place", "rough_km", "rough_calls", "precise_call", "precise_km"]
    if places is None or len(places) == 0:
        return pd.DataFrame(columns=cols)
    d = places[places["c_km"].notna()]
    rows = []
    for band in lc.bands_top_down(d):
        f = lc.farthest_contact(d, band)
        g = d[(d["band"] == band) & (d["call"] == f["call"])]
        rough = f.get("rough") or {}
        precise = f.get("precise") or {}
        rows.append({"band": band, "call": f["call"], "calls": f["calls"], "place": f["place"], "km": f["km"], "approx": f["approx"], "time": g["time"].min(),
                     "rough_place": rough.get("place", ""), "rough_km": rough.get("km", float("nan")), "rough_calls": rough.get("calls", []),
                     "precise_call": precise.get("call", ""), "precise_km": precise.get("km", float("nan"))})
    return pd.DataFrame(rows, columns=cols)


REPEAT_MIN_SHARE = 0.05        # the repeat line is written only when at least this share of the contacts were with a station again on a band already worked with it


def repeat_contacts(log):
    """The contacts with a station already worked earlier in the session, from the log alone: how many were with a station on another band than it was first worked on
    (`other_band`) and how many were with it again on a band already worked with it (`same_band`), with the total and `share` of all contacts. A station is a callsign exactly
    as logged."""
    out = {"total": 0, "same_band": 0, "other_band": 0, "repeats": 0, "share": 0.0}
    if log is None or len(log) == 0:
        return out
    d = log.sort_values("time")
    seen_call, seen_pair = set(), set()
    for call, band in zip(d["call"], d["band"]):
        if (call, band) in seen_pair:
            out["same_band"] += 1
        elif call in seen_call:
            out["other_band"] += 1
        seen_call.add(call)
        seen_pair.add((call, band))
    out["total"], out["repeats"] = len(d), out["same_band"] + out["other_band"]
    out["share"] = out["repeats"] / out["total"]
    return out


def _names(calls, limit=3):
    calls = list(calls)
    shown = ", ".join(calls[:limit]) if len(calls) <= 2 else ", ".join(calls[:limit]) + (f" and {len(calls) - limit} more" if len(calls) > limit else "")
    return shown.replace(", ", " and ") if len(calls) == 2 else shown


def _farthest_line(far):
    """The sentence about the farthest contact from farthest_by_band's table, honest about how well the place is known: a contact placed by its grid, park or summit is named
    and its distance given; when only a country is known, the country and the stations in it are named and the distance is called rough; a farther contact placed only by
    country is mentioned beside a precisely placed one without taking its place."""
    lead = far.loc[far["km"].idxmax()]
    if bool(lead["approx"]) and lead["precise_call"]:             # a country far beyond anything placed precisely leads, said to be rough, with the best known place beside it
        return (f"The farthest contact{'s were' if len(lead['calls']) > 1 else ' was'} " + (f"with {lead['place']}" if lead["place"] else "") + f" ({_names(lead['calls'])} on {lead['band']}), "
                f"about {lead['km']:,.0f} km ({lead['km'] / 1.609344:,.0f} mi) away, placed only by country, so that distance is rough. The farthest placed by a grid or a park was "
                f"{lead['precise_call']}, {lead['precise_km']:,.0f} km.")
    precise = far[~far["approx"].astype(bool)]
    if len(precise):
        top = precise.loc[precise["km"].idxmax()]
        text = (f"The farthest contact was {top['call']}" + (f" in {top['place']}" if top["place"] else "") + f" on {top['band']}, "
                f"{top['km']:,.0f} km ({top['km'] / 1.609344:,.0f} mi) away.")
        rough = far[far["rough_km"].notna() & (far["rough_km"] > top["km"])]
        if len(rough):
            r = rough.loc[rough["rough_km"].idxmax()]
            text += (f" Contacts with {r['rough_place'] or 'another country'} ({_names(r['rough_calls'])}) were farther, about {r['rough_km']:,.0f} km, "
                     "but they are placed only by country, so that distance is rough.")
        return text
    top = far.loc[far["km"].idxmax()]
    return (f"The farthest contact{'s were' if len(top['calls']) > 1 else ' was'} " + (f"in {top['place']}" if top["place"] else "") + f" ({_names(top['calls'])} on {top['band']}), "
            f"about {top['km']:,.0f} km ({top['km'] / 1.609344:,.0f} mi) away. The log gives no grid square, so each is placed at the centre of its country and the distance is rough.")


def highlight_lines(first, far, repeats=None, dated=False):
    """The few sentences that lead the highlights, from the tables above and nothing else. The repeat line is written only when `repeats` (repeat_contacts) says at least
    REPEAT_MIN_SHARE of the contacts were with a station again on a band already worked with it. Stations that came back on another band are the multiband hunters, which the
    page shows on their own, and on most logs they are a tenth of the contacts, so they alone do not make a line. With `dated` (a log over more than one UTC day) a time
    carries its day, since the same clock time comes twice. Checked against the wording guard."""
    lines = []
    clock = "%d %b %H:%M" if dated else "%H:%M"
    if len(first):
        r = first.iloc[0]
        lines.append(f"The first contact outside your continent was {r['name']}: {r['call']} on {r['band']} at {r['time']:{clock}} UTC, "
                     + ("the first contact of the session." if r["since"] < 1 else f"{_hm(r['since'])} into the session."))
        if len(first) > 1:
            last = first.iloc[-1]
            lines.append(f"{last['name']} came last, at {last['time']:{clock}} UTC ({last['call']} on {last['band']}).")
    if len(far):
        lines.append(_farthest_line(far))
    if repeats and repeats["total"] and repeats["same_band"] / repeats["total"] >= REPEAT_MIN_SHARE:
        text = f"{repeats['same_band']} of {repeats['total']} contacts ({repeats['same_band'] / repeats['total'] * 100:.0f}%) were with a station already worked on the same band"
        if repeats["other_band"]:
            text += f"; a further {repeats['other_band']} were with stations that came back on another band"
        lines.append(text + ".")
    for line in lines:
        assert not unsupported_claims(line), unsupported_claims(line)
    return lines


# ------------------------------------------------------------------------------------------------- how fast the contacts came in

RATE_BIN_MIN = 10      # one bar is this many minutes
RATE_GAP_MIN = 30      # a pause between two contacts longer than this is time off the air, as it is for the active rate on the tiles


def _pauses(times, gap_min=RATE_GAP_MIN):
    """The pauses of more than `gap_min` minutes between consecutive contacts, as (from, to)."""
    t = sorted(pd.Timestamp(x) for x in times)
    return [(a, b) for a, b in zip(t, t[1:]) if (b - a) > pd.Timedelta(minutes=gap_min)]


def rate_table(log, bin_min=RATE_BIN_MIN, gap_min=RATE_GAP_MIN):
    """The rate at which the contacts came in, in contacts an hour, from the log alone. Returns (bars, line):
    bars  one row for each time bin and band with contacts: slot, end, band, contacts (the count the bar shows), `rate` (that count scaled to an hour) and `pace`
          (all the bin's contacts, on every band, scaled to an hour: the pace the bin was at);
    line  one row for each bin from the first contact to the last: slot, mid and `rolling` (the contacts in the hour around the middle of the bin, divided by the
          time on the air within that hour, so the start and the end of a session, where the hour is not full, are not read low; empty where the bin lies inside
          a pause of more than `gap_min` minutes, so the line breaks there instead of dipping to zero)."""
    cols_b, cols_l = ["slot", "end", "band", "contacts", "rate", "pace"], ["slot", "mid", "rolling"]
    if log is None or len(log) == 0:
        return pd.DataFrame(columns=cols_b), pd.DataFrame(columns=cols_l)
    step = pd.Timedelta(minutes=bin_min)
    d = log.assign(slot=log["time"].dt.floor(f"{bin_min}min"))
    g = d.groupby(["slot", "band"]).size().rename("contacts").reset_index()
    g["end"], g["rate"] = g["slot"] + step, g["contacts"] * 60 / bin_min
    g["pace"] = g.groupby("slot")["contacts"].transform("sum") * 60 / bin_min
    g["_r"] = g["band"].map(lc._rank)
    bars = g.sort_values(["slot", "_r"], ascending=[True, False])[cols_b].reset_index(drop=True)
    slots = pd.date_range(d["slot"].min(), d["slot"].max(), freq=f"{bin_min}min")
    times = d["time"].sort_values().reset_index(drop=True)
    pauses = _pauses(times, gap_min)
    runs = [(a, b) for a, b in zip(times, times[1:]) if (b - a) <= pd.Timedelta(minutes=gap_min)]          # the stretches counted as time on the air
    half = pd.Timedelta(minutes=30)
    rows = []
    for s in slots:
        mid = s + step / 2
        lo, hi = mid - half, mid + half
        on_air = sum(max((min(b, hi) - max(a, lo)).total_seconds(), 0.0) for a, b in runs)
        n = int(((times >= lo) & (times < hi)).sum())
        off = any(a < mid < b for a, b in pauses) or on_air < 300
        rows.append({"slot": s, "mid": mid, "rolling": None if off else n / (on_air / 3600)})
    return bars, pd.DataFrame(rows, columns=cols_l)


STRETCH_GAP_H = 4          # a pause this long in the log starts a new chart on the rate view, as it does on the session chart, so two days are not squeezed into one axis


def stretches(log, gap_h=STRETCH_GAP_H):
    """The log cut into stretches of activity wherever there is a pause of `gap_h` hours or more: a list of (first contact, last contact)."""
    if log is None or len(log) == 0:
        return []
    t = log["time"].sort_values().reset_index(drop=True)
    new = (t.diff() > pd.Timedelta(hours=gap_h)).cumsum()
    return [(g.min(), g.max()) for _, g in t.groupby(new)]


def best_stretch(log, minutes=10):
    """The busiest `minutes` of the log: the window that holds the most contacts. Returns {'start', 'end', 'contacts', 'pace', 'bands'} where pace is the contacts
    an hour that window would be if kept up, or None for a log of fewer than 3 contacts. A short window runs hot, so the page calls it a pace, not a rate."""
    if log is None or len(log) < 3:
        return None
    t = log["time"].sort_values().reset_index(drop=True)
    width = pd.Timedelta(minutes=minutes)
    best, at = 0, 0
    for i in range(len(t)):
        n = int(((t >= t[i]) & (t < t[i] + width)).sum())
        if n > best:
            best, at = n, i
    start = t[at]
    inside = log[(log["time"] >= start) & (log["time"] < start + width)]
    return {"start": start, "end": start + width, "contacts": best, "pace": best * 60 / minutes, "bands": sorted(set(inside["band"]), key=lc._rank, reverse=True)}


def band_starts(log):
    """The first contact on each band, in time order: time, band and the call. They mark where you moved to a new band on the rate chart."""
    if log is None or len(log) == 0:
        return pd.DataFrame(columns=["time", "band", "call"])
    first = log.sort_values("time").drop_duplicates("band")
    return first[["time", "band", "call"]].reset_index(drop=True)


def rate_line(best, dated=False):
    """The sentence under the chart about the busiest stretch; with `dated` the day is named too (a log over two days has the same clock time twice). Checked against the
    wording guard."""
    if not best:
        return ""
    when = f"{best['start']:%d %b %H:%M} UTC" if dated else f"{best['start']:%H:%M} UTC"
    text = (f"The busiest {int((best['end'] - best['start']).total_seconds() // 60)} minutes began at {when}: {best['contacts']} contacts, "
            f"a pace of {best['pace']:.0f} an hour if it had been kept up.")
    assert not unsupported_claims(text), unsupported_claims(text)
    return text


def rate_lines(log):
    """The sentences under the rate charts: the busiest 60 minutes (the contacts in any hour of the log, as a count) and the busiest 10 minutes (a pace), with the day named
    when the log covers more than one UTC day. They are different measures and are not mixed with the estimated active rate on the tiles, which divides by the time on the
    air. Checked against the wording guard."""
    if log is None or len(log) < 3:
        return []
    dated = log["time"].dt.date.nunique() > 1
    lines = []
    hour = best_stretch(log, 60)
    if hour:
        when = f"{hour['start']:%d %b %H:%M} UTC" if dated else f"{hour['start']:%H:%M} UTC"
        lines.append(f"The busiest 60 minutes began at {when}: {hour['contacts']} contacts.")
    lines.append(rate_line(best_stretch(log, 10), dated))
    for line in lines:
        assert not unsupported_claims(line), unsupported_claims(line)
    return [x for x in lines if x]


_DATE_AT_MIDNIGHT = "hours(datum.value) === 0 && minutes(datum.value) === 0 ? timeFormat(datum.value, '%d %b') : timeFormat(datum.value, '%H:%M')"


RATE_AXIS_PX = 75        # the room each pair of charts keeps on the left, for its axis numbers and title, so the plots of side-by-side stretches line up
RATE_PAGE_PX = 1030      # about the width the charts will have; only the proportions between stretches depend on it, the charts themselves fill whatever room they get
RATE_COLUMN_GAP_PX = 16  # the gap Streamlit leaves between columns


def rate_charts(log, colours):
    """The rate as charts on a time axis, so a bar and a line are never read as the same thing. Above: a bar for each ten minutes, as tall as the contacts made in those ten
    minutes, stacked by band in the band's colour, with a triangle where each band was first used; hovering gives the count and the pace that bin was at. Below: a line of
    the contacts an hour over the hour around each bar, counting only the time on the air, broken at a pause of more than 30 minutes.

    A log with a long pause (two days, or a morning and an evening) gets one pair of charts for each stretch of activity side by side, each on its own time axis and as wide as
    the stretch is long, with the date in its title, so the overnight gap is not drawn as hours of nothing and 19:00 on one day cannot be taken for 19:00 on the next; the
    vertical scales are shared so the stretches can be compared. Each chart is its own Altair chart, so the page can stretch it to exactly the room it has (a chart made of
    several parts cannot be made to fit, it runs past the edge by the width of its axis).

    Returns None when there is nothing to draw, else {"bands": [(band, colour), ...] for the key the page draws once, "columns": [{"weight", "top", "bottom"}, ...]}; `weight` is
    the share of the width a column takes, and the key is left to the page so every chart has the same height whatever its column."""
    import altair as alt
    bars, line = rate_table(log)
    if bars.empty:
        return None
    parts = stretches(log)
    many = len(parts) > 1
    order = sorted(set(bars["band"]), key=lc._rank, reverse=True)
    scale = alt.Scale(domain=order, range=[colours.get(b, "#888888") for b in order])
    day = "%d %b " if many else ""
    bars = bars.assign(window=bars["slot"].dt.strftime(day + "%H:%M") + "–" + bars["end"].dt.strftime("%H:%M") + " UTC")
    bars["top"] = bars.groupby("slot")["contacts"].cumsum()                # stacked by hand (the highest band at the foot), so every bar runs from its own foot to its own top
    bars["foot"] = bars["top"] - bars["contacts"]
    bars["shown_end"] = bars["end"] - pd.Timedelta(minutes=1)              # a minute of gap between bars, so the bins can be told apart without an outline
    bars["pace_text"] = bars["pace"].round().astype(int).astype(str) + " an hour"
    line = line.assign(window=line["slot"].dt.strftime(day + "%H:%M") + "–" + (line["slot"] + pd.Timedelta(minutes=RATE_BIN_MIN)).dt.strftime("%H:%M") + " UTC")
    marks = band_starts(log).assign(zero=0, label=lambda d: "First " + d["band"] + " contact: " + d["call"] + " at " + d["time"].dt.strftime(day + "%H:%M") + " UTC")
    top_max, line_max = int(bars["top"].max()) + 1, max(float(line["rolling"].max() or 0), 1.0) * 1.1
    durations = [max((b - a).total_seconds() + RATE_BIN_MIN * 60, 1800) for a, b in parts]
    usable = RATE_PAGE_PX - len(parts) * RATE_AXIS_PX - RATE_COLUMN_GAP_PX * (len(parts) - 1)
    plots = [max(140.0, usable * d / sum(durations)) for d in durations]
    columns = []
    for i, (a, b) in enumerate(parts):
        lo, hi = a.floor(f"{RATE_BIN_MIN}min"), b.floor(f"{RATE_BIN_MIN}min") + pd.Timedelta(minutes=RATE_BIN_MIN)
        x_scale = alt.Scale(domain=[lo.isoformat(), hi.isoformat()])
        bi, li, mi = bars[(bars["slot"] >= lo) & (bars["slot"] < hi)], line[(line["slot"] >= lo) & (line["slot"] < hi)], marks[(marks["time"] >= lo) & (marks["time"] < hi)]
        first = i == 0
        y_axis = alt.Axis(minExtent=44) if first else alt.Axis(minExtent=RATE_AXIS_PX - 10, title=None)     # a column without the title keeps the room the title takes, so the plots line up
        stack = alt.Chart(bi).mark_bar(strokeWidth=0).encode(
            x=alt.X("slot:T", scale=x_scale, axis=alt.Axis(labels=False, ticks=False, title=None)), x2="shown_end:T",
            y=alt.Y("foot:Q", title="Contacts in 10 minutes" if first else None, axis=y_axis, scale=alt.Scale(domain=[0, top_max], nice=True)), y2="top:Q",
            color=alt.Color("band:N", scale=scale, sort=order, legend=None),
            tooltip=[alt.Tooltip("window:N", title="Time"), alt.Tooltip("band:N", title="Band"), alt.Tooltip("contacts:Q", title="Contacts on this band"),
                     alt.Tooltip("pace_text:N", title="All bands, at that pace")])
        starts = alt.Chart(mi).mark_point(shape="triangle-up", size=110, filled=True, color="#ffd54f", strokeWidth=0).encode(
            x=alt.X("time:T", scale=x_scale), y="zero:Q", tooltip=[alt.Tooltip("label:N", title="")])
        rolling = alt.Chart(li).mark_line(strokeWidth=2.2, point=alt.OverlayMarkDef(size=24)).encode(
            x=alt.X("mid:T", scale=x_scale, axis=alt.Axis(labelExpr=_DATE_AT_MIDNIGHT, title=None) if many else alt.Axis(format="%H:%M", title=None)),
            y=alt.Y("rolling:Q", title="Contacts an hour" if first else None, axis=y_axis, scale=alt.Scale(domain=[0, line_max], nice=True)),
            tooltip=[alt.Tooltip("window:N", title="Around"), alt.Tooltip("rolling:Q", title="Contacts an hour, over the hour around", format=".0f")])
        if many:
            span = f"{a:%a %d %b}" if a.date() == b.date() else f"{a:%a %d %b} to {b:%a %d %b}"
            top_title = alt.TitleParams(f"{span}, {a:%H:%M}–{b:%H:%M} UTC", anchor="start", fontSize=13, fontWeight="normal")
            bottom_title = alt.TitleParams("", fontSize=1)                  # the same space as the other columns' charts, so a pair of columns lines up
        else:
            top_title = alt.TitleParams("Contacts in each 10 minutes, by band", anchor="start", fontSize=13, fontWeight="normal")
            bottom_title = alt.TitleParams("Contacts an hour, over the hour around (time on the air only)", anchor="start", fontSize=13, fontWeight="normal")
        fit = alt.AutoSizeParams(type="fit-x", contains="padding")           # fill the width, but the height is the plot's own
        top = alt.layer(stack, starts).properties(height=210, title=top_title, autosize=fit).configure_view(strokeWidth=0)
        bottom = rolling.properties(height=110, title=bottom_title, autosize=fit).configure_view(strokeWidth=0)
        columns.append({"weight": plots[i] + RATE_AXIS_PX, "top": top, "bottom": bottom})
    return {"bands": [(b, colours.get(b, "#888888")) for b in order], "columns": columns}
