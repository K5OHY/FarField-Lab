"""What stood out in a CW session, worked out from the log alone (and, for the timing of RBN spots, from the spots of your own call).

Nothing here scores or judges. Each piece says what the log shows: when each other continent first answered, the farthest contact on each band, how many
new stations came in each hour, and when RBN first and last spotted you on each band next to your first and last contact there. The times are logged
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


def new_by_hour(log):
    """The contacts in each UTC hour of the log and how many of them were with a station not worked earlier in the session (on any band). Columns:
    hour, contacts, new, share (new / contacts). A station is a callsign exactly as logged. Hours with no contact between the first and the last are kept
    as zeros so a gap shows as a gap."""
    cols = ["hour", "contacts", "new", "share"]
    if log is None or len(log) == 0:
        return pd.DataFrame(columns=cols)
    d = log.sort_values("time").assign(first=lambda x: ~x["call"].duplicated())
    d["hour"] = d["time"].dt.floor("h")
    g = d.groupby("hour").agg(contacts=("call", "size"), new=("first", "sum"))
    g = g.reindex(pd.date_range(g.index.min(), g.index.max(), freq="h"), fill_value=0)
    out = g.rename_axis("hour").reset_index()
    out["contacts"], out["new"] = out["contacts"].astype(int), out["new"].astype(int)
    out["share"] = out["new"] / out["contacts"].where(out["contacts"] > 0)
    return out[cols]


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


def highlight_lines(first, far, hours):
    """The few sentences that lead the highlights, from the tables above and nothing else. Checked against the wording guard."""
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
    if len(hours) and hours["new"].sum():
        best = hours.loc[hours["new"].idxmax()]
        lines.append(f"The most new stations came in the hour from {best['hour']:%H:%M} UTC: {int(best['new'])} of {int(best['contacts'])} contacts.")
    for line in lines:
        assert not unsupported_claims(line), unsupported_claims(line)
    return lines
