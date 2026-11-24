"""Shared foundations for the Log analysis page: the rules every part of the page uses, in one place so they cannot drift apart.

Nothing here draws a page or asks the network. The pieces:

  * time bins: one clock-aligned bin size (30 minutes, or 15) for WSPR, RBN spots and contacts, with the exact bounds of each bin and of
    the hour of WSPR behind it, and a count of how much of that hour the box before also used;
  * "nearby": the radius within which a WSPR transmitter counts as near you, chosen from a short list;
  * regions: compass sectors seen from you (eight of 45 degrees), or the continent, as an alternative;
  * SNR: everything stated in WSPR's reference bandwidth of 2,500 Hz, and which readings have been converted and which not;
  * coverage: how many transmitters, receivers and receiving sites stand behind a bin, and when that is too few ("sparse");
  * the states a box can be in when it has nothing to show, each with its own name, so that "no reports", "too few stations" and "none
    strong enough" are never drawn as the same blank.
"""
import math

import numpy as np
import pandas as pd

from rbn_data import GRID_RE, maidenhead_to_latlon

# ------------------------------------------------------------------------------------------------- time bins

BIN_MINUTES_CHOICES = (15, 30)
DEFAULT_BIN_MIN = 30
WSPR_LOOKBACK_MIN = 60       # each bin is judged on the hour of WSPR up to its end, as the Band conditions page does


def _minutes(minutes):
    if minutes not in BIN_MINUTES_CHOICES:
        raise ValueError(f"A time bin is {' or '.join(str(m) for m in BIN_MINUTES_CHOICES)} minutes, not {minutes}.")
    return int(minutes)


def bin_floor(times, minutes=DEFAULT_BIN_MIN):
    """The start of the clock-aligned bin each time falls in (13:47 gives 13:30 in 30-minute bins). Takes one time or a column of them.
    A bin is half open: it holds its start and everything up to, but not including, its end."""
    freq = f"{_minutes(minutes)}min"
    return times.dt.floor(freq) if isinstance(times, pd.Series) else pd.Timestamp(times).floor(freq)


def bin_bounds(start, minutes=DEFAULT_BIN_MIN):
    """(start, end) of the bin that begins at `start`."""
    return pd.Timestamp(start), pd.Timestamp(start) + pd.Timedelta(minutes=_minutes(minutes))


def bins_between(first, last, minutes=DEFAULT_BIN_MIN):
    """The starts of every bin from the one holding `first` to the one holding `last`."""
    return list(pd.date_range(bin_floor(first, minutes), bin_floor(last, minutes), freq=f"{_minutes(minutes)}min"))


def wspr_window(start, minutes=DEFAULT_BIN_MIN, lookback=WSPR_LOOKBACK_MIN):
    """(from, to) of the WSPR behind the bin that begins at `start`: spots after `from` and up to and including `to`, which is the bin's
    end. `lookback` minutes long, so it reaches back before the bin itself."""
    _, end = bin_bounds(start, minutes)
    return end - pd.Timedelta(minutes=lookback), end


def shared_minutes(window_a, window_b):
    """How many minutes two WSPR windows have in common (0 when they do not meet)."""
    lo, hi = max(window_a[0], window_b[0]), min(window_a[1], window_b[1])
    return max(0.0, (hi - lo).total_seconds() / 60)


def window_table(starts, minutes=DEFAULT_BIN_MIN, lookback=WSPR_LOOKBACK_MIN):
    """For each bin start: the bin's bounds, the bounds of its WSPR window, and `shared_min`, how much of that window the bin before it
    already used. `reused` is True when that is more than nothing: the same WSPR reports then speak for two boxes."""
    rows, previous = [], None
    for start in sorted(pd.Timestamp(s) for s in starts):
        a, b = bin_bounds(start, minutes)
        window = wspr_window(start, minutes, lookback)
        shared = shared_minutes(previous, window) if previous is not None else 0.0
        rows.append({"bin_start": a, "bin_end": b, "window_start": window[0], "window_end": window[1], "shared_min": shared, "reused": shared > 0})
        previous = window
    return pd.DataFrame(rows, columns=["bin_start", "bin_end", "window_start", "window_end", "shared_min", "reused"])


# ------------------------------------------------------------------------------------------------- nearby

KM_PER_MILE = 1.609344
RADIUS_CHOICES_KM = (300, 400, 500)
DEFAULT_RADIUS_KM = 500       # about the 300 miles the page has always used


def radius_text(km):
    """'500 km (311 miles)', for any sentence that says how far 'near you' reaches."""
    return f"{km:,.0f} km ({km / KM_PER_MILE:,.0f} miles)"


# ------------------------------------------------------------------------------------------------- regions

SECTORS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
SECTOR_NAMES = {"N": "North", "NE": "Northeast", "E": "East", "SE": "Southeast", "S": "South", "SW": "Southwest", "W": "West", "NW": "Northwest"}
SECTOR_WIDTH = 360 / len(SECTORS)
CONTINENT_NAMES = {"NA": "North America", "SA": "South America", "EU": "Europe", "AF": "Africa", "AS": "Asia", "OC": "Oceania", "AN": "Antarctica"}
REGION_VIEWS = {"sector": "Direction from you (8 sectors)", "continent": "Continent"}


def sector_of(bearing):
    """The compass sector a bearing (degrees from north, from you) falls in: North is 337.5 up to, but not including, 22.5, and so on round.
    None when there is no bearing."""
    if bearing is None or (isinstance(bearing, float) and math.isnan(bearing)):
        return None
    return SECTORS[int(((float(bearing) % 360) + SECTOR_WIDTH / 2) // SECTOR_WIDTH) % len(SECTORS)]


def sector_label(sector):
    """'Northeast (23-67°)': the name and the bearings it covers."""
    i = SECTORS.index(sector)
    lo, hi = (i * SECTOR_WIDTH - SECTOR_WIDTH / 2) % 360, (i * SECTOR_WIDTH + SECTOR_WIDTH / 2) % 360
    return f"{SECTOR_NAMES[sector]} ({math.ceil(lo):.0f}–{math.floor(hi - 1e-9) if hi else 0:.0f}°)"


def region_of_point(bearing, continent, view="sector"):
    """The region a station is in, in the chosen view: its sector seen from you, or its continent's name. None when that is not known."""
    if view == "continent":
        return CONTINENT_NAMES.get(str(continent or "").upper())
    return sector_of(bearing)


# ------------------------------------------------------------------------------------------------- locating a station by its grid

def grid_point(text):
    """(lat, lon) of the centre of a 4, 6 or 8 character grid square, or None when the text is not a valid grid. The 6 character grid is
    used when it is given, so a contact's own grid is never rounded off to the 4 character one."""
    text = str(text or "").strip()
    if not GRID_RE.match(text):
        return None
    return maidenhead_to_latlon(text)


# ------------------------------------------------------------------------------------------------- SNR

REFERENCE_BW_HZ = 2500.0      # WSPR's reference bandwidth, and the one the Band conditions page states its thresholds in
# For each source of an SNR figure: the bandwidth it is stated in, whether that is certain, and where the answer comes from.
SNR_BASIS = {
    "wspr": (2500.0, True, "WSPR reports SNR in 2,500 Hz by definition."),
    "threshold": (2500.0, True, "The mode thresholds on the Band conditions page (CW -5, SSB +8, FT8 -21, WSPR -28 dB) are stated in 2,500 Hz."),
    "rbn": (500.0, False, "RBN's operator describes a spot's SNR as signal against the noise scaled to 500 Hz (N4ZR, 2014). That is an assumption here: "
                          "it depends on each skimmer's software, antenna and noise, and no spot says which."),
}


def to_reference_bw(snr_db, bandwidth_hz, reference_hz=REFERENCE_BW_HZ):
    """An SNR stated in `bandwidth_hz` restated in the reference bandwidth. Noise grows with bandwidth, so a reading against 500 Hz of noise
    is 10*log10(2500/500), about 7 dB, higher than the same signal against 2,500 Hz."""
    return snr_db + 10 * np.log10(float(bandwidth_hz) / float(reference_hz))


def snr_in_reference(source, snr_db):
    """`snr_db` from `source` ('wspr', 'threshold' or 'rbn') restated in 2,500 Hz. Use SNR_BASIS[source] to say how sure that is."""
    return to_reference_bw(snr_db, SNR_BASIS[source][0])


# ------------------------------------------------------------------------------------------------- coverage

SPARSE_MIN_TRANSMITTERS = 3    # fewer different WSPR transmitters near you than this in a bin's window and the bin is sparse
SPARSE_MIN_RECEIVERS = 20      # likewise for the stations that decoded them


def reaches(lat, lon):
    """A receiving site: its position to about a kilometre, so two callsigns at one place are one site."""
    return (round(float(lat), 2), round(float(lon), 2))


def coverage(wspr):
    """What stands behind a window of WSPR spots (the table conditions.fetch_nearby returns: tx, rx, rx_lat, rx_lon, ...): the reports,
    the different transmitters, the different receivers and the different receiving sites. Repeated reports of one transmitter by one
    receiver add to the reports and to nothing else."""
    if wspr is None or len(wspr) == 0:
        return {"reports": 0, "transmitters": 0, "receivers": 0, "sites": 0}
    sites = {reaches(a, b) for a, b in zip(wspr["rx_lat"], wspr["rx_lon"])} if {"rx_lat", "rx_lon"} <= set(wspr.columns) else set()
    return {"reports": int(len(wspr)), "transmitters": int(wspr["tx"].nunique()), "receivers": int(wspr["rx"].nunique()), "sites": len(sites)}


def is_sparse(transmitters, receivers):
    """True when too few transmitters or too few receivers stand behind a box for it to say anything."""
    return transmitters < SPARSE_MIN_TRANSMITTERS or receivers < SPARSE_MIN_RECEIVERS


# ------------------------------------------------------------------------------------------------- what a box can be

EVIDENCE = "evidence"
NO_REPORTS = "no reports"
SPARSE = "insufficient coverage"
BELOW = "below threshold"
UNAVAILABLE = "unavailable"
NOT_APPLICABLE = "not applicable"
STATE_NOTES = {
    EVIDENCE: "There are reports, enough stations behind them, and some reach the threshold.",
    NO_REPORTS: "Nothing was reported in the window. That says nothing about the band: nobody may have been listening or sending.",
    SPARSE: f"Fewer than {SPARSE_MIN_TRANSMITTERS} transmitters or {SPARSE_MIN_RECEIVERS} receivers stand behind it, so it says nothing.",
    BELOW: "Enough stations reported, but none looked strong enough to reach the threshold.",
    UNAVAILABLE: "The data could not be fetched.",
    NOT_APPLICABLE: "This kind of evidence does not apply (for RBN, a mode it does not carry, or a session in which you were not calling CQ).",
}


def cell_state(applicable=True, available=True, reports=0, transmitters=0, receivers=0, reaching=0):
    """Which of the neutral states a box is in, checked in this order: not applicable, unavailable, no reports, insufficient coverage,
    below threshold; otherwise it has evidence. `reaching` is how many receivers looked strong enough."""
    if not applicable:
        return NOT_APPLICABLE
    if not available:
        return UNAVAILABLE
    if reports <= 0:
        return NO_REPORTS
    if is_sparse(transmitters, receivers):
        return SPARSE
    if reaching <= 0:
        return BELOW
    return EVIDENCE


RBN_MODES = ("CW", "RTTY")


def rbn_applicability(mode, running=None):
    """(applicable, why not): whether statements about RBN spots make sense. RBN carries CW and RTTY only (FT8 is on PSK Reporter, which this
    page does not use), and a skimmer spots you when you call CQ, not when you answer others. `running` is True when you were calling CQ,
    False when you were not, None when that is not known; only True counts."""
    if str(mode).upper() not in RBN_MODES:
        return False, f"RBN carries {' and '.join(RBN_MODES)}, not {mode}."
    if running is not True:
        return False, "RBN spots you when you call CQ, and it is not known that you were." if running is None else "You were not calling CQ."
    return True, ""
