"""Makes the example logs in `examples/log/`: for each entry of `manifest.json`, the log itself (cut to the stretch the example is about and stripped of everything the page does not
need, so no name, address or comment of anyone worked is kept and the grid of a station worked is cut to four characters), and the real RBN and WSPR data the page reads for it
(see frozen_data.py), so the example opens at once. Needs the internet and the original log files, which are not in the repository: `SOURCES` says where each came from.

    python build_log_examples.py              (all of them)
    python build_log_examples.py yagi-10m     (just this one)

Run it again to refresh an example. The text of a card (title, antenna, power, video) is edited in `manifest.json`, with no need to run anything."""
import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

import frozen_data
import log_check as lc
import log_foundations as lf
import callbook
import donki
import log_story
import space_weather as sw
from conditions import fetch_nearby
from data_sources import download_rbn_day, load_contact_places, load_nearby, load_pota_park, load_rbn_listening, load_reference_places, load_sota_summit
from rbn_data import load_skimmers, maidenhead_to_latlon

OUT = Path(__file__).resolve().parent / "examples" / "log"
DOWNLOADS = Path(r"C:\Users\halet\Downloads")
# key: (the original log, the first and last moment to keep (UTC, None for no limit)).
SOURCES = {
    "yagi-doublet": (DOWNLOADS / "2025-10-23 K5OHY at US-2989.adi", (None, None)),
    "sota-efhw": (DOWNLOADS / "2026-03-31 K5OHY at W5T-GU-018.adi", (None, None)),
    "efhw-black-friday": (DOWNLOADS / "2025-11-28 K5OHY at US-2989.adi", (None, None)),
    "bush-house-ocf": (DOWNLOADS / "2026-11-21 K5OHY at US-10272.adi", (None, None)),
    "storm-kp9": (DOWNLOADS / "204730_K5OHY_51497_qyhRUmK.adif", (None, None)),
}
# what a logging program leaves out or writes its own way: the station callsign when the log has none, and a park written in the SIG fields (N3FJP) rather than POTA_REF
OPTIONS = {"storm-kp9": {"own_call": "K5OHY"}}
KEEP = ("CALL", "QSO_DATE", "TIME_ON", "BAND", "FREQ", "MODE", "RST_SENT", "RST_RCVD", "STATION_CALLSIGN", "OPERATOR", "MY_GRIDSQUARE", "GRIDSQUARE", "STATE", "COUNTRY",
        "DXCC", "CQZ", "ITUZ", "CONT", "MY_POTA_REF", "POTA_REF", "MY_SOTA_REF", "SOTA_REF", "MY_STATE", "MY_COUNTRY", "MY_DXCC", "MY_CONT")
TAG = re.compile(r"<(\w+):(\d+)(?::\w+)?>", re.I)
CALL = r"[A-Z0-9]{1,4}(?:/[A-Z0-9]{1,4})?[A-Z0-9/]*"
GRID = r"[A-Ra-r]{2}\d{2}(?:[A-Xa-x]{2})?"
PATTERNS = {                       # what each kept field may look like; anything else (a pasted note, a snippet of code) stops the build instead of being kept
    "CALL": CALL, "STATION_CALLSIGN": CALL, "OPERATOR": CALL, "QSO_DATE": r"\d{8}", "TIME_ON": r"\d{4}(?:\d{2})?", "BAND": r"\d+(?:\.\d+)?(?:m|cm|mm)", "FREQ": r"\d+(?:\.\d+)?",
    "MODE": r"[A-Z0-9]{2,8}", "RST_SENT": r"\d{2,3}[A-Z]?", "RST_RCVD": r"\d{2,3}[A-Z]?", "MY_GRIDSQUARE": GRID, "GRIDSQUARE": GRID, "STATE": r"[A-Za-z0-9 -]{1,20}", "MY_STATE": r"[A-Z]{2}",
    "COUNTRY": r"[A-Za-z .,'()-]{2,40}", "MY_COUNTRY": r"[A-Za-z .,'()-]{2,40}", "DXCC": r"\d{1,3}", "MY_DXCC": r"\d{1,3}", "CQZ": r"\d{1,2}", "ITUZ": r"\d{1,2}", "CONT": r"[A-Z]{2}", "MY_CONT": r"[A-Z]{2}",
    "MY_POTA_REF": r"[A-Z]{1,3}-\d{3,6}(?:,\s*[A-Z]{1,3}-\d{3,6})*", "POTA_REF": r"[A-Z]{1,3}-\d{3,6}(?:,\s*[A-Z]{1,3}-\d{3,6})*",
    "MY_SOTA_REF": r"[A-Z0-9]{1,3}/[A-Z]{2}-[A-Z0-9]{3}", "SOTA_REF": r"[A-Z0-9]{1,3}/[A-Z]{2}-[A-Z0-9]{3}",
}


def read_records(text):
    """The contacts of an ADIF file as dictionaries of field name to value."""
    body = re.split(r"<eoh>", text, maxsplit=1, flags=re.I)[-1]
    out = []
    for chunk in re.split(r"<eor>", body, flags=re.I):
        fields, pos = {}, 0
        while True:
            m = TAG.search(chunk, pos)
            if not m:
                break
            n = int(m.group(2))
            fields[m.group(1).upper()] = chunk[m.end():m.end() + n]
            pos = m.end() + n
        if fields.get("CALL"):
            out.append(fields)
    return out


def when(rec):
    return pd.Timestamp(f"{rec['QSO_DATE']} {rec['TIME_ON'][:2]}:{rec['TIME_ON'][2:4]}:{rec['TIME_ON'][4:6] if len(rec['TIME_ON']) >= 6 else '00'}")


POTA_REF = re.compile(r"[A-Z]{1,3}-\d{3,6}(?:,\s*[A-Z]{1,3}-\d{3,6})*", re.I)


def sanitized(records, first=None, last=None, own_call=None):
    """ADIF text of the contacts between `first` and `last` with only the fields the page reads, a station worked kept to the four character grid square. `own_call` is written as the
    station callsign when a log has none; a park a logging program wrote as MY_SIG_INFO or SIG_INFO is written as MY_POTA_REF or POTA_REF when it is a POTA reference."""
    lines = ["FarField Lab example log: only what the page reads is kept.", "<ADIF_VER:5>3.1.5", "<EOH>", ""]
    kept = 0
    for rec in records:
        t = when(rec)
        if (first and t < pd.Timestamp(first)) or (last and t > pd.Timestamp(last)):
            continue
        parts = []
        rec = dict(rec)
        if own_call and not rec.get("STATION_CALLSIGN"):
            rec["STATION_CALLSIGN"] = own_call
        for sig, pota in (("MY_SIG_INFO", "MY_POTA_REF"), ("SIG_INFO", "POTA_REF")):
            if not rec.get(pota) and POTA_REF.fullmatch(rec.get(sig, "")):
                rec[pota] = rec[sig]
        for name in KEEP:
            value = rec.get(name, "")
            if name == "GRIDSQUARE":
                value = value[:4]
            if value:
                if not re.fullmatch(PATTERNS[name], value, re.I):
                    raise ValueError(f"{name} of {rec.get('CALL')} at {when(rec)} is not what that field holds ({value[:40]!r}): look at the original log before keeping it")
                parts.append(f"<{name}:{len(value)}>{value}")
        lines.append(" ".join(parts) + " <EOR>")
        kept += 1
    return "\n".join(lines) + "\n", kept


def example_power(key):
    """The power an example opens with, from its card: a plain power, or the plan when its power changed during the log."""
    card = next(e for e in json.loads((OUT / "manifest.json").read_text(encoding="utf-8")) if e["key"] == key)
    return lf.PowerPlan(card["power_plan"]) if card.get("power_plan") else float(card["power_w"])


def merged(intervals):
    """Overlapping or touching (start, end) pairs joined into the fewest."""
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1] + pd.Timedelta(seconds=1):
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _retry(fn, *args, tries=4):
    """A lookup that sometimes fails on a bad connection, tried a few times."""
    import time
    for i in range(tries):
        try:
            return fn(*args)
        except RuntimeError:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def build_lookups(log, spots):
    """What the page looks up about this log, done once live and saved (see frozen_data.lookup): where every station worked was, the home park or summit and the other parks named, the
    space weather and, when a storm is in the days around it, NASA's cause. Run as the page runs them, so the arguments match what the page will ask with."""
    from views import log_view
    skimmers = load_skimmers()
    out = {}
    dx_calls = lc.contact_dx_calls(log)
    call_places = None
    if dx_calls:
        call_places = callbook.load_places(tuple(dx_calls))
        out["dx_places"] = [((tuple(dx_calls),), call_places)]
        log.attrs["call_places"] = call_places
    parks, summits = lc.contact_references(log)
    if parks or summits:
        args = (tuple(sorted(parks)), tuple(sorted(summits)))
        ref_places = load_reference_places(*args)
        out["reference_places"] = [(args, ref_places)]
        log.attrs["ref_places"] = ref_places
    rows, seen = [], set()
    for band in log["band"].value_counts().index:
        for row in log[log["band"] == band].drop_duplicates("call")[["call", "state", "country"]].itertuples(index=False, name=None):
            if row[0] not in seen:
                seen.add(row[0])
                rows.append(row)
    out["places"] = [((), load_contact_places(rows, skimmers, workers=4, grids=log_view._log_grids(log), dx_places=call_places, ref_grids=log_view._ref_grids(log)))]
    for ref in lc.pota_refs(log):
        out.setdefault("pota_park", []).append(((ref,), _retry(load_pota_park, ref)))
    for ref in lc.sota_refs(log):
        out.setdefault("sota_summit", []).append(((ref,), _retry(load_sota_summit, ref)))
    a, b = log_story.window(log)
    history = sw.history(a, b)
    out["space_history"] = [((str(a), str(b)), history)]
    if log_story.needs_donki(history, log):
        out["donki_events"] = [((str(a), str(b)), donki.events(a, b))]
    frozen_data.save_lookups(KEY_BEING_BUILT[0], out, OUT)
    return out


KEY_BEING_BUILT = [None]


def build(key):
    KEY_BEING_BUILT[0] = key
    path, (first, last) = SOURCES[key]
    text, kept = sanitized(read_records(path.read_text(encoding="utf-8", errors="replace")), first, last, **OPTIONS.get(key, {}))
    (OUT / f"{key}.adi").write_text(text, encoding="utf-8")
    log = lc.parse_adif(text)
    cw = log[log["mode"] == "CW"]
    call, grid = lc.log_origin(log)
    lat, lon = maidenhead_to_latlon(grid)
    radius = lf.DEFAULT_RADIUS_KM
    start, end = cw["time"].min() - pd.Timedelta(minutes=lc.LOOKBACK_MIN), cw["time"].max() + pd.Timedelta(minutes=lc.WINDOW_PAD_MIN)
    span = sorted({f"{d:%Y%m%d}" for d in pd.date_range(start.floor("D"), end.floor("D"))})
    days = sorted(set(span) | {f"{d:%Y%m%d}" for d in log["time"].dt.date})
    print(f"{key}: {kept} contacts ({len(cw)} CW), {call} at {grid}, RBN days {days}", flush=True)
    frozen_data.DIR = OUT / "none"                                       # read the live services, not an earlier copy of this example
    frozen_data._entries.cache_clear()
    spots = pd.concat([download_rbn_day(d, call) for d in days], ignore_index=True)
    spots = spots[(spots["time"] >= cw["time"].min() - pd.Timedelta(minutes=15)) & (spots["time"] <= cw["time"].max() + pd.Timedelta(minutes=15))].reset_index(drop=True)
    # only the stretch the example is about, so the two halves of one day do not show each other's spots
    listening = load_rbn_listening(tuple(span), start, end)
    asked = []

    def wspr_for(a, b):
        table = load_nearby(lat, lon, radius, a, b)
        asked.append((pd.Timestamp(a), pd.Timestamp(b), table))
        return table
    power = example_power(key)                                           # the power the example opens with: the grid and the comparison are made for it and saved
    grid_of = lc.conditions_grid(log, wspr_for, (lat, lon), power, radius_km=radius)            # the stretches the page asks for: the conditions grid and the comparison
    compared = lc.compare(log, spots, wspr_for, listening, load_skimmers(), (lat, lon), power)
    from views.log_view import _power_key
    args = (_power_key(power), round(lat, 3), round(lon, 3), float(radius))
    results = {"conditions_grid": [(args, grid_of)], "compare": [(args, compared)]}
    nearby = pd.concat([t for _, _, t in asked if len(t)], ignore_index=True).drop_duplicates(["time", "rx", "tx"]).sort_values("time")
    covered = merged([(a, b) for a, b, _ in asked])
    spots.to_csv(OUT / f"{key}_spots.csv.gz", index=False)
    listening.to_csv(OUT / f"{key}_listening.csv.gz", index=False)
    nearby.to_csv(OUT / f"{key}_nearby.csv.gz", index=False)
    meta = {"call": call, "days": days, "lat": lat, "lon": lon, "radius_km": radius, "listening_start": str(start), "listening_end": str(end),
            "nearby_covered": [[str(a), str(b)] for a, b in covered], "built": str(date.today()), "grid": grid}
    (OUT / f"{key}.frozen.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    frozen_data.save_results(key, results, OUT)
    lookups = build_lookups(log, spots)
    print(f"   lookups saved: {len(lookups['places'][0][1])} stations placed, {len(lookups.get('pota_park', [])) + len(lookups.get('sota_summit', []))} park or summit records, "
          f"space weather {'with' if lookups.get('donki_events') else 'without'} a storm to explain")
    print(f"   saved: {len(spots)} spots of you, {len(listening)} skimmer slots, {len(nearby)} WSPR spots over {len(covered)} stretch(es); a grid of {len(grid_of)} boxes", flush=True)


if __name__ == "__main__":
    for name in (sys.argv[1:] or list(SOURCES)):
        build(name)
