"""The park to park map: the other parks (or summits) the log names for its contacts, found only where the log carries them."""
import unittest
from unittest import mock

import pandas as pd

import log_check as lc
import maps

T = pd.Timestamp
OWN = "US-3053"
PLACES = {"US-1111": (40.0, -75.0, "Valley Forge"), "US-2222": (47.0, -122.0, "Rainier View"), "US-3333": (35.0, -90.0, "River Park"), "W7W/CS-001": (48.5, -121.0, "Mount Baker")}


def log_of(*records):
    return lc.parse_adif("<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(records) + "\n")


def rec(call, hhmm="2010", band="20m", **fields):
    extra = "".join(f"<{k.upper()}:{len(str(v))}>{v} " for k, v in fields.items())
    return f"<CALL:{len(call)}>{call} <QSO_DATE:8>20261118 <TIME_ON:4>{hhmm} <BAND:{len(band)}>{band} <MODE:2>CW {extra}<EOR>"


def mine(call, hhmm="2010", band="20m", **fields):
    return rec(call, hhmm, band, my_pota_ref=OWN, **fields)


class TheTable(unittest.TestCase):
    def test_each_park_the_log_names_is_one_row_with_who_and_when(self):
        log = log_of(mine("K1AAA", "2010", pota_ref="US-1111"), mine("K1BBB", "2015", "40m", pota_ref="US-1111"), mine("W7CCC", "2020", pota_ref="US-2222"), mine("N0PLAIN", "2025"))
        t = lc.park_to_park(log, OWN, PLACES)
        self.assertEqual(list(t["ref"]), ["US-1111", "US-2222"])                                   # most contacts first
        first = t.iloc[0]
        self.assertEqual((first["contacts"], first["stations"], first["name"]), (2, 2, "Valley Forge"))
        self.assertEqual(first["bands"], ["40m", "20m"])
        self.assertEqual((first["first"], first["last"]), (T("2026-11-18 20:10"), T("2026-11-18 20:15")))
        self.assertEqual(t.attrs["with_ref"], 3)
        self.assertEqual(t.attrs["total"], 4)                                                      # four contacts from the park, three of them named a park

    def test_a_two_fer_counts_for_both_its_parks(self):
        log = log_of(mine("K1AAA", pota_ref="US-1111,US-3333"))
        self.assertEqual(sorted(lc.park_to_park(log, OWN, PLACES)["ref"]), ["US-1111", "US-3333"])

    def test_only_contacts_made_from_this_park_count_and_never_the_park_itself(self):
        log = log_of(mine("K1AAA", pota_ref="US-1111"), rec("K1BBB", "2011", my_pota_ref="US-9999", pota_ref="US-2222"), mine("K1CCC", "2012", pota_ref=OWN))
        t = lc.park_to_park(log, OWN, PLACES)
        self.assertEqual(list(t["ref"]), ["US-1111"])                                              # a contact from another park of the log, or one naming our own park, is not here

    def test_a_park_nobody_can_place_is_listed_but_has_no_place(self):
        log = log_of(mine("K1AAA", pota_ref="US-1111"), mine("K1BBB", "2011", pota_ref="US-0000"))
        t = lc.park_to_park(log, OWN, PLACES).set_index("ref")
        self.assertTrue(pd.isna(t.loc["US-0000", "lat"]))
        self.assertEqual(lc.park_to_park(log, OWN, PLACES).attrs["unplaced"], 1)

    def test_no_park_to_park_contact_is_an_empty_table_that_still_says_how_many_were_made(self):
        t = lc.park_to_park(log_of(mine("K1AAA"), mine("K1BBB", "2011")), OWN, PLACES)
        self.assertTrue(t.empty)
        self.assertEqual((t.attrs["total"], t.attrs["with_ref"]), (2, 0))
        self.assertTrue(lc.park_to_park(log_of(rec("K1AAA")), OWN, PLACES).empty)                  # a log with no park at all

    def test_a_summit_log_finds_summit_to_summit(self):
        log = log_of(rec("W7SUM", my_sota_ref="W7W/CS-002", sota_ref="W7W/CS-001"), rec("W7PARK", "2011", my_sota_ref="W7W/CS-002", pota_ref="US-1111"))
        t = lc.park_to_park(log, "W7W/CS-002", PLACES, "SOTA")
        self.assertEqual(list(t["ref"]), ["W7W/CS-001"])                                           # a park is not a summit
        self.assertEqual(t.iloc[0]["name"], "Mount Baker")

    def test_places_without_a_name_still_work(self):
        log = log_of(mine("K1AAA", pota_ref="US-1111"))
        t = lc.park_to_park(log, OWN, {"US-1111": (40.0, -75.0)})                                  # a two number place, as the tests and older answers have
        self.assertEqual((t.iloc[0]["name"], t.iloc[0]["lat"]), ("", 40.0))


class TheMap(unittest.TestCase):
    def table(self):
        log = log_of(mine("K1AAA", "2010", pota_ref="US-1111"), mine("K1BBB", "2015", "40m", pota_ref="US-1111"), mine("W7CCC", "2020", pota_ref="US-2222"), mine("N0UNK", "2030", pota_ref="US-0000"))
        return lc.park_to_park(log, OWN, PLACES)

    def test_the_map_shows_your_park_and_the_others_with_who_was_there(self):
        html = maps.p2p_map((31.4556, -100.497, "US-3053 San Angelo"), self.table()).get_root().render()
        for text in ("US-3053 San Angelo", "US-1111", "Valley Forge", "K1AAA, K1BBB", "US-2222", "Rainier View"):
            self.assertIn(text, html)
        self.assertNotIn("US-0000", html)                                                          # not placed, so not drawn
        self.assertEqual(html.count("L.polyline("), 2)                                             # a line to each placed park

    def test_one_nearby_park_does_not_zoom_in_without_limit(self):
        log = log_of(mine("K1AAA", pota_ref="US-1111"))
        near = {"US-1111": (31.46, -100.50, "Next Door")}
        t = lc.park_to_park(log, OWN, near)
        html = maps.p2p_map((31.4556, -100.497, "US-3053"), t).get_root().render()
        self.assertIn("fitBounds", html)

    def test_a_table_with_nothing_placed_still_draws_your_park(self):
        empty = self.table().iloc[0:0]
        self.assertIn("US-3053", maps.p2p_map((31.4556, -100.497, "US-3053"), empty).get_root().render())


class TheCardBlock(unittest.TestCase):
    def block(self, log):
        import views.log_view as view
        col = mock.MagicMock()
        log.attrs["ref_places"] = PLACES
        with mock.patch.object(view, "p2p_map", wraps=maps.p2p_map):
            view._p2p_block(col, log, OWN, "POTA", (31.4556, -100.497, "US-3053 San Angelo"), "park")
        return col

    def test_with_park_contacts_there_is_a_map_and_a_line_that_says_what_it_cannot_show(self):
        col = self.block(log_of(mine("K1AAA", pota_ref="US-1111"), mine("W7CCC", "2020", pota_ref="US-2222"), mine("N0PLAIN", "2025")))
        col.iframe.assert_called_once()
        caption = col.caption.call_args[0][0]
        self.assertIn("2 parks reached, 2 contacts with 2 stations", caption)
        self.assertIn("only the contacts where your log names the other station's park (2 of the 3 made from US-3053)", caption)

    def test_with_none_it_says_why_instead_of_leaving_a_gap(self):
        col = self.block(log_of(mine("N0PLAIN", "2025")))
        col.iframe.assert_not_called()
        self.assertIn("No park to park contacts are recorded", col.caption.call_args[0][0])
        self.assertIn("POTA_REF", col.caption.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
