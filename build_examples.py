"""Makes the saved example data in `examples/`: the real spots behind each example button, where the transmitter is, and for a
WSPR test which receivers were listening. Needs the internet. Run it again to refresh the examples:

    python build_examples.py            (all of them)
    python build_examples.py rbn long   (just these)
"""
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd

from data_sources import download_rbn_day
from rbn_data import load_skimmers, lookup_callsign_location, maidenhead_to_latlon
from wspr_data import clean_callsign, fetch_listening, fetch_wspr_spots

OUT = Path(__file__).resolve().parent / "examples"

# name: (callsign, source, day, band for the listening list, extras). The extras are `call_b` (the second callsign, for a
# test where each antenna was sent under its own callsign) and `grid` (where the station is, when the callsign has no location).
EXAMPLES = {
    "map": ("K5OHY", "RBN", date(2025, 10, 23), None, {}),
    "rbn": ("K5OHY", "RBN", date(2026, 9, 27), None, {}),
    "quick": ("K5OHY", "WSPR", date(2026, 10, 4), "20m", {}),
    "long": ("N3HXZ", "WSPR", date(2026, 8, 26), "20m", {}),
    # Callum (M0MCX, DX Commander): a delta loop (M0MCX) against a vertical (M0XXT), three pairs on each band
    "dxc20": ("M0MCX", "WSPR", date(2026, 1, 14), "20m", {"call_b": "M0XXT", "grid": "IO92di"}),
    "dxc40": ("M0XXT", "WSPR", date(2026, 1, 14), "40m", {"call_b": "M0MCX", "grid": "IO92di"}),
}


def build(name):
    call, source, day, band, extra = EXAMPLES[name]
    if extra.get("grid"):
        grid = extra["grid"]
        lat, lon = maidenhead_to_latlon(grid)
        home = [lat, lon, f"{grid[:2].upper()}{grid[2:]} (manual)"]  # as the sidebar's grid box labels it
    else:
        found = lookup_callsign_location(call, load_skimmers())
        if not found:
            raise SystemExit(f"No location found for {call}.")
        lat, lon, grid, via = found
        home = [lat, lon, f"{grid or f'{lat:.2f}, {lon:.2f}'} via {via}"]
    meta = {"callsign": call, "kind": source, "file_date": f"{day:%Y%m%d}", "tx_call": None, "tx_call_b": None, "listening": None,
            "home": home,
            "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    if source == "RBN":
        spots = download_rbn_day(f"{day:%Y%m%d}", call)
    else:
        meta["tx_call"] = clean_callsign(call)
        spots, truncated = fetch_wspr_spots(call, datetime.combine(day, time(0, 0)), datetime.combine(day, time(23, 59, 59)))
        if extra.get("call_b"):
            meta["tx_call_b"] = clean_callsign(extra["call_b"])
            more, more_truncated = fetch_wspr_spots(extra["call_b"], datetime.combine(day, time(0, 0)),
                                                    datetime.combine(day, time(23, 59, 59)))
            spots, truncated = pd.concat([spots, more], ignore_index=True), truncated or more_truncated
        if truncated:
            raise SystemExit(f"{name}: the spot limit was hit, so the day is incomplete.")
    spots.to_csv(OUT / f"{name}.csv.gz", index=False)
    print(f"{name}: {len(spots)} spots")
    if band:
        on_band = spots[spots["band"] == band]
        start, end = on_band["time"].min().to_pydatetime(), (on_band["time"].max() + timedelta(minutes=2)).to_pydatetime()
        listening, truncated = fetch_listening(band, start, end)
        if truncated:
            raise SystemExit(f"{name}: the listening list hit its limit.")
        listening.to_csv(OUT / f"{name}_listening.csv.gz", index=False)
        meta["listening"] = {"band": band, "start": f"{start:%Y-%m-%d %H:%M:%S}", "end": f"{end:%Y-%m-%d %H:%M:%S}"}
        print(f"{name}: {len(listening)} listening rows on {band}")
    (OUT / f"{name}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for chosen in sys.argv[1:] or EXAMPLES:
        build(chosen)
