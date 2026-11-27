"""The example logs on the Log page: their cards, their logs (cut and stripped), and the saved RBN and WSPR data that lets them open without the live services."""
import re
import unittest
from unittest import mock

import pandas as pd

import data_sources as ds
import frozen_data as fz
import log_check as lc
import log_examples as ex
import log_foundations as lf
import log_openings as lo
import log_story as lstory
from rbn_data import maidenhead_to_latlon

KEYS = ("yagi-doublet", "sota-efhw", "efhw-black-friday", "bush-house-ocf", "storm-kp9")


def log_of(key):
    return lc.parse_adif((fz.DIR / f"{key}.adi").read_text(encoding="utf-8"))


class TheCards(unittest.TestCase):
    def test_each_example_has_what_its_card_needs(self):
        found = {e["key"]: e for e in ex.manifest()}
        for key in KEYS:
            self.assertIn(key, found)
            card = found[key]
            for field in ("title", "when", "antenna", "power_w", "blurb", "video"):
                self.assertIn(field, card, f"{key}: {field}")
            self.assertGreater(int(card["power_w"]), 0)
            self.assertTrue(card["title"].strip() and card["blurb"].strip())
            self.assertTrue(card["video"] == "" or card["video"].startswith("https://"), card["video"])        # a link, or nothing until there is one

    def test_the_big_spring_example_is_one_log_whose_power_changes(self):
        card = {e["key"]: e for e in ex.manifest()}["yagi-doublet"]
        self.assertEqual(card["power_w"], 75)                                           # the first power, which the box shows
        plan = lf.PowerPlan(card["power_plan"])
        self.assertEqual((lf.power_at(plan, "2025-10-23 14:00"), lf.power_at(plan, "2025-10-23 18:30")), (75.0, 5.0))
        log = log_of("yagi-doublet")
        before = log[log["time"] < "2025-10-23 17:00"]
        self.assertEqual((len(log), set(before["band"])), (281, {"10m"}))               # everything before the change is the Yagi's 10m
        self.assertNotIn("10m", set(log[log["time"] >= "2025-10-23 17:00"]["band"]) - {"10m"})

    def test_the_text_of_a_card_does_not_claim_more_than_the_log_shows(self):
        for example in ex.manifest():
            self.assertEqual(lo.unsupported_claims(example["blurb"]), [])
            self.assertNotIn("better", example["blurb"].lower())          # a card says what was used, never which antenna was better


class TheLogs(unittest.TestCase):
    def test_each_log_is_the_whole_of_its_session(self):
        yagi, sota, efhw, bush, storm = (log_of(k) for k in KEYS)
        self.assertEqual(len(yagi), 281)                                                 # the whole day, in one log
        self.assertEqual(len(sota), 91)
        self.assertEqual(set(sota["mode"]), {"CW"})
        self.assertEqual((len(efhw), set(efhw["band"])), (257, {"20m", "15m", "10m"}))
        self.assertEqual((len(bush), set(bush["band"])), (179, {"20m", "15m", "17m", "12m", "10m"}))
        self.assertEqual((len(storm), set(storm["band"]), storm["time"].dt.date.nunique()), (24, {"20m", "30m"}, 1))
        self.assertEqual(lc.pota_refs(storm), ["US-10272"])                                       # a park the logging program wrote in its own field is still read
        self.assertEqual(lc.log_origin(storm)[0], "K5OHY")

    def test_nothing_about_a_person_worked_is_kept(self):
        for key in KEYS:
            text = (fz.DIR / f"{key}.adi").read_text(encoding="utf-8")
            for tag in ("NAME", "QTH", "COMMENT", "NOTES", "ADDRESS", "EMAIL", "LAT", "LON", "APP_"):
                self.assertIsNone(re.search(rf"<{tag}\w*:", text, re.I), f"{key} still has {tag}")
            for m in re.finditer(r"<GRIDSQUARE:(\d+)>", text):
                self.assertLessEqual(int(m.group(1)), 4)                                  # a station worked is only as exact as its four character square
            self.assertRegex(text, r"<MY_GRIDSQUARE:6>")                                   # the operator's own place is kept: the page places the session from it

    def test_each_log_says_where_and_who(self):
        for key in KEYS:
            call, grid = lc.log_origin(log_of(key))
            self.assertEqual(call, "K5OHY")
            self.assertEqual(len(grid), 6)


class TheLookups(unittest.TestCase):
    """What the page looks up about an example is saved with it and handed back only while that example is open."""

    def setUp(self):
        self._open = fz._open_example

    def tearDown(self):
        fz._open_example = self._open

    def test_each_example_carries_where_its_stations_were_and_its_park_and_space_weather(self):
        for key in KEYS:
            fz._open_example = lambda key=key: key
            log = log_of(key)
            places = fz.lookup("places")
            self.assertEqual(places.index.name, "call", key)
            self.assertGreater(len(places), 0.7 * log["call"].nunique(), key)                          # most stations placed; the rest could not be
            self.assertEqual(set(places.columns), {"lat", "lon", "source", "level", "grid"}, key)
            self.assertTrue(places["grid"].dropna().astype(str).str.len().le(6).all(), key)             # a place is a grid square, never an address
            a, b = lstory.window(log)
            history = fz.lookup("space_history", str(a), str(b))
            self.assertTrue(history["kp"], key)
            park_refs = lc.pota_refs(log) + lc.sota_refs(log)
            found = [fz.lookup("pota_park", r) or fz.lookup("sota_summit", r) for r in park_refs]
            self.assertTrue(all(f is not None for f in found) and found, key)

    def test_nothing_is_handed_back_when_no_example_is_open_or_the_question_is_different(self):
        fz._open_example = lambda: None
        self.assertIsNone(fz.lookup("places"))
        self.assertIsNone(fz.result("compare", "x", 1, 2, 3))
        fz._open_example = lambda: "bush-house-ocf"
        self.assertIsNone(fz.lookup("pota_park", "US-0000"))                                          # another park: looked up as always
        self.assertIsNone(fz.lookup("space_history", "2020-01-01 00:00:00", "2020-01-08 00:00:00"))
        self.assertIsNone(fz.lookup("no_such_lookup"))

    def test_what_is_handed_back_is_a_copy_and_the_saved_one_is_unchanged(self):
        fz._open_example = lambda: "bush-house-ocf"
        first = fz.lookup("places")
        first.loc[first.index[0], "lat"] = 0.0
        self.assertNotEqual(fz.lookup("places").iloc[0]["lat"], 0.0)

    def test_the_two_long_calculations_are_saved_for_the_examples_power_and_place(self):
        from views.log_view import _power_key
        card = {e["key"]: e for e in ex.manifest()}
        for key in KEYS:
            fz._open_example = lambda key=key: key
            power = lf.PowerPlan(card[key]["power_plan"]) if card[key].get("power_plan") else float(card[key]["power_w"])
            lat, lon = maidenhead_to_latlon(lc.log_origin(log_of(key))[1])
            args = (_power_key(power), round(lat, 3), round(lon, 3), float(lf.DEFAULT_RADIUS_KM))
            grid, compared = fz.result("conditions_grid", *args), fz.result("compare", *args)
            self.assertGreater(len(grid), 10, key)
            self.assertIn("evidence", grid.attrs, key)
            self.assertIn("bands", compared, key)
            self.assertIsNone(fz.result("compare", args[0], args[1], args[2], 1500.0), key)            # another radius is calculated, not guessed
            self.assertIsNone(fz.result("compare", "75.0" if args[0] != "75.0" else "5.0", *args[1:]), key)

    def test_the_storm_example_has_nasas_cause_saved_and_the_story_names_the_storm(self):
        fz._open_example = lambda: "storm-kp9"
        log = log_of("storm-kp9")
        a, b = lstory.window(log)
        history = fz.lookup("space_history", str(a), str(b))
        found = fz.lookup("donki_events", str(a), str(b))
        self.assertIsNotNone(found)
        story = lstory.build(log, history, found)
        text = " ".join(story["sentences"])
        self.assertIn("G5", text)
        self.assertIn("NASA's DONKI links it to", text)
        self.assertIn("You were on the air while the storm was under way", text)


class TheStripping(unittest.TestCase):
    """A log is kept to what the page reads: a pasted note, a snippet of code or a person's details never reaches an example."""

    def record(self, **extra):
        rec = {"CALL": "K1ABC", "QSO_DATE": "20251128", "TIME_ON": "1500", "BAND": "20m", "MODE": "CW", "RST_SENT": "599", "RST_RCVD": "599", "GRIDSQUARE": "FN31pr"}
        rec.update(extra)
        return rec

    def test_only_the_fields_the_page_reads_are_kept(self):
        import build_log_examples as b
        text, kept = b.sanitized([self.record(COMMENT="import os; os.system('x')", NOTES="def f(): pass", NAME="Pat", QTH="Hartford", ADDRESS="1 Main St", LAT="N041 45.000", EMAIL="a@b.c")])
        self.assertEqual(kept, 1)
        for word in ("import", "def f", "Pat", "Hartford", "Main St", "N041", "a@b.c", "COMMENT", "NOTES", "NAME", "QTH", "ADDRESS", "EMAIL", "LAT"):
            self.assertNotIn(word, text)
        self.assertIn("<GRIDSQUARE:4>FN31", text)                                       # a station worked is cut to four characters

    def test_a_kept_field_that_holds_something_else_stops_the_build(self):
        import build_log_examples as b
        for field, value in (("MODE", "print(1)"), ("RST_SENT", "599; rm -rf"), ("CALL", "K1ABC <script>"), ("STATE", "x = 1; y = {2}")):
            with self.assertRaises(ValueError, msg=field):
                b.sanitized([self.record(**{field: value})])

    def test_a_park_a_logging_program_wrote_in_its_own_fields_and_a_missing_callsign_are_filled_in(self):
        import build_log_examples as b
        text, _ = b.sanitized([self.record(MY_SIG_INFO="US-10272", SIG_INFO="US-2495", STATION_CALLSIGN="", COMMENT="note")], own_call="K5OHY")
        self.assertIn("<MY_POTA_REF:8>US-10272", text)
        self.assertIn("<POTA_REF:7>US-2495", text)
        self.assertIn("<STATION_CALLSIGN:5>K5OHY", text)
        self.assertNotIn("note", text)
        stray, _ = b.sanitized([self.record(MY_SIG_INFO="import os")])                                  # something that is not a park reference is not kept
        self.assertNotIn("import", stray)
        self.assertNotIn("MY_POTA_REF", stray)

    def test_the_odd_but_real_values_in_the_logs_are_accepted(self):
        import build_log_examples as b
        text, kept = b.sanitized([self.record(STATE="H-", CALL="EC1D"), self.record(STATE="England"), self.record(SOTA_REF="W7W/KG-O31")])
        self.assertEqual(kept, 3)


class TheSavedData(unittest.TestCase):
    def setUp(self):
        self._open = fz._open_example

    def tearDown(self):
        fz._open_example = self._open

    def home(self, key):
        return maidenhead_to_latlon(lc.log_origin(log_of(key))[1])

    def test_each_example_is_served_from_its_saved_data_without_the_live_services(self):
        def refuse(*a, **k):
            raise AssertionError("went to the live service")
        with mock.patch.object(ds, "fetch_nearby", refuse), mock.patch.object(ds, "rbn_day_zip", refuse), mock.patch.object(ds, "listening_from_zip", refuse):
            for key in KEYS:
                fz._open_example = lambda key=key: key
                log = log_of(key)
                cw = log[log["mode"] == "CW"]
                call = lc.log_origin(log)[0]
                start, end = cw["time"].min() - pd.Timedelta(minutes=lc.LOOKBACK_MIN), cw["time"].max() + pd.Timedelta(minutes=lc.WINDOW_PAD_MIN)
                days = tuple(sorted({f"{d:%Y%m%d}" for d in pd.date_range(start.floor("D"), end.floor("D"))}))
                spots = pd.concat([ds.download_rbn_day(d, call) for d in days])
                self.assertGreater(len(spots), 20, key)
                self.assertGreater(len(fz.listening(days, start, end)), 1000, key)
                lat, lon = self.home(key)
                first = cw["time"].min() - pd.Timedelta(minutes=lc.LOOKBACK_MIN)
                table = ds.load_nearby(lat, lon, lf.DEFAULT_RADIUS_KM, first, first + pd.Timedelta(hours=1))
                self.assertGreater(len(table), 100, key)
                self.assertTrue(table["time"].between(first, first + pd.Timedelta(hours=1)).all())

    def test_a_question_the_saved_data_does_not_cover_goes_to_the_live_service(self):
        self.assertIsNone(fz.spots("20251023", "K5ABC"))                                       # another callsign
        self.assertIsNone(fz.spots("20240101", "K5OHY"))                                       # another day
        lat, lon = self.home("sota-efhw")
        self.assertIsNone(fz.nearby(lat + 5, lon, lf.DEFAULT_RADIUS_KM, "2026-03-31 18:00", "2026-03-31 19:00"))     # another place
        self.assertIsNone(fz.nearby(lat, lon, 1500, "2026-03-31 18:00", "2026-03-31 19:00"))                         # another radius
        self.assertIsNone(fz.nearby(lat, lon, lf.DEFAULT_RADIUS_KM, "2026-03-31 03:00", "2026-03-31 04:00"))         # a stretch the example does not hold
        with mock.patch.object(ds, "_download_rbn_day", return_value="live") as live:
            self.assertEqual(ds.download_rbn_day("20240101", "K5OHY"), "live")
        self.assertEqual(live.call_count, 1)

    def test_the_saved_stretch_is_cut_the_way_the_live_service_cuts_it(self):
        lat, lon = self.home("sota-efhw")
        a, b = pd.Timestamp("2026-03-31 17:00:00"), pd.Timestamp("2026-03-31 17:30:00")
        part = fz.nearby(lat, lon, lf.DEFAULT_RADIUS_KM, a, b)
        whole = fz.nearby(lat, lon, lf.DEFAULT_RADIUS_KM, a, pd.Timestamp("2026-03-31 18:00:00"))
        self.assertTrue(part["time"].between(a, b).all())
        self.assertEqual(len(part), len(whole[whole["time"] <= b]))                              # both ends included, as BETWEEN does

    def test_a_power_that_changes_is_used_at_each_moment_in_the_grid_and_the_comparison(self):
        """With 75 W before 17:00 UTC and 5 W after, the boxes before it are the 75 W estimate and those after it the 5 W estimate, and each band's comparison uses its own."""
        from rbn_data import load_skimmers
        fz._open_example = lambda: "yagi-doublet"
        log = log_of("yagi-doublet")
        home = self.home("yagi-doublet")
        wspr_for = lambda a, b: ds.load_nearby(home[0], home[1], lf.DEFAULT_RADIUS_KM, a, b)
        plan = lf.PowerPlan([("2025-10-23 00:00", 75), ("2025-10-23 17:00", 5)])
        grids = {name: lc.conditions_grid(log, wspr_for, home, power, radius_km=lf.DEFAULT_RADIUS_KM) for name, power in (("plan", plan), ("75", 75.0), ("5", 5.0))}
        slot = grids["plan"]["slot"]
        early, late = slot < pd.Timestamp("2025-10-23 17:00"), slot >= pd.Timestamp("2025-10-23 17:00")      # a box has the power it began with
        key = ["receivers", "good", "dx_good"]
        pd.testing.assert_frame_equal(grids["plan"][early][key].reset_index(drop=True), grids["75"][early][key].reset_index(drop=True))
        pd.testing.assert_frame_equal(grids["plan"][late][key].reset_index(drop=True), grids["5"][late][key].reset_index(drop=True))
        self.assertGreater(grids["75"][early]["good"].sum(), grids["5"][early]["good"].sum())          # the two powers really differ here
        self.assertIs(grids["plan"].attrs["power_w"], plan)
        cw = log[log["mode"] == "CW"]
        start, end = cw["time"].min() - pd.Timedelta(minutes=lc.LOOKBACK_MIN), cw["time"].max() + pd.Timedelta(minutes=lc.WINDOW_PAD_MIN)
        spots, listening = ds.download_rbn_day("20251023", "K5OHY"), fz.listening(("20251023",), start, end)
        res = lc.compare(log, spots, wspr_for, listening, load_skimmers(), home, plan)
        self.assertEqual(res["power_by_band"]["10m"], 75.0)
        self.assertTrue(all(v == 5.0 for b, v in res["power_by_band"].items() if b != "10m"))

    def test_the_card_and_the_comparison_run_on_the_saved_data(self):
        """The SOTA example from the log to the comparison and the card, with no live service."""
        def refuse(*a, **k):
            raise AssertionError("went to the live service")
        import log_reach as lr
        from rbn_data import load_skimmers
        fz._open_example = lambda: "sota-efhw"
        with mock.patch.object(ds, "fetch_nearby", refuse), mock.patch.object(ds, "rbn_day_zip", refuse), mock.patch.object(ds, "listening_from_zip", refuse):
            log = log_of("sota-efhw")
            cw = log[log["mode"] == "CW"]
            home = self.home("sota-efhw")
            start, end = cw["time"].min() - pd.Timedelta(minutes=lc.LOOKBACK_MIN), cw["time"].max() + pd.Timedelta(minutes=lc.WINDOW_PAD_MIN)
            days = ("20260331",)
            spots = ds.download_rbn_day("20260331", "K5OHY")
            listening = fz.listening(days, start, end)
            rows = lr.reach_by_band(log, spots, listening, load_skimmers(), home)
            self.assertEqual([r["band"] for r in rows], ["10m", "15m", "20m"])
            self.assertTrue(all(r["state"] == "ok" and r["active"] > 10 for r in rows))
            wspr_for = lambda a, b: ds.load_nearby(home[0], home[1], lf.DEFAULT_RADIUS_KM, a, b)
            grid = lc.conditions_grid(log, wspr_for, home, 5, radius_km=lf.DEFAULT_RADIUS_KM)
            self.assertGreater(len(grid), 20)


if __name__ == "__main__":
    unittest.main()
