"""The heat map of where nearby WSPR reached on one band."""
import unittest

import pandas as pd
from geographiclib.geodesic import Geodesic

import log_check as lc
from maps import reach_map

HOME = (31.0, -102.0)
T = pd.Timestamp


def grid_with(rows):
    g = pd.DataFrame({"slot": [T("2026-11-18 20:00")], "band": ["20m"]})
    g.attrs["receivers"] = pd.DataFrame(rows, columns=["band", "rx", "km", "bearing", "verdict", "slot"])
    return g


ROWS = [("20m", "DL1AAA", 8000.0, 40.0, "good", T("2026-11-18 20:00")), ("20m", "DL1AAA", 8000.0, 40.0, "good", T("2026-11-18 20:30")),
        ("20m", "DL1AAA", 8000.0, 40.0, "good", T("2026-11-18 21:00")), ("20m", "DL2BBB", 8200.0, 42.0, "heard", T("2026-11-18 20:00")),
        ("20m", "W5NEAR", 300.0, 10.0, "good", T("2026-11-18 20:00")), ("15m", "JA1CCC", 10000.0, 330.0, "good", T("2026-11-18 20:00"))]


class ReachPoints(unittest.TestCase):
    def test_a_receiving_station_is_a_point_with_the_number_of_half_hours_it_decoded_you(self):
        pts = lc.reach_points(grid_with(ROWS), HOME, "20m", "heard")
        self.assertEqual(sorted(pts["rx"]), ["DL1AAA", "DL2BBB", "W5NEAR"])
        self.assertEqual(int(pts.set_index("rx").loc["DL1AAA", "windows"]), 3)
        self.assertEqual(int(pts.set_index("rx").loc["DL2BBB", "windows"]), 1)

    def test_only_the_band_asked_for_is_used(self):
        self.assertEqual(list(lc.reach_points(grid_with(ROWS), HOME, "15m", "heard")["rx"]), ["JA1CCC"])
        self.assertTrue(lc.reach_points(grid_with(ROWS), HOME, "40m", "heard").empty)

    def test_what_looked_strong_enough_is_a_smaller_set_than_what_was_decoded(self):
        good = lc.reach_points(grid_with(ROWS), HOME, "20m", "good")
        self.assertEqual(sorted(good["rx"]), ["DL1AAA", "W5NEAR"])                              # DL2BBB decoded WSPR but did not look strong enough for the power

    def test_it_can_be_limited_to_some_half_hours_and_to_receivers_beyond_ground_wave(self):
        some = lc.reach_points(grid_with(ROWS), HOME, "20m", "heard", {T("2026-11-18 20:30")})
        self.assertEqual(list(some["rx"]), ["DL1AAA"])
        far = lc.reach_points(grid_with(ROWS), HOME, "20m", "heard", None, 500)
        self.assertNotIn("W5NEAR", set(far["rx"]))

    def test_a_receivers_place_is_found_again_from_its_distance_and_bearing(self):
        pts = lc.reach_points(grid_with(ROWS), HOME, "20m", "heard").set_index("rx")
        inv = Geodesic.WGS84.Inverse(HOME[0], HOME[1], pts.loc["DL1AAA", "lat"], pts.loc["DL1AAA", "lon"])
        self.assertAlmostEqual(inv["s12"] / 1000, 8000.0, places=3)
        self.assertAlmostEqual(inv["azi1"] % 360, 40.0, places=3)

    def test_no_grid_or_no_receivers_is_an_empty_table_with_the_columns(self):
        self.assertEqual(list(lc.reach_points(None, HOME, "20m").columns), lc.REACH_COLUMNS)
        self.assertTrue(lc.reach_points(pd.DataFrame({"slot": [], "band": []}), HOME, "20m").empty)


class ReachMap(unittest.TestCase):
    def contacts(self):
        return pd.DataFrame({"call": ["DL1ZZZ"], "c_lat": [50.0], "c_lon": [10.0]})

    def test_the_map_has_the_heat_your_star_and_your_contacts(self):
        pts = lc.reach_points(grid_with(ROWS), HOME, "20m", "heard")
        html = reach_map(pts, self.contacts(), HOME, "20m").get_root().render()
        self.assertIn("heatLayer", html)
        self.assertIn("DL1ZZZ on 20m", html)                                                     # the contact is on it, with its band
        self.assertIn("You", html)

    def test_a_band_with_contacts_but_no_receivers_still_draws_without_heat(self):
        empty = lc.reach_points(grid_with(ROWS), HOME, "40m", "heard")
        html = reach_map(empty, self.contacts(), HOME, "40m").get_root().render()
        self.assertNotIn("heatLayer", html)
        self.assertIn("DL1ZZZ on 40m", html)

    def test_a_contact_with_no_place_is_left_off(self):
        odd = pd.DataFrame({"call": ["NOPLACE"], "c_lat": [float("nan")], "c_lon": [float("nan")]})
        pts = lc.reach_points(grid_with(ROWS), HOME, "20m", "heard")
        self.assertNotIn("NOPLACE", reach_map(pts, odd, HOME, "20m").get_root().render())


if __name__ == "__main__":
    unittest.main()
