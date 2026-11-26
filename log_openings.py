"""How you used the openings: the Log analysis grid read for one destination.

Each box of the grid is a band in one time bin. For the destination chosen (a compass sector or a continent, at or beyond a minimum distance)
the box says three separate things, and never mixes them into a score:

  * WSPR path evidence: receivers there decoded WSPR transmitters near you, and, in the estimate view, looked strong enough to hear you;
  * what you did: whether you were active on the band in that box, and whether you made a contact with that destination;
  * RBN: whether skimmers there spotted you. It speaks only for CW and RTTY and only when you were calling CQ (RBN spots a station that calls,
    not one that answers); otherwise the box says RBN does not apply or is not known.

From those come one of five conclusions, in cautious words. Nothing here infers when a station was listening, what you tried, or what you
should have done, and there is no utilisation score. Nothing here draws a page or asks the network, so it can be tested with made-up data.
"""
import numpy as np
import pandas as pd
from geographiclib.geodesic import Geodesic

import conditions as cond
import log_check as lc
import log_foundations as lf
from compare_stats import locate as locate_skimmer
from session_report import region_of

METRIC = {"observed": "heard", "estimate": "good"}      # the DX picture's two views: what was decoded, or what looked strong enough for you

BOTH, PATH_OTHER, PATH_IDLE, CONTACT_NO_PATH, NEITHER = "both", "path_other", "path_idle", "contact_no_path", "neither"
CONCLUSIONS = {
    BOTH: "A path, and a contact with it",
    PATH_OTHER: "A path; active on the band, no contact with it",
    PATH_IDLE: "A path; no contact on the band",
    CONTACT_NO_PATH: "A contact, but no path in the WSPR",
    NEITHER: "No path in the WSPR, and no contact with it",
}

# Phrases a summary must never contain: they claim a cause, a missed chance, a failed attempt or a score that the data cannot support.
UNSUPPORTED = ("caught", "missed", "failed", "should have", "could have", "would have", "wasted", "opportunit", "score", "utilis", "utiliz",
               "efficien", "was listening", "were listening", "tried", "attempt", "wrong band", "right band", "better band", "you chose")


def unsupported_claims(text):
    """The phrases in `text` that claim more than the data shows (see UNSUPPORTED). An empty list means it is clean."""
    low = text.lower()
    return [phrase for phrase in UNSUPPORTED if phrase in low]


def where_forms(view, dest):
    """The destination as it reads in a sentence, in the ways a sentence needs it: `to` ('a path to ...'), `with` ('a contact with ...') and
    `skimmers` ('RBN skimmers ... spotted you'), plus `short` for a heading. With no destination chosen it is the stations at the distance chosen."""
    if dest is None:
        return {"to": "stations at this distance", "with": "stations at this distance", "skimmers": "at this distance", "short": "any destination"}
    name = lf.CONTINENT_NAMES.get(dest, dest) if view == "continent" else f"the {lf.SECTOR_NAMES[dest].lower()}"
    return {"to": name, "with": f"stations in {name}", "skimmers": f"in {name}", "short": name}


def _within(df, view, dest, min_km, sector_col="sector", continent_col="continent", km_col="km"):
    """A mask of the rows of `df` that are in the destination and at least `min_km` from you."""
    if dest is None and min_km <= 0:
        return pd.Series(True, index=df.index)
    keep = df[km_col].fillna(-1) >= min_km
    if dest is not None:
        keep &= (df[continent_col] == dest) if view == "continent" else (df[sector_col] == dest)
    return keep


def skimmer_table(spots, locs, home):
    """Where each skimmer that spotted you is, as seen from you: spotter, who (its callsign without the -number), km, bearing, sector and
    continent. A skimmer the skimmer list does not know is left out."""
    cols = ["spotter", "who", "km", "bearing", "sector", "continent"]
    if spots is None or len(spots) == 0:
        return pd.DataFrame(columns=cols)
    rows = []
    for spotter in spots["spotter"].unique():
        place = locate_skimmer(spotter, locs)
        if not place:
            continue
        inv = Geodesic.WGS84.Inverse(home[0], home[1], float(place[0]), float(place[1]))
        bearing = inv["azi1"] % 360
        rows.append({"spotter": spotter, "who": lc._base(spotter), "km": inv["s12"] / 1000, "bearing": bearing, "sector": lf.sector_of(bearing),
                     "continent": lf.continent_of_region(region_of(spotter, (float(place[0]), float(place[1]))))})
    return pd.DataFrame(rows, columns=cols)


# ------------------------------------------------------------------------------------------------- the five conclusions

def conclude(state, active, with_dest, where, band):
    """(key, sentence) for one box. `state` is the box's WSPR state (see log_foundations.cell_state), `active` how many contacts you logged on the
    band in it and `with_dest` how many of those were with the destination. The key is one of the five in CONCLUSIONS, or None when WSPR
    had too little behind it to say anything about a path."""
    plural = "" if with_dest == 1 else "s"
    if state in (lf.SPARSE, lf.UNAVAILABLE):
        text = f"Too little WSPR to say whether there was a path to {where['to']}."
        return None, text + (f" You logged {with_dest} contact{plural} with {where['with']}." if with_dest else "")
    path, contact = state == lf.EVIDENCE, with_dest > 0
    if path and contact:
        return BOTH, f"WSPR showed a path to {where['to']}. You were active on {band} and logged {with_dest} contact{plural} with {where['with']}."
    if path and active:
        return PATH_OTHER, f"WSPR showed a path to {where['to']}. You were active on {band} but logged no contact with {where['with']}."
    if path:
        return PATH_IDLE, f"WSPR showed a path to {where['to']}. You logged no contact on {band} in this box."
    why = {lf.NO_REPORTS: "no WSPR reports from there", lf.BELOW: "none of the WSPR stations there looked strong enough"}.get(state, state)
    if contact:
        return CONTACT_NO_PATH, f"You logged {with_dest} contact{plural} with {where['with']}, although WSPR showed no path ({why})."
    return NEITHER, f"WSPR showed no path to {where['to']} ({why}), and you logged no contact with {where['with']}."


def rbn_sentence(state, n, where, why=""):
    """The RBN part of a box's statement, from its RBN state (see opening_cells): said only when RBN applies."""
    if state == lf.NOT_APPLICABLE:
        return "RBN not applicable or unknown." + (f" ({why})" if why else "")
    if state == lf.UNAVAILABLE:
        return "RBN spots are not available."
    if n > 0:
        return f"{n} RBN skimmer{'s' if n != 1 else ''} {where['skimmers']} spotted you."
    return f"No RBN skimmer {where['skimmers']} spotted you (RBN has few skimmers, so this says little)."


# ------------------------------------------------------------------------------------------------- the cells

def opening_cells(grid, log, places, spots, locs, home, view="sector", dest=None, min_km=lc.DX_KM, metric="good", rbn_ok=True):
    """One row for each band and time bin of `grid` (lc.conditions_grid), read for one destination.

    grid, log    the conditions grid and the contacts; places is lc.contact_places(log, home)
    spots, locs  your RBN spots and the skimmer list; rbn_ok is False when the RBN spots could not be read
    view, dest   'sector' or 'continent', and the sector code or continent code asked about (None for all of them)
    min_km       a station nearer than this is not a destination
    metric       'good' (estimate: receivers that looked strong enough for you) or 'heard' (what WSPR showed: receivers that decoded)

    Columns: the box (panel, slot, band, worked, the WSPR window and what it shares), `heard` and `good` (receivers in the destination), `n`
    (the one the metric picks), `state` (see log_foundations.cell_state, for the path), `active` (your contacts on the band in the box),
    `with_dest` (those with the destination), `rbn_state` and `rbn_n`, `rbn_why`, and the conclusion `key` and `text`."""
    bin_min = grid.attrs.get("bin_min", lc.CONDITIONS_SLOT_MIN)
    where = where_forms(view, dest)
    rec = grid.attrs.get("receivers")
    if rec is None or len(rec) == 0:
        rec = pd.DataFrame(columns=["slot", "band", "km", "sector", "continent", "verdict"])
    rec = rec[_within(rec, view, dest, min_km)]
    heard = rec.groupby(["slot", "band"]).size()
    good = rec[rec["verdict"] == "good"].groupby(["slot", "band"]).size()

    pl = places.assign(slot=lf.bin_floor(places["time"], bin_min))
    active = pl.groupby(["slot", "band"]).size()
    with_dest = pl[_within(pl, view, dest, min_km, sector_col="sector_whole", km_col="c_km")].groupby(["slot", "band"]).size()
    mode_in = pl.groupby(["slot", "band"])["mode"].agg(lambda m: str(m.mode().iloc[0]))
    session_mode = str(log["mode"].mode().iloc[0]) if len(log) else "CW"
    activation = bool((log["my_pota"] != "").any() or (log["my_sota"] != "").any())      # an activation is run by calling CQ

    sk = skimmer_table(spots if rbn_ok else None, locs, home)
    running, rbn_dest = {}, pd.Series(dtype=int)
    if rbn_ok and spots is not None and len(spots):
        sp = spots.assign(slot=lf.bin_floor(spots["time"], bin_min))
        if "mode" in sp:
            running = sp.groupby(["slot", "band"])["mode"].agg(lambda k: any(str(x).upper() in lf.RUNNING_KINDS for x in k)).to_dict()
        joined = sp.merge(sk, on="spotter")
        rbn_dest = joined[_within(joined, view, dest, min_km)].groupby(["slot", "band"])["who"].nunique()

    rows = []
    for r in grid.itertuples():
        key = (r.slot, r.band)
        h, g = int(heard.get(key, 0)), int(good.get(key, 0))
        n = g if metric == "good" else h
        state = lf.cell_state(reports=h, transmitters=r.wspr_tx, receivers=r.receivers, reaching=n)
        act, wd = int(active.get(key, 0)), int(with_dest.get(key, 0))
        run = running.get(key, True if activation else None)
        applicable, why = lf.rbn_applicability(mode_in.get(key, session_mode), run)
        rbn_n = int(rbn_dest.get(key, 0))
        rbn_state = (lf.NOT_APPLICABLE if not applicable else lf.UNAVAILABLE if not rbn_ok else lf.EVIDENCE if rbn_n else lf.NO_REPORTS)
        conclusion, text = conclude(state, act, wd, where, r.band)
        rows.append({"panel": r.panel, "slot": r.slot, "band": r.band, "worked": r.worked, "window_start": r.window_start, "window_end": r.window_end,
                     "shared_min": r.shared_min, "wspr_tx": r.wspr_tx, "receivers": r.receivers, "heard": h, "good": g, "n": n, "state": state,
                     "active": act, "with_dest": wd, "rbn_state": rbn_state, "rbn_n": rbn_n, "rbn_why": "" if applicable else why,
                     "key": conclusion, "text": text})
    out = pd.DataFrame(rows, columns=["panel", "slot", "band", "worked", "window_start", "window_end", "shared_min", "wspr_tx", "receivers", "heard",
                                      "good", "n", "state", "active", "with_dest", "rbn_state", "rbn_n", "rbn_why", "key", "text"])
    out.attrs.update(view=view, dest=dest, min_km=min_km, metric=metric, where=where, bin_min=bin_min, power_w=grid.attrs.get("power_w"))
    return out


# ------------------------------------------------------------------------------------------------- the summary

def _num(n):
    return "none" if n == 0 else str(n)


def _s(n, word):
    return f"{n} {word}" + ("" if n == 1 else "es" if word.endswith("x") else "s")


def rbn_line(cells):
    """One sentence on RBN for the whole grid: how many of the boxes in which it applies had a skimmer in the destination spot you, or why RBN
    does not apply, or that its spots were not available. Empty when there are no cells."""
    if cells.empty:
        return ""
    where = cells.attrs.get("where") or where_forms("sector", None)
    rbn = cells[cells["rbn_state"].isin([lf.EVIDENCE, lf.NO_REPORTS])]
    if len(rbn):
        spotted = int((rbn["rbn_state"] == lf.EVIDENCE).sum())
        return (f"RBN skimmers {where['skimmers']} spotted you in {_num(spotted)} of the {_s(len(rbn), 'box')} in which RBN applies. "
                "RBN has few skimmers, so a box without one says little.")
    if cells["rbn_state"].eq(lf.NOT_APPLICABLE).all():
        why = next((w for w in cells["rbn_why"] if w), "")
        return "RBN not applicable or unknown for this session." + (f" {why}" if why else "")
    if cells["rbn_state"].eq(lf.UNAVAILABLE).any():
        return "RBN spots were not available, so nothing is said about them."
    return ""


def openings_headline(cells):
    """One sentence that leads the section: over the boxes of the bands you worked, in how many WSPR showed a path to the destination, in how many
    you were active, and in how many you logged a contact with it. Built only from those counts, and checked against UNSUPPORTED."""
    worked = cells[cells["worked"].astype(bool)]
    if worked.empty:
        return ""
    where = cells.attrs.get("where") or where_forms("sector", None)
    n, path, active, contact = len(worked), int((worked["state"] == lf.EVIDENCE).sum()), int((worked["active"] > 0).sum()), int((worked["with_dest"] > 0).sum())
    text = (f"Looking at {where['to']}: WSPR showed a path in {_num(path)} of {_s(n, 'box')} on the bands you worked. "
            f"You were active in {_num(active)} of the {n} and logged a contact with {where['with']} in {_num(contact)}.")
    assert not unsupported_claims(text), unsupported_claims(text)
    return text


OPENINGS_COLUMNS = ["Band", "Boxes", "You were active", "WSPR path", "Contact there", "Path and contact", "Too little WSPR"]


def openings_table(cells, max_not_worked=3):
    """The summary as a small table, one row for each band: how many boxes, in how many you were active, in how many WSPR showed a path to the
    destination, in how many you logged a contact with it, in how many both, and in how many there was too little WSPR to say. Bands you worked
    come first, highest band first; a band you did not work gets a row only when WSPR showed a path on it, and at most `max_not_worked` do."""
    if cells.empty:
        return pd.DataFrame(columns=OPENINGS_COLUMNS)
    rows, idle = [], 0
    for band in lc.bands_top_down(pd.DataFrame({"band": cells["band"].unique()})):
        d = cells[cells["band"] == band]
        worked = bool(d["worked"].iloc[0])
        path = int((d["state"] == lf.EVIDENCE).sum())
        if not worked:
            if not path or idle >= max_not_worked:
                continue
            idle += 1
        rows.append({"Band": band + ("" if worked else " (not worked)"), "Boxes": len(d), "You were active": int((d["active"] > 0).sum()), "WSPR path": path,
                     "Contact there": int((d["with_dest"] > 0).sum()), "Path and contact": int((d["key"] == BOTH).sum()),
                     "Too little WSPR": int(d["state"].isin([lf.SPARSE, lf.UNAVAILABLE]).sum())})
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["Band"].endswith("(not worked)"), i))
    return pd.DataFrame([rows[i] for i in order], columns=OPENINGS_COLUMNS)


def openings_summary(cells, max_not_worked=3):
    """The summary as a list of sentences, built only from the counts in `cells` (opening_cells' table) and checked against UNSUPPORTED. Bands
    you worked come first, each in one sentence: how many boxes you were active in, how many showed a path, and in how many of those you
    logged a contact with the destination. A band you did not work is mentioned only when WSPR showed a path on it."""
    if cells.empty:
        return []
    where = cells.attrs.get("where") or where_forms("sector", None)
    lines, shown_idle = [], 0
    for band in lc.bands_top_down(pd.DataFrame({"band": cells["band"].unique()})):
        d = cells[cells["band"] == band]
        n_boxes, active = len(d), int((d["active"] > 0).sum())
        path = int((d["state"] == lf.EVIDENCE).sum())
        both, contact_only = int((d["key"] == BOTH).sum()), int((d["key"] == CONTACT_NO_PATH).sum())
        thin = int(d["state"].isin([lf.SPARSE, lf.UNAVAILABLE]).sum())
        if active:
            text = (f"{band}: of {_s(n_boxes, 'box')}, you were active in {_num(active)} and WSPR showed a path to {where['to']} in {_num(path)}.")
            if path:
                text += f" You logged a contact with {where['with']} in {_num(both)} of the {path} with a path."
            if contact_only:
                text += f" In {_s(contact_only, 'other box')} you logged a contact with {where['with']} although WSPR showed no path then."
        elif path and shown_idle < max_not_worked:
            shown_idle += 1
            text = f"{band}: you logged no contact on it. Of {_s(n_boxes, 'box')}, WSPR showed a path to {where['to']} in {path}."
        else:
            continue
        if thin:
            text = text.rstrip() + f" {_s(thin, 'box')} had too little WSPR behind it to say either way."
        lines.append(text)
    rbn = rbn_line(cells)
    if rbn:
        lines.append(rbn)
    for line in lines:
        bad = unsupported_claims(line)
        assert not bad, f"an unsupported claim got into the summary: {bad}"
    return lines


# ------------------------------------------------------------------------------------------------- the evidence behind one box

def cell_evidence(grid, log, places, spots, locs, wspr_for, home, band, slot, view="sector", dest=None, min_km=lc.DX_KM, rbn_ok=True):
    """Everything behind one box (a band in one time bin), for the page's 'look at one box': the window, the coverage, the WSPR transmitters near
    you with their distances, the receivers in the destination with the times they decoded and whether they looked strong enough, all of your
    RBN spots on the band in that box (each marked as from a skimmer in the destination or not: most are from nearby skimmers), and your contacts. `wspr_for(start, end)` gives the WSPR spots between two times, as the grid was made with."""
    bin_min = grid.attrs.get("bin_min", lc.CONDITIONS_SLOT_MIN)
    mode, power_w = grid.attrs.get("mode", "CW"), grid.attrs.get("power_w", 100.0)
    start, end = lf.wspr_window(slot, bin_min)
    wspr = wspr_for(start, end)
    wspr = wspr[(wspr["time"] > start) & (wspr["time"] <= end) & (wspr["band"] == band)] if len(wspr) else wspr
    coverage = lf.coverage(wspr)
    out = {"window": (start, end), "bin": lf.bin_bounds(slot, bin_min), "coverage": coverage,
           "state": lf.cell_state(reports=coverage["reports"], transmitters=coverage["transmitters"], receivers=coverage["receivers"], reaching=0)}

    if len(wspr):
        tx = wspr.groupby("tx").agg(lat=("tx_lat", "median"), lon=("tx_lon", "median"), reports=("snr", "size"), first=("time", "min"), last=("time", "max"))
        tx["km"] = [Geodesic.WGS84.Inverse(home[0], home[1], la, lo)["s12"] / 1000 for la, lo in zip(tx["lat"], tx["lon"])]
        transmitters = tx.reset_index().sort_values("km")[["tx", "km", "reports", "first", "last"]]
    else:
        transmitters = pd.DataFrame(columns=["tx", "km", "reports", "first", "last"])
    out["transmitters"] = transmitters.rename(columns={"tx": "Transmitter", "km": "Km from you", "reports": "Reports", "first": "First report", "last": "Last report"})

    receivers = pd.DataFrame(columns=["Receiver", "Direction", "Km from you", "Looked strong enough", "First decode", "Last decode", "Reports"])
    if len(wspr):
        res = cond.analyze(wspr, home, power_w, mode, end.to_pydatetime(), lc.LOOKBACK_MIN, 0.0, 3.0)
        rec = res["receivers"]
        if len(rec):
            rec = rec.assign(sector=rec["bearing"].map(lf.sector_of), continent=rec["region"].map(lf.continent_of_region))
            times = wspr.groupby("rx")["time"].agg(["min", "max"])
            rec = rec[_within(rec, view, dest, min_km)].sort_values("km", ascending=False)
            receivers = pd.DataFrame({
                "Receiver": rec["rx"].tolist(), "Direction": [lf.SECTOR_NAMES.get(s, "") for s in rec["sector"]], "Km from you": rec["km"].round().astype(int).tolist(),
                "Looked strong enough": ["yes" if v == "good" else "no" for v in rec["verdict"]],
                "First decode": [times.at[r, "min"] for r in rec["rx"]], "Last decode": [times.at[r, "max"] for r in rec["rx"]], "Reports": rec["reports"].tolist()})
    out["receivers"] = receivers

    rbn = pd.DataFrame(columns=["Time", "Skimmer", "Km from you", "Direction", "SNR", "In the destination"])
    if rbn_ok and spots is not None and len(spots):
        sk = skimmer_table(spots, locs, home)
        sp = spots[(spots["band"] == band) & (lf.bin_floor(spots["time"], bin_min) == slot)].merge(sk, on="spotter", how="left").sort_values("time")
        inside = _within(sp, view, dest, min_km) if len(sp) else pd.Series(dtype=bool)
        rbn = pd.DataFrame({"Time": sp["time"].tolist(), "Skimmer": sp["spotter"].tolist(),
                            "Km from you": [int(round(k)) if pd.notna(k) else None for k in sp["km"]],
                            "Direction": [lf.SECTOR_NAMES.get(x, "") if isinstance(x, str) else "" for x in sp["sector"]],
                            "SNR": sp["snr"].round().astype(int).tolist(), "In the destination": ["yes" if i else "no" for i in inside]})
    out["rbn"] = rbn

    pl = places[(places["band"] == band) & (lf.bin_floor(places["time"], bin_min) == slot)].sort_values("time")
    with_it = _within(pl, view, dest, min_km, sector_col="sector_whole", km_col="c_km") if len(pl) else pd.Series(dtype=bool)
    out["qsos"] = pd.DataFrame({
        "Time": pl["time"].tolist(), "Call": pl["call"].tolist(), "Mode": pl["mode"].tolist(),
        "Km from you": [int(round(k)) if pd.notna(k) else None for k in pl["c_km"]],
        "Direction": [lf.SECTOR_NAMES.get(s, "") if isinstance(s, str) else "" for s in pl["sector"]],
        "Placed by": [{"grid": "its grid", "park": "its park", "summit": "its summit", "coords": "its logged coordinates", "home": "its station profile", "area": "its call area", "state": "its state", "country": "its country"}.get(s, "") for s in pl["c_source"]],
        "With the destination": ["yes" if w else "no" for w in with_it]})
    return out


# ------------------------------------------------------------------------------------------------- the band timeline

LANES = ("EU", "AF", "AS", "OC", "SA")      # the distant continents for a station in North America, in the order they are drawn
CONTINENT_LANES = ("EU", "AF", "AS", "OC", "SA", "NA")
REGIONAL_MIN_KM = 500                      # the regional picture starts beyond the reach of a ground wave and a short skip, and ends where the DX picture begins
LANE_COLOURS = {"EU": "#2a78d6", "AF": "#eb6834", "AS": "#1baf7a", "OC": "#6250d6", "SA": "#e87ba4", "NA": "#c9a227",
                "N": "#2a78d6", "NE": "#1baf7a", "E": "#c9a227", "SE": "#eb6834", "S": "#e87ba4", "SW": "#6250d6", "W": "#20a6b8", "NW": "#8a8f98"}
REACH = {"dx": "DX: distant continents", "regional": "Regional: by direction"}
NO_PATHS = "No distant-continent paths in the nearby WSPR."
NO_PATHS_REGIONAL = "No paths at regional distances in the nearby WSPR."


def lane_set(reach="dx", home_cont="NA"):
    """The lanes of the band cards: (codes in drawing order, {code: name}, {code: colour}, the word for one, the table column that holds it).
    DX is the other continents (never the one you are on, so a station in Europe has North America as a destination); regional is the eight compass
    directions, for stations from REGIONAL_MIN_KM out to where DX begins."""
    if reach == "regional":
        codes = lf.SECTORS
        return codes, {c: f"the {lf.SECTOR_NAMES[c].lower()}" for c in codes}, {c: LANE_COLOURS[c] for c in codes}, "direction", "sector"
    codes = tuple(c for c in CONTINENT_LANES if c != (home_cont or "NA"))
    return codes, {c: lf.CONTINENT_NAMES[c] for c in codes}, {c: LANE_COLOURS[c] for c in codes}, "continent", "continent"


def _cap(text):
    return text[:1].upper() + text[1:]
ACTIVITY_GAP_MIN = 15                      # a pause this long between two contacts on a band ends one stretch of logged activity and starts the next


def _join(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _ranges(starts, step):
    """Time bins that follow each other as windows ('20:00-21:00 and 21:30-22:30'), given the bins' start times."""
    runs = []
    for t in sorted(starts):
        if runs and t == runs[-1][1] + step:
            runs[-1][1] = t
        else:
            runs.append([t, t])
    return " and ".join(f"{a:%H:%M}\u2013{b + step:%H:%M}" for a, b in runs)


def activity_spans(times, gap_min=ACTIVITY_GAP_MIN):
    """The stretches of logged activity on one band: [(first, last, contacts)], a new stretch starting after a pause of more than `gap_min` minutes.
    The log holds only contacts, so a stretch says when contacts were logged, not when you were listening, resting or calling without an answer."""
    spans, gap = [], pd.Timedelta(minutes=gap_min)
    for t in sorted(pd.Timestamp(x) for x in times):
        if spans and t - spans[-1][1] <= gap:
            spans[-1][1], spans[-1][2] = t, spans[-1][2] + 1
        else:
            spans.append([t, t, 1])
    return [tuple(s) for s in spans]


def _when(bins, contact_times, step):
    """How the bins in which WSPR showed a path to a continent sit against the times you worked it: 'at the time' when a path bin is the contact's own
    bin or the one next to it (neighbouring bins share most of their hour of WSPR), else 'later', 'earlier' or 'at other times' than every contact."""
    floor = f"{max(int(step.total_seconds() // 60), 1)}min"
    near = [any(abs(pd.Timestamp(t).floor(floor) - b) <= step for b in bins) for t in contact_times]
    if all(near):
        return "at the time"
    if any(near):
        return "at the time of some"
    last, first = max(contact_times), min(contact_times)
    if all(b > last for b in bins):
        return "later"
    if all(b < first for b in bins):
        return "earlier"
    return "at other times"


def band_finding(band, opened, own_bins, elsewhere, worked, n_contacts, first, step, rbn_cont=(), names=None, activity=None):
    """The finding for a band card, in cautious words: for each distant continent, what your log shows and what the nearby WSPR showed, and when,
    so a path that appeared hours from a contact is never read as support for it.
    opened     {continent code: [bin starts in which WSPR showed a path there]}
    own_bins   the bins in which this band has logged contacts
    elsewhere  {bin start: [other bands with logged contacts in it]}
    worked     [(time, call, continent code)] contacts with the distant continents on this band
    rbn_cont   the continents in which an RBN skimmer spotted you on this band (only where RBN applies)
    names      {lane code: name}, the continents unless the lanes are directions
    activity   {'reports', 'receivers'}: the WSPR near you on this band in the windows of your contacts, anywhere in the world, so a destination with no path can say whether
               WSPR was quiet on the band or only silent there"""
    names = names or lf.CONTINENT_NAMES
    when_worked = {}
    for t, _, c in worked:
        when_worked.setdefault(c, []).append(t)
    text, outside_times = "", set()
    if when_worked:
        at_time = [c for c, ts in when_worked.items() if opened.get(c) and _when(opened[c], ts, step) in ("at the time", "at the time of some")]
        other_time = [c for c in when_worked if opened.get(c) and c not in at_time]
        no_path = [c for c in when_worked if not opened.get(c)]
        if no_path:
            where = _join(names[c] for c in no_path)
            if activity and activity.get("reports"):
                text += (f"Worked {where}. WSPR was active on {band} then ({activity['reports']:,} reports from {activity['receivers']} receivers), "
                         f"but none of the receivers there decoded the stations near you.")
            elif activity is not None:
                text += f"Worked {where}. There were no nearby WSPR reports on {band} then."
            else:
                text += f"Worked {where}. No corresponding nearby WSPR reports in the selected window."
        if at_time:
            text += (" " if text else "") + f"Worked {_join(names[c] for c in at_time)}; nearby WSPR showed a path there at the time."
        for c in other_time:
            text += (" " if text else "") + f"Worked {names[c]} at {_join(f'{t:%H:%M}' for t in when_worked[c][:3])}{' and others' if len(when_worked[c]) > 3 else ''}; "                     f"nearby WSPR showed a path there {_when(opened[c], when_worked[c], step)} ({_ranges(opened[c], step)})."
        spotted = [names[c] for c in when_worked if c in rbn_cont]
        if spotted:
            text += f" RBN skimmers in {_join(spotted)} also spotted you."
    not_worked = {c: v for c, v in opened.items() if c not in when_worked}
    outside = {c: [t for t in v if t not in own_bins] for c, v in not_worked.items()}
    outside = {c: v for c, v in outside.items() if v}
    if outside:
        groups = {}
        for c, v in outside.items():
            groups.setdefault(_ranges(v, step), []).append(c)
        paths = "; ".join(f"{_join(names[c] for c in cs)} paths appeared {rng}" for rng, cs in groups.items())
        paths = _cap(paths)                                    # only the first of several is the start of the sentence
        times = sorted({t for v in outside.values() for t in v})
        others = sorted({b for t in times for b in elsewhere.get(t, [])}, key=lambda b: lc._rank(b), reverse=True)
        text += (" " if text else "") + (f"{paths}; you logged no contact on {band}." if n_contacts == 0 else f"{paths}, outside your logged activity on {band}.")
        text += (f" Your log shows {_join(others)} activity then." if others else " Your log shows no contacts then.")
        if 0 < n_contacts <= 3 and not when_worked:              # a count only helps when it is small enough to be the point
            text += f" Your log has {n_contacts} {band} contact{'s' if n_contacts != 1 else ''}" + (f", at {first:%H:%M} UTC." if n_contacts == 1 else ".")
    elif not_worked:
        text += (" " if text else "") + f"{_cap(_join(names[c] for c in not_worked))} paths appeared during your logged activity on {band}; you logged no contact there."
    return text or NO_PATHS


def timeline_headline(panels, names=None, reach="dx"):
    """One plain sentence for the top of the band cards, from the cards alone: who you worked in the other continents (or, for the regional picture, in
    which directions), and the bands on which WSPR near you showed a path there at times when your log shows no contact on that band. Checked against
    UNSUPPORTED."""
    cards = [c for p in panels for c in p["cards"]]
    if not cards:
        return ""
    names = names or lf.CONTINENT_NAMES
    regional = reach == "regional"
    worked = {}
    for c in cards:
        for call, cont in c["worked"]:
            worked.setdefault(cont, set()).add(call)
    n = len({call for v in worked.values() for call in v})
    outside = [c["band"] for c in cards if c["outside"]]
    path_where = "at regional distances" if regional else "to a distant continent"
    if worked:
        place = f"toward {_join(names[c] for c in worked)}" if regional else f"in {_join(names[c] for c in worked)}"
        parts = [f"You worked {n} station{'s' if n != 1 else ''} {place}."]
    else:
        parts = [f"You logged no contact {'at regional distances' if regional else 'with a distant continent'}."]
    if outside:
        parts.append(f"WSPR near you showed a path {path_where} on {_join(outside)} at times when your log has no contact on that band.")
    elif not any(c["opened"] for c in cards):
        parts.append(f"WSPR near you showed no path {path_where} on the bands you worked.")
    text = " ".join(parts)
    assert not unsupported_claims(text), unsupported_claims(text)
    return text


def band_timeline(grid, log, places, spots, locs, home, min_km=lc.DX_KM, metric="good", rbn_ok=True, only=None, reach="dx", home_cont="NA"):
    """The data for the band-by-band timeline: one entry for each stretch of the log (a panel of the grid) and, in it, one card for each band you
    worked, highest band first (a fixed order), then one for each band you did not work on which the nearby WSPR showed a path. A card holds, on the same
    time axis:
      lanes       for each destination (see lane_set: the other continents, or the eight compass directions for the regional picture), the receivers
                  there in each time bin: `n` by the view's metric (`heard` decoded WSPR near you; `good` also looked strong enough for you). One
                  receiver is thin evidence, not a weak signal, so the page draws 1 pale and 2 or more solid, and shows the count when asked;
      thin        the bins in which there was too little WSPR near you to say anything at all;
      spans       the stretches of logged activity on the band (see activity_spans);
      contacts    your contacts on the band, those with a destination marked (the same distance rule as the receivers and the skimmers);
      rbn         for each destination and bin, the skimmers there that spotted you, only where RBN applies (see opening_cells);
      finding, worked   the finding in words, and the calls worked at the destinations; `worked_band` is False for a band you did not work.
    `only` limits the lanes to one destination code. DX counts stations `min_km` or more away; regional counts those from REGIONAL_MIN_KM to DX_KM.
    Bands with nothing to show are named in `idle`."""
    bin_min = grid.attrs.get("bin_min", lc.CONDITIONS_SLOT_MIN)
    step = pd.Timedelta(minutes=bin_min)
    codes, names, colours, word, col = lane_set(reach, home_cont)
    lo_km, hi_km = (min_km, float("inf")) if reach == "dx" else (REGIONAL_MIN_KM, lc.DX_KM)
    rec = grid.attrs.get("receivers")
    if rec is None or len(rec) == 0:
        rec = pd.DataFrame(columns=["slot", "band", "km", "continent", "sector", "verdict"])
    rec = rec[(rec["km"] >= lo_km) & (rec["km"] < hi_km)]
    per_bin = {}
    for (slot, band, lane), g in rec.groupby(["slot", "band", col]):
        per_bin[(slot, band, lane)] = {"heard": int(len(g)), "good": int((g["verdict"] == "good").sum())}
    states = {(r.slot, r.band): r.state for r in grid.itertuples()}
    cells = opening_cells(grid, log, places, spots, locs, home, "continent", None, min_km, metric, rbn_ok)
    rbn_state = {(r.slot, r.band): (r.rbn_state, r.rbn_why) for r in cells.itertuples()}
    rbn_who = {}
    if rbn_ok and spots is not None and len(spots):
        sk = skimmer_table(spots, locs, home)
        sp = spots.assign(slot=lf.bin_floor(spots["time"], bin_min)).merge(sk, on="spotter")
        sp = sp[(sp["km"] >= lo_km) & (sp["km"] < hi_km)]
        for (slot, band, lane), g in sp.groupby(["slot", "band", col]):
            rbn_who[(slot, band, lane)] = sorted(set(g["spotter"]))
    pl = places.assign(slot=lf.bin_floor(places["time"], bin_min))
    panels, carded, idle = [], set(), []

    def card_for(band, mine, slots, elsewhere):
        own_bins = set(mine["slot"])
        used = set(mine[col][(mine["c_km"] >= lo_km) & (mine["c_km"] < hi_km)]) if len(mine) else set()      # the destinations you worked on this band
        lanes = {}
        for c in codes:
            if only and c != only:
                continue
            row = [per_bin.get((s, band, c), {"heard": 0, "good": 0}) for s in slots]
            row = [{"heard": 0, "good": 0} if states.get((s, band)) == lf.SPARSE else r for s, r in zip(slots, row)]       # too little WSPR: no bar, the card marks it
            ns = [r["good"] if metric == "good" else r["heard"] for r in row]
            spotted = any(rbn_who.get((s, band, c)) and rbn_state.get((s, band), ("", ""))[0] in (lf.EVIDENCE, lf.NO_REPORTS) for s in slots)
            if any(ns) or spotted or only or (reach == "regional" and c in used):          # in the directions picture a contact is drawn in its own lane
                lanes[c] = [{"slot": s, "n": n, "heard": r["heard"], "good": r["good"],
                             "rbn": rbn_who.get((s, band, c), []) if rbn_state.get((s, band), (lf.NOT_APPLICABLE, ""))[0] in (lf.EVIDENCE, lf.NO_REPORTS) else []}
                            for s, n, r in zip(slots, ns, row)]
        opened = {c: [x["slot"] for x in v if x["n"] >= 1] for c, v in lanes.items()}
        opened = {c: v for c, v in opened.items() if v}
        if not len(mine) and not opened:
            return None                                                # a band you did not work gets a card only when there is a path to show
        steady = []
        if reach == "regional":
            # Close to home a path is nearly always there, so a lane that never changes says nothing a sentence does not say better. A lane that stays open from the
            # first bin to the last, with no contact and no skimmer in it, is left off the chart and named in one line; a lane that changes, or has you in it, is drawn.
            for c, v in list(lanes.items()):
                judged = [x for x, s_ in zip(v, slots) if states.get((s_, band)) != lf.SPARSE]
                if judged and all(x["n"] >= 1 for x in judged) and c not in used and not any(x["rbn"] for x in v):
                    steady.append(c)
                    del lanes[c]
                    opened.pop(c, None)
        contacts = [{"time": t, "call": call, "cont": (c if c in codes and lo_km <= km < hi_km else ""), "km": km}      # the same distance rule as the WSPR and the skimmers
                    for t, call, c, km in zip(mine["time"], mine["call"], mine[col], mine["c_km"])]
        worked = [(c["time"], c["call"], c["cont"]) for c in contacts if c["cont"] and (not only or c["cont"] == only)]
        first = mine["time"].iloc[0] if len(mine) else None
        rbn_cont = {c for c, v in lanes.items() if any(x["rbn"] for x in v)}
        act = grid[(grid["band"] == band) & grid["slot"].isin(own_bins)] if len(own_bins) else grid.iloc[0:0]
        activity = {"reports": int(act["wspr_reports"].max()) if len(act) else 0, "receivers": int(act["receivers"].max()) if len(act) else 0} if len(mine) else None
        finding = band_finding(band, opened, own_bins, elsewhere, worked, len(mine), first, step, rbn_cont, names, activity)
        if reach == "regional" and finding == NO_PATHS:
            finding = NO_PATHS_REGIONAL
        if steady:
            line = f"Paths stayed open the whole time toward {_join(names[c] for c in steady)}."
            finding = line if finding in (NO_PATHS, NO_PATHS_REGIONAL) else f"{finding} {line}"
        assert not unsupported_claims(finding), unsupported_claims(finding)
        worked_c = {c for _, _, c in worked}
        outside = any(t not in own_bins for c, v in opened.items() if c not in worked_c for t in v)
        return {"band": band, "worked_band": bool(len(mine)), "steady": steady, "lanes": lanes, "opened": opened, "outside": outside,
                "thin": [s for s in slots if states.get((s, band)) == lf.SPARSE], "spans": activity_spans(mine["time"]), "contacts": contacts, "finding": finding, "activity": activity,
                "worked": list(dict.fromkeys((call, cont) for _, call, cont in worked)),
                "rbn_why": next((rbn_state[(s, band)][1] for s in slots if rbn_state.get((s, band), ("", ""))[1]), "")}

    for panel, gp in grid.groupby("panel"):
        slots = sorted(gp["slot"].unique())
        lo_t, hi_t = slots[0], slots[-1] + step
        here = pl[(pl["time"] >= lo_t) & (pl["time"] < hi_t)]
        bands = lc.bands_top_down(here) if len(here) else []
        elsewhere = {}
        for (slot, band), g in here.groupby(["slot", "band"]):
            elsewhere.setdefault(slot, []).append(band)
        cards = []
        for band in bands:
            card = card_for(band, here[here["band"] == band].sort_values("time"), slots, elsewhere)
            cards.append(card)
            carded.add(band)
        for band in lc.bands_top_down(gp):                      # bands you did not work, with a path to show, after the ones you did
            if band not in bands:
                card = card_for(band, here.iloc[0:0], slots, elsewhere)
                if card:
                    cards.append(card)
                    carded.add(band)
        panels.append({"panel": panel, "slots": slots, "bin_min": bin_min, "cards": cards})
    for band in lc.bands_top_down(grid):
        if band not in carded:
            d = grid[grid["band"] == band]
            has_path = any(v["good" if metric == "good" else "heard"] > 0 for (_, b2, _), v in per_bin.items() if b2 == band)
            idle.append((band, "path" if has_path else "thin" if (d["state"] == lf.SPARSE).any() else "none"))
    return {"headline": timeline_headline(panels, names, reach), "panels": panels, "idle": idle, "metric": metric, "min_km": min_km, "only": only, "bin_min": bin_min,
            "power_w": grid.attrs.get("power_w"), "mode": grid.attrs.get("mode", "CW"), "rbn_line": rbn_line(cells),
            "reach": reach, "lane_order": list(codes), "lane_names": names, "lane_colours": colours, "lane_word": word}


# ------------------------------------------------------------------------------------------------- the destination view

STRIP_MIN = 15      # the 'you were on' strip names the band with the most contacts in each quarter hour


def _band_runs(contacts, start, end, strip_min=STRIP_MIN):
    """Runs of the band you were on, for the strip above the lanes: [(from, to, band or None)] over [start, end), the band with the most contacts in each
    `strip_min` minutes, runs of the same band joined, None where no contact was logged."""
    if not contacts:
        return [(start, end, None)]
    d = pd.DataFrame(contacts, columns=["time", "band"])
    d["slot"] = pd.to_datetime(d["time"]).dt.floor(f"{strip_min}min")
    q = d.groupby(["slot", "band"]).size().reset_index(name="n").sort_values(["slot", "n"], ascending=[True, False]).drop_duplicates("slot").set_index("slot")["band"]
    runs = []
    for s in pd.date_range(start.floor(f"{strip_min}min"), end - pd.Timedelta(minutes=strip_min), freq=f"{strip_min}min"):
        b, e = q.get(s), s + pd.Timedelta(minutes=strip_min)
        if runs and runs[-1][2] == b:
            runs[-1] = (runs[-1][0], e, b)
        else:
            runs.append((s, e, b))
    return runs


def _rbn_only_line(band, name):
    text = f"RBN skimmers in {name} spotted you on {band}; the nearby WSPR showed no path there and you logged no contact with {name} on {band}."
    assert not unsupported_claims(text), unsupported_claims(text)
    return text


def destination_views(tl, max_lines=3):
    """The band timeline (band_timeline, every destination) turned round: one view for each destination that has something to show, which is a path in the
    nearby WSPR, an RBN skimmer there that spotted you, or a contact with it. Returns (views, empty): `views` ordered with the destination you worked most
    first, then by the bands that had a path; `empty` the destinations with nothing, in order. A view holds `code`, `name`, `contacts`, `paths` (bands with a
    path), `rbn` and, for each stretch of the log, the strip of the band you were on, a lane for each band that has something to show and the lines worth a
    look: what the page already says for a band, but for this destination alone, so a contact at 17:25 is never read as backed by a path at noon."""
    names, codes = tl["lane_names"], tl["lane_order"]
    views = {c: {"code": c, "name": names[c], "contacts": 0, "paths": 0, "rbn": False, "panels": []} for c in codes}
    for panel in tl["panels"]:
        slots, step = panel["slots"], pd.Timedelta(minutes=panel["bin_min"])
        start, end = slots[0], slots[-1] + step
        every = [(pd.Timestamp(k["time"]), card["band"]) for card in panel["cards"] for k in card["contacts"]]
        runs = _band_runs(every, start, end)
        floor = f"{panel['bin_min']}min"
        elsewhere = {}
        for t, b in every:
            elsewhere.setdefault(t.floor(floor), set()).add(b)
        elsewhere = {t: sorted(bs, key=lc._rank, reverse=True) for t, bs in elsewhere.items()}
        for c in codes:
            lanes, lines = [], []
            for card in sorted(panel["cards"], key=lambda x: lc._rank(x["band"]), reverse=True):
                bins = card["opened"].get(c, [])
                mine = [k for k in card["contacts"] if k["cont"] == c]
                rbn_bins = [x["slot"] for x in card["lanes"].get(c, []) if x["rbn"]]
                if not (bins or mine or rbn_bins):
                    continue
                own = {pd.Timestamp(k["time"]).floor(floor) for k in card["contacts"]}
                first = min((pd.Timestamp(k["time"]) for k in card["contacts"]), default=None)
                cells = card["lanes"].get(c, [])
                lanes.append({"band": card["band"], "cells": [{"slot": x["slot"], "n": x["n"], "rbn": bool(x["rbn"])} for x in cells],
                              "contacts": [{"time": k["time"], "call": k["call"]} for k in mine], "worked_band": card["worked_band"]})
                if bins or mine:
                    text = band_finding(card["band"], {c: bins} if bins else {}, own, elsewhere, [(k["time"], k["call"], c) for k in mine], len(card["contacts"]), first, step,
                                        {c} if rbn_bins else (), names, card.get("activity"))
                else:
                    text = _rbn_only_line(card["band"], names[c])
                outside = len([t for t in bins if t not in own])
                at_time = bool(mine and bins and _when(bins, [pd.Timestamp(k["time"]) for k in mine], step).startswith("at the time"))
                cb = pd.Timestamp(mine[0]["time"]).floor(floor) if mine else None          # the window the details should open on: where a path was nearest your contact, else the first path
                focus = (min(bins, key=lambda t: abs(pd.Timestamp(t) - cb)) if bins else cb) if cb is not None else (bins[0] if bins else rbn_bins[0])
                lines.append((0 if at_time else 1 if mine else 2, -outside, -len(bins), lc._rank(card["band"]) * -1, card["band"], text, focus))
                v = views[c]
                v["contacts"] += len(mine)
                v["paths"] += 1 if bins else 0
                v["rbn"] = v["rbn"] or bool(rbn_bins)
            lines.sort()
            views[c]["panels"].append({"panel": panel["panel"], "slots": slots, "bin_min": panel["bin_min"], "strip": runs, "lanes": lanes,
                                       "lines": [(x[4], x[5]) for x in lines[:max_lines]],
                                       "focus": (lines[0][4], pd.Timestamp(lines[0][6])) if lines else None})
    shown = [v for v in views.values() if v["contacts"] or v["paths"] or v["rbn"]]
    shown.sort(key=lambda v: (-v["contacts"], -v["paths"], not v["rbn"]))
    empty = [v["name"] for c in codes for v in [views[c]] if not (v["contacts"] or v["paths"] or v["rbn"])]
    return shown, empty


def destination_badge(view):
    """The short note on a destination's tab: how many contacts, RBN, or 'paths only'."""
    parts = []
    if view["contacts"]:
        parts.append(f"{view['contacts']} contact{'s' if view['contacts'] != 1 else ''}")
    if view["rbn"]:
        parts.append("RBN")
    return " · ".join(parts) if parts else "paths only"


def inside_limit_note(places, home_cont, min_km):
    """A sentence naming the countries you worked on another continent that were nearer than the distance rule, so they are not counted as DX (the answer to 'why is
    my contact missing?'). Empty when there are none."""
    if places is None or len(places) == 0 or not min_km:
        return ""
    d = places[places["continent"].isin(lf.CONTINENT_NAMES) & (places["continent"] != (home_cont or "NA")) & (places["c_km"] < min_km)]
    if d.empty:
        return ""
    from rbn_data import country_location
    named = []
    for call in dict.fromkeys(d.sort_values("c_km")["call"]):             # by callsign, with the country its prefix says (a log's own COUNTRY field can be wrong)
        guess = country_location(call)
        named.append(f"{call} ({guess[2]})" if guess and guess[2] else call)
    shown = ", ".join(named[:4]) + (f" and {len(named) - 4} more" if len(named) > 4 else "")
    return f"Inside the {min_km * 0.621371:,.0f} mile limit, so not counted as DX: {shown}."
