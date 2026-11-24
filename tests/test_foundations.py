"""Checks of the shared foundations of the Log analysis page (log_foundations.py and what builds on it), with made-up data and no network."""
import math
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import log_check as lc  # noqa: E402
import log_check_html as lh  # noqa: E402
import log_foundations as lf  # noqa: E402

HOME = (31.0, -102.0)
T = pd.Timestamp


class TimeBins(unittest.TestCase):
    def test_a_time_falls_in_the_bin_that_starts_on_the_clock(self):
        self.assertEqual(lf.bin_floor(T("2026-11-18 13:47"), 30), T("2026-11-18 13:30"))
        self.assertEqual(lf.bin_floor(T("2026-11-18 13:47"), 15), T("2026-11-18 13:45"))
        self.assertEqual(lf.bin_floor(T("2026-11-18 14:00"), 30), T("2026-11-18 14:00"))      # a bin holds its start, not its end

    def test_contacts_rbn_spots_and_wspr_land_in_the_same_bins(self):
        contacts = pd.Series(pd.to_datetime(["2026-11-18 20:05", "2026-11-18 20:29"]))
        rbn = pd.Series(pd.to_datetime(["2026-11-18 20:00:00", "2026-11-18 20:29:59"]))
        wspr = pd.Series(pd.to_datetime(["2026-11-18 20:14", "2026-11-18 20:18"]))
        for minutes in (30, 15):
            self.assertEqual(lf.bin_floor(contacts, minutes).tolist(), lf.bin_floor(rbn, minutes).tolist())
        self.assertEqual(set(lf.bin_floor(contacts, 30)) | set(lf.bin_floor(rbn, 30)) | set(lf.bin_floor(wspr, 30)), {T("2026-11-18 20:00")})
        self.assertEqual(set(lf.bin_floor(wspr, 15)), {T("2026-11-18 20:00"), T("2026-11-18 20:15")})    # 20:14 and 20:18 are in different 15-minute bins

    def test_a_bin_has_exact_bounds(self):
        self.assertEqual(lf.bin_bounds(T("2026-11-18 20:30"), 30), (T("2026-11-18 20:30"), T("2026-11-18 21:00")))
        self.assertEqual(lf.bin_bounds(T("2026-11-18 20:30"), 15), (T("2026-11-18 20:30"), T("2026-11-18 20:45")))

    def test_bins_run_from_the_one_holding_the_first_time_to_the_one_holding_the_last(self):
        starts = lf.bins_between(T("2026-11-18 20:10"), T("2026-11-18 21:20"), 30)
        self.assertEqual(starts, [T("2026-11-18 20:00"), T("2026-11-18 20:30"), T("2026-11-18 21:00")])

    def test_only_15_or_30_minutes_are_bins(self):
        with self.assertRaises(ValueError):
            lf.bin_floor(T("2026-11-18 20:10"), 20)
        self.assertEqual(lf.DEFAULT_BIN_MIN, 30)
        self.assertIn(15, lf.BIN_MINUTES_CHOICES)

    def test_the_wspr_window_is_the_hour_up_to_the_end_of_the_bin(self):
        self.assertEqual(lf.wspr_window(T("2026-11-18 20:30"), 30), (T("2026-11-18 20:00"), T("2026-11-18 21:00")))
        self.assertEqual(lf.wspr_window(T("2026-11-18 20:30"), 15), (T("2026-11-18 19:45"), T("2026-11-18 20:45")))

    def test_neighbouring_boxes_that_share_wspr_are_flagged_with_how_much(self):
        table = lf.window_table(lf.bins_between(T("2026-11-18 20:00"), T("2026-11-18 21:00"), 30), 30)
        self.assertEqual(table["shared_min"].tolist(), [0.0, 30.0, 30.0])                      # each box reuses half of the hour of the one before
        self.assertEqual(table["reused"].tolist(), [False, True, True])
        fifteen = lf.window_table(lf.bins_between(T("2026-11-18 20:00"), T("2026-11-18 20:45"), 15), 15)
        self.assertEqual(fifteen["shared_min"].tolist(), [0.0, 45.0, 45.0, 45.0])

    def test_boxes_far_apart_share_nothing(self):
        table = lf.window_table([T("2026-11-18 13:30"), T("2026-11-18 17:00")], 30)
        self.assertEqual(table["shared_min"].tolist(), [0.0, 0.0])
        self.assertEqual(table["reused"].tolist(), [False, False])
        self.assertEqual(lf.shared_minutes((T("2026-11-18 12:00"), T("2026-11-18 13:00")), (T("2026-11-18 13:00"), T("2026-11-18 14:00"))), 0.0)


class Nearby(unittest.TestCase):
    def test_the_radius_is_chosen_from_a_short_list_between_300_and_500_km(self):
        self.assertEqual(lf.RADIUS_CHOICES_KM, (300, 400, 500))
        self.assertIn(lf.DEFAULT_RADIUS_KM, lf.RADIUS_CHOICES_KM)
        self.assertTrue(300 <= lf.DEFAULT_RADIUS_KM <= 500)

    def test_the_radius_is_said_in_both_units(self):
        self.assertEqual(lf.radius_text(500), "500 km (311 miles)")
        self.assertEqual(lf.radius_text(300), "300 km (186 miles)")


class Regions(unittest.TestCase):
    def test_sectors_are_45_degrees_wide_and_centred_on_the_compass_points(self):
        for bearing, sector in ((0, "N"), (22.4, "N"), (22.5, "NE"), (45, "NE"), (67.4, "NE"), (67.5, "E"), (90, "E"), (135, "SE"), (180, "S"),
                                (225, "SW"), (270, "W"), (315, "NW"), (337.4, "NW"), (337.5, "N"), (359.9, "N"), (360, "N"), (-45, "NW"), (405, "NE")):
            self.assertEqual(lf.sector_of(bearing), sector, bearing)
        self.assertIsNone(lf.sector_of(None))
        self.assertIsNone(lf.sector_of(float("nan")))

    def test_a_sector_is_labelled_with_the_bearings_it_covers(self):
        self.assertEqual(lf.sector_label("N"), "North (338–22°)")
        self.assertEqual(lf.sector_label("NE"), "Northeast (23–67°)")
        self.assertEqual(lf.sector_label("E"), "East (68–112°)")

    def test_the_region_view_is_the_sector_or_the_continent(self):
        self.assertEqual(lf.region_of_point(100, "EU", "sector"), "E")
        self.assertEqual(lf.region_of_point(100, "EU", "continent"), "Europe")
        self.assertIsNone(lf.region_of_point(100, "", "continent"))
        self.assertIsNone(lf.region_of_point(100, "ZZ", "continent"))
        self.assertIsNone(lf.region_of_point(None, "EU", "sector"))


def log_of(*records):
    return lc.parse_adif("<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(records) + "\n")


def rec(call, hhmm="2000", band="20m", **fields):
    extra = "".join(f"<{k.upper()}:{len(str(v))}>{v} " for k, v in fields.items())
    return f"<CALL:{len(call)}>{call} <QSO_DATE:8>20261118 <TIME_ON:4>{hhmm} <BAND:{len(band)}>{band} <MODE:2>CW {extra}<EOR>"


class ContactPlaces(unittest.TestCase):
    def test_a_contacts_own_grid_beats_its_state_and_its_country(self):
        places = lc.contact_places(log_of(rec("W1AAA", gridsquare="FN31pr", state="TX", country="United States", cont="NA")), HOME)
        row = places.iloc[0]
        self.assertEqual(row["c_source"], "grid")
        self.assertFalse(row["c_approx"])
        self.assertAlmostEqual(row["c_lat"], 41.72917, places=3)              # the centre of FN31pr, not of Texas
        self.assertEqual(row["sector"], "NE")

    def test_the_six_character_grid_is_used_when_there_is_one(self):
        four = lc.contact_places(log_of(rec("W1AAA", gridsquare="FN31")), HOME).iloc[0]
        six = lc.contact_places(log_of(rec("W1AAA", gridsquare="FN31pr")), HOME).iloc[0]
        self.assertNotEqual((four["c_lat"], four["c_lon"]), (six["c_lat"], six["c_lon"]))
        self.assertAlmostEqual(four["c_lat"], 41.5, places=3)

    def test_a_station_that_moved_is_placed_where_it_was_each_time(self):
        log = log_of(rec("W1ROVER", "2000", gridsquare="FN31pr"), rec("W1ROVER", "2100", gridsquare="DM79ab"))
        places = lc.contact_places(log, HOME)
        self.assertEqual(places["c_source"].tolist(), ["grid", "grid"])
        self.assertNotEqual(places["c_lat"].iloc[0], places["c_lat"].iloc[1])            # one place per contact, not one per callsign
        self.assertNotEqual(places["sector"].iloc[0], places["sector"].iloc[1])

    def test_without_a_grid_the_state_is_the_fallback_and_is_flagged_approximate(self):
        row = lc.contact_places(log_of(rec("W2BBB", state="NY", country="United States", cont="NA")), HOME).iloc[0]
        self.assertEqual((row["c_source"], bool(row["c_approx"])), ("state", True))
        self.assertEqual((row["c_lat"], row["c_lon"]), lc.STATE_CENTRES["NY"])

    def test_without_a_grid_or_state_the_countrys_centre_by_callsign_is_the_last_resort(self):
        row = lc.contact_places(log_of(rec("DL1ABC")), HOME).iloc[0]
        self.assertEqual((row["c_source"], bool(row["c_approx"])), ("country", True))
        self.assertEqual(row["continent"], "EU")                                          # from the callsign, as the log gave none

    def test_a_grid_that_is_not_valid_is_ignored(self):
        row = lc.contact_places(log_of(rec("DL1ABC", gridsquare="ZZ99")), HOME).iloc[0]
        self.assertEqual(row["c_source"], "country")

    def test_the_continent_in_the_log_is_used_when_it_is_given(self):
        row = lc.contact_places(log_of(rec("DL1ABC", cont="AF")), HOME).iloc[0]
        self.assertEqual(row["continent"], "AF")

    def test_distance_and_bearing_are_from_the_station(self):
        row = lc.contact_places(log_of(rec("W1AAA", gridsquare="EM10")), (30.5, -97.0)).iloc[0]     # EM10 is about 20 km from there: due north-ish, very near
        self.assertLess(row["c_km"], 60)
        row = lc.contact_places(log_of(rec("JA1AAA", gridsquare="PM95")), HOME).iloc[0]
        self.assertGreater(row["c_km"], 9000)
        self.assertEqual(row["sector"], "NW")


class DirectionTable(unittest.TestCase):
    def places(self):
        return lc.contact_places(log_of(
            rec("W1AAA", gridsquare="FN31pr"), rec("W1BBB", gridsquare="FN32aa"), rec("JA1AAA", gridsquare="PM95"),
            rec("W2CCC", state="NY", country="United States", cont="NA"), rec("DL1ABC")), HOME)

    def test_a_direction_counts_only_contacts_placed_by_their_own_grid(self):
        table = lc.contact_direction_table(self.places(), "sector")
        counted = dict(zip(table["Region"], table["Contacts"]))
        self.assertEqual(sum(counted.values()), 3)                                          # the three with grids
        self.assertEqual(table.attrs["counted"], 3)
        self.assertEqual(table.attrs["approximate"], 2)                                     # a state's centre and a country's centre are left out
        self.assertEqual(sum(table["Placed only by state or country"]), 2)
        self.assertEqual(table.attrs["total"], 5)

    def test_the_continent_view_counts_every_contact(self):
        table = lc.contact_direction_table(self.places(), "continent")
        counted = dict(zip(table["Region"], table["Contacts"]))
        self.assertEqual(counted, {"North America": 3, "Europe": 1, "Asia": 1})
        self.assertNotIn("Placed only by state or country", table.columns)


class Bandwidth(unittest.TestCase):
    def test_an_snr_in_another_bandwidth_is_restated_in_2500_hz(self):
        self.assertAlmostEqual(lf.to_reference_bw(10.0, 500.0), 10 + 10 * math.log10(0.2), places=6)     # against less noise: 7 dB lower in 2,500 Hz
        self.assertAlmostEqual(lf.to_reference_bw(10.0, 2500.0), 10.0, places=9)                         # the reference itself does not move
        self.assertAlmostEqual(lf.to_reference_bw(10.0, 50.0), 10 - 10 * math.log10(50), places=6)

    def test_wspr_and_the_thresholds_are_already_in_the_reference_bandwidth(self):
        self.assertEqual(lf.snr_in_reference("wspr", -20.0), -20.0)
        self.assertEqual(lf.snr_in_reference("threshold", -28.0), -28.0)
        self.assertTrue(lf.SNR_BASIS["wspr"][1] and lf.SNR_BASIS["threshold"][1])

    def test_rbn_is_converted_but_stated_as_an_assumption(self):
        self.assertAlmostEqual(lf.snr_in_reference("rbn", 10.0), 10 - 6.9897, places=3)
        self.assertFalse(lf.SNR_BASIS["rbn"][1])                                                          # not certain, and the note says so
        self.assertIn("assumption", lf.SNR_BASIS["rbn"][2])


class Coverage(unittest.TestCase):
    def wspr(self):
        rows = [("T1", "R1", 35.0, -90.0), ("T1", "R1", 35.0, -90.0),                       # the same report twice
                ("T1", "R2", 35.001, -90.001),                                              # another callsign at the same site
                ("T2", "R3", 40.0, -80.0), ("T3", "R4", 50.0, 0.0)]
        return pd.DataFrame(rows, columns=["tx", "rx", "rx_lat", "rx_lon"])

    def test_repeated_reports_collapse_into_stations_and_sites(self):
        c = lf.coverage(self.wspr())
        self.assertEqual(c, {"reports": 5, "transmitters": 3, "receivers": 4, "sites": 3})

    def test_no_wspr_is_no_coverage(self):
        zero = {"reports": 0, "transmitters": 0, "receivers": 0, "sites": 0}
        self.assertEqual(lf.coverage(None), zero)
        self.assertEqual(lf.coverage(self.wspr().iloc[0:0]), zero)

    def test_a_box_is_sparse_below_the_minimum_transmitters_or_receivers(self):
        self.assertTrue(lf.is_sparse(lf.SPARSE_MIN_TRANSMITTERS - 1, 100))
        self.assertTrue(lf.is_sparse(10, lf.SPARSE_MIN_RECEIVERS - 1))
        self.assertFalse(lf.is_sparse(lf.SPARSE_MIN_TRANSMITTERS, lf.SPARSE_MIN_RECEIVERS))


class States(unittest.TestCase):
    def test_each_empty_state_has_its_own_name(self):
        names = {lf.NO_REPORTS, lf.SPARSE, lf.BELOW, lf.UNAVAILABLE, lf.NOT_APPLICABLE, lf.EVIDENCE}
        self.assertEqual(len(names), 6)
        self.assertEqual(set(lf.STATE_NOTES), names)

    def test_a_box_is_in_the_first_state_that_fits(self):
        ok = dict(reports=50, transmitters=5, receivers=40, reaching=10)
        self.assertEqual(lf.cell_state(**ok), lf.EVIDENCE)
        self.assertEqual(lf.cell_state(applicable=False, **ok), lf.NOT_APPLICABLE)
        self.assertEqual(lf.cell_state(available=False, **ok), lf.UNAVAILABLE)
        self.assertEqual(lf.cell_state(**{**ok, "reports": 0}), lf.NO_REPORTS)
        self.assertEqual(lf.cell_state(**{**ok, "transmitters": 1}), lf.SPARSE)
        self.assertEqual(lf.cell_state(**{**ok, "receivers": 5}), lf.SPARSE)
        self.assertEqual(lf.cell_state(**{**ok, "reaching": 0}), lf.BELOW)
        self.assertEqual(lf.cell_state(applicable=False, available=False, reports=0), lf.NOT_APPLICABLE)    # the order matters
        self.assertEqual(lf.cell_state(available=False, reports=0), lf.UNAVAILABLE)
        self.assertEqual(lf.cell_state(reports=3, transmitters=1, receivers=2, reaching=0), lf.SPARSE)       # too thin to call it below the threshold

    def test_rbn_speaks_only_for_cw_and_rtty_when_you_were_calling_cq(self):
        self.assertEqual(lf.rbn_applicability("CW", True), (True, ""))
        self.assertEqual(lf.rbn_applicability("RTTY", True)[0], True)
        self.assertFalse(lf.rbn_applicability("SSB", True)[0])
        self.assertFalse(lf.rbn_applicability("FT8", True)[0])                                            # FT8 is on PSK Reporter, not RBN
        self.assertFalse(lf.rbn_applicability("CW", False)[0])
        ok, why = lf.rbn_applicability("CW", None)
        self.assertFalse(ok)
        self.assertIn("not known", why)


class GridCarriesTheFoundations(unittest.TestCase):
    def log(self):
        rows = [("W1AAA", "2000", "20m"), ("W2BBB", "2010", "20m"), ("W3CCC", "2040", "20m"), ("W4DDD", "2105", "15m")]
        return log_of(*[rec(c, t, b) for c, t, b in rows])

    def wspr(self, transmitters=3):
        recs = []
        for i in range(30):
            for t in ("2026-11-18 20:10", "2026-11-18 20:40", "2026-11-18 21:10"):
                recs.append({"time": T(t), "tx": f"N5T{i % transmitters}", "tx_lat": 31.0, "tx_lon": -102.0, "rx": f"RX{i}", "rx_lat": 35.0 + i * 0.1,
                             "rx_lon": -90.0, "band": "20m", "power": 37.0, "snr": 10.0 if i % 2 == 0 else -30.0})
        return pd.DataFrame(recs)

    def grid(self, wspr=None, **kw):
        wspr = self.wspr() if wspr is None else wspr
        return lc.conditions_grid(self.log(), lambda a, b: wspr[(wspr["time"] > a) & (wspr["time"] <= b)], HOME, 100.0, **kw)

    def test_each_box_carries_the_exact_wspr_window_and_what_it_shares(self):
        g = self.grid()
        g20 = g[g["band"] == "20m"].set_index("slot")
        self.assertEqual((g20.loc[T("2026-11-18 20:30"), "window_start"], g20.loc[T("2026-11-18 20:30"), "window_end"]),
                         (T("2026-11-18 20:00"), T("2026-11-18 21:00")))
        self.assertEqual(g20["shared_min"].tolist(), [0.0, 30.0, 30.0])
        self.assertTrue(g.attrs["bin_min"] == 30)

    def test_each_box_counts_the_transmitters_and_sites_behind_it(self):
        g20 = self.grid().query("band == '20m'").set_index("slot")
        row = g20.loc[T("2026-11-18 20:30")]                                                # the window (20:00, 21:00] holds the 20:10 and 20:40 reports
        self.assertEqual((row["wspr_tx"], row["receivers"], row["wspr_reports"]), (3, 30, 60))
        self.assertEqual(row["wspr_sites"], 30)

    def test_the_state_of_each_box_is_one_of_the_named_states(self):
        g = self.grid()
        self.assertTrue(set(g["state"]) <= {lf.EVIDENCE, lf.NO_REPORTS, lf.SPARSE, lf.BELOW})
        self.assertEqual(g[(g["band"] == "20m") & (g["slot"] == T("2026-11-18 20:30"))]["state"].iloc[0], lf.EVIDENCE)
        self.assertEqual(set(g[g["band"] == "15m"]["state"]), {lf.NO_REPORTS})              # nothing reported on 15m
        thin = self.grid(self.wspr(transmitters=1))                                           # one transmitter is too few to say anything
        self.assertEqual(thin[(thin["band"] == "20m") & (thin["slot"] == T("2026-11-18 20:30"))]["state"].iloc[0], lf.SPARSE)

    def test_a_box_where_nothing_reaches_the_threshold_is_below_it_not_blank(self):
        weak = self.wspr().assign(snr=-30.0)
        g = self.grid(weak)
        self.assertEqual(g[(g["band"] == "20m") & (g["slot"] == T("2026-11-18 20:30"))]["state"].iloc[0], lf.BELOW)

    def test_15_minute_bins_line_up_and_share_three_quarters_of_the_hour(self):
        g = self.grid(bin_min=15)
        slots = sorted(g["slot"].unique())
        self.assertTrue(all(s.minute % 15 == 0 for s in slots))
        self.assertEqual(g.attrs["bin_min"], 15)
        g20 = g[g["band"] == "20m"].sort_values("slot")
        self.assertEqual(g20["shared_min"].iloc[1], 45.0)
        self.assertEqual(int(g20[g20["slot"] == T("2026-11-18 20:00")]["contacts"].iloc[0]), 2)    # the 20:00 and 20:10 contacts
        self.assertEqual(int(g20[g20["slot"] == T("2026-11-18 20:30")]["contacts"].iloc[0]), 1)

    def test_the_rbn_spots_are_binned_the_same_way_as_the_grid(self):
        g = self.grid(bin_min=15)
        locs = {"EU1SKIM": (48.0, 2.0)}
        spots = pd.DataFrame({"spotter": ["EU1SKIM", "EU1SKIM"], "band": ["20m", "20m"], "snr": [10, 12],
                              "time": pd.to_datetime(["2026-11-18 20:05", "2026-11-18 20:35"])})
        out = lc.add_rbn_far(g, spots, locs, HOME)
        got = out[out["band"] == "20m"].set_index("slot")["rbn_far"]
        self.assertEqual(int(got.loc[T("2026-11-18 20:00")]), 1)
        self.assertEqual(int(got.loc[T("2026-11-18 20:30")]), 1)
        self.assertEqual(int(got.loc[T("2026-11-18 20:15")]), 0)
        self.assertEqual(out.attrs["bin_min"], 15)                                           # it keeps what the grid carries

    def test_the_radius_asked_for_is_kept_and_said_in_the_words(self):
        g = self.grid(radius_km=400)
        self.assertEqual(g.attrs["evidence"]["radius_km"], 400)
        html = lh.dx_windows_html(g, [], 100.0, "CW", None, "estimate")
        self.assertIn("within 400 km (249 miles) of you", html)
        self.assertNotIn("300 miles of you", html)
        self.assertIn("within 400 km (249 miles) of you", lh.conditions_html(g, lc.conditions_notes(g), 100.0, "CW"))

    def test_a_grid_made_without_a_radius_still_says_300_miles(self):
        g = self.grid()
        self.assertIn("within 483 km (300 miles) of you", lh.dx_windows_html(g, [], 100.0, "CW", None, "observed"))

    def test_the_coverage_table_lists_the_boxes_with_their_exact_windows(self):
        table = lc.coverage_table(self.grid())
        self.assertEqual(list(table.columns), lc.COVERAGE_COLUMNS)
        first = table[table["Band"] == "20m"].iloc[1]
        self.assertEqual(first["Box (UTC)"], "20:30–21:00")
        self.assertEqual(first["WSPR window (UTC)"], "20:00–21:00")
        self.assertEqual(first["Shared with the box before (min)"], 30)
        self.assertEqual((first["Transmitters"], first["Receivers"], first["Reports"]), (3, 30, 60))
        self.assertEqual(first["What it can say"], lf.EVIDENCE)
        self.assertEqual(list(lc.coverage_table(pd.DataFrame()).columns), lc.COVERAGE_COLUMNS)

    def test_a_grid_that_spans_days_labels_its_boxes_with_the_date(self):
        log = log_of(rec("W1AAA", "2000"), rec("W2BBB", "2010").replace("20261118", "20261120"))
        wspr = self.wspr()
        g = lc.conditions_grid(log, lambda a, b: wspr[(wspr["time"] > a) & (wspr["time"] <= b)], HOME, 100.0)
        self.assertEqual(g["panel"].nunique(), 2)
        self.assertIn("18 Nov", lc.coverage_table(g)["Box (UTC)"].iloc[0])


if __name__ == "__main__":
    unittest.main()
