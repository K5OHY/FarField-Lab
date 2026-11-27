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
from geographiclib.geodesic import Geodesic

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


# The continent each of the page's receiver regions (session_report.region_of) lies in.
REGION_CONTINENT = {"Europe": "EU", "Africa": "AF", "Asia": "AS", "Oceania": "OC", "South America": "SA", "Mexico, Caribbean & Central America": "NA",
                    "US East": "NA", "US Central": "NA", "US West": "NA", "Canada": "NA", "Other": ""}


def continent_of_region(region):
    """The continent code (NA, EU, ...) of one of the page's region names, or '' when it is not one."""
    return REGION_CONTINENT.get(region, "")


def destination_options(view):
    """The destinations a view offers, as [(key, label)], with the first being 'all of them': a compass sector's code and label, or a continent's
    code and name."""
    if view == "continent":
        return [(None, "All continents")] + [(k, v) for k, v in CONTINENT_NAMES.items() if k != "AN"]
    return [(None, "All directions")] + [(s, sector_label(s)) for s in SECTORS]


# How far away a station must be to count as a destination: the DX distance the page has always used, a middle choice, or any distance.
DISTANCE_CHOICES = {"dx": ("DX: 3,000 miles or more", 3000 * KM_PER_MILE), "far": ("1,000 km or more", 1000.0), "any": ("Any distance", 0.0)}
DEFAULT_DISTANCE = "dx"

# The box (south, north, west, east, in degrees) round each US state and Canadian province, to about half a degree. It is used for one question
# only: does the whole state lie inside one compass sector as seen from your station? If so a contact placed only by its state is counted in
# that sector; if not, it is between sectors and is listed apart.
STATE_BOXES = {
    "AL": (30.2, 35.0, -88.5, -84.9), "AK": (54.6, 71.4, -168.1, -130.0), "AZ": (31.3, 37.0, -114.8, -109.0), "AR": (33.0, 36.5, -94.6, -89.6),
    "CA": (32.5, 42.0, -124.4, -114.1), "CO": (37.0, 41.0, -109.05, -102.05), "CT": (41.0, 42.05, -73.7, -71.8), "DE": (38.45, 39.84, -75.8, -75.0),
    "DC": (38.8, 39.0, -77.1, -76.9), "FL": (24.5, 31.0, -87.6, -80.0), "GA": (30.35, 35.0, -85.6, -80.8), "HI": (18.9, 22.2, -160.3, -154.8),
    "ID": (42.0, 49.0, -117.2, -111.0), "IL": (36.97, 42.5, -91.5, -87.5), "IN": (37.8, 41.76, -88.1, -84.8), "IA": (40.4, 43.5, -96.6, -90.1),
    "KS": (37.0, 40.0, -102.05, -94.6), "KY": (36.5, 39.15, -89.6, -81.96), "LA": (28.9, 33.0, -94.04, -88.8), "ME": (43.06, 47.46, -71.1, -66.95),
    "MD": (37.9, 39.72, -79.5, -75.05), "MA": (41.2, 42.9, -73.5, -69.9), "MI": (41.7, 47.5, -90.4, -82.4), "MN": (43.5, 49.4, -97.2, -89.5),
    "MS": (30.2, 35.0, -91.65, -88.1), "MO": (36.0, 40.6, -95.8, -89.1), "MT": (44.4, 49.0, -116.05, -104.04), "NE": (40.0, 43.0, -104.05, -95.3),
    "NV": (35.0, 42.0, -120.0, -114.04), "NH": (42.7, 45.3, -72.56, -70.7), "NJ": (38.9, 41.36, -75.56, -73.9), "NM": (31.33, 37.0, -109.05, -103.0),
    "NY": (40.5, 45.0, -79.76, -71.86), "NC": (33.84, 36.59, -84.3, -75.46), "ND": (45.9, 49.0, -104.05, -96.55), "OH": (38.4, 41.98, -84.82, -80.52),
    "OK": (33.6, 37.0, -103.0, -94.43), "OR": (42.0, 46.3, -124.6, -116.46), "PA": (39.72, 42.27, -80.52, -74.69), "RI": (41.1, 42.02, -71.9, -71.1),
    "SC": (32.03, 35.2, -83.35, -78.5), "SD": (42.48, 45.94, -104.06, -96.44), "TN": (34.98, 36.68, -90.3, -81.65), "TX": (25.84, 36.5, -106.65, -93.51),
    "UT": (37.0, 42.0, -114.05, -109.04), "VT": (42.73, 45.02, -73.44, -71.46), "VA": (36.54, 39.47, -83.68, -75.24), "WA": (45.54, 49.0, -124.8, -116.92),
    "WV": (37.2, 40.64, -82.64, -77.72), "WI": (42.5, 47.1, -92.9, -86.8), "WY": (41.0, 45.0, -111.05, -104.05), "PR": (17.9, 18.5, -67.3, -65.2),
    "ON": (41.7, 56.9, -95.2, -74.3), "QC": (45.0, 62.6, -79.8, -57.1), "BC": (48.3, 60.0, -139.1, -114.0), "AB": (49.0, 60.0, -120.0, -110.0),
    "SK": (49.0, 60.0, -110.0, -101.4), "MB": (49.0, 60.0, -102.0, -88.9), "NS": (43.4, 47.0, -66.4, -59.7), "NB": (44.6, 48.1, -69.1, -63.8),
    "NL": (46.6, 60.4, -67.8, -52.6), "PE": (45.9, 47.1, -64.4, -62.0), "YT": (60.0, 69.6, -141.0, -124.0), "NT": (60.0, 78.0, -136.5, -102.0),
    "NU": (51.0, 83.0, -120.0, -61.0)}


def state_sector(state, home):
    """The one compass sector a whole state or province lies in, seen from `home`: the corners, edge middles and centre of its box all fall in
    the same sector. None when it spreads over more than one, when `home` is inside it, or when the state is not known."""
    box = STATE_BOXES.get(str(state or "").upper())
    if box is None:
        return None
    south, north, west, east = box
    if south <= home[0] <= north and west <= home[1] <= east:
        return None
    sectors = {sector_of(Geodesic.WGS84.Inverse(home[0], home[1], la, lo)["azi1"] % 360)
               for la in (south, (south + north) / 2, north) for lo in (west, (west + east) / 2, east)}
    return sectors.pop() if len(sectors) == 1 else None


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
RUNNING_KINDS = ("CQ", "DX")      # the kind of an RBN spot that says you were calling (CQ, or CQ DX), as opposed to answering or sending a beacon


def rbn_applicability(mode, running=None):
    """(applicable, why not): whether statements about RBN spots make sense. RBN carries CW and RTTY only (FT8 is on PSK Reporter, which this
    page does not use), and a skimmer spots you when you call CQ, not when you answer others. `running` is True when you were calling CQ,
    False when you were not, None when that is not known; only True counts."""
    if str(mode).upper() not in RBN_MODES:
        return False, f"RBN carries {' and '.join(RBN_MODES)}, not {mode}."
    if running is not True:
        return False, "RBN spots you when you call CQ, and it is not known that you were." if running is None else "You were not calling CQ."
    return True, ""


# ------------------------------------------------------------------------------------------------------------------------ power that changed

class PowerPlan(float):
    """A power that changed during the log, such as 75 W on a beam until 17:00 UTC and then 5 W on a doublet. As a number it is the first power, so code that wants one
    number still has one; `power_at(plan, time)` is the power at a moment and `{plan:g} W` is written out in words ("75 W until 17:00 UTC, then 5 W"). `steps` is
    ((time the power starts, watts), ...) in order of time, the first applying from the start of the log."""

    def __new__(cls, steps):
        steps = sorted(((pd.Timestamp(t), float(w)) for t, w in steps), key=lambda x: x[0])
        if not steps or any(w <= 0 for _, w in steps):
            raise ValueError("a power plan needs at least one step, each with a power above zero")
        self = super().__new__(cls, steps[0][1])
        self.steps = tuple(steps)
        return self

    def at(self, when):
        watts = self.steps[0][1]
        for start, w in self.steps:
            if pd.Timestamp(when) >= start:
                watts = w
        return watts

    def words(self):
        """'75 W until 17:00 UTC, then 5 W', with the date of a change when the log spans more than one day."""
        steps = self.steps
        dated = any(t.date() != steps[0][0].date() for t, _ in steps[1:])         # a change on another day than the log's first power starts
        out = f"{steps[0][1]:g} W"
        for (_, w), (t, w2) in zip(steps, steps[1:]):
            out += f" until {t:%d %b %H:%M} UTC, then {w2:g} W" if dated else f" until {t:%H:%M} UTC, then {w2:g} W"
        return out

    def __format__(self, spec):
        if spec == "g":
            return self.words()[:-2]                                   # the caller writes ' W' after it
        return float.__format__(float(self), spec)

    def __repr__(self):
        return "PowerPlan(" + ", ".join(f"({t:%Y-%m-%d %H:%M}, {w:g})" for t, w in self.steps) + ")"

    def __reduce__(self):
        return (PowerPlan, (list(self.steps),))


def power_at(power, when):
    """The power in watts at a moment: a plain power is the same all the time, a PowerPlan changes at its steps."""
    return power.at(when) if isinstance(power, PowerPlan) else float(power)


def power_text(power, when=None):
    """The power as the page writes it: '100 W', or for a plan the words ('75 W until 17:00 UTC, then 5 W'), or with `when` the one power at that moment."""
    if isinstance(power, PowerPlan) and when is None:
        return power.words()
    return f"{power_at(power, when) if when is not None else float(power):g} W"
