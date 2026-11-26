"""The batch after the fourth review: logged coordinates, honest labels for how a station was placed, one set of park counts, dated times on a log over several days, and a
labelled signal card."""
import unittest

import pandas as pd

import data_sources as ds
import log_check as lc
import log_check_html as lh
import log_highlights as hl

HOME = (31.0, -102.0)
T = pd.Timestamp


def log_of(*records):
    return lc.parse_adif("<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(records) + "\n")


def rec(call, hhmm="2010", band="20m", day="20261118", **fields):
    extra = "".join(f"<{k.upper()}:{len(str(v))}>{v} " for k, v in fields.items())
    return f"<CALL:{len(call)}>{call} <QSO_DATE:8>{day} <TIME_ON:4>{hhmm} <BAND:{len(band)}>{band} <MODE:2>CW {extra}<EOR>"


class LoggedCoordinates(unittest.TestCase):
    def test_adif_coordinates_read_as_decimal_degrees(self):
        self.assertAlmostEqual(lc.adif_coordinate("N031 28.750"), 31.47917, places=4)
        self.assertAlmostEqual(lc.adif_coordinate("W100 29.250"), -100.4875)
        self.assertAlmostEqual(lc.adif_coordinate("S033 51.000"), -33.85)
        self.assertAlmostEqual(lc.adif_coordinate("31.4792"), 31.4792)                             # a plain decimal, as some programs write it
        for bad in ("", "x", "N091 00.000", "N031 61.0", "400"):
            self.assertIsNone(lc.adif_coordinate(bad), bad)

    def test_the_reader_keeps_the_other_stations_lat_and_lon_and_not_ours(self):
        log = log_of(rec("JA1ABC", lat="N035 42.000", lon="E139 48.000", my_lat="N031 00.000", my_lon="W102 00.000"), rec("DL1XYZ", "2011"))
        self.assertAlmostEqual(log["their_lat"].iloc[0], 35.7)
        self.assertAlmostEqual(log["their_lon"].iloc[0], 139.8)
        self.assertTrue(pd.isna(log["their_lat"].iloc[1]))

    def test_coordinates_in_the_log_place_a_contact_after_its_grid_and_before_a_park(self):
        log = log_of(rec("JA1ABC", lat="N035 42.000", lon="E139 48.000"), rec("JA2GRID", "2011", gridsquare="PM85", lat="N035 42.000", lon="E139 48.000"),
                     rec("W1PARK", "2012", pota_ref="US-1234", lat="N040 00.000", lon="W075 00.000"))
        log.attrs["ref_places"] = {"US-1234": (10.0, 10.0)}
        p = lc.contact_places(log, HOME).set_index("call")
        self.assertEqual((p.loc["JA1ABC", "c_source"], p.loc["JA2GRID", "c_source"], p.loc["W1PARK", "c_source"]), ("coords", "grid", "coords"))
        self.assertAlmostEqual(p.loc["JA1ABC", "c_lat"], 35.7, places=3)
        self.assertFalse(p.loc["JA1ABC", "c_approx"])
        self.assertIn("coords", lc.PRECISE_SOURCES)

    def test_a_log_with_no_coordinates_places_as_before(self):
        p = lc.contact_places(log_of(rec("DL1ABC", country="Germany")), HOME)
        self.assertEqual(p.iloc[0]["c_source"], "country")

    def test_the_maps_use_the_grid_most_of_a_stations_contacts_carry_and_fall_back_to_its_coordinates(self):
        from views.log_view import _log_grids
        log = log_of(rec("W1MOVE", gridsquare="FN31"), rec("W1MOVE", "2011", gridsquare="EM10"), rec("W1MOVE", "2012", gridsquare="EM10"),
                     rec("JA1ABC", "2013", lat="N035 42.000", lon="E139 48.000"), rec("W1NONE", "2014"))
        grids = _log_grids(log)
        self.assertEqual(grids["W1MOVE"], "EM10")                                                  # not simply the first one logged
        self.assertTrue(grids["JA1ABC"].startswith("PM95"))
        self.assertNotIn("W1NONE", grids)


class HonestPlaceLabels(unittest.TestCase):
    def test_each_way_of_placing_a_station_says_what_it_is(self):
        self.assertEqual(lc.place_note("grid", "grid square in the log"), "Logged grid: the centre of its grid square")
        home = lc.place_note("grid", "FCC")
        self.assertIn("Registered home location (FCC)", home)
        self.assertIn("where it operated is not confirmed", home)
        self.assertIn("Registered home location (HamQTH callbook)", lc.place_note("grid", "HamQTH callbook"))
        self.assertTrue(lc.place_note("park", "park reference").startswith("Park or summit reference"))
        self.assertTrue(lc.place_note("summit", "summit reference").startswith("Park or summit reference"))
        for level in ("area", "state", "country"):
            self.assertTrue(lc.place_note(level, "x").startswith("Approximate"), level)
        self.assertIn("call area", lc.place_note("area", "HamQTH call area, Japan (Kinki)"))

    def test_a_park_placed_contact_is_not_called_a_logged_grid(self):
        placed = ds.load_contact_places([("W1PARK", "PA", "United States")], {}, ref_grids={"W1PARK": ("FN20AB", "park")})
        row = placed.loc["W1PARK"]
        self.assertEqual(row["level"], "park")
        self.assertNotIn("grid square in the log", row["source"])
        shown = lc.where_worked(log_of(rec("W1PARK", pota_ref="US-1234")), placed)
        self.assertTrue(shown.iloc[0]["place"].startswith("Park or summit reference"))


class OneSetOfParkCounts(unittest.TestCase):
    def log(self):
        mine = dict(my_pota_ref="US-3053")
        return log_of(rec("K1AAA", pota_ref="US-1111", **mine), rec("K1BBB", "2011", pota_ref="US-1111,US-2222", **mine), rec("K1CCC", "2012", pota_ref="US-3053", **mine),
                      rec("K1DDD", "2013", **mine))

    def test_the_summary_counts_the_other_parks_the_way_the_map_does(self):
        s = lc.summary(self.log())
        self.assertEqual((s["park_to_park"], s["parks"], s["park_same"]), (2, 2, 1))              # two contacts, two other parks, and one that named our own
        t = lc.park_to_park(self.log(), "US-3053", {"US-1111": (40.0, -75.0, "A"), "US-2222": (47.0, -122.0, "B")})
        self.assertEqual((t.attrs["with_ref"], len(t), t.attrs["same"]), (s["park_to_park"], s["parks"], s["park_same"]))

    def test_a_contact_naming_two_parks_is_one_contact(self):
        t = lc.park_to_park(self.log(), "US-3053", {})
        self.assertEqual(t.attrs["with_ref"], 2)                                                   # K1BBB names two parks but is one contact

    def test_the_fact_on_the_page_says_other_parks_and_the_one_that_named_our_own(self):
        log = self.log()
        html = lh.followers_html(log, lc.summary(log))
        self.assertIn("with 2 other parks; 1 more named your own park.", html)
        none = log_of(rec("K1AAA", my_pota_ref="US-3053"))
        self.assertNotIn("Park to park", lh.followers_html(none, lc.summary(none)))


class DatesOnALogOverSeveralDays(unittest.TestCase):
    def places(self):
        log = log_of(rec("W1AAA", "2300", day="20261112"), rec("DL1ABC", "0100", day="20261113", country="Germany", cont="EU"),
                     rec("ZS1ABC", "1817", day="20261113", country="South Africa", cont="AF"))
        return lc.contact_places(log, HOME)

    def test_a_time_carries_its_day_on_a_log_over_two_days(self):
        first = hl.first_by_continent(self.places(), "NA")
        far = hl.farthest_by_band(self.places())
        dated = hl.highlight_lines(first, far, None, True)
        plain = hl.highlight_lines(first, far, None, False)
        self.assertIn("Africa came last, at 13 Nov 18:17 UTC", " ".join(dated))
        self.assertIn("Africa came last, at 18:17 UTC", " ".join(plain))
        self.assertIn("13 Nov 18:17", lh.highlights_html(first, far, dated, True))
        self.assertNotIn("13 Nov", lh.highlights_html(first, far, plain, False))


class TheSignalCardIsLabelled(unittest.TestCase):
    def source(self):
        import views.log_view as view
        with open(view.__file__, encoding="utf-8") as f:
            return f.read()

    def test_the_card_near_the_top_says_it_is_experimental_and_counts_skimmers(self):
        src = self.source()
        self.assertIn("Experimental: about", src)
        self.assertIn("skimmers.", src)
        self.assertNotIn("receiving stations.\", \"sec-signal\"", src)

    def test_the_page_has_its_own_title_like_the_other_analysis_pages(self):
        src = self.source()
        self.assertIn("st.title(\":material/fact_check: Log analysis\")", src)
        self.assertIn("brand_strip()", src)


if __name__ == "__main__":
    unittest.main()
