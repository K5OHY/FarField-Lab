"""Space weather during a session: the sun at the station, flares from NOAA's list or the HEK, and the card built from them."""
import json
import re
import unittest
from unittest import mock

import pandas as pd

import log_check as lc
import log_openings as lo
import log_space as ls
import log_space_html as lsh
import space_weather as sw

T = pd.Timestamp
HOME = (32.23, -101.49)


def log_of(*pairs, date="20251023"):
    rec = lambda i, hhmm, band: f"<CALL:5>W1A{i:02d} <QSO_DATE:8>{date} <TIME_ON:4>{hhmm} <BAND:{len(band)}>{band} <MODE:2>CW <EOR>"
    return lc.parse_adif("<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(rec(i, h, b) for i, (h, b) in enumerate(pairs)) + "\n")


def wx(**kw):
    base = {"kp": [(T("2025-10-23 12:00"), 1.0), (T("2025-10-23 15:00"), 3.0)], "flux": [(T("2025-10-23"), 130.0)], "flares": [], "flare_details": {}, "flare_source": "NOAA"}
    base.update(kw)
    return base


class TheSun(unittest.TestCase):
    def test_sunrise_and_sunset_match_known_times(self):
        events = {k: t for t, k in ls.sun_events(51.5074, -0.1278, "2025-06-21 00:00", "2025-06-21 23:59")}         # London at midsummer: 03:43 and 20:21 UTC
        self.assertLessEqual(abs((events["sunrise"] - T("2025-06-21 03:43")).total_seconds()), 180)
        self.assertLessEqual(abs((events["sunset"] - T("2025-06-21 20:21")).total_seconds()), 180)
        self.assertAlmostEqual(ls.sun_elevation(51.48, 0.0, "2025-03-20 12:00"), 38.5, delta=0.6)                # noon at Greenwich at the equinox

    def test_the_sun_is_up_down_or_low(self):
        self.assertEqual([ls.daylight_state(v) for v in (30.0, -0.5, -3.0, -6.5, -40.0)], ["daylight", "daylight", "twilight", "night", "night"])
        segments = ls.daylight_segments(*HOME, "2025-10-23 11:00", "2025-10-23 15:00")
        self.assertEqual([s for _, _, s in segments], ["night", "twilight", "daylight"])
        self.assertEqual((segments[0][0], segments[-1][1]), (T("2025-10-23 11:00"), T("2025-10-23 15:00")))


class TheLog(unittest.TestCase):
    def test_a_pause_ends_a_stretch_on_a_band(self):
        log = log_of(("1300", "20m"), ("1310", "20m"), ("1400", "20m"), ("1305", "15m"))
        runs = ls.activity_runs(log)
        self.assertEqual([(b, n) for b, _, _, n in runs], [("15m", 1), ("20m", 2), ("20m", 1)])                   # highest band first; 13:10 to 14:00 is a pause
        self.assertEqual(ls.bands_active_at(runs, T("2025-10-23 13:07")), ["15m", "20m"])
        self.assertEqual(ls.bands_active_at(runs, T("2025-10-23 13:40")), [])


class TheReadings(unittest.TestCase):
    def test_the_words_follow_noaas_scales(self):
        self.assertEqual([ls.kp_label(k) for k in (1.0, 2.67, 3.0, 4.33, 5.0, 7.0, 9.0)], ["Quiet", "Quiet", "Unsettled", "Active", "Storm G1", "Storm G3", "Storm G5"])
        self.assertEqual([ls.r_level(c) for c in ("C9.9", "M1.0", "M4.9", "M5.0", "X1.0", "X10", "X20.5")], ["", "R1", "R1", "R2", "R3", "R4", "R5"])
        self.assertEqual([ls.flux_label(f) for f in (60, 80, 110, 140, 180, 233)], ["Very low", "Low", "Fair", "Good", "Very good", "Excellent"])
        self.assertEqual([ls.article(c) for c in ("M2.1", "X1.0", "C4.9", "B1.0")], ["an", "an", "a", "a"])

    def test_the_strongest_flare_is_the_biggest_and_then_the_earliest(self):
        flares = [(T("2025-10-23 15:00"), "M2.1"), (T("2025-10-23 16:00"), "X1.0"), (T("2025-10-23 14:00"), "X1.0"), (T("2025-10-23 17:00"), "C9.0")]
        self.assertEqual(ls.strongest_flare(flares), (T("2025-10-23 14:00"), "X1.0"))
        self.assertIsNone(ls.strongest_flare([]))


class TheFlareList(unittest.TestCase):
    def rows(self):
        return [(T("2024-05-08 21:40"), "X9.0", None, None, 0),                    # the same flare reported three times, once with a saturated class and no region
                (T("2024-05-08 21:40"), "X1.0", T("2024-05-08 21:08"), T("2024-05-08 23:10"), 13664),
                (T("2024-05-08 21:40"), "X1.0", T("2024-05-08 21:08"), T("2024-05-09 03:07"), 13664),
                (T("2024-05-09 22:15"), "M1.0", T("2024-05-09 22:08"), T("2024-05-09 22:24"), 0),             # a flare NOAA gave no region: kept
                (T("2024-05-09 23:00"), "M2.0", None, None, ""), (T("2024-05-09 23:00"), "M5.0", None, None, "")]  # no region either way: the lower class

    def test_one_flare_for_each_peak_with_the_class_tied_to_a_region(self):
        flares, details = sw.merge_flares(self.rows())
        self.assertEqual(flares, [(T("2024-05-08 21:40"), "X1.0"), (T("2024-05-09 22:15"), "M1.0"), (T("2024-05-09 23:00"), "M2.0")])
        self.assertEqual(details[T("2024-05-08 21:40")]["region"], "13664")
        self.assertEqual(details[T("2024-05-08 21:40")]["end"], T("2024-05-09 03:07"))

    def hek(self, entries):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"result": entries}
        return mock.Mock(return_value=Resp())

    def entry(self, peak, cls, feeder="SWPC", ar=13664):
        return {"event_starttime": peak, "event_peaktime": peak, "event_endtime": peak, "fl_goescls": cls, "frm_name": feeder, "ar_noaanum": ar}

    def test_the_hek_gives_flares_for_a_past_day_and_only_noaas_entries_count(self):
        entries = [self.entry("2024-05-09T09:13:00", "X2.2"), self.entry("2024-05-09T09:13:00", "X2.2"), self.entry("2024-05-09T09:14:00", "", "Flare Detective - Trigger Module"),
                   self.entry("2024-05-09T09:13:00", "X9.9", "Llyr Humphries"), self.entry("2024-05-09T04:00:00", "M1.5"), self.entry("2024-05-11T04:00:00", "M3.0")]
        with mock.patch.object(sw.requests, "get", self.hek(entries)) as get, mock.patch("disk_cache.get_bytes", return_value=None), mock.patch("disk_cache.put_bytes") as put:
            flares, details = sw.hek_flares("2024-05-09 00:00", "2024-05-09 23:59")
        self.assertEqual(flares, [(T("2024-05-09 04:00"), "M1.5"), (T("2024-05-09 09:13"), "X2.2")])              # another service's entries and a flare outside the stretch are left out
        self.assertEqual(details[T("2024-05-09 09:13")]["region"], "13664")
        sent = get.call_args.kwargs["params"]
        self.assertEqual(sorted(k for k in sent if "callsign" in k.lower() or "call" in k.lower()), [])           # only dates and a box on the sun are sent
        self.assertEqual(put.call_count, 1)                                                                          # a past stretch is kept on disk

    def test_a_kept_answer_is_used_without_asking_again(self):
        kept = json.dumps([self.entry("2024-05-09T09:13:00", "X2.2")]).encode()
        with mock.patch.object(sw.requests, "get", side_effect=AssertionError("asked again")), mock.patch("disk_cache.get_bytes", return_value=kept):
            flares, _ = sw.hek_flares("2024-05-09 00:00", "2024-05-09 23:59")
        self.assertEqual(flares, [(T("2024-05-09 09:13"), "X2.2")])

    def test_a_service_that_fails_or_answers_with_something_else_is_none(self):
        with mock.patch.object(sw.requests, "get", side_effect=RuntimeError("down")), mock.patch("disk_cache.get_bytes", return_value=None):
            self.assertIsNone(sw.hek_flares("2024-05-09 00:00", "2024-05-09 23:59"))
        with mock.patch.object(sw.requests, "get", return_value=mock.Mock(json=lambda: [1, 2], raise_for_status=lambda: None)), mock.patch("disk_cache.get_bytes", return_value=None):
            self.assertIsNone(sw.hek_flares("2024-05-09 00:00", "2024-05-09 23:59"))

    def test_history_falls_back_to_the_hek_when_noaas_list_does_not_reach_back(self):
        def get(url, params=None, **k):
            if "gfz" in url:
                return mock.Mock(json=lambda: {"Kp": [1.0], "Fobs": [233.0], "datetime": ["2024-05-09T12:00:00Z"]}, raise_for_status=lambda: None)
            if "edited_events" in url:
                return mock.Mock(json=lambda: [{"type": "XRA", "begin_datetime": "2026-11-01T00:00:00", "max_datetime": "2026-11-02T00:00:00", "particulars1": "C1.0"}], raise_for_status=lambda: None)
            return mock.Mock(json=lambda: {"result": [self.entry("2024-05-09T17:44:00", "X1.1")]}, raise_for_status=lambda: None)
        with mock.patch.object(sw.requests, "get", side_effect=get), mock.patch("disk_cache.get_bytes", return_value=None), mock.patch("disk_cache.put_bytes"):
            out = sw.history(T("2024-05-09 12:00"), T("2024-05-09 22:00"))
        self.assertEqual(out["flares"], [(T("2024-05-09 17:44"), "X1.1")])
        self.assertIn("HEK", out["flare_source"])


class TodaysSpaceWeather(unittest.TestCase):
    """A session from today: the day's own flux is not published yet, so the latest earlier one is used and said to be that."""

    def get(self, gfz_flux_today, swpc_rows=None):
        def get(url, params=None, **k):
            if "gfz" in url:
                if params["index"] == "Kp":
                    return mock.Mock(json=lambda: {"Kp": [0.0, 0.333], "datetime": ["2026-11-27T09:00:00Z", "2026-11-27T12:00:00Z"]}, raise_for_status=lambda: None)
                if pd.Timestamp(params["start"][:10]) >= T("2026-11-27"):                 # today: nothing yet
                    return mock.Mock(json=lambda: {"Fobs": gfz_flux_today, "datetime": []}, raise_for_status=lambda: None)
                return mock.Mock(json=lambda: {"Fobs": [88.0, 87.0], "datetime": ["2026-11-25T00:00:00Z", "2026-11-26T00:00:00Z"]}, raise_for_status=lambda: None)
            if "10cm-flux-30-day" in url:
                return mock.Mock(json=lambda: swpc_rows or [], raise_for_status=lambda: None)
            return mock.Mock(json=lambda: [], raise_for_status=lambda: None)
        return get

    def test_the_latest_earlier_flux_stands_in_and_is_said_to_be_that(self):
        with mock.patch.object(sw.requests, "get", side_effect=self.get([])), mock.patch("disk_cache.get_bytes", return_value=None), mock.patch("disk_cache.put_bytes"):
            out = sw.history(T("2026-11-27 11:00"), T("2026-11-27 16:00"))
        self.assertEqual(out["flux"], [])
        self.assertEqual(out["flux_latest"], (T("2026-11-26"), 87.0))
        log = log_of(("1300", "20m"), ("1400", "20m"), date="20261127")
        f = ls.facts(log, dict(out, flares=[]), HOME)
        self.assertEqual((round(f["flux"]), f["flux_latest"][0]), (87, T("2026-11-26")))
        html = lsh.space_html(f, {})
        self.assertIn("Latest daily solar flux, 26 Nov: the session's own day is not published yet", html)
        self.assertIn("the latest daily reading, from 26 Nov", " ".join(b for _, b in f["bullets"]))
        self.assertIn("the flux for the session's own day is not published yet", html)

    def test_noaas_thirty_day_list_is_used_when_gfz_has_nothing(self):
        rows = [{"time_tag": "2026-11-25T20:00:00", "flux": 88}, {"time_tag": "2026-11-26T20:00:00", "flux": 91}]
        def get(url, params=None, **k):
            if "gfz" in url:
                raise RuntimeError("down")
            return mock.Mock(json=lambda: rows, raise_for_status=lambda: None)
        with mock.patch.object(sw.requests, "get", side_effect=get):
            self.assertEqual(sw.latest_flux(T("2026-11-27 11:00")), (T("2026-11-26"), 91.0))
        with mock.patch.object(sw.requests, "get", side_effect=RuntimeError("down")):
            self.assertIsNone(sw.latest_flux(T("2026-11-27 11:00")))

    def test_a_flux_the_day_has_is_used_as_it_is(self):
        with mock.patch.object(sw.requests, "get", side_effect=self.get([120.0])), mock.patch("disk_cache.get_bytes", return_value=None), mock.patch("disk_cache.put_bytes"):
            pass
        f = ls.facts(log_of(("1300", "20m"), date="20251023"), wx(), HOME)
        self.assertIsNone(f["flux_latest"])
        self.assertEqual(round(f["flux"]), 130)

    def test_a_calm_field_is_said_without_or_lower_at_kp_zero(self):
        f = ls.facts(log_of(("1300", "20m"), date="20251023"), wx(kp=[(T("2025-10-23 12:00"), 0.0)]), HOME)
        self.assertTrue(f["headline"].startswith("The magnetic field stayed quiet (Kp 0)."), f["headline"])


class TheFacts(unittest.TestCase):
    def log(self):
        return log_of(("1300", "20m"), ("1310", "20m"), ("1500", "15m"), ("1520", "15m"), ("1800", "20m"))

    def test_a_quiet_session_with_no_big_flare(self):
        f = ls.facts(self.log(), wx(kp=[(T("2025-10-23 12:00"), 1.0), (T("2025-10-23 15:00"), 2.0)], flares=[(T("2025-10-23 15:06"), "C2.1")]), HOME)
        self.assertEqual(f["headline"], "The magnetic field stayed quiet (Kp 2 or lower). No flare reached M class (R1) in these hours.")
        self.assertEqual(f["focus"]["class"], "C2.1")
        self.assertEqual(f["focus"]["level"], "")
        self.assertEqual(f["focus"]["bands"], ["15m"])                                                     # it peaked during the 15m stretch

    def test_magnetic_activity_that_rose_and_a_flare_outside_the_logged_activity(self):
        f = ls.facts(self.log(), wx(flares=[(T("2025-10-23 16:30"), "M2.1")]), HOME)
        self.assertEqual(f["headline"], "Magnetic activity rose to Kp 3 (unsettled) from 15:00 UTC. An M2.1 flare peaked at 16:30 UTC, outside your logged activity.")
        self.assertEqual(f["focus"]["bands"], [])

    def test_a_flare_during_logged_activity_names_the_band(self):
        f = ls.facts(self.log(), wx(flares=[(T("2025-10-23 15:08"), "X1.1"), (T("2025-10-23 13:05"), "M3.0")]), HOME)
        self.assertIn("An X1.1 flare peaked at 15:08 UTC during your logged 15m activity.", f["headline"])
        text = " ".join(a + " " + b for a, b in f["bullets"])
        self.assertIn("an X1.1 flare is R3 (strong) on NOAA's radio blackout scale", text)
        self.assertIn("not a measurement of your paths", text)

    def test_missing_data_is_said_and_not_filled_in(self):
        f = ls.facts(self.log(), wx(flares=None), HOME)
        self.assertIn("Flare data is not available for these dates.", f["headline"])
        self.assertIn("could not be read", " ".join(b for _, b in f["bullets"]))
        g = ls.facts(self.log(), wx(kp=None, flux=None), HOME)                                               # the flare list alone
        self.assertIsNone(g["kp_peak"])
        self.assertIsNone(g["flux"])
        self.assertEqual([a for a, _ in g["bullets"]], ["Flare effects:", "Usable frequency:"])              # no flux or Kp line is made up
        self.assertIsNone(ls.facts(self.log(), {"kp": None, "flux": None, "flares": None}, HOME))            # nothing at all: no card

    def test_the_words_pass_the_wording_guard(self):
        for flares in ([], [(T("2025-10-23 15:08"), "X1.1")], [(T("2025-10-23 16:30"), "M2.1")], None):
            f = ls.facts(self.log(), wx(flares=flares), HOME)
            for text in [f["headline"]] + [a + " " + b for a, b in f["bullets"]]:
                self.assertEqual(lo.unsupported_claims(text), [], text)
                self.assertNotIn("should", text)

    def test_daylight_is_counted_for_the_contacts(self):
        f = ls.facts(log_of(("1200", "20m"), ("1300", "20m"), ("1400", "20m")), wx(), HOME)
        self.assertEqual(f["contacts_by_light"], {"daylight": 2, "twilight": 0, "night": 1})                # the sun came up at 12:56 UTC at Big Spring
        word, sentence = ls.daylight_summary(f)
        self.assertEqual(word, "Mixed")
        self.assertIn("2 in daylight", sentence)


class TheCard(unittest.TestCase):
    def facts(self, **kw):
        return ls.facts(log_of(("1300", "20m"), ("1310", "20m"), ("1500", "15m"), ("1520", "15m"), ("1800", "20m")), wx(**kw), HOME)

    def test_the_card_has_the_tiles_the_timeline_and_the_boxes(self):
        html = lsh.space_html(self.facts(flares=[(T("2025-10-23 15:08"), "X1.1")]), {"20m": "#800080", "15m": "#444444"})
        for text in ("Space weather during your session", "Solar background", "Geomagnetic activity", "Strongest flare", "Daylight at your station", "During your session",
                     "Magnetic activity", "Solar X-rays", "Logged activity", "Flare in focus", "What this means for HF", "Technical details and data coverage", "R3-level"):
            self.assertIn(text, html)
        self.assertIn("X1.1 · 15:08", html)
        self.assertIn("During logged 15m activity", html)
        self.assertIn("Storm threshold", html)
        self.assertEqual(html.count("sw-run"), 3 + 1)                                                          # three stretches (the class name once more in the stylesheet)
        self.assertIsNone(re.search(r"\d+\s*MHz", re.sub(r"<style>.*?</style>", "", html, flags=re.S)))        # no MUF number is made up

    def test_what_is_missing_is_said_in_the_card(self):
        html = lsh.space_html(self.facts(flares=None), {})
        self.assertIn("Flare data is not available for these dates.", html)
        self.assertIn("The flare list could not be read for these dates", html)
        self.assertIn("MUF:</b> not shown", html)
        quiet = lsh.space_html(self.facts(flares=[]), {})
        self.assertIn("No flares were listed for these hours.", quiet)
        self.assertEqual(lsh.space_html(None, {}), "")

    def test_a_label_near_the_edge_of_the_plot_is_kept_inside_it(self):
        early = self.facts(flares=[(T("2025-10-23 12:05"), "M2.9")])                                          # the stretch drawn begins at 11:00
        html = lsh.space_html(early, {})
        self.assertRegex(html, r'class="sw-fn" style="left:[\d.]+%;top:2px;transform:translate\(0,0\)')
        late = lsh.space_html(self.facts(flares=[(T("2025-10-23 18:50"), "M2.9")]), {})
        self.assertIn("translate(-100%,0)", late)


if __name__ == "__main__":
    unittest.main()
