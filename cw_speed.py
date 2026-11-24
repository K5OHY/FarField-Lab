"""CW speed from RBN spots: the speed each skimmer measured for the sender, in words per minute.

Only CW spots have a speed in words per minute (an RTTY spot's speed is in baud, so those are left out), and WSPR has none. A measured speed
outside a sensible range is a misread and is ignored. The speed is the skimmer's measurement of the sending, not what the sender set.
"""
import pandas as pd

LOW, HIGH = 5, 80                                        # a CW speed outside this (words per minute) is a misread
EDGES = [0, 20, 25, 30, float("inf")]                    # the speed groups of the Heard by speed table
LABELS = ["Under 20 wpm", "20 to 24 wpm", "25 to 29 wpm", "30 wpm or more"]
MIN_SPOTS = 3                                            # fewer spots than this say nothing about a typical speed


def cw_speeds(spots):
    """The spots that carry a CW speed, as a table (empty when there is none: WSPR, or spots pasted without a speed)."""
    if "speed" not in spots.columns:
        return spots.iloc[0:0]
    speed = pd.to_numeric(spots["speed"], errors="coerce")
    keep = speed.between(LOW, HIGH)
    if "tx_mode" in spots.columns:                       # a known non-CW mode (RTTY) is left out; an unknown one is taken as CW
        mode = spots["tx_mode"].astype(str).str.upper()
        keep &= mode.eq("CW") | spots["tx_mode"].isna()
    return spots[keep].assign(speed=speed[keep])


def summary(spots):
    """{'n', 'median', 'low', 'high'} for the CW speeds in `spots` (low and high are the 10th and 90th percentiles, so one misread does not
    stretch the range), or None when there are too few to say."""
    s = cw_speeds(spots)
    if len(s) < MIN_SPOTS:
        return None
    return {"n": len(s), "median": float(s["speed"].median()), "low": float(s["speed"].quantile(0.1)), "high": float(s["speed"].quantile(0.9))}


def label(spots):
    """'24 wpm', or '22 to 25 wpm' when the spots span a range, for a popup; '' when none has a CW speed."""
    s = cw_speeds(spots)
    if s.empty:
        return ""
    lo, hi = round(float(s["speed"].min())), round(float(s["speed"].max()))
    return f"{lo} wpm" if lo == hi else f"{lo} to {hi} wpm"


def table(spots, band_order=()):
    """One row for each speed group that has spots: how many spots, how many different skimmers, the bands, and the median SNR."""
    s = cw_speeds(spots)
    if s.empty:
        return pd.DataFrame(columns=["Speed", "Spots", "Skimmers", "Bands", "Median signal (dB)"])
    group = pd.cut(s["speed"], EDGES, labels=LABELS, right=False)
    rows = []
    for name in LABELS:
        g = s[group == name]
        if g.empty:
            continue
        bands = sorted(g["band"].unique(), key=lambda b: band_order.index(b) if b in band_order else len(band_order))
        rows.append({"Speed": name, "Spots": len(g), "Skimmers": int(g["spotter"].nunique()), "Bands": ", ".join(bands),
                     "Median signal (dB)": float(g["snr"].median())})
    return pd.DataFrame(rows)
