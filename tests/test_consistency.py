"""Numbers and words that must agree wherever the site says them: how many skimmers, what a flare overlapped, what the dashboard says about DX."""
import re
import unittest
from unittest import mock

import pandas as pd

import log_check as lc
import log_check_html as lh
import log_openings as lo
import log_reach as lr
import log_space as ls
import log_space_html as lsh
import session_report as sr

T = pd.Timestamp


def log_of(*stamps, band="20m"):
    rec = lambda i, d, hhmm, b: f"<CALL:5>W1A{i:02d} <QSO_DATE:8>{d} <TIME_ON:4>{hhmm} <BAND:{len(b)}>{b} <MODE:2>CW <EOR>"
    return lc.parse_adif("<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(rec(i, d, h, b) for i, (d, h, b) in enumerate(stamps)) + "\n")


class OneDefinitionOfASkimmer(unittest.TestCase):
    def spots(self):
        return pd.DataFrame({"spotter": ["W3LPL", "W3LPL-2", "W3LPL-3", "DL1AAA", "DL1AAA-1", "K9XYZ"], "band": ["20m"] * 6, "snr": [10.0] * 6,
                             "time": [T("2026-11-21 20:30")] * 6})

    def test_a_station_with_several_receivers_is_one_skimmer_on_the_log_page_and_in_the_card(self):
        spots = self.spots()
        self.assertEqual(spots["spotter"].nunique(), 6)                                   # the old count
        self.assertEqual(lr.reporter_count(spots), 3)                                     # what the findings card and the card under the maps both say now

    def test_the_session_report_counts_the_same_way(self):
        locs = {"W3LPL": (39.0, -77.0), "W3LPL-2": (39.0, -77.0), "W3LPL-3": (39.0, -77.0), "DL1AAA": (50.0, 8.0), "DL1AAA-1": (50.0, 8.0), "K9XYZ": (40.0, -88.0)}
        spots, home = self.spots(), (32.2, -101.5)
        self.assertEqual(sr.band_scorecard(spots, locs, home).loc["20m", "Receivers"], 3)
        self.assertIn("from **3 skimmers**", " ".join(sr.headline(spots, locs, home, noun="skimmer")))
        table = sr.region_table(spots, locs, home)
        self.assertEqual(int(table.loc["All bands", "Total"]), 3)
        self.assertEqual(int(sr.country_table(spots)["Receivers"].sum()), 3)

    def test_the_findings_card_says_the_same_number_as_the_card_under_the_maps(self):
        import inspect
        from views import log_view
        source = inspect.getsource(log_view._glance)
        self.assertIn("lreach.reporter_count(spots)", source)
        self.assertNotIn("spots['spotter'].nunique()", source)


class TheDashboardDoesNotContradictItself(unittest.TestCase):
    def result(self, n):
        rx = pd.DataFrame({"rx": [f"JA{i}AAA" for i in range(n)], "region": ["Asia"] * n})
        return {"receivers": rx}

    def test_reports_from_afar_with_no_solid_region_are_not_called_good(self):
        from views import conditions_view
        with mock.patch.object(conditions_view.cond, "_dx_cells", return_value=([("20m", "Asia", .5)], [], [], [("20m", "Asia", .5)])):
            label, tone, text = conditions_view._dx_badge(self.result(7), "mi", 1.6)
        self.assertEqual(label, "DX reports available · regional evidence sparse")
        self.assertEqual(tone, "ta")
        self.assertIn("no single region has enough", text)

    def test_a_solid_region_is_called_good_and_too_few_receivers_are_thin(self):
        from views import conditions_view
        with mock.patch.object(conditions_view.cond, "_dx_cells", return_value=([], [("20m", "Asia", .8)], [("20m", "Asia", .8)], [])):
            label, tone, text = conditions_view._dx_badge(self.result(7), "mi", 1.6)
        self.assertEqual((label, tone), ("DX evidence good", "tg"))
        self.assertIn("at least one region has enough", text)
        self.assertEqual(conditions_view._dx_badge(self.result(2), "mi", 1.6)[0], "Thin DX evidence")


class AFlaresPeakAndIntervalAreTold(unittest.TestCase):
    """The 11 May 2024 activation: the M8.8 peaked at 15:25, between a morning on 30m (to 14:54) and an afternoon on 20m (from 19:07), but it ran from 14:46."""

    def facts(self, begin="2024-05-11 14:46", end="2024-05-11 15:52"):
        log = log_of(("20240511", "1424", "30m"), ("20240511", "1454", "30m"), ("20240511", "1907", "20m"), ("20240511", "1950", "20m"))
        peak = T("2024-05-11 15:25")
        details = {peak: {"begin": T(begin), "end": T(end), "region": "13664"}} if begin else {}
        wx = {"kp": [(T("2024-05-11 12:00"), 7.67), (T("2024-05-11 15:00"), 8.67)], "flux": [(T("2024-05-11"), 214.0)], "flares": [(peak, "M8.8")], "flare_details": details, "flare_source": "x"}
        return ls.facts(log, wx, (31.4, -100.4))

    def test_the_peak_between_sessions_and_the_interval_overlapping_one_are_both_said(self):
        f = self.facts()
        self.assertEqual((f["focus"]["bands"], f["focus"]["overlap"]), ([], ["30m"]))
        self.assertIn("An M8.8 flare peaked at 15:25 UTC, between your logged sessions; it ran from 14:46 to 15:52 UTC and overlapped your logged 30m activity.", f["headline"])
        self.assertEqual(lo.unsupported_claims(f["headline"]), [])
        html = lsh.space_html(f, {})
        self.assertIn("Peak between logged sessions", html)
        self.assertIn("Flare overlapped logged 30m activity", html)
        self.assertNotIn("Outside your logged activity", html)
        self.assertIn('class="sw-int"', html)                                                  # the whole interval is drawn faintly under the peak

    def test_a_flare_that_missed_every_session_is_still_outside_them(self):
        f = self.facts(begin="2024-05-11 15:10", end="2024-05-11 15:40")
        self.assertEqual(f["focus"]["overlap"], [])
        self.assertIn("outside your logged activity", f["headline"])
        self.assertIn("Outside your logged activity", lsh.space_html(f, {}))

    def test_a_flare_without_its_times_is_judged_by_its_peak_alone(self):
        f = self.facts(begin=None)
        self.assertEqual(f["focus"]["overlap"], [])
        self.assertIn("outside your logged activity", f["headline"])

    def test_a_peak_during_a_session_is_unchanged(self):
        log = log_of(("20240511", "1500", "15m"), ("20240511", "1530", "15m"))
        peak = T("2024-05-11 15:25")
        f = ls.facts(log, {"kp": [(T("2024-05-11 15:00"), 3.0)], "flux": [], "flares": [(peak, "X1.1")], "flare_details": {peak: {"begin": T("2024-05-11 15:10"), "end": T("2024-05-11 15:40")}}}, (31.4, -100.4))
        self.assertIn("An X1.1 flare peaked at 15:25 UTC during your logged 15m activity.", f["headline"])
        self.assertIn("During logged 15m activity", lsh.space_html(f, {}))


class TheTilesSayWhatTheyAre(unittest.TestCase):
    def test_the_flux_describes_the_sun_and_does_not_praise_it(self):
        self.assertEqual([ls.flux_label(v) for v in (60, 80, 110, 140, 180, 233)], ["Very low", "Low", "Moderate", "Elevated", "High", "Very high"])
        f = ls.facts(log_of(("20240511", "1500", "15m")), {"kp": [(T("2024-05-11 15:00"), 3.0)], "flux": [(T("2024-05-11"), 233.0)], "flares": []}, (31.4, -100.4))
        html = lsh.space_html(f, {})
        self.assertIn("Very high solar activity", html)
        self.assertNotIn("Excellent", html)

    def test_kp_is_a_peak_with_its_range_when_it_moved(self):
        log = log_of(("20240511", "1400", "20m"), ("20240511", "1900", "20m"))
        moved = ls.facts(log, {"kp": [(T("2024-05-11 12:00"), 7.67), (T("2024-05-11 18:00"), 8.67)], "flux": [], "flares": []}, (31.4, -100.4))
        self.assertIn("Peak during your session (it ranged from Kp 7.7 to 8.7).", lsh.space_html(moved, {}))
        steady = ls.facts(log, {"kp": [(T("2024-05-11 12:00"), 2.0), (T("2024-05-11 18:00"), 2.0)], "flux": [], "flares": []}, (31.4, -100.4))
        html = lsh.space_html(steady, {})
        self.assertIn("Peak during your session. A storm starts at Kp 5.", html)
        self.assertNotIn("ranged", html)


class SmallLogs(unittest.TestCase):
    def test_nobody_worked_on_more_than_one_band_is_said_once(self):
        log = log_of(("20240511", "1400", "20m"), ("20240511", "1410", "30m"))
        html = lh.followers_html(log, lc.summary(log))
        text = re.sub(r"<[^>]+>", " ", html)
        self.assertEqual(text.count("Nobody was worked on more than one band."), 1)


if __name__ == "__main__":
    unittest.main()
