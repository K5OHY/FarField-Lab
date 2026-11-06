"""Saved copies of the real data behind the example buttons, so an example opens at once and shows the same thing every time,
without waiting on the Reverse Beacon Network or wspr.live. `build_examples.py` makes them; the files live in `examples/`."""
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

DIR = Path(__file__).resolve().parent / "examples"


def available(name):
    return (DIR / f"{name}.json").exists() and (DIR / f"{name}.csv.gz").exists()


@lru_cache(maxsize=16)
def _read(name):
    meta = json.loads((DIR / f"{name}.json").read_text(encoding="utf-8"))
    return meta, pd.read_csv(DIR / f"{name}.csv.gz", parse_dates=["time"])


def load(name):
    """(meta, spots) for an example, or None when its files are missing. Each file is read once; the caller gets its own copy."""
    if not available(name):
        return None
    meta, spots = _read(name)
    return json.loads(json.dumps(meta)), spots.copy()


@lru_cache(maxsize=1)
def _saved_listings():
    """[(meta listening info, rows)] for every saved example that carries a list of which receivers were on the band."""
    found = []
    for path in sorted(DIR.glob("*.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        saved = meta.get("listening")
        file = DIR / f"{path.stem}_listening.csv.gz"
        if saved and file.exists():
            found.append((saved, pd.read_csv(file, parse_dates=["time"])))
    return found


def listening(band, start, end):
    """What a saved example knows about which receivers were decoding on `band` between `start` and `end`, in the shape
    wspr_data.fetch_listening returns, or None when no saved example covers that."""
    for saved, rows in _saved_listings():
        if saved["band"] != band:
            continue
        lo, hi = pd.Timestamp(saved["start"]), pd.Timestamp(saved["end"])
        if lo <= pd.Timestamp(start) and pd.Timestamp(end) <= hi:
            return rows[(rows["time"] >= pd.Timestamp(start)) & (rows["time"] <= pd.Timestamp(end))].reset_index(drop=True), False
    return None
