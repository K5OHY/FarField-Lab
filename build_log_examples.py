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
from conditions import fetch_nearby
from data_sources import download_rbn_day, load_nearby, load_rbn_listening
from rbn_data import load_skimmers, maidenhead_to_latlon

OUT = Path(__file__).resolve().parent / "examples" / "log"
DOWNLOADS = Path(r"C:\Users\halet\Downloads")
# key: (the original log, the first and last moment to keep (UTC, None for no limit)).
SOURCES = {
    "yagi-doublet": (DOWNLOADS / "2025-10-23 K5OHY at US-2989.adi", (None, None)),
    "sota-efhw": (DOWNLOADS / "2026-03-31 K5OHY at W5T-GU-018.adi", (None, None)),
    "efhw-black-friday": (DOWNLOADS / "2025-11-28 K5OHY at US-2989.adi", (None, None)),
}
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


def sanitized(records, first=None, last=None):
    """ADIF text of the contacts between `first` and `last` with only the fields the page reads, a station worked kept to the four character grid square."""
    lines = ["FarField Lab example log: only what the page reads is kept.", "<ADIF_VER:5>3.1.5", "<EOH>", ""]
    kept = 0
    for rec in records:
        t = when(rec)
        if (first and t < pd.Timestamp(first)) or (last and t > pd.Timestamp(last)):
            continue
        parts = []
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


def merged(intervals):
    """Overlapping or touching (start, end) pairs joined into the fewest."""
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1] + pd.Timedelta(seconds=1):
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def build(key):
    path, (first, last) = SOURCES[key]
    text, kept = sanitized(read_records(path.read_text(encoding="utf-8", errors="replace")), first, last)
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
    grid_of = lc.conditions_grid(log, wspr_for, (lat, lon), 75, radius_km=radius)            # the stretches the page asks for: the conditions grid and the comparison
    lc.compare(log, spots, wspr_for, listening, load_skimmers(), (lat, lon), 75)
    nearby = pd.concat([t for _, _, t in asked if len(t)], ignore_index=True).drop_duplicates(["time", "rx", "tx"]).sort_values("time")
    covered = merged([(a, b) for a, b, _ in asked])
    spots.to_csv(OUT / f"{key}_spots.csv.gz", index=False)
    listening.to_csv(OUT / f"{key}_listening.csv.gz", index=False)
    nearby.to_csv(OUT / f"{key}_nearby.csv.gz", index=False)
    meta = {"call": call, "days": days, "lat": lat, "lon": lon, "radius_km": radius, "listening_start": str(start), "listening_end": str(end),
            "nearby_covered": [[str(a), str(b)] for a, b in covered], "built": str(date.today()), "grid": grid}
    (OUT / f"{key}.frozen.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"   saved: {len(spots)} spots of you, {len(listening)} skimmer slots, {len(nearby)} WSPR spots over {len(covered)} stretch(es); a grid of {len(grid_of)} boxes", flush=True)


if __name__ == "__main__":
    for name in (sys.argv[1:] or list(SOURCES)):
        build(name)
