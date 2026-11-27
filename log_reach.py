"""Where RBN heard you: for each band of a log, which Reverse Beacon Network skimmers reported you, where they are, and how many skimmers were reporting any station at all
while your logged CW contacts were being made. The functions take tables and return plain values, so they can be tested with made-up data.

The counts use one definition of time for both numbers: the half hours that hold a logged CW contact on the band. A skimmer is *active* in a half hour when it reported any
station on that band (you included); it *reported you* when it reported you on that band in one of those half hours. Each skimmer is counted once per band, whatever the number
of half hours (a skimmer called W3LPL-2 is W3LPL), so the two numbers are the same kind of count. A skimmer that was active at some other time of the day is not counted, and
neither is one that was active a quarter of an hour before your first contact. They are approximate activity windows, not a record of when you were calling."""
import pandas as pd

import conditions as cond
import log_check as lc
from session_report import region_of

WINDOW_MIN = 30
NORTH_AMERICA = ("US East", "US Central", "US West", "Canada", "Mexico, Caribbean & Central America")
OTHER, UNKNOWN = "Other regions", "Location unknown"
SHORT_NAMES = {"Mexico, Caribbean & Central America": "Caribbean and Central America"}


def region_label(region):
    """The region as the page writes it."""
    return SHORT_NAMES.get(region, region)


def window_starts(log, band, minutes=WINDOW_MIN):
    """The half hours that hold a logged CW contact on `band`, as the time each begins."""
    cw = log[(log["mode"] == "CW") & (log["band"] == band)]
    return sorted(set(cw["time"].dt.floor(f"{minutes}min")))


def window_spots(log, spots, band, minutes=WINDOW_MIN):
    """(your spots on `band` that fall in the half hours holding a logged CW contact on it, the number of those half hours). The card and the map both read their skimmers from
    here, so they count the same spots over the same time."""
    wins = window_starts(log, band, minutes)
    if not wins or spots is None or len(spots) == 0:
        return (spots.iloc[0:0] if spots is not None else pd.DataFrame({"spotter": [], "band": [], "snr": [], "time": pd.to_datetime([])})), len(wins)
    keep = (spots["band"] == band) & spots["time"].dt.floor(f"{minutes}min").isin(set(wins))
    return spots[keep], len(wins)


def reporter_count(spots):
    """How many different skimmers are in a table of spots, a skimmer being its callsign without a -# suffix, as the card counts them."""
    return int(spots["spotter"].map(lc._base).nunique()) if len(spots) else 0


def _locations(locs):
    out = {}
    for call, place in locs.items():
        out.setdefault(lc._base(call), place)
    return out


def _count_by_region(receivers, reporters, where):
    """{region: [receivers that reported you, receivers active]} for a set of receivers, a receiver with no known place going under UNKNOWN."""
    regions = {}
    for base in receivers:
        place = where.get(base)
        name = UNKNOWN if place is None else region_of(base, place)
        name = OTHER if name == "Other" else name
        cell = regions.setdefault(name, [0, 0])
        cell[1] += 1
        cell[0] += base in reporters
    return regions


def reach_by_band(log, spots, listening, locs, home, missing=(), minutes=WINDOW_MIN):
    """One entry for each band with logged CW contacts, the highest band first:
    band, contacts (CW), other_mode (contacts on the band in other modes, which RBN cannot hear), first_contact, last_contact, windows (the half hours counted),
    reporters (receivers that reported you), active (receivers that reported any station, you included), reports (your spots in those half hours),
    regions ({region: [reported you, active]}), farthest (km, receiver, region or None), first_spot, last_spot (your first and last spot on the band over the whole log),
    state and the same two counts over the whole stretch from the first to the last contact (reporters_wide, active_wide) for comparison. `state` is
    'ok', 'unavailable' (RBN has no file for any of the days the band's half hours fall on, or the skimmers that were listening could not be read) or 'no_activity'
    (the file is there and no skimmer reported anyone on the band in those half hours). `missing` is the days (YYYYMMDD) RBN has no file for; half hours on those days are left out."""
    cw = log[log["mode"] == "CW"]
    if cw.empty:
        return []
    have_listening = listening is not None and len(listening) > 0
    where = _locations(locs)
    spots = spots if spots is not None and len(spots) else pd.DataFrame({"spotter": [], "band": [], "time": pd.to_datetime([])})
    spots = spots.assign(b=spots["spotter"].map(lc._base))
    if have_listening:
        listening = listening.assign(slot=pd.to_datetime(listening["slot"]))
        listening = listening.assign(half=listening["slot"].dt.floor(f"{minutes}min"))
    rows = []
    for band in lc.bands_top_down(cw):
        mine = cw[cw["band"] == band]["time"]
        everything = log[log["band"] == band]
        wins_all = window_starts(log, band, minutes)
        wins = [w for w in wins_all if f"{w:%Y%m%d}" not in missing]
        mine_spots = spots[spots["band"] == band]
        entry = {"band": band, "contacts": int(len(mine)), "other_mode": int((everything["mode"] != "CW").sum()), "first_contact": mine.min(), "last_contact": mine.max(),
                 "windows": len(wins), "windows_all": len(wins_all), "missing_days": sorted({f"{w:%Y%m%d}" for w in wins_all} & set(missing)),
                 "reporters": 0, "active": 0, "reports": 0, "regions": {}, "farthest": None,
                 "first_spot": mine_spots["time"].min() if len(mine_spots) else pd.NaT, "last_spot": mine_spots["time"].max() if len(mine_spots) else pd.NaT,
                 "spots_total": int(len(mine_spots)), "reporters_wide": 0, "active_wide": 0, "state": "ok"}
        if not wins or not have_listening:
            entry["state"] = "unavailable"
            rows.append(entry)
            continue
        window_set = set(wins)
        in_windows, _ = window_spots(log, mine_spots, band, minutes)
        in_windows = in_windows[in_windows["time"].dt.floor(f"{minutes}min").isin(window_set)]       # without the half hours on a day RBN has no file for
        reporters = set(in_windows["b"])
        active = set(listening[(listening["band"] == band) & listening["half"].isin(window_set)]["b"]) | reporters
        entry.update(reporters=len(reporters), active=len(active), reports=int(len(in_windows)), regions=_count_by_region(active, reporters, where))
        far = None
        for base in reporters:
            place = where.get(base)
            if place is not None:
                km = float(cond._km_between(home[0], home[1], place[0], place[1]))
                if far is None or km > far[0]:
                    far = (km, base, region_of(base, place))
        entry["farthest"] = far
        lo, hi = mine.min().floor("15min"), mine.max()
        wide_spots = mine_spots[(mine_spots["time"] >= lo) & (mine_spots["time"] <= hi)]
        wide_rep = set(wide_spots["b"])
        wide = set(listening[(listening["band"] == band) & (listening["slot"] >= lo) & (listening["slot"] <= hi)]["b"]) | wide_rep
        entry.update(reporters_wide=len(wide_rep), active_wide=len(wide))
        if not active:
            entry["state"] = "no_activity"
        rows.append(entry)
    return rows


def overall(rows):
    """The facts for the card's takeaway: the farthest report of any band, and the busiest band when everything that reported you on it was in North America."""
    best = None
    for r in rows:
        if r["farthest"] and (best is None or r["farthest"][0] > best["farthest"][0]):
            best = r
    busiest = max((r for r in rows if r["state"] == "ok" and r["reporters"] >= 3), key=lambda r: r["contacts"], default=None)
    home_only = False
    if busiest:
        names = {n for n, (heard, _) in busiest["regions"].items() if heard}
        beyond = any(n not in NORTH_AMERICA and active for n, (_, active) in busiest["regions"].items())
        home_only = bool(names) and names <= set(NORTH_AMERICA) and beyond
    reporters = set()
    return {"farthest_band": best, "busiest": busiest if home_only else None, "bands_with_reports": sum(1 for r in rows if r["reporters"])}
