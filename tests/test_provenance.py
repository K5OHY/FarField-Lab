"""Where a contact was, and how sure the page is: parks and summits place a contact, and the farthest contact is never decided by a centre."""
import unittest
from unittest import mock

import pandas as pd
from geographiclib.geodesic import Geodesic

import data_sources as ds
import log_check as lc
import log_highlights as hl
import share_card as sc

HOME = (31.0, -102.0)
T = pd.Timestamp


def log_of(*records):
    return lc.parse_adif("<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(records) + "\n")


def rec(call, hhmm="2010", band="20m", **fields):
    extra = "".join(f"<{k.upper()}:{len(str(v))}>{v} " for k, v in fields.items())
    return f"<CALL:{len(call)}>{call} <QSO_DATE:8>20261118 <TIME_ON:4>{hhmm} <BAND:{len(band)}>{band} <MODE:2>CW {extra}<EOR>"


PARKS = {"US-1234": (40.0, -75.0), "US-9999": (47.0, -122.0)}


class ParkAndSummitPlacement(unittest.TestCase):
    def test_a_contact_with_another_park_is_placed_at_that_park(self):
        log = log_of(rec("W1PARK", pota_ref="US-1234", state="PA"))
        row = lc.contact_places(log, HOME, PARKS).iloc[0]
        self.assertEqual(row["c_source"], "park")
        self.assertFalse(row["c_approx"])
        self.assertAlmostEqual(row["c_lat"], 40.0)
        self.assertAlmostEqual(row["c_km"], Geodesic.WGS84.Inverse(HOME[0], HOME[1], 40.0, -75.0)["s12"] / 1000, places=3)

    def test_the_place_of_a_contact_at_our_own_park_is_next_to_us_not_hundreds_of_km_away(self):
        log = log_of(rec("N5NU", band="2m", pota_ref="US-3053", state="TX"))
        by_state = lc.contact_places(log, HOME).iloc[0]
        by_park = lc.contact_places(log, HOME, {"US-3053": (31.01, -102.01)}).iloc[0]
        self.assertEqual(by_state["c_source"], "state")
        self.assertGreater(by_state["c_km"], 50)                                                   # a state's centre is nowhere near the park
        self.assertLess(by_park["c_km"], 5)                                                        # the park is where the contact was

    def test_the_order_is_grid_then_park_then_state_then_country(self):
        log = log_of(rec("W1GRID", pota_ref="US-1234", state="PA", gridsquare="FN31"), rec("W1PARK", "2011", pota_ref="US-1234", state="PA"),
                     rec("W1STATE", "2012", state="PA"), rec("DL1CTRY", "2013", country="Germany"), rec("W1UNKNOWN", "2014", pota_ref="US-0000", state="PA"))
        p = lc.contact_places(log, HOME, PARKS).set_index("call")["c_source"].to_dict()
        self.assertEqual(p, {"W1GRID": "grid", "W1PARK": "park", "W1STATE": "state", "DL1CTRY": "country", "W1UNKNOWN": "state"})      # a park nobody knows falls back

    def test_a_two_fer_uses_the_first_park_that_is_known(self):
        log = log_of(rec("W1TWOFER", pota_ref="US-0000,US-9999", state="WA"))
        row = lc.contact_places(log, HOME, PARKS).iloc[0]
        self.assertEqual(row["c_source"], "park")
        self.assertAlmostEqual(row["c_lat"], 47.0)

    def test_a_summit_places_a_contact_when_there_is_no_park(self):
        log = log_of(rec("W7SUMMIT", sota_ref="W7W/CS-001", state="WA"))
        row = lc.contact_places(log, HOME, {"W7W/CS-001": (48.5, -121.0)}).iloc[0]
        self.assertEqual((row["c_source"], row["c_approx"]), ("summit", False))

    def test_the_places_can_travel_with_the_log(self):
        log = log_of(rec("W1PARK", pota_ref="US-1234", state="PA"))
        self.assertEqual(lc.contact_places(log, HOME).iloc[0]["c_source"], "state")
        log.attrs["ref_places"] = PARKS
        self.assertEqual(lc.contact_places(log, HOME).iloc[0]["c_source"], "park")

    def test_a_park_places_a_contact_in_a_direction_not_between_two(self):
        log = log_of(rec("W1PARK", pota_ref="US-1234", state="PA"))
        row = lc.contact_places(log, HOME, PARKS).iloc[0]
        self.assertIsInstance(row["sector_whole"], str)                                            # a known point has one direction, unlike a state that spreads over several
        self.assertEqual(row["sector_basis"], "park")

    def test_the_parks_and_summits_to_look_up_are_the_other_stations_not_ours(self):
        log = log_of(rec("W1PARK", pota_ref="US-1234, us-9999 ", my_pota_ref="US-3053"), rec("W7SUMMIT", sota_ref="W7W/CS-001"), rec("K1PLAIN"))
        pota, sota = lc.contact_references(log)
        self.assertEqual(pota, {"US-1234", "US-9999"})
        self.assertEqual(sota, {"W7W/CS-001"})


class LookingUpReferences(unittest.TestCase):
    def test_each_reference_is_asked_for_once_and_one_that_fails_is_left_out(self):
        ds._REF_PLACES.clear()
        calls = []

        def fake_get(url, **kw):
            calls.append(url)
            if "US-0000" in url:
                raise ds.requests.ConnectionError("down")
            resp = mock.Mock(content=b"x")
            resp.raise_for_status = lambda: None
            resp.json = lambda: ({"latitude": 40.1, "longitude": -75.2} if "park" in url else {"latitude": 48.5, "longitude": -121.0})
            return resp

        with mock.patch.object(ds.requests, "get", fake_get):
            found = ds.load_reference_places(["US-1234", "US-0000"], ["W7W/CS-001"])
            again = ds.load_reference_places(["US-1234"], [])
        self.assertEqual(found, {"US-1234": (40.1, -75.2), "W7W/CS-001": (48.5, -121.0)})
        self.assertNotIn("US-0000", found)                                                        # a reference that could not be reached is simply not placed
        self.assertEqual(again, {"US-1234": (40.1, -75.2)})
        self.assertEqual(sum("US-1234" in c for c in calls), 1)                                   # remembered, not asked twice
        self.assertEqual(ds.load_reference_places([], []), {})
        ds._REF_PLACES.clear()

    def test_the_maps_place_a_contact_at_its_park_as_a_grid_square(self):
        from views.log_view import _log_grids
        log = log_of(rec("W1PARK", pota_ref="US-1234"), rec("W1GRID", "2011", pota_ref="US-1234", gridsquare="FN31"), rec("W1NONE", "2012"))
        log.attrs["ref_places"] = PARKS
        grids = _log_grids(log)
        self.assertEqual(grids["W1GRID"], "FN31")                                                  # the log's own grid wins
        self.assertEqual(len(grids["W1PARK"]), 6)                                                  # the park, as the grid square it is in
        self.assertNotIn("W1NONE", grids)


class FarthestIsNeverDecidedByACentre(unittest.TestCase):
    def places(self, *records, refs=None):
        log = log_of(*records)
        if refs:
            log.attrs["ref_places"] = refs
        return lc.contact_places(log, HOME)

    def test_a_precisely_placed_contact_keeps_the_answer_against_a_country_that_is_only_slightly_farther(self):
        p = self.places(rec("DL1GRID", gridsquare="JN58"), rec("HA1CTRY", "2011", country="Hungary"))
        far = lc.farthest_contact(p)
        self.assertEqual((far["call"], far["approx"]), ("DL1GRID", False))
        self.assertEqual(far["rough"]["place"], "Hungary")                                         # the farther one is said, but does not take the place: a centre can be this far out
        self.assertGreater(far["rough"]["km"], far["km"])
        self.assertLess(far["rough"]["km"] - far["km"], lc.ROUGH_MARGIN_KM)

    def test_a_country_far_beyond_the_farthest_known_place_leads_and_is_called_rough(self):
        p = self.places(rec("W1PARK", pota_ref="US-1234", state="PA"), rec("JA1CTRY", "2011", country="Japan"), refs=PARKS)
        far = lc.farthest_contact(p)
        self.assertEqual((far["call"], far["approx"], far["place"]), ("JA1CTRY", True, "Japan"))
        self.assertEqual(far["precise"]["call"], "W1PARK")                                         # the best placed contact is kept beside it
        table = hl.farthest_by_band(p)
        line = hl._farthest_line(table)
        self.assertTrue(line.startswith("The farthest contact was with Japan (JA1CTRY on 20m), about"), line)
        self.assertIn("placed only by country, so that distance is rough. The farthest placed by a grid or a park was W1PARK", line)
        import log_check_html as lh
        self.assertIn("farthest placed precisely: W1PARK", lh.highlights_html(hl.first_by_continent(p), table, [line]))

    def test_stations_at_the_same_centre_are_all_named_and_not_ranked(self):
        p = self.places(rec("JA1SKE", band="15m", country="Japan"), rec("JH3EUJ", "2011", band="15m", country="Japan"), rec("EA4R", "2012", band="15m", country="Spain"))
        far = lc.farthest_contact(p)
        self.assertTrue(far["approx"])
        self.assertEqual(sorted(far["calls"]), ["JA1SKE", "JH3EUJ"])                               # two stations at exactly the same distance: neither is 'the' farthest
        self.assertEqual(far["place"], "Japan")

    def test_a_band_can_be_asked_for_and_nothing_placed_is_none(self):
        p = self.places(rec("DL1GRID", gridsquare="JN58"), rec("JA1ZZZ", "2011", band="15m", gridsquare="PM95"))
        self.assertEqual(lc.farthest_contact(p, "20m")["call"], "DL1GRID")
        self.assertEqual(lc.farthest_contact(p, "15m")["call"], "JA1ZZZ")
        self.assertIsNone(lc.farthest_contact(p, "40m"))
        self.assertIsNone(lc.farthest_contact(None))

    def test_a_park_is_precise_enough_to_win(self):
        p = self.places(rec("W1PARK", pota_ref="US-1234", state="PA"), rec("W1STATE", "2011", state="FL"), refs=PARKS)
        self.assertEqual(lc.farthest_contact(p)["call"], "W1PARK")

    def test_the_table_the_sentence_and_the_card_say_the_same_thing(self):
        p = self.places(rec("JA1SKE", band="15m", country="Japan"), rec("JH3EUJ", "2011", band="15m", country="Japan"))
        table = hl.farthest_by_band(p)
        self.assertEqual(table.iloc[0]["calls"], ["JA1SKE", "JH3EUJ"])
        self.assertTrue(table.iloc[0]["approx"])
        line = hl._farthest_line(table)
        self.assertIn("The farthest contacts were in Japan (JA1SKE and JH3EUJ on 15m), about", line)
        self.assertIn("placed at the centre of its country and the distance is rough", line)
        far = sc.map_facts(p, HOME)["farthest"]
        self.assertTrue(far["approx"])
        self.assertEqual(sc._farthest_text(far).split(" (")[0], "Farthest: Japan")
        self.assertIn("about", sc._farthest_text(far))

    def test_a_precise_contact_is_named_with_its_distance_and_a_slightly_farther_rough_one_is_mentioned(self):
        import log_check_html as lh
        p = self.places(rec("DL1GRID", gridsquare="JN58"), rec("HA1CTRY", "2011", country="Hungary"))
        table = hl.farthest_by_band(p)
        line = hl._farthest_line(table)
        self.assertTrue(line.startswith("The farthest contact was DL1GRID"))
        self.assertIn("Contacts with Hungary (HA1CTRY) were farther", line)
        self.assertIn("placed only by country, so that distance is rough", line)
        html = lh.highlights_html(hl.first_by_continent(p), table, [line])
        self.assertIn("farther, by country only", html)
        self.assertEqual(sc._farthest_text(sc.map_facts(p, HOME)["farthest"]).split(",")[0], "Farthest: DL1GRID")
        wide = self.places(rec("W1GRID", gridsquare="FN31"), rec("JA1CTRY", "2011", country="Japan"))
        self.assertTrue(sc._farthest_text(sc.map_facts(wide, HOME)["farthest"]).startswith("Farthest: Japan (JA1CTRY), about"))

    def test_nothing_in_the_new_sentences_breaks_the_wording_guard(self):
        import log_openings as lo
        for records in ((rec("JA1SKE", country="Japan"), rec("JH3EUJ", "2011", country="Japan")), (rec("DL1GRID", gridsquare="JN58"), rec("JA1CTRY", "2011", country="Japan")),
                        (rec("DL1GRID", gridsquare="JN58"), rec("HA1CTRY", "2011", country="Hungary"))):
            line = hl._farthest_line(hl.farthest_by_band(self.places(*records)))
            self.assertEqual(lo.unsupported_claims(line), [], line)


if __name__ == "__main__":
    unittest.main()
