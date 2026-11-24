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
        "Placed by": [{"grid": "its grid", "state": "its state", "country": "its country"}.get(s, "") for s in pl["c_source"]],
        "With the destination": ["yes" if w else "no" for w in with_it]})
    return out


# ------------------------------------------------------------------------------------------------- the band timeline

LANES = ("EU", "AF", "AS", "OC", "SA")      # the distant continents, in the order they are drawn
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


def band_finding(band, opened, own_bins, elsewhere, worked, n_contacts, first, step, rbn_cont=()):
    """The one useful finding for a band card, in cautious words, and the list of contacts with the distant continents.
    opened     {continent code: [bin starts in which WSPR showed a path there]}
    own_bins   the bins in which this band has logged contacts
    elsewhere  {bin start: [other bands with logged contacts in it]}
    worked     [(time, call, continent code)] contacts with the distant continents on this band
    rbn_cont   the continents in which an RBN skimmer spotted you on this band (only where RBN applies)"""
    names = lf.CONTINENT_NAMES
    if worked:
        got = _join(dict.fromkeys(names[c] for _, _, c in worked))
        with_path = {c for _, _, c in worked if opened.get(c)}
        text = f"Worked {got}."
        if not with_path:
            text += " No corresponding nearby WSPR reports in the selected window."
        elif len(with_path) < len({c for _, _, c in worked}):
            text += " Nearby WSPR showed a path to some of them."
        else:
            text += " Nearby WSPR also showed a path there."
        spotted = [names[c] for c in dict.fromkeys(c for _, _, c in worked) if c in rbn_cont]
        if spotted:
            text += f" RBN skimmers in {_join(spotted)} also spotted you."
        return text
    outside = {c: [t for t in bins if t not in own_bins] for c, bins in opened.items()}
    outside = {c: v for c, v in outside.items() if v}
    if outside:
        times = sorted({t for v in outside.values() for t in v})
        others = sorted({b for t in times for b in elsewhere.get(t, [])}, key=lambda b: lc._rank(b), reverse=True)
        text = f"{_join(names[c] for c in outside)} paths appeared {_ranges(times, step)}, outside your logged activity on {band}."
        text += (f" Your log shows {_join(others)} activity then." if others else " Your log shows no contacts then.")
        if n_contacts <= 3:                  # a count only helps when it is small enough to be the point
            text += f" Your log has {n_contacts} {band} contact{'s' if n_contacts != 1 else ''}" + (f", at {first:%H:%M} UTC." if n_contacts == 1 else ".")
        return text
    if opened:
        return f"{_join(names[c] for c in opened)} paths appeared during your logged activity on {band}; you logged no contact there."
    return "No distant-continent paths in the nearby WSPR."


def timeline_headline(panels):
    """One plain sentence for the top of the band cards, from the cards alone: who you worked in distant continents, and the bands on which WSPR near
    you showed a path to a distant continent at times when your log shows no contact on that band. Checked against UNSUPPORTED."""
    cards = [c for p in panels for c in p["cards"]]
    if not cards:
        return ""
    names = lf.CONTINENT_NAMES
    worked = {}
    for c in cards:
        for call, cont in c["worked"]:
            worked.setdefault(cont, set()).add(call)
    n = len({call for v in worked.values() for call in v})
    outside = [c["band"] for c in cards if c["outside"]]
    parts = [f"You worked {n} station{'s' if n != 1 else ''} in {_join(names[c] for c in worked)}." if worked else "You logged no contact with a distant continent."]
    if outside:
        parts.append(f"WSPR near you showed a path to a distant continent on {_join(outside)} at times when your log has no contact on that band.")
    elif not any(c["opened"] for c in cards):
        parts.append("WSPR near you showed no path to a distant continent on the bands you worked.")
    text = " ".join(parts)
    assert not unsupported_claims(text), unsupported_claims(text)
    return text


def band_timeline(grid, log, places, spots, locs, home, min_km=lc.DX_KM, metric="good", rbn_ok=True, only=None):
    """The data for the band-by-band timeline: one entry for each stretch of the log (a panel of the grid) and, in it, one card for each band you
    worked, highest band first (a fixed order). A card holds, on the same time axis:
      lanes       for each distant continent (EU, AF, AS, OC, SA), the receivers there in each time bin: `n` by the view's metric (`heard` decoded
                  WSPR near you; `good` also looked strong enough for you). One receiver is thin evidence, not a weak signal, so the page draws
                  1 pale and 2 or more solid, and shows the count when asked;
      thin        the bins in which there was too little WSPR near you to say anything at all;
      spans       the stretches of logged activity on the band (see activity_spans);
      contacts    your contacts on the band, those with a distant continent marked;
      rbn         for each continent and bin, the skimmers there that spotted you, only where RBN applies (see opening_cells);
      finding, worked   the one finding in words, and the calls worked in the distant continents.
    `only` limits the lanes to one continent code. Bands you did not work are named in `idle` and `thin_bands`."""
    bin_min = grid.attrs.get("bin_min", lc.CONDITIONS_SLOT_MIN)
    step = pd.Timedelta(minutes=bin_min)
    rec = grid.attrs.get("receivers")
    if rec is None or len(rec) == 0:
        rec = pd.DataFrame(columns=["slot", "band", "km", "continent", "verdict"])
    rec = rec[rec["km"] >= min_km]
    per_bin = {}
    for (slot, band, cont), g in rec.groupby(["slot", "band", "continent"]):
        per_bin[(slot, band, cont)] = {"heard": int(len(g)), "good": int((g["verdict"] == "good").sum())}
    states = {(r.slot, r.band): r.state for r in grid.itertuples()}
    cells = opening_cells(grid, log, places, spots, locs, home, "continent", None, min_km, metric, rbn_ok)
    rbn_state = {(r.slot, r.band): (r.rbn_state, r.rbn_why) for r in cells.itertuples()}
    rbn_who = {}
    if rbn_ok and spots is not None and len(spots):
        sk = skimmer_table(spots, locs, home)
        sp = spots.assign(slot=lf.bin_floor(spots["time"], bin_min)).merge(sk, on="spotter")
        sp = sp[sp["km"] >= min_km]
        for (slot, band, cont), g in sp.groupby(["slot", "band", "continent"]):
            rbn_who[(slot, band, cont)] = sorted(set(g["spotter"]))
    pl = places.assign(slot=lf.bin_floor(places["time"], bin_min))
    panels, worked_all, idle = [], set(), []
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
            mine = here[here["band"] == band].sort_values("time")
            own_bins = set(mine["slot"])
            lanes = {}
            for c in LANES:
                if only and c != only:
                    continue
                row = [per_bin.get((s, band, c), {"heard": 0, "good": 0}) for s in slots]
                row = [{"heard": 0, "good": 0} if states.get((s, band)) == lf.SPARSE else r for s, r in zip(slots, row)]       # too little WSPR: no bar, the card marks it
                ns = [r["good"] if metric == "good" else r["heard"] for r in row]
                spotted = any(rbn_who.get((s, band, c)) and rbn_state.get((s, band), ("", ""))[0] in (lf.EVIDENCE, lf.NO_REPORTS) for s in slots)
                if any(ns) or spotted or only:
                    lanes[c] = [{"slot": s, "n": n, "heard": r["heard"], "good": r["good"],
                                 "rbn": rbn_who.get((s, band, c), []) if rbn_state.get((s, band), (lf.NOT_APPLICABLE, ""))[0] in (lf.EVIDENCE, lf.NO_REPORTS) else []}
                                for s, n, r in zip(slots, ns, row)]
            opened = {c: [x["slot"] for x in v if x["n"] >= 1] for c, v in lanes.items()}
            opened = {c: v for c, v in opened.items() if v}
            contacts = [{"time": t, "call": call, "cont": cont if cont in LANES else "", "km": km}
                        for t, call, cont, km in zip(mine["time"], mine["call"], mine["continent"], mine["c_km"])]
            worked = [(c["time"], c["call"], c["cont"]) for c in contacts if c["cont"] and (not only or c["cont"] == only)]
            first = mine["time"].iloc[0]
            rbn_cont = {c for c, v in lanes.items() if any(x["rbn"] for x in v)}
            finding = band_finding(band, opened, own_bins, elsewhere, worked, len(mine), first, step, rbn_cont)
            assert not unsupported_claims(finding), unsupported_claims(finding)
            outside = (not worked) and any(t not in own_bins for v in opened.values() for t in v)
            cards.append({"band": band, "lanes": lanes, "opened": opened, "outside": outside, "thin": [s for s in slots if states.get((s, band)) == lf.SPARSE],
                          "spans": activity_spans(mine["time"]), "contacts": contacts, "finding": finding,
                          "worked": list(dict.fromkeys((call, cont) for _, call, cont in worked)),
                          "rbn_why": next((rbn_state[(s, band)][1] for s in slots if rbn_state.get((s, band), ("", ""))[1]), "")})
            worked_all.add(band)
        panels.append({"panel": panel, "slots": slots, "bin_min": bin_min, "cards": cards})
    for band in lc.bands_top_down(grid):
        if band not in worked_all:
            d = grid[grid["band"] == band]
            has_path = any(v["good" if metric == "good" else "heard"] > 0 for (_, b2, _), v in per_bin.items() if b2 == band)
            idle.append((band, "path" if has_path else "thin" if (d["state"] == lf.SPARSE).any() else "none"))
    return {"headline": timeline_headline(panels), "panels": panels, "idle": idle, "metric": metric, "min_km": min_km, "only": only, "bin_min": bin_min, "power_w": grid.attrs.get("power_w"),
            "mode": grid.attrs.get("mode", "CW"), "rbn_line": rbn_line(cells)}
