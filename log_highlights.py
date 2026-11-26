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
    """The farthest contact on each band, highest band first. Columns: band, call, place (the country, else the continent), km, approx (True when the
    contact was placed by its state or country rather than its own grid square, so the distance is a rough one) and time."""
    cols = ["band", "call", "place", "km", "approx", "time"]
    if places is None or len(places) == 0:
        return pd.DataFrame(columns=cols)
    d = places[places["c_km"].notna()]
    rows = []
    for band in lc.bands_top_down(d):
        g = d[d["band"] == band]
        far = g.loc[g["c_km"].idxmax()]
        rows.append({"band": band, "call": far["call"], "place": far["country"] or lf.CONTINENT_NAMES.get(far["continent"], ""), "km": float(far["c_km"]),
                     "approx": bool(far["c_approx"]), "time": far["time"]})
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


def rbn_timing(log, spots):
    """For each band: the first and last of your contacts and the first and last RBN spot of you, in UTC, with the number of spots. Highest band first. A band
    with spots but no contact is left out (the log is what is being read). Columns: band, first_contact, last_contact, first_spot, last_spot, spots."""
    cols = ["band", "first_contact", "last_contact", "first_spot", "last_spot", "spots"]
    if log is None or len(log) == 0 or spots is None or len(spots) == 0:
        return pd.DataFrame(columns=cols)
    rows = []
    for band in lc.bands_top_down(log):
        mine, sp = log[log["band"] == band]["time"], spots[spots["band"] == band]["time"]
        rows.append({"band": band, "first_contact": mine.min(), "last_contact": mine.max(), "first_spot": sp.min() if len(sp) else pd.NaT,
                     "last_spot": sp.max() if len(sp) else pd.NaT, "spots": int(len(sp))})
    return pd.DataFrame(rows, columns=cols)


def highlight_lines(first, far, repeats=None):
    """The few sentences that lead the highlights, from the tables above and nothing else. The repeat line is written only when `repeats` (repeat_contacts) says at least
    REPEAT_MIN_SHARE of the contacts were with a station again on a band already worked with it. Stations that came back on another band are the multiband hunters, which the
    page shows on their own, and on most logs they are a tenth of the contacts, so they alone do not make a line. Checked against the wording guard."""
    lines = []
    if len(first):
        r = first.iloc[0]
        lines.append(f"The first contact outside your continent was {r['name']}: {r['call']} on {r['band']} at {r['time']:%H:%M} UTC, "
                     + ("the first contact of the session." if r["since"] < 1 else f"{_hm(r['since'])} into the session."))
        if len(first) > 1:
            last = first.iloc[-1]
            lines.append(f"{last['name']} came last, at {last['time']:%H:%M} UTC ({last['call']} on {last['band']}).")
    if len(far):
        top = far.loc[far["km"].idxmax()]
        lines.append(f"The farthest contact was {top['call']}" + (f" in {top['place']}" if top["place"] else "") + f" on {top['band']}, "
                     f"{'about ' if top['approx'] else ''}{top['km']:,.0f} km ({top['km'] / 1.609344:,.0f} mi) away.")
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


def rate_line(best):
    """The sentence under the chart about the busiest stretch. Checked against the wording guard."""
    if not best:
        return ""
    text = (f"The busiest {int((best['end'] - best['start']).total_seconds() // 60)} minutes began at {best['start']:%H:%M} UTC: {best['contacts']} contacts, "
            f"a pace of {best['pace']:.0f} an hour if it had been kept up.")
    assert not unsupported_claims(text), unsupported_claims(text)
    return text


def rate_chart(log, colours):
    """The rate as two charts on one time axis, so a bar and a line are never read as the same thing. Above: a bar for each ten minutes, as tall as the contacts made in
    those ten minutes, stacked by band in the band's colour, with a triangle where each band was first used; hovering gives the count and the pace that bin was at.
    Below: a line of the contacts an hour over the hour around each bar, counting only the time on the air, broken at a pause of more than 30 minutes. An Altair chart,
    or None when there is nothing to draw."""
    import altair as alt
    bars, line = rate_table(log)
    if bars.empty:
        return None
    order = sorted(set(bars["band"]), key=lc._rank, reverse=True)
    scale = alt.Scale(domain=order, range=[colours.get(b, "#888888") for b in order])
    lo, hi = bars["slot"].min(), bars["end"].max()
    x_scale = alt.Scale(domain=[lo.isoformat(), hi.isoformat()])
    bars = bars.assign(window=bars["slot"].dt.strftime("%H:%M") + "\u2013" + bars["end"].dt.strftime("%H:%M") + " UTC")
    bars["top"] = bars.groupby("slot")["contacts"].cumsum()                # stacked by hand (the highest band at the foot), so every bar runs from its own foot to its own top
    bars["foot"] = bars["top"] - bars["contacts"]
    bars["shown_end"] = bars["end"] - pd.Timedelta(minutes=1)              # a minute of gap between bars, so the bins can be told apart without an outline
    bars["pace_text"] = bars["pace"].round().astype(int).astype(str) + " an hour"
    axis = alt.Axis(format="%H:%M", title=None)
    left = alt.Axis(minExtent=44)                                           # the same left margin on both charts, so the two time axes line up
    stack = alt.Chart(bars).mark_bar(strokeWidth=0).encode(
        x=alt.X("slot:T", scale=x_scale, axis=alt.Axis(format="%H:%M", title=None, labels=False, ticks=False)), x2="shown_end:T",
        y=alt.Y("foot:Q", title="Contacts in 10 minutes", axis=left, scale=alt.Scale(domain=[0, int(bars["top"].max()) + 1], nice=True)), y2="top:Q",     # the axis has to reach the tallest stack
        color=alt.Color("band:N", scale=scale, sort=order, legend=alt.Legend(title="Band", orient="top", symbolStrokeWidth=0, symbolType="square")),
        tooltip=[alt.Tooltip("window:N", title="Time"), alt.Tooltip("band:N", title="Band"), alt.Tooltip("contacts:Q", title="Contacts on this band"),
                 alt.Tooltip("pace_text:N", title="All bands, at that pace")])
    marks = band_starts(log).assign(zero=0, label=lambda d: "First " + d["band"] + " contact: " + d["call"] + " at " + d["time"].dt.strftime("%H:%M") + " UTC")
    starts = alt.Chart(marks).mark_point(shape="triangle-up", size=110, filled=True, color="#ffd54f", strokeWidth=0).encode(
        x=alt.X("time:T", scale=x_scale), y="zero:Q", tooltip=[alt.Tooltip("label:N", title="")])
    line = line.assign(window=line["slot"].dt.strftime("%H:%M") + "\u2013" + (line["slot"] + pd.Timedelta(minutes=RATE_BIN_MIN)).dt.strftime("%H:%M") + " UTC")
    rolling = alt.Chart(line).mark_line(color="#f5f5f5", strokeWidth=2.2, point=alt.OverlayMarkDef(color="#f5f5f5", size=24)).encode(
        x=alt.X("mid:T", scale=x_scale, axis=axis), y=alt.Y("rolling:Q", title="Contacts an hour", axis=left, scale=alt.Scale(zero=True)),
        tooltip=[alt.Tooltip("window:N", title="Around"), alt.Tooltip("rolling:Q", title="Contacts an hour, over the hour around", format=".0f")])
    top = alt.layer(stack, starts).properties(height=210, title=alt.TitleParams("Contacts in each 10 minutes, by band", anchor="start", fontSize=13, fontWeight="normal"))
    bottom = rolling.properties(height=110, title=alt.TitleParams("Contacts an hour, over the hour around (time on the air only)", anchor="start", fontSize=13, fontWeight="normal"))
    return alt.vconcat(top, bottom, spacing=14).resolve_scale(x="shared", color="independent").configure_view(strokeWidth=0)
