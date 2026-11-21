"""Checks of the calculations and the HTML helpers, with made-up data and no network. Run from the project folder with:

    python -m unittest discover -s tests -v
"""
import math
import io
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import compare_stats as cs  # noqa: E402
import data_sources as ds  # noqa: E402
import disk_cache  # noqa: E402
import conditions as cond  # noqa: E402
import log_check as lc  # noqa: E402
import log_check_html as lh  # noqa: E402
import dashboard as dash  # noqa: E402
import example_data  # noqa: E402
import ionosphere as iono  # noqa: E402
import space_weather as sw  # noqa: E402
import pdfs  # noqa: E402
import world_map as wm  # noqa: E402

HOME = (31.0, -102.0)


def spots(by_call):
    """A spot table from {call: [snr, ...]}."""
    return pd.DataFrame([(c, s) for c, snrs in by_call.items() for s in snrs], columns=["spotter", "snr"])


def places(*calls):
    """Receivers a known distance from HOME: the n-th is n * 5 degrees of longitude east of it (a few hundred miles apart)."""
    return {c: (31.0, -102.0 + 5 * (n + 1)) for n, c in enumerate(calls)}


class RelativeGain(unittest.TestCase):
    def test_sign_b_minus_a(self):
        a, b = spots({"AAA": [-20, -20, -20]}), spots({"AAA": [-15, -15, -15]})
        t = cs.station_gains(a, b, places("AAA"), HOME)
        self.assertEqual(float(-t.loc["AAA", "gap"]), 5.0)  # B is 5 dB stronger

    def test_linear_average_example_from_the_readme(self):
        a, b = spots({"AAA": [0, 0, 0, 20]}), spots({"AAA": [5, 5, 5, 5]})
        t = cs.station_gains(a, b, places("AAA"), HOME, method="linear")
        self.assertAlmostEqual(float(t.loc["AAA", "snr_a"]), 14.1, places=1)
        self.assertAlmostEqual(float(t.loc["AAA", "snr_b"]), 5.0, places=1)

    def test_minimum_reports(self):
        a, b = spots({"AAA": [-10] * 5, "BBB": [-10] * 2}), spots({"AAA": [-8] * 5, "BBB": [-8] * 2})
        t = cs.station_gains(a, b, places("AAA", "BBB"), HOME, min_spots=3)
        self.assertEqual(list(t.index), ["AAA"])

    def test_floor_drops_reports_not_stations(self):
        a, b = spots({"AAA": [-30, -20, -20]}), spots({"AAA": [-15, -15, -15]})
        t = cs.station_gains(a, b, places("AAA"), HOME, floor=cs.WSPR_FLOOR_DB)
        self.assertEqual(float(t.loc["AAA", "snr_a"]), -20.0)  # the -30 is gone, the station stays

    def test_leave_out_close_receivers(self):
        locs = {"NEAR": (31.0, -101.5), "FAR": (31.0, -90.0)}
        a, b = spots({"NEAR": [-10] * 3, "FAR": [-10] * 3}), spots({"NEAR": [-8] * 3, "FAR": [-8] * 3})
        t = cs.station_gains(a, b, locs, HOME, min_km=200)
        self.assertEqual(list(t.index), ["FAR"])

    def test_drop_a_station_that_is_mostly_at_the_floor(self):
        a = spots({"WEAK": [-30, -30, -30, -20], "OK": [-20] * 4})
        b = spots({"WEAK": [-28, -28, -28, -20], "OK": [-18] * 4})
        locs = places("WEAK", "OK")
        self.assertEqual(set(cs.station_gains(a, b, locs, HOME, weak_pct=50).index), {"OK"})
        self.assertEqual(set(cs.station_gains(a, b, locs, HOME, weak_pct=90).index), {"WEAK", "OK"})
        self.assertEqual(set(cs.station_gains(a, b, locs, HOME).index), {"WEAK", "OK"})

    def test_every_station_counts_on_its_own(self):
        locs = {"K9TRV": (40.0, -90.0), "K9TRV-2": (40.0, -90.0)}  # two stations at one place
        a, b = spots({"K9TRV": [-20] * 3, "K9TRV-2": [-20] * 3}), spots({"K9TRV": [-15] * 3, "K9TRV-2": [-10] * 3})
        pm = cs.power_method(a, b, locs, HOME)
        self.assertEqual(pm["n"], 2)


class LeaveOutForTheVerdict(unittest.TestCase):
    """The Receiver by receiver settings can narrow the strength figures, but never the count of who heard each side."""

    def setUp(self):
        calls = [f"R{n}" for n in range(12)]
        self.locs = places(*calls, "EDGE", "ONLYA")
        self.a = spots({**{c: [-10, -11, -12] for c in calls}, "EDGE": [-29], "ONLYA": [-15, -15]})
        self.b = spots({**{c: [-14, -15, -16] for c in calls}, "EDGE": [-29]})

    def test_only_the_kept_receivers_count_for_strength(self):
        every = cs.analyze(self.a, self.b, self.locs, HOME)
        cut = cs.analyze(self.a, self.b, self.locs, HOME, leave_out=dict(min_spots=2))
        self.assertEqual((every["strength"]["n"], cut["strength"]["n"]), (13, 12))
        self.assertEqual(cut["leave_out"], {"kept": 12, "total": 13})
        self.assertIsNone(every["leave_out"])

    def test_who_heard_each_side_is_not_changed(self):
        every = cs.analyze(self.a, self.b, self.locs, HOME)
        cut = cs.analyze(self.a, self.b, self.locs, HOME, leave_out=dict(min_spots=2))
        for key in ("a", "b", "only_a", "only_b", "both"):
            self.assertEqual(cut["reach"][key], every["reach"][key])

    def test_the_floor_drops_reports_before_the_averages(self):
        cut = cs.analyze(self.a, self.b, self.locs, HOME, leave_out=dict(floor=cs.WSPR_FLOOR_DB))
        self.assertNotIn("EDGE", cut["shared"].index)  # its only report was at the floor

    def test_nothing_kept_leaves_the_comparison_as_it_was(self):
        every = cs.analyze(self.a, self.b, self.locs, HOME)
        cut = cs.analyze(self.a, self.b, self.locs, HOME, leave_out=dict(min_spots=99))
        self.assertEqual(cut["leave_out"]["kept"], 0)
        self.assertEqual(cut["strength"]["n"], every["strength"]["n"])

    def test_alternating_rounds_are_cut_the_same_way(self):
        rounds = lambda s: s.assign(round=[float(n % 3) for n in range(len(s))])  # noqa: E731
        a, b = rounds(self.a), rounds(self.b)
        cut = cs.analyze(a, b, self.locs, HOME, leave_out=dict(min_spots=2))
        self.assertTrue(cut["paired"])
        self.assertNotIn("EDGE", cut["shared"].index)


class KeepBetweenPages(unittest.TestCase):
    """The step that keeps a test's setup when you visit another page must not write to a table widget (st.data_editor): the live site
    stopped with StreamlitValueAssignmentNotAllowedError on the antenna list of any alternating test (November 2026)."""

    def test_the_antenna_list_is_never_written_back_but_the_setup_is(self):
        from unittest import mock
        import streamlit as st
        from views import inputs

        class Recording(dict):
            written = []

            def __setitem__(self, key, value):
                self.written.append(key)
                super().__setitem__(key, value)

        state = Recording({"antenna_log_ABBA_12_041800": object(), "cmp_name_a": "Loop", "blk_len": 30, "test_mode": "In long blocks",
                           "callsign_in": "K5OHY", "_example": "quick"})
        with mock.patch.object(st, "session_state", state):
            inputs.keep_between_pages()
        self.assertNotIn("antenna_log_ABBA_12_041800", Recording.written)
        for key in ("cmp_name_a", "blk_len", "test_mode", "callsign_in"):
            self.assertIn(key, Recording.written)


class ConditionsRefresh(unittest.TestCase):
    """A phone's position wobbles from one reading to the next; a refresh must still find the spots it kept, and Refresh must forget them."""

    def test_nearby_positions_look_spots_up_at_the_same_point(self):
        from views.conditions_view import _lookup_point
        self.assertEqual(_lookup_point(31.99917, -102.158146), _lookup_point(31.9981, -102.1584))
        self.assertNotEqual(_lookup_point(31.99917, -102.158146), _lookup_point(32.2, -102.158146))  # a real move is a new point

    def test_refresh_forgets_the_kept_spots_for_both_ways_of_asking(self):
        from unittest import mock
        from views import conditions_view as cv
        calls = []

        def fake(*args, **kwargs):
            calls.append(args)
            return pd.DataFrame({"tx": []})

        with mock.patch.object(cv.cond, "fetch_nearby", fake), mock.patch.object(cv.cond, "fetch_station", fake):
            cv._refresh_data()
            cv._nearby_spots(1.0, 2.0, 100.0, "2026-01-01T00:00:00", 30)
            cv._nearby_spots(1.0, 2.0, 100.0, "2026-01-01T00:00:00", 30)
            cv._station_spots("K5OHY", "2026-01-01T00:00:00", 30)
            cv._station_spots("K5OHY", "2026-01-01T00:00:00", 30)
            self.assertEqual(len(calls), 2)  # each asked once, then kept
            cv._refresh_data()
            cv._nearby_spots(1.0, 2.0, 100.0, "2026-01-01T00:00:00", 30)
            cv._station_spots("K5OHY", "2026-01-01T00:00:00", 30)
            self.assertEqual(len(calls), 4)  # both forgotten
            cv._refresh_data()


class TextIsNeverTakenAsMarkup(unittest.TestCase):
    """An antenna name can arrive in a shared link, and a receiver's callsign comes from outside the app: neither may become HTML."""

    EVIL = '<img src=x onerror=alert(1)><script>x</script>'

    def test_a_name_loses_the_characters_that_make_tags_and_links(self):
        from ui_common import clean_name
        self.assertEqual(clean_name("40m loop, 20 ft"), "40m loop, 20 ft")
        self.assertEqual(clean_name("Vertical (tuned) & friends"), "Vertical (tuned) & friends")
        cleaned = clean_name(self.EVIL + "[click](http://e.example)`code`\\\n\t end")
        for bad in "<>[]`\\\n\t":
            self.assertNotIn(bad, cleaned)
        self.assertLessEqual(len(clean_name("x" * 500)), 60)

    def test_bold_marks_up_only_the_bold_markers(self):
        from ui_common import _bold, esc
        self.assertEqual(_bold("**<b>x</b>** & y"), "<b>&lt;b&gt;x&lt;/b&gt;</b> &amp; y")
        self.assertEqual(esc('R&D <1 "q"'), "R&amp;D &lt;1 &quot;q&quot;")

    def test_the_scoreboard_and_the_summary_card_escape_names(self):
        import charts
        html = charts.scoreboard_html(self.EVIL, "Safe", [("Unique receivers", "note <b>", (self.EVIL, ""), ("2", ""), None)])
        self.assertNotIn("<img", html)
        self.assertNotIn("<script", html)
        self.assertIn("&lt;img", html)
        card = charts.verdict_card_html({"winner": "A", "headline": f"**{self.EVIL}** is stronger.", "points": [("\U0001F4E1", self.EVIL)],
                                         "caveats": [self.EVIL]})
        self.assertNotIn("<img", card)
        self.assertNotIn("<script", card)

    def test_a_receiver_callsign_cannot_become_markup_in_a_map_popup(self):
        import maps
        spots = example_data.load("quick")[1]
        one = spots[spots["spotter"] == spots["spotter"].iloc[0]]
        html = maps.spot_popup_html(self.EVIL, one, 100.0, "mi")
        self.assertNotIn("<img", html)
        self.assertNotIn("<script", html)
        self.assertIn("&lt;img", html)


class LongTestsUseAveragePower(unittest.TestCase):
    """A long test run in blocks is judged on each receiver's average power (Dale's method); a test that alternates keeps the median."""

    def setUp(self):
        # one strong report in four on A: its middle report is 0 dB but its average power is 14.1 dB; B is steady at 5 dB
        self.a, self.b = spots({"AAA": [0, 0, 0, 20]}), spots({"AAA": [5, 5, 5, 5]})
        self.locs = places("AAA")

    def test_linear_uses_the_average_power_and_the_default_the_median(self):
        long_test = cs.analyze(self.a, self.b, self.locs, HOME, linear=True)["strength"]["mean"]
        median = cs.analyze(self.a, self.b, self.locs, HOME)["strength"]["mean"]
        self.assertAlmostEqual(long_test, 14.1 - 5.0, places=1)
        self.assertAlmostEqual(median, 0.0 - 5.0, places=1)

    def test_it_matches_the_receiver_by_receiver_average_gain(self):
        every = cs.station_gains(self.a, self.b, self.locs, HOME, "linear", 1)
        summary = cs.analyze(self.a, self.b, self.locs, HOME, linear=True)["strength"]["mean"]
        self.assertAlmostEqual(summary, float(every["gap"].mean()), places=1)

    def test_a_test_that_alternates_ignores_the_flag(self):
        rounds = lambda s: s.assign(round=[float(n) for n in range(len(s))])  # noqa: E731
        a, b = rounds(self.a), rounds(self.b)
        self.assertEqual(cs.analyze(a, b, self.locs, HOME, linear=True)["strength"]["mean"],
                         cs.analyze(a, b, self.locs, HOME)["strength"]["mean"])


class RememberedForSpeed(unittest.TestCase):
    """What is remembered between page redraws must never change what is shown, or leak a change from one caller to the next."""

    def test_an_example_is_read_once_but_each_caller_gets_its_own_copy(self):
        first = example_data.load("quick")
        first[1]["snr"] = 999.0  # a caller changing its spots, as the app does when it adds columns
        first[0]["callsign"] = "CHANGED"
        again = example_data.load("quick")
        self.assertNotEqual(again[1]["snr"].iloc[0], 999.0)
        self.assertNotEqual(again[0]["callsign"], "CHANGED")

    def test_the_saved_list_of_receivers_on_the_band_is_the_same_each_time(self):
        a = example_data.listening("20m", "2026-10-04 18:00:00", "2026-10-04 18:30:00")
        b = example_data.listening("20m", "2026-10-04 18:00:00", "2026-10-04 18:30:00")
        self.assertIsNotNone(a)
        self.assertTrue(a[0].equals(b[0]))
        self.assertIsNone(example_data.listening("20m", "2001-01-01 00:00:00", "2001-01-01 00:30:00"))  # no example covers it

    def test_a_remembered_path_is_the_same_path_and_a_list_nobody_else_shares(self):
        import maps
        one = maps.great_circle((31.0, -102.0), (52.0, 5.0))
        two = maps.great_circle((31.0, -102.0), (52.0, 5.0))
        self.assertEqual(one, two)
        self.assertEqual(len(one), 51)
        one.append((0.0, 0.0))
        self.assertEqual(len(maps.great_circle((31.0, -102.0), (52.0, 5.0))), 51)  # the first caller's change did not stick
        self.assertAlmostEqual(maps.distance_km((31.0, -102.0), (52.0, 5.0)), maps.distance_km((31.0, -102.0), (52.0, 5.0)))


class PairByPairGain(unittest.TestCase):
    """The dashboard's pair-by-pair tile: the summary's way of averaging, over the receivers the dashboard shows."""

    def setUp(self):
        # One receiver over four rounds. Rounds 1 and 4 have both antennas (B is 4 dB stronger each time); round 2 has only A and
        # round 3 only B (and weak). Pooled over the whole test it is +3 dB; pair by pair it is +4 dB.
        rows_a = [("AAA", 1, -20), ("AAA", 2, -18), ("AAA", 4, -19)]
        rows_b = [("AAA", 1, -16), ("AAA", 3, -22), ("AAA", 4, -15)]
        self.a = pd.DataFrame(rows_a, columns=["spotter", "round", "snr"])
        self.b = pd.DataFrame(rows_b, columns=["spotter", "round", "snr"])
        self.locs = places("AAA")

    def test_the_whole_test_and_pair_by_pair_differ_as_explained(self):
        every = cs.station_gains(self.a, self.b, self.locs, HOME)
        self.assertEqual(cs.gain_readout(every)["mean"], 3.0)
        self.assertEqual(cs.pair_by_pair_gain(every, self.a, self.b, self.locs, HOME), (1, 4.0))

    def test_it_matches_the_verdict_on_the_same_receivers(self):
        an = cs.analyze(self.a, self.b, self.locs, HOME)
        every = cs.station_gains(self.a, self.b, self.locs, HOME)
        n, gain = cs.pair_by_pair_gain(every, self.a, self.b, self.locs, HOME)
        self.assertEqual(n, an["strength"]["n"])
        self.assertAlmostEqual(gain, -an["strength"]["mean"])

    def test_only_the_receivers_on_the_dashboard_count(self):
        a = pd.concat([self.a, self.a.assign(spotter="BBB", snr=self.a["snr"] - 5)])
        b = pd.concat([self.b, self.b.assign(spotter="BBB", snr=self.b["snr"] - 9)])
        locs = places("AAA", "BBB")
        every = cs.station_gains(a, b, locs, HOME).loc[["AAA"]]  # BBB was left off the dashboard (say, by the slider)
        self.assertEqual(cs.pair_by_pair_gain(every, a, b, locs, HOME), (1, 4.0))

    def test_a_test_without_pairs_has_no_pair_by_pair_figure(self):
        every = cs.station_gains(self.a, self.b, self.locs, HOME)
        n, gain = cs.pair_by_pair_gain(every, self.a.drop(columns="round"), self.b.drop(columns="round"), self.locs, HOME)
        self.assertEqual(n, 0)
        self.assertTrue(math.isnan(gain))


class VerdictCard(unittest.TestCase):
    """The summary card is labelled and shows every evidence line, none hidden behind a click."""

    POINTS = [("📡", "**Reach:** r"), ("📶", "**Strength:** s"), ("🌍", "far"),
              ("📏", "**By distance:** d"), ("🧭", "**By direction:** e"), ("🔁", "**Consistency:** c")]

    def card(self, points):
        import charts
        return charts.verdict_card_html({"winner": "B", "headline": "**B is stronger.**", "points": points, "caveats": ["careful"]})

    def test_it_is_labelled_the_verdict(self):
        self.assertIn(">Summary</div>", self.card(self.POINTS))

    def test_every_line_and_caveat_is_shown(self):
        html = self.card(self.POINTS)
        self.assertNotIn("<details", html)
        for word in ("Reach:", "Strength:", "far", "By distance:", "By direction:", "Consistency:", "careful"):
            self.assertIn(word, html)


class SettledSlider(unittest.TestCase):
    """A short test opens the slider where the result stops moving much, and says so."""

    @staticmethod
    def trend(receivers, average, signal=None):
        n = len(receivers)
        return pd.DataFrame({"reports": range(1, n + 1), "receivers": receivers, "average": average, "typical": average,
                             "biggest": average, "smallest": average, "signal": signal if signal is not None else [math.nan] * n})

    def test_it_opens_where_the_next_step_barely_moves_the_result(self):
        # 1 November: the average moves 0.4 from 2 to 3 but only 0.1 from 3 to 4, so 3 is where it settles
        t = self.trend([139, 115, 87, 72, 52, 29], [1.6, 1.8, 2.2, 2.3, 3.0, 3.6], [2.13, 2.17, 2.74, 2.76, 3.29, 3.48])
        found = cs.settled_min_reports(t)
        self.assertEqual(found[0], 3)
        self.assertLess(found[1], cs.SETTLED_DB)

    def test_the_pair_by_pair_figure_must_settle_too(self):
        t = self.trend([100, 90, 80, 70], [1.0, 2.0, 2.1, 2.2], [1.0, 2.0, 3.0, 4.0])  # the average is steady from 2, the signal is not
        self.assertIsNone(cs.settled_min_reports(t))

    def test_it_never_settles_on_a_handful_of_receivers(self):
        t = self.trend([100, 20, 15, 10], [1.0, 2.0, 2.05, 2.1])  # steady, but fewer than SETTLED_MIN_RECEIVERS are left
        self.assertIsNone(cs.settled_min_reports(t))

    def test_a_result_that_keeps_climbing_has_no_settled_setting(self):
        t = self.trend([100, 80, 60, 40], [1.0, 1.6, 2.2, 2.8])
        self.assertIsNone(cs.settled_min_reports(t))

    def test_the_trend_has_one_row_per_setting_and_matches_the_dashboard(self):
        calls = [f"R{n}" for n in range(12)]
        a, b = spots({c: [-20, -21, -22] for c in calls}), spots({c: [-15, -16] for c in calls})
        t = cs.slider_trend(a, b, places(*calls), HOME)
        self.assertEqual(list(t["reports"]), [1, 2])  # nobody has 3 reports on B
        self.assertEqual(int(t.loc[1, "receivers"]), 12)
        every = cs.station_gains(a, b, places(*calls), HOME, "snr", 2)
        self.assertAlmostEqual(float(t.loc[1, "average"]), cs.gain_readout(every)["mean"])
        self.assertTrue(math.isnan(t.loc[0, "signal"]))  # no pairs, so no pair-by-pair figure

    def test_the_trend_chart_draws_the_lines_the_band_and_the_receiver_strip(self):
        import charts
        t = self.trend([139, 115, 87, 72, 52], [1.6, 1.8, 2.2, 2.3, 3.0], [2.13, 2.17, 2.74, 2.76, 3.29])
        t["smallest"], t["biggest"] = [-17.0, -17.0, -4.0, -4.0, -2.0], [12.5, 9.5, 9.5, 9.5, 9.5]  # one far-out receiver at 1 and 2
        fig = charts.slider_trend_chart(t, chosen=5, opened=3)
        self.assertEqual(len(fig.axes), 2)  # the gain panel and the receivers strip
        top, strip = fig.axes
        self.assertEqual(len(top.lines) >= 2, True)  # average and signal advantage (plus the zero line and the two markers)
        low, high = top.get_ylim()
        self.assertGreater(low, -17.0)  # the far-out receiver does not squash the lines; the chart says it was cut off
        self.assertEqual(len(strip.patches), 5)  # one bar per setting

    def test_the_trend_chart_copes_with_no_pairs_and_one_marker(self):
        import charts
        t = self.trend([100, 80, 60], [1.0, 1.1, 1.2])  # no pair-by-pair figure: the signal column is empty
        fig = charts.slider_trend_chart(t, chosen=2, opened=2)
        self.assertEqual(len(fig.axes), 2)

    def test_the_settings_shown_scale_to_how_many_reports_receivers_have(self):
        calls = [f"R{n}" for n in range(12)]
        places_ = places(*calls)
        short = spots({c: [-20] * 6 for c in calls})  # 6 reports each: every setting from 1 to 6
        self.assertEqual(cs.trend_settings(short, short, places_, HOME), [1, 2, 3, 4, 5, 6])
        medium = spots({c: [-20] * 14 for c in calls})  # 14 reports each (a 28-transmission test): still every setting, not 1, 5, 10
        self.assertEqual(cs.trend_settings(medium, medium, places_, HOME), list(range(1, 15)))
        edge = spots({c: [-20] * 20 for c in calls})
        self.assertEqual(cs.trend_settings(edge, edge, places_, HOME), list(range(1, 21)))
        past = spots({c: [-20] * 21 for c in calls})  # one more and it goes to steps of 5
        self.assertEqual(cs.trend_settings(past, past, places_, HOME), [1, 5, 10, 15, 20])
        long_ = spots({c: [-20] * 47 for c in calls})  # 47 reports each: steps of 5, and the slider's own settings are always in
        self.assertEqual(cs.trend_settings(long_, long_, places_, HOME), [1, 5, 10, 15, 20, 25, 30, 35, 40, 45])
        self.assertEqual(cs.trend_settings(long_, long_, places_, HOME, extra=(40, 37, 20)), [1, 5, 10, 15, 20, 25, 30, 35, 37, 40, 45])
        t = cs.slider_trend(long_, long_, places_, HOME, settings=cs.trend_settings(long_, long_, places_, HOME))
        self.assertEqual(list(t["reports"]), [1, 5, 10, 15, 20, 25, 30, 35, 40, 45])
        self.assertTrue((t["receivers"] == 12).all())

    def test_the_trend_chart_spaces_a_long_test_in_steps(self):
        import charts
        t = self.trend([40, 38, 30, 20, 9], [2.0, 2.1, 2.2, 2.3, 2.4])
        t["reports"] = [1, 10, 20, 30, 40]
        fig = charts.slider_trend_chart(t, chosen=40, opened=20)
        top, strip = fig.axes
        self.assertEqual(len(strip.patches), 5)
        self.assertEqual(sorted(strip.get_xticks()), [1, 10, 20, 30, 40])  # a tick at each setting, not at 1, 2, 3 ...
        self.assertGreater(top.get_xlim()[1], 40)

    def test_a_trend_worked_out_already_gives_the_same_plan(self):
        calls = [f"R{n}" for n in range(40)]
        a, b = spots({c: [-20 - n % 5] * 9 for n, c in enumerate(calls)}), spots({c: [-17 - n % 3] * 9 for n, c in enumerate(calls)})
        places_ = places(*calls)
        trend = cs.slider_trend(a, b, places_, HOME, "snr", 0.0)
        self.assertEqual(cs.min_reports_plan(a, b, places_, HOME, long_test=False, trend=trend),
                         cs.min_reports_plan(a, b, places_, HOME, long_test=False))

    def test_a_long_test_keeps_its_published_default(self):
        calls = [f"R{n}" for n in range(12)]
        many = spots({c: [-20] * 25 for c in calls})
        self.assertEqual(cs.min_reports_plan(many, many, places(*calls), HOME, long_test=True), (20, None))


class DefaultMinimumReports(unittest.TestCase):
    """The 'at least this many reports on each antenna' slider opens as strict as it can while leaving enough receivers."""

    def test_a_short_test_opens_at_two_when_enough_receivers_have_two_reports(self):
        calls = [f"R{n}" for n in range(12)]
        a, b = spots({c: [-20, -21] for c in calls}), spots({c: [-15, -16] for c in calls})
        self.assertEqual(cs.default_min_reports(a, b, places(*calls), HOME, long_test=False), 2)

    def test_a_very_short_test_falls_back_to_one_instead_of_an_empty_table(self):
        calls = [f"R{n}" for n in range(12)]
        a, b = spots({c: [-20] for c in calls}), spots({c: [-15] for c in calls})  # one report each, as in 2 transmissions
        self.assertEqual(cs.default_min_reports(a, b, places(*calls), HOME, long_test=False), 1)

    def test_too_few_receivers_with_two_reports_falls_back_to_one(self):
        calls = [f"R{n}" for n in range(12)]
        a = spots({c: [-20, -21] if n < 5 else [-20] for n, c in enumerate(calls)})
        b = spots({c: [-15, -16] for c in calls})
        self.assertEqual(cs.default_min_reports(a, b, places(*calls), HOME, long_test=False), 1)

    def test_a_long_test_steps_down_from_twenty_until_enough_receivers_are_left(self):
        calls = [f"R{n}" for n in range(12)]
        many = spots({c: [-20] * 25 for c in calls})
        self.assertEqual(cs.default_min_reports(many, many, places(*calls), HOME, long_test=True), 20)
        some = spots({c: [-20] * 6 for c in calls})
        self.assertEqual(cs.default_min_reports(some, some, places(*calls), HOME, long_test=True), 5)
        few = spots({c: [-20] * 1 for c in calls})
        self.assertEqual(cs.default_min_reports(few, few, places(*calls), HOME, long_test=True), 1)


class HintsForShortTests(unittest.TestCase):
    """A short test cannot call a difference in how many receivers heard each side, but it should still point at one."""

    def setUp(self):
        self.ta = pd.DataFrame({"km": [800.0] * 3 + [4000.0] * 11, "bearing": [10.0] * 14})
        self.tb = pd.DataFrame({"km": [800.0] * 3 + [4000.0] * 2, "bearing": [10.0] * 5})
        self.shared = pd.DataFrame({"km_a": [800.0] * 2, "bearing_a": [10.0] * 2, "delta": [0.0, 0.0]})
        self.names = {"A": "Loop", "B": "Vertical"}

    def test_a_long_enough_test_calls_it(self):
        rows = cs.distance_breakdown(self.ta, self.tb, self.shared, "km", allow_counts=True)
        far = rows[rows["label"] == "3,000–6,000 km"].iloc[0] if (rows["label"] == "3,000–6,000 km").any() else rows.iloc[3]
        self.assertEqual((far["call"], far["basis"], far["hint"]), ("A", "more receivers", ""))

    def test_a_short_test_leaves_it_uncalled_but_hints(self):
        rows = cs.distance_breakdown(self.ta, self.tb, self.shared, "km", allow_counts=False)
        self.assertEqual(list(rows["call"].unique()), [""])
        text = cs._hint_text(rows, self.names, "receiver", "at ")
        self.assertIn("Loop was heard by 11 receivers at", text)
        self.assertIn("against 2", text)

    def test_no_hint_when_the_counts_are_close(self):
        tb = pd.DataFrame({"km": [800.0] * 3 + [4000.0] * 10, "bearing": [10.0] * 13})
        rows = cs.distance_breakdown(self.ta, tb, self.shared, "km", allow_counts=False)
        self.assertEqual(cs._hint_text(rows, self.names, "receiver", "at "), "")


class GainReadout(unittest.TestCase):
    """The numbers shown beside the minimum-reports slider."""

    @staticmethod
    def table(groups):
        rows = [(gap, bearing, 1000.0) for gap, bearing, count in groups for _ in range(count)]
        return pd.DataFrame(rows, columns=["gap", "bearing_a", "km_a"])

    def test_average_typical_biggest_and_smallest(self):
        # gap is A minus B, so a gap of -3 is B stronger by 3 dB. The biggest and smallest are single receivers.
        every = self.table([(-3.0, 0.0, 5), (1.0, 180.0, 5), (-10.0, 90.0, 2)])
        every.index = [f"RX{i}" for i in range(len(every))]
        out = cs.gain_readout(every)
        self.assertEqual(out["n"], 12)
        self.assertEqual(out["typical"], 3.0)
        self.assertAlmostEqual(out["mean"], (15 - 5 + 20) / 12)
        self.assertEqual((out["biggest"], out["smallest"]), (10.0, -1.0))
        self.assertEqual((out["biggest_who"], out["smallest_who"]), ("RX10", "RX5"))

    def test_nothing_left_gives_no_biggest_or_smallest(self):
        out = cs.gain_readout(self.table([]))
        self.assertEqual(out["n"], 0)
        self.assertIsNone(out["biggest"])
        self.assertIsNone(out["smallest"])

    def test_one_direction_average(self):
        every = self.table([(-3.0, 0.0, 5), (1.0, 180.0, 4), (-10.0, 90.0, 2)])
        self.assertEqual(cs.direction_average(every, "N"), (5, 3.0))
        self.assertEqual(cs.direction_average(every, "S"), (4, -1.0))
        n, mean = cs.direction_average(every, "W")
        self.assertEqual(n, 0)
        self.assertTrue(math.isnan(mean))

    def test_a_direction_average_by_quadrant(self):
        every = self.table([(-3.0, 0.0, 3), (-1.0, 40.0, 2), (1.0, 180.0, 4)])  # 0 and 40 degrees are both in the N quadrant
        self.assertEqual(cs.direction_average(every, "N", "quadrant"), (5, (9 + 2) / 5))
        self.assertEqual(cs.direction_average(every, "NE"), (2, 1.0))  # the octant of the same 40 degrees
        self.assertEqual(cs.busiest_direction(every, "quadrant"), "N")

    def test_a_direction_says_the_compass_range_it_covers(self):
        self.assertEqual(cs.direction_degrees("W", "quadrant"), "225°–315°")
        self.assertEqual(cs.direction_degrees("N", "quadrant"), "315°–45°")
        self.assertEqual(cs.direction_degrees("N"), "337.5°–22.5°")
        self.assertEqual(cs.direction_degrees("NE"), "22.5°–67.5°")

    def test_the_busiest_direction_is_the_one_to_watch(self):
        every = self.table([(-3.0, 0.0, 5), (1.0, 180.0, 7), (-10.0, 90.0, 2)])
        self.assertEqual(cs.busiest_direction(every), "S")
        self.assertEqual(cs.busiest_direction(self.table([])), "N")


class Intervals(unittest.TestCase):
    def test_student_t_values(self):
        self.assertAlmostEqual(cs.t_crit(10), 2.228, places=2)
        self.assertAlmostEqual(cs.t_crit(2), 4.303, places=2)
        self.assertAlmostEqual(cs.t_crit(1000), 1.962, places=2)

    def test_mean_interval(self):
        mean, lo, hi = cs.mean_interval([1, 2, 3, 4, 5])
        half = cs.t_crit(4) * np.std([1, 2, 3, 4, 5], ddof=1) / math.sqrt(5)
        self.assertAlmostEqual(mean, 3.0)
        self.assertAlmostEqual(hi - mean, half, places=6)
        self.assertAlmostEqual(mean - lo, half, places=6)

    def test_one_number_has_no_range(self):
        mean, lo, hi = cs.mean_interval([4.0])
        self.assertEqual(mean, 4.0)
        self.assertTrue(math.isnan(lo) and math.isnan(hi))


class BandConditions(unittest.TestCase):
    def test_chance_of_being_heard(self):
        self.assertAlmostEqual(float(cond.chance(0)), 0.5)
        self.assertGreater(float(cond.chance(24)), 0.99)
        self.assertLess(float(cond.chance(-24)), 0.01)

    def test_the_mode_list(self):
        self.assertEqual(list(cond.MODES), ["CW", "SSB", "FT8", "WSPR"])

    def test_thin_regions_are_hints_not_dx(self):
        bands = ["20m", "15m"]
        regions = ["Europe", "Oceania"]
        frame = lambda v: pd.DataFrame(v, index=bands, columns=regions)  # noqa: E731
        result = {"regions": frame([[10.0, 10.0], [10.0, 10.0]]), "regions_n": frame([[1, 5], [2, 0]]),
                  "chance": frame([[0.99, 0.9], [0.95, np.nan]])}
        cells, solid, good, hints = cond._dx_cells(result)
        self.assertEqual([(b, r) for b, r, _ in good], [("20m", "Oceania")])  # only the cell with enough receivers
        self.assertEqual({(b, r) for b, r, _ in hints}, {("20m", "Europe"), ("15m", "Europe")})


class SimulationScript(unittest.TestCase):
    def test_a_simulated_test_gives_a_verdict_and_a_big_gap_is_found(self):
        import numpy as np
        import simulate_validation as sim
        rng = np.random.default_rng(1)
        names, locs = sim._receivers(rng)
        results = [sim.experiment(rng, names, locs, 6, 12, "ABBA") for _ in range(5)]
        calls = [r[0] for r in results if r]
        self.assertTrue(calls)
        self.assertEqual(set(calls), {"B"})  # a 6 dB gap is not missed, and never called the wrong way

    def test_complete_data_can_be_simulated_too(self):
        import numpy as np
        import simulate_validation as sim
        rng = np.random.default_rng(2)
        names, locs = sim._receivers(rng)
        r = sim.experiment(rng, names, locs, 3, 12, "ABBA", floor=None, listen=1.0, drift_sd=0.0)
        self.assertIsNotNone(r)
        self.assertGreater(r[4], 60)  # with nothing lost, nearly every receiver heard both antennas


class LocalOnlyBands(unittest.TestCase):
    """A band is not open just because receivers a few miles away hear you: on the upper bands that is ground wave, not skip."""

    def status(self, band, miles):
        t0 = datetime(2026, 10, 25, 12, 0)
        rows = [{"time": t0 + timedelta(minutes=2 * k), "band": band, "rx": f"R{i}", "rx_lat": HOME[0] + mi / 69.0,
                 "rx_lon": HOME[1], "tx": "T1", "snr": 5.0, "power": 37.0}
                for i, mi in enumerate(miles) for k in range(3)]
        result = cond.analyze(pd.DataFrame(rows), HOME, 100, "CW", t0 + timedelta(minutes=10), 30, 0.0, 3.0)
        return result["bands"].at[band, "Status"]

    def test_nearby_receivers_on_10m_are_local_only(self):
        self.assertEqual(self.status("10m", [36, 54, 80, 101, 135, 179]), "Local")

    def test_receivers_beyond_the_skip_distance_open_10m(self):
        self.assertEqual(self.status("10m", [36, 54, 700, 900, 1200]), "Open")

    def test_close_receivers_still_count_on_40m(self):
        self.assertEqual(self.status("40m", [36, 54, 80]), "Open")

    def test_each_band_has_its_own_distance(self):
        self.assertEqual(self.status("20m", [100, 150, 200]), "Local")
        self.assertEqual(self.status("20m", [300, 400, 500]), "Open")

    def test_a_local_band_is_not_listed_as_rising_or_open(self):
        bands = pd.DataFrame({"Status": ["Local"], "Trend": ["opening"], "Receivers": [12], "Good": [10], "Marginal": [0],
                              "Farthest good (km)": [250.0]}, index=["10m"])
        self.assertEqual(dash.state("Local", "opening"), ("Local only", "tm"))
        html = dash.tiles_html(bands, {})
        self.assertIn("Local only", html)
        self.assertIn("to 155 mi", html)


class DashboardPieces(unittest.TestCase):
    def test_open_and_rising_reads_open_with_an_arrow(self):
        self.assertEqual(dash.state("Open", "opening"), ("Open ↗", "tg"))
        self.assertEqual(dash.state("Open", "fading"), ("Open ↘", "tg"))
        self.assertEqual(dash.state("Marginal", "steady"), ("Marginal", "ta"))
        self.assertEqual(dash.state("Quiet", "unclear"), ("Quiet", "tm"))

    def test_thin_cells_show_only_the_count(self):
        chance = pd.DataFrame({"US East": [0.99, 0.8]}, index=["20m", "15m"])
        counts = pd.DataFrame({"US East": [1, 12]}, index=["20m", "15m"])
        html = dash.grid_html(chance, counts)
        self.assertIn("1 RX", html)
        self.assertNotIn("99%", html)
        self.assertIn("80%", html)

    def test_detail_table_hides_figures_for_thin_cells(self):
        margin = pd.DataFrame({"Europe": [20.0, 9.0]}, index=["20m", "15m"])
        need = pd.DataFrame({"Europe": [1.0, 25.0]}, index=["20m", "15m"])
        counts = pd.DataFrame({"Europe": [2, 9]}, index=["20m", "15m"])
        html = dash.detail_grid_html(margin, need, counts, 3)
        self.assertIn("2 RX", html)
        self.assertNotIn("+20 dB", html)
        self.assertIn("+9 dB", html)
        self.assertIn("25 W", html)

    def test_tiles_for_every_band(self):
        bands = pd.DataFrame({"Status": ["Open", "Quiet"], "Trend": ["steady", "unclear"], "Receivers": [30, 1],
                              "Good": [20, 1], "Marginal": [5, 0]}, index=["20m", "10m"])
        html = dash.tiles_html(bands, {})
        self.assertIn("20m", html)
        self.assertIn("10m", html)
        self.assertIn("High confidence", html)
        self.assertIn("Low confidence", html)


class SunAndSky(unittest.TestCase):
    def test_space_weather_readings(self):
        words = {r["label"]: r["word"] for r in sw.readings(
            {"flux": 121, "ssn": 66, "kp": 2.0, "xray": 1.2e-6, "xray_max": 1.2e-6, "wind": 430, "bz": -1})}
        self.assertEqual(words["Solar flux"], "Good")
        self.assertEqual(words["Kp index"], "Quiet")
        self.assertEqual(words["X-ray"], "Low activity")
        self.assertEqual(words["Solar wind"], "Calm")

    def test_missing_feeds_are_left_out(self):
        self.assertEqual(sw.readings({}), [])

    def test_top_band_under_the_muf(self):
        self.assertEqual(iono.top_band(10.2), "30m")
        self.assertEqual(iono.top_band(30.0), "10m")
        self.assertIsNone(iono.top_band(1.0))

    def test_shorter_paths_need_a_lower_frequency(self):
        self.assertLess(iono.muf_for(20.0, 300, 500, 3.0), iono.muf_for(20.0, 300, 3000, 3.0))

    def test_sun_position_in_october(self):
        decl, lon = wm._sun_position(datetime(2026, 10, 21, 12, 0))
        self.assertAlmostEqual(decl, -11, delta=1.5)
        self.assertAlmostEqual(lon, -4, delta=1.5)

    def test_day_night_line_stays_inside_the_map(self):
        x, y = wm._terminator(31.0, -102.0, 12000.0, datetime(2026, 10, 21, 12, 0))
        inside = ~np.isnan(x)
        self.assertTrue(inside.any())
        self.assertTrue((np.hypot(x[inside], y[inside]) <= 12000.0 + 1e-6).all())

    def test_map_draws_with_the_day_night_line(self):
        pts = pd.DataFrame({"km": [500.0, 3000.0], "bearing": [10.0, 100.0], "group": "single", "gap": np.nan,
                            "snr_a": [5.0, 3.0], "snr_b": np.nan, "color": "#ffffff"})
        fig = wm.azimuth_map_figure(31.0, -102.0, pts, {"A": "", "B": ""}, "TEST", "mi", 12000.0, "dots", True, (0, 20),
                                    when=datetime(2026, 10, 21, 12, 0))
        self.assertIsNotNone(fig)


class SavedExamples(unittest.TestCase):
    def test_every_example_has_its_spots_and_a_place(self):
        for name, kind in (("map", "RBN"), ("rbn", "RBN"), ("quick", "WSPR"), ("long", "WSPR")):
            meta, spots = example_data.load(name)
            self.assertEqual(meta["kind"], kind)
            self.assertGreater(len(spots), 100, name)
            self.assertEqual(len(meta["home"]), 3)
            self.assertTrue({"spotter", "snr", "time", "band", "freq"} <= set(spots.columns), name)
            self.assertTrue(pd.api.types.is_datetime64_any_dtype(spots["time"]), name)

    def test_the_wspr_examples_carry_who_was_listening(self):
        meta, spots = example_data.load("long")
        on_band = spots[spots["band"] == meta["listening"]["band"]]
        start, end = on_band["time"].min(), on_band["time"].max() + pd.Timedelta(minutes=2)
        listening, truncated = example_data.listening("20m", start, end)
        self.assertFalse(truncated)
        self.assertGreater(len(listening), 10_000)
        self.assertEqual(list(listening.columns), ["time", "spotter"])

    def test_nothing_is_returned_for_a_band_or_time_no_example_covers(self):
        self.assertIsNone(example_data.listening("40m", "2026-08-26 12:00", "2026-08-26 13:00"))
        self.assertIsNone(example_data.listening("20m", "2020-01-01 00:00", "2020-01-01 01:00"))


class ReportTitle(unittest.TestCase):
    def test_named_antennas_make_a_two_line_coloured_title(self):
        lines = pdfs.comparison_headline({"A": "Loop", "B": "Dipole"}, "20m")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], [("Loop (A)", pdfs.COLOR_A)])
        self.assertEqual(lines[1][1], ("Dipole (B)", pdfs.COLOR_B))
        self.assertIn("on 20 m", lines[1][2][0])

    def test_unnamed_antennas_make_one_line(self):
        lines = pdfs.comparison_headline({"A": "A", "B": "B"}, "20m")
        self.assertEqual([piece[0].strip() for piece in lines[0]], ["A", "vs", "B", "on 20 m"])

    def test_a_long_name_is_shortened(self):
        lines = pdfs.comparison_headline({"A": "x" * 80, "B": "B"}, "")
        self.assertLessEqual(len(lines[0][0][0]), 45)


class DownloadsAreRemembered(unittest.TestCase):
    """A day that is over is fetched once. These use a throwaway cache folder and made-up answers, so they need no internet."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        patch = mock.patch.dict(os.environ, {"RBN_CACHE_DIR": self.folder.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.folder.cleanup)

    def frame(self, hours_ago):
        stamp = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours_ago)
        return pd.DataFrame({"time": [pd.Timestamp(stamp)], "spotter": ["W1AW"], "snr": [-12]})

    def test_a_frame_comes_back_as_it_went_in(self):
        original = self.frame(5)
        disk_cache.put_frame("t", "key", original, {"truncated": True})
        frame, meta = disk_cache.get_frame("t", "key")
        pd.testing.assert_frame_equal(frame, original, check_dtype=False)
        self.assertTrue(meta["truncated"])
        self.assertIsNone(disk_cache.get_frame("t", "another key"))

    def _old_file(self, name, seconds_old):
        """A cached file made `seconds_old` seconds ago, with that file time set exactly, so the test does not depend on the clock."""
        path = disk_cache._name("b", name, ".bin")
        path.write_bytes(bytes(1000))
        when = (datetime.now(timezone.utc).timestamp() - seconds_old)
        os.utime(path, (when, when))
        return path

    def test_the_folder_is_trimmed_oldest_first(self):
        for n in range(5):  # k0 is the oldest, k4 the newest
            self._old_file(f"k{n}", seconds_old=(5 - n) * 100)
        with mock.patch.object(disk_cache, "MAX_BYTES", 3000):
            disk_cache.put_bytes("b", "k5", bytes(1000))  # six files of 1000 bytes: the three oldest go
        kept = [n for n in range(6) if disk_cache.get_bytes("b", f"k{n}") is not None]
        self.assertEqual(kept, [3, 4, 5])

    def test_the_file_just_saved_is_never_the_one_trimmed(self):
        """File times are coarse, so older files can share the newest's time. The new one must still survive."""
        same = datetime.now(timezone.utc).timestamp()
        for n in range(5):
            path = self._old_file(f"k{n}", seconds_old=0)
            os.utime(path, (same, same))
        with mock.patch.object(disk_cache, "MAX_BYTES", 3000):
            for i in range(30):  # the order among tied files is arbitrary, so try many different new files
                disk_cache.put_bytes("b", f"new{i}", bytes(1000))
                self.assertIsNotNone(disk_cache.get_bytes("b", f"new{i}"), i)
                for n in range(5):  # put the older ones back at the same time
                    path = self._old_file(f"k{n}", seconds_old=0)
                    os.utime(path, (same, same))

    def test_a_finished_wspr_period_is_fetched_once(self):
        start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=30)
        end = start + timedelta(hours=1)
        with mock.patch.object(ds, "fetch_wspr_spots", return_value=(self.frame(30), False)) as fetch:
            first = ds.load_wspr("K5OHY", start, end)
            second = ds.load_wspr("k5ohy", start, end)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(len(first[0]), len(second[0]))
        self.assertFalse(second[1])

    def test_a_period_in_the_last_hour_is_always_fetched_fresh(self):
        end = datetime.now(timezone.utc).replace(tzinfo=None)
        start = end - timedelta(hours=3)
        with mock.patch.object(ds, "fetch_wspr_spots", return_value=(self.frame(0), False)) as fetch:
            ds.load_wspr("K5OHY", start, end)
            ds.load_wspr("K5OHY", start, end)
        self.assertEqual(fetch.call_count, 2)

    def test_a_cut_off_answer_is_remembered_as_cut_off(self):
        start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=40)
        with mock.patch.object(ds, "fetch_wspr_spots", return_value=(self.frame(40), True)) as fetch:
            ds.load_wspr("K5OHY", start, start + timedelta(hours=2))
            again = ds.load_wspr("K5OHY", start, start + timedelta(hours=2))
        self.assertEqual(fetch.call_count, 1)
        self.assertTrue(again[1])

    def test_who_was_listening_is_fetched_once_for_a_finished_period(self):
        start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=50)
        end = start + timedelta(hours=1)
        ds.load_listening.clear()
        with mock.patch.object(ds, "fetch_listening", return_value=(self.frame(50), False)) as fetch:
            ds.load_listening("17m", start, end)
            ds.load_listening.clear()  # forget the in-memory minute, so only the saved copy can answer
            ds.load_listening("17m", start, end)
        self.assertEqual(fetch.call_count, 1)

    def test_a_days_rbn_file_is_downloaded_once_for_every_callsign(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("day.csv", "callsign,dx,db,freq,date\nW1AW,K5OHY,12,14050.0,2026-01-02 10:00:00\n"
                                  "W1AW,K5ABC,9,7030.0,2026-01-02 11:00:00\n")
        reply = mock.Mock(status_code=200, content=buf.getvalue())
        with mock.patch.object(ds.requests, "get", return_value=reply) as get:
            mine = ds.download_rbn_day("20260102", "K5OHY")
            theirs = ds.download_rbn_day("20260102", "K5ABC")
        self.assertEqual(get.call_count, 1)
        self.assertEqual((len(mine), len(theirs)), (1, 1))


class MapZoomAndGainText(unittest.TestCase):
    def _points(self, kms):
        rows = [(km, 45.0, "both", 2.0, -10.0, -12.0) for km in kms]
        return pd.DataFrame(rows, columns=["km", "bearing", "group", "gap", "snr_a", "snr_b"])

    def test_the_map_zooms_to_where_the_cells_are(self):
        import world_map
        near = world_map.fit_radius_km(self._points([300, 400, 500]))
        self.assertLess(near, 3000)
        self.assertGreaterEqual(near, 2000)  # never tighter than the floor
        far = world_map.fit_radius_km(self._points([300, 400, 500] + [9000, 9100, 9200]))
        self.assertGreater(far, 9200)  # far cells pull the map out to include them

    def test_the_map_shows_the_whole_world_when_there_is_nothing_to_fit(self):
        import world_map
        self.assertEqual(world_map.fit_radius_km(self._points([])), world_map.MAX_KM)
        self.assertEqual(world_map.fit_radius_km(self._points([300, 9000]), "dots"), world_map.MAX_KM)

    def test_receivers_shown_as_dots_are_included_in_the_fit(self):
        import world_map
        points = self._points([300, 400, 500, 7000])  # one far receiver, too few there for a cell
        self.assertLess(world_map.fit_radius_km(points), 3000)
        self.assertGreater(world_map.fit_radius_km(points, include_points=True), 7000)

    def test_a_tie_reads_zero_not_minus_zero(self):
        from ui_common import signed
        self.assertEqual(signed(-0.0), "0")
        self.assertEqual(signed(0.04), "0")
        self.assertEqual(signed(3.5), "+3.5")
        self.assertEqual(signed(-2), "-2")


class LowBands(unittest.TestCase):
    """630m and 2200m (WSPR runs on both) are named, loadable, offered in the Band list, and kept out of the Band conditions page."""

    def test_the_wspr_frequencies_are_named(self):
        from rbn_data import get_band
        self.assertEqual(get_band(474.4), "630m")    # 475.7 is the WSPR window's centre; the lowest spot seen is 474.4 kHz
        self.assertEqual(get_band(475.7), "630m")
        self.assertEqual(get_band(137.4), "2200m")
        self.assertEqual(get_band(137.6), "2200m")
        self.assertEqual(get_band(14097.0), "20m")   # the HF bands are unchanged
        self.assertEqual(get_band(1838.0), "160m")
        self.assertEqual(get_band(300.0), "unknown")  # between the two, in no amateur band
        self.assertEqual(get_band(70091.0), "4m")     # the VHF and UHF WSPR frequencies, as the app holds them (kHz)
        self.assertEqual(get_band(144490.5), "2m")
        self.assertEqual(get_band(432300.0), "70cm")
        self.assertEqual(get_band(1296500.0), "23cm")
        self.assertEqual(get_band(50293.0), "6m")     # 6m is unchanged
        self.assertEqual(get_band(88000.0), "unknown")  # the FM broadcast band is in none of them

    def test_wspr_live_numbers_them_minus_one_and_zero(self):
        import wspr_data
        self.assertEqual(wspr_data.band_filter("2200m"), "band = -1")
        self.assertEqual(wspr_data.band_filter("630m"), "band = 0")
        self.assertEqual(wspr_data.band_filter("20m"), "band = 14")  # an HF band is one code, as before
        # a VHF or UHF band takes a run of codes (wspr.live numbers by the first digits of the frequency)
        self.assertEqual(wspr_data.band_filter("4m"), "band = 70")
        self.assertEqual(wspr_data.band_filter("2m"), "band BETWEEN 144 AND 147")
        self.assertEqual(wspr_data.band_filter("70cm"), "band BETWEEN 420 AND 449")
        self.assertEqual(wspr_data.band_filter("23cm"), "band BETWEEN 1240 AND 1299")

    def test_the_band_conditions_page_never_asks_for_them(self):
        """That page asks wspr.live for every code in BAND_CODES; 630m has about 160,000 spots a day and would crowd out the HF ones."""
        import wspr_data
        for band in ("2200m", "630m", "4m", "2m", "70cm", "23cm"):
            self.assertNotIn(band, wspr_data.BAND_CODES)
        for code in (-1, 0, 70, 144, 432, 1296):
            self.assertNotIn(code, cond.CODE_TO_BAND)

    def test_a_station_load_asks_for_the_right_band(self):
        import wspr_data
        seen = []

        def fake_get(url, params=None, headers=None, timeout=None):
            seen.append(params["query"])
            resp = mock.Mock(status_code=200)
            resp.json.return_value = {"meta": [{"name": n} for n in ("time", "tx_sign", "tx_loc", "rx_sign", "rx_loc", "rx_lat", "rx_lon",
                                                                      "frequency", "power", "snr", "drift")],
                                      "data": [["2026-11-07 00:04:00", "SV8ANW", "KM09", "GM0UDL", "IO75", 55.0, -3.0, 474402, 37, -22, 0]]}
            return resp

        with mock.patch.object(wspr_data.requests, "get", fake_get):
            spots, _ = wspr_data.fetch_wspr_spots("SV8ANW", datetime(2026, 11, 7), datetime(2026, 11, 8), band="630m")
            wspr_data.fetch_listening("630m", datetime(2026, 11, 7), datetime(2026, 11, 8))
            wspr_data.fetch_wspr_spots("SV8ANW", datetime(2026, 10, 28), datetime(2026, 10, 29), band="2m")
            wspr_data.fetch_listening("2m", datetime(2026, 10, 28), datetime(2026, 10, 29))
        self.assertIn("band = 0 AND", seen[0])
        self.assertIn("band = 0 AND", seen[1])
        self.assertEqual(list(spots["band"]), ["630m"])   # not "unknown"
        self.assertIn("band BETWEEN 144 AND 147", seen[2])  # 2m: wspr.live files it under 144, 145 and 146
        self.assertIn("band BETWEEN 144 AND 147", seen[3])

    def test_they_come_first_in_the_band_list_and_the_order(self):
        import session_report
        import ui_common
        self.assertEqual(list(ui_common.BAND_COLORS)[:3], ["2200m", "630m", "160m"])
        self.assertEqual(session_report.BAND_ORDER[:3], ["2200m", "630m", "160m"])
        self.assertEqual(list(ui_common.BAND_COLORS)[-5:], ["6m", "4m", "2m", "70cm", "23cm"])
        self.assertEqual(session_report.BAND_ORDER[-5:], ["6m", "4m", "2m", "70cm", "23cm"])
        self.assertEqual(session_report.band_list(pd.DataFrame({"band": ["2m", "20m", "630m", "unknown"]})),
                         ["630m", "20m", "2m", "unknown"])
        self.assertEqual(set(ui_common.BAND_COLORS), set(session_report.BAND_ORDER))  # every band has a colour and a place


class MapWheelZoom(unittest.TestCase):
    """The mouse wheel scrolls the page past a map, and zooms the map only after a click on it."""

    def test_every_map_starts_with_the_wheel_off_and_a_click_turns_it_on(self):
        import maps
        for tiles in maps.TILE_STYLES:
            html = maps.base_map((32.0, -102.0), tiles).get_root().render()
            self.assertIn('"scrollWheelZoom": false', html, tiles)                      # off when the map is drawn
            self.assertIn("map.scrollWheelZoom.disable();", html, tiles)
            self.assertIn("map.on('mousedown', function () { map.scrollWheelZoom.enable(); });", html, tiles)
            self.assertIn("window.addEventListener('blur', function () { map.scrollWheelZoom.disable(); });", html, tiles)

    def test_the_hint_tells_people_what_to_do(self):
        import maps
        self.assertIn("Click the map", maps.ZOOM_HINT)
        self.assertIn("wheel", maps.ZOOM_HINT)


class SlashSkimmerLocations(unittest.TestCase):
    """A skimmer such as KW7MM/7 that RBN's list does not have is placed where KW7MM is; a prefix form is not guessed."""
    LOCS = {"KW7MM": (32.5, -110.9), "KW7MM-2": (32.4, -111.0), "W6ELA": (36.0, -121.0), "DL8LAS": (50.0, 8.0)}

    def test_a_call_with_a_suffix_is_placed_at_its_base_callsign(self):
        self.assertEqual(cs.locate("KW7MM/7", self.LOCS), self.LOCS["KW7MM"])
        self.assertEqual(cs.locate("KW7MM/P", self.LOCS), self.LOCS["KW7MM"])
        self.assertEqual(cs.locate("KW7MM/7-2", self.LOCS), self.LOCS["KW7MM"])
        self.assertEqual(cs.placed_by_base("KW7MM/7", self.LOCS), "KW7MM")

    def test_names_the_list_has_are_not_touched(self):
        self.assertEqual(cs.locate("KW7MM-2", self.LOCS), self.LOCS["KW7MM-2"])
        self.assertEqual(cs.locate("DL8LAS-3", self.LOCS), self.LOCS["DL8LAS"])  # the existing '-#' rule
        self.assertIsNone(cs.placed_by_base("KW7MM-2", self.LOCS))
        self.assertIsNone(cs.placed_by_base("DL8LAS-3", self.LOCS))
        self.assertEqual(cs.locate("KW7MM", {**self.LOCS, "KW7MM/7": (1.0, 2.0)}), self.LOCS["KW7MM"])
        self.assertEqual(cs.locate("KW7MM/7", {**self.LOCS, "KW7MM/7": (1.0, 2.0)}), (1.0, 2.0))  # a name of its own wins
        self.assertIsNone(cs.placed_by_base("KW7MM/7", {**self.LOCS, "KW7MM/7": (1.0, 2.0)}))

    def test_a_prefix_form_or_an_unknown_call_is_not_guessed(self):
        self.assertIsNone(cs.locate("F/W6ELA", self.LOCS))   # a station abroad, not where W6ELA lives
        self.assertIsNone(cs.locate("7/KW7MM", self.LOCS))
        self.assertIsNone(cs.locate("ZZ9ZZ/7", self.LOCS))
        self.assertIsNone(cs.locate("KW7MM/", self.LOCS))
        self.assertIsNone(cs.placed_by_base("F/W6ELA", self.LOCS))


class FarApart(unittest.TestCase):
    """The count behind the floor hint: receivers whose two averages are 20 dB or more apart, whichever antenna is stronger."""

    def table(self, gaps):
        return pd.DataFrame({"gap": gaps}, index=[f"R{i}" for i in range(len(gaps))])

    def test_counts_both_directions_and_the_edge(self):
        self.assertEqual(cs.far_apart(self.table([25.0, -22.5, 20.0, -20.0, 19.9, 0.0, -3.0])), (4, 7))

    def test_a_different_distance_can_be_asked_for(self):
        self.assertEqual(cs.far_apart(self.table([12.0, -15.0, 3.0]), db=10), (2, 3))

    def test_an_empty_or_missing_table_is_zero(self):
        self.assertEqual(cs.far_apart(self.table([])), (0, 0))
        self.assertEqual(cs.far_apart(None), (0, 0))
        self.assertEqual(cs.far_apart(pd.DataFrame({"snr_a": [1.0]})), (0, 0))

    def test_the_suggested_rule_is_the_20_percent_one(self):
        self.assertEqual((cs.FAR_APART_DB, cs.SUGGESTED_WEAK_PCT), (20, 20))


class LogCheck(unittest.TestCase):
    """The log check: reading an ADIF file, the facts from the log alone, and setting it beside spots and WSPR (made-up data)."""

    ADIF = ("Header text\n<ADIF_VER:5>3.1.5 <EOH>\n"
            "<CALL:5>W1AAA <QSO_DATE:8>20261118 <TIME_ON:6>200000 <BAND:3>20m <MODE:2>CW <STATE:2>PA <CONT:2>NA <EOR>\n"
            "<call:5>W2BBB <qso_date:8>20261118 <time_on:4>2001 <band:3>20M <mode:2>CW <state:2>NY <eor>\n"
            "<CALL:5>W1AAA <QSO_DATE:8>20261118 <TIME_ON:6>201000 <FREQ:6>14.060 <MODE:2>CW <STATE:2>PA <CONT:2>NA <EOR>\n"
            "<CALL:5>W3CCC <QSO_DATE:8>20261118 <TIME_ON:6>203000 <BAND:3>15m <MODE:3>SSB <CONT:2>NA <EOR>\n"
            "<CALL:5>W4DDD <QSO_DATE:8>20261118 <TIME_ON:6>203500 <BAND:3>15m <MODE:2>CW <CONT:2>OC <EOR>\n"
            "<CALL:5>W5EEE <QSO_DATE:8>20261118 <BAND:3>20m <MODE:2>CW <EOR>\n"        # no time: left out
            "<STATION_CALLSIGN:5>K5OHY <QSO_DATE:8>20261118 <TIME_ON:6>204000 <BAND:3>20m <EOR>\n")  # no call: left out

    def test_the_contacts_are_read_with_their_lengths_and_either_case(self):
        log = lc.parse_adif(self.ADIF)
        self.assertEqual(list(log["call"]), ["W1AAA", "W2BBB", "W1AAA", "W3CCC", "W4DDD"])
        self.assertEqual(log["time"].iloc[1], pd.Timestamp("2026-11-18 20:01:00"))  # a four digit time has no seconds
        self.assertEqual(list(log["band"]), ["20m", "20m", "20m", "15m", "15m"])  # the third had only a frequency, 14.060 MHz
        self.assertEqual(log["state"].iloc[0], "PA")

    def test_a_file_with_no_contacts_is_refused(self):
        with self.assertRaises(ValueError):
            lc.parse_adif("<ADIF_VER:5>3.1.5 <EOH>\n")

    def test_a_file_without_a_header_still_reads(self):
        log = lc.parse_adif("<CALL:5>W1AAA <QSO_DATE:8>20261118 <TIME_ON:6>200000 <BAND:3>40m <MODE:2>CW <EOR>")
        self.assertEqual(len(log), 1)

    def test_the_facts_from_the_log_alone(self):
        log = lc.parse_adif(self.ADIF)
        s = lc.summary(log)
        self.assertEqual((s["contacts"], s["stations"], s["states"]), (5, 4, 2))
        self.assertEqual(s["best_hour"], 5)  # all five contacts fall in the hour from 20:00
        self.assertAlmostEqual(s["longest_gap_min"], 20.0)
        rep = lc.repeat_stations(log)
        self.assertEqual(len(rep), 0)  # W1AAA came back, but on the same band
        self.assertEqual(lc.same_band_repeats(log), 1)

    def test_stations_that_come_back_on_another_band_are_found_in_band_order(self):
        text = "".join(f"<CALL:5>{c} <QSO_DATE:8>20261118 <TIME_ON:6>{t} <BAND:3>{b} <MODE:2>CW <EOR>\n" for c, t, b in
                        [("W1AAA", "200000", "10m"), ("W1AAA", "201000", "40m"), ("W1AAA", "202000", "20m"), ("W2BBB", "203000", "20m")])
        rep = lc.repeat_stations(lc.parse_adif(text))
        self.assertEqual(list(rep.index), ["W1AAA"])
        self.assertEqual(rep["bands"].iloc[0], ["40m", "20m", "10m"])  # lowest frequency first, the order the app lists bands in

    def test_a_long_pause_on_a_band_starts_a_new_stretch(self):
        text = "".join(f"<CALL:5>W{i}AAA <QSO_DATE:8>20261118 <TIME_ON:6>{t} <BAND:3>20m <MODE:2>CW <EOR>\n"
                        for i, t in enumerate(["200000", "201000", "210000"]))
        stretches = lc.stretches(lc.parse_adif(text))
        self.assertEqual([(b, n) for b, _, _, n in stretches], [("20m", 2), ("20m", 1)])

    def test_the_skimmers_that_were_listening_are_read_from_the_day_file(self):
        csv = ("callsign,de_pfx,de_cont,freq,band,dx,dx_pfx,dx_cont,cqz,mode,db,date,speed,tx_mode\n"
               "K1AAA-2,K,NA,14050.0,20m,W9XYZ,K,NA,5,CQ,10,2026-11-18 20:05:00,20,CW\n"
               "K1AAA-2,K,NA,14050.0,20m,W9XYZ,K,NA,5,CQ,10,2026-11-18 20:10:00,20,CW\n"
               "K2BBB,K,NA,7050.0,40m,W9XYZ,K,NA,5,CQ,10,2026-11-18 20:20:00,20,CW\n"
               "K3CCC,K,NA,14050.0,20m,W9XYZ,K,NA,5,CQ,10,2026-11-18 23:50:00,20,CW\n")  # outside the hours asked for
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("20261118.csv", csv)
        got = lc.listening_from_zip(buffer.getvalue(), pd.Timestamp("2026-11-18 20:00"), pd.Timestamp("2026-11-18 21:00"))
        self.assertEqual(sorted(zip(got["band"], got["b"])), [("20m", "K1AAA"), ("40m", "K2BBB")])  # the -2 is dropped, a repeat counts once

    # ---- setting the log beside spots and WSPR
    def scene(self, spotters=("K1AAA", "K2BBB", "K3CCC", "K5EEE"), wspr_calls=("K1AAA", "K2BBB", "K3CCC", "K4DDD"), obs=22.0):
        """Five CW contacts on 20m between 20:00 and 20:10; four WSPR stations hear a nearby transmitter at +15 dB margin; six skimmers
        are listening in US East and `spotters` spotted you."""
        log = lc.parse_adif("".join(f"<CALL:5>W{i}AAA <QSO_DATE:8>20261118 <TIME_ON:6>20{i:02d}00 <BAND:3>20m <MODE:2>CW <EOR>\n" for i in range(5)))
        spots = pd.DataFrame({"spotter": list(spotters), "band": "20m", "snr": obs, "time": pd.Timestamp("2026-11-18 20:05:00")})
        wspr = pd.DataFrame({"time": pd.Timestamp("2026-11-18 19:50:00"), "tx": "W9TX", "tx_lat": 31.1, "tx_lon": -102.1, "rx": list(wspr_calls),
                             "rx_lat": 40.0, "rx_lon": -75.0, "band": "20m", "power": 30.0, "snr": -10.0})
        calls = ["K1AAA", "K2BBB", "K3CCC", "K4DDD", "K5EEE", "K6FFF"]
        locs = {c: (40.0, -75.0) for c in calls}
        listening = pd.DataFrame({"band": "20m", "slot": pd.Timestamp("2026-11-18 20:00"), "b": calls})
        return log, spots, wspr, listening, locs

    def run_compare(self, log, spots, wspr, listening, locs):
        return lc.compare(log, spots, lambda a, b: wspr[(wspr["time"] > a) & (wspr["time"] <= b)], listening, locs, HOME, 100.0)

    def test_the_page_chance_is_set_against_the_share_of_listening_skimmers_that_spotted_you(self):
        out = self.run_compare(*self.scene())
        row = out["bands"].iloc[0]
        self.assertEqual((row["band"], row["contacts"], row["skimmers"], row["listening"]), ("20m", 5, 4, 6))
        self.assertGreater(row["page"], 0.95)               # a +15 dB margin, with 8 dB of error allowed
        self.assertAlmostEqual(row["spotted"], 4 / 6)       # four of the six listening skimmers spotted you
        self.assertEqual(row["note"], "")

    def test_strength_is_the_skimmers_reading_minus_the_page_figure_minus_the_typical_offset(self):
        out = self.run_compare(*self.scene())
        row = out["bands"].iloc[0]
        self.assertEqual(row["matches"], 3)  # K1AAA, K2BBB and K3CCC both spotted you and are WSPR receivers
        # the page figure at those receivers is +10 dB (-10 dB heard, a 30 dBm transmitter restated to 100 W = 50 dBm); they read 22: 12 above
        self.assertAlmostEqual(row["stronger_db"], 12.0 - lc.TYPICAL_OFFSET_DB)
        self.assertTrue(row["thin"])  # three matches are fewer than MIN_MATCHES

    def test_too_few_matches_give_no_strength(self):
        out = self.run_compare(*self.scene(spotters=("K1AAA", "K5EEE")))
        self.assertTrue(np.isnan(out["bands"].iloc[0]["stronger_db"]))

    def test_regions_with_too_few_wspr_receivers_are_left_out_of_the_percentages(self):
        out = self.run_compare(*self.scene(wspr_calls=("K1AAA", "K2BBB")))
        row = out["bands"].iloc[0]
        self.assertTrue(np.isnan(row["page"]))
        self.assertEqual(out["overall"]["thin_listening"], 6)   # all six listening skimmers are in a region the page greys
        self.assertEqual(out["overall"]["thin_spotted"], 4)

    def test_only_cw_contacts_are_compared(self):
        log, spots, wspr, listening, locs = self.scene()
        log = pd.concat([log, lc.parse_adif("<CALL:5>W9ZZZ <QSO_DATE:8>20261118 <TIME_ON:6>200500 <BAND:3>15m <MODE:3>SSB <EOR>")], ignore_index=True)
        out = self.run_compare(log, spots, wspr, listening, locs)
        self.assertEqual(list(out["bands"]["band"]), ["15m", "20m"])             # highest band first; 15m has only the SSB contact
        self.assertEqual(out["bands"].set_index("band").loc["15m", ["contacts", "other"]].tolist(), [0, 1])
        self.assertEqual(out["bands"].set_index("band").loc["20m", ["contacts", "other"]].tolist(), [5, 0])
        self.assertTrue(np.isnan(out["bands"].set_index("band").loc["15m", "page"]))       # nothing was compared on 15m

    def test_a_band_with_a_big_gap_and_few_spotted_is_called_worked_but_barely_spotted(self):
        out = self.run_compare(*self.scene(spotters=("K1AAA",)))   # one of six
        row = out["bands"].iloc[0]
        self.assertEqual((row["note"], row["tone"]), ("Worked, barely spotted", "warn"))
        out = self.run_compare(*self.scene(spotters=("K1AAA", "K2BBB", "K3CCC", "K4DDD", "K5EEE", "K6FFF")))
        self.assertEqual(out["bands"].iloc[0]["note"], "Page and skimmers close")

    def test_a_log_with_no_wspr_in_the_hour_reports_that(self):
        log, spots, wspr, listening, locs = self.scene()
        out = self.run_compare(log, spots, wspr.iloc[0:0], listening, locs)
        self.assertTrue(out["bands"].iloc[0]["no_picture"])


    def test_a_band_by_region_table_counts_distinct_skimmers_and_the_page_figure(self):
        out = self.run_compare(*self.scene())
        r = out["regions"]
        row = r[(r["band"] == "20m") & (r["region"] == "US East")].iloc[0]
        self.assertEqual((row["contacts"], row["cw"], row["stations"]), (5, 5, 5))
        self.assertEqual((row["on_band"], row["spotted"], row["wspr_receivers"]), (6, 4, 4))
        self.assertGreater(row["page"], 0.95)

    def test_a_region_with_too_few_wspr_receivers_has_no_page_figure_but_still_shows_the_skimmers(self):
        out = self.run_compare(*self.scene(wspr_calls=("K1AAA", "K2BBB")))
        row = out["regions"].iloc[0]
        self.assertTrue(np.isnan(row["page"]))
        self.assertEqual((row["on_band"], row["spotted"]), (6, 4))

    def test_dx_regions_are_listed_before_the_us_and_the_bands_run_from_the_top_down(self):
        text = "".join(f"<CALL:{len(c)}>{c} <QSO_DATE:8>20261118 <TIME_ON:6>20{i:02d}00 <BAND:{len(b)}>{b} <MODE:2>CW <STATE:{len(s)}>{s} <EOR>\n"
                        for i, (c, b, s) in enumerate([("W1AAA", "20m", "PA"), ("DL1ABC", "10m", ""), ("W6BBB", "10m", "CA"), ("W9CCC", "10m", "IL")]))
        log = lc.parse_adif(text)
        self.assertEqual(lc.bands_top_down(log), ["10m", "20m"])             # 10m on top
        regions = lc.compare(log, pd.DataFrame({"spotter": [], "band": [], "snr": [], "time": pd.to_datetime([])}), lambda a, b: pd.DataFrame(), None, {}, HOME, 100.0)["regions"]
        self.assertEqual(list(regions["band"]), ["10m", "10m", "10m", "20m"])
        self.assertEqual(list(regions[regions["band"] == "10m"]["region"]), ["Europe", "US West", "US Central"])   # DX first, then west to east


class LogCheckPictures(unittest.TestCase):
    """The HTML for the log check: nothing breaks when numbers are missing, and the chart has a block for every contact."""

    def setUp(self):
        self.log = lc.parse_adif("".join(
            f"<CALL:5>{c} <QSO_DATE:8>20261118 <TIME_ON:6>{t} <BAND:3>{b} <MODE:2>CW <CONT:2>{k} <EOR>\n"
            for c, t, b, k in [("W1AAA", "200000", "10m", "NA"), ("W1AAA", "201000", "15m", "NA"), ("W1AAA", "202000", "20m", "NA"),
                               ("W2BBB", "202100", "20m", "NA"), ("KH6DE", "202200", "20m", "OC")]))

    def test_the_chart_has_one_block_for_each_contact_and_names_the_follower(self):
        html = lh.afternoon_html(self.log, None)
        self.assertEqual(html.count('class="lc-b'), 5)
        self.assertEqual(html.count('class="lc-b rep'), 3)  # W1AAA's three contacts
        self.assertIn("W1AAA: 3 bands", html)

    def two_day_log(self):
        rows = [("20261112", f"{17 + i // 60:02d}{i % 60:02d}00", "20m") for i in range(0, 180, 3)]       # day one: 60 contacts in 3 hours
        rows += [("20261113", f"{13 + i // 60:02d}{i % 60:02d}00", "40m") for i in range(0, 360, 4)]      # day two, 12 hours later: 90 contacts in 6 hours
        return lc.parse_adif("".join(f"<CALL:6>W{n:05d} <QSO_DATE:8>{d} <TIME_ON:6>{t} <BAND:3>{b} <MODE:2>CW <EOR>\n" for n, (d, t, b) in enumerate(rows)))

    def test_a_log_over_two_days_is_drawn_as_two_charts_with_visible_blocks(self):
        import re
        log = self.two_day_log()
        html = lh.afternoon_html(log, None)
        self.assertEqual(html.count('class="lc-ph"'), 2)            # the 12 hour pause starts a second chart
        self.assertEqual(html.count('class="lc-b'), 150)            # every contact has a block
        widths = {float(w) for w in re.findall(r"width:max\(3px, calc\(([\d.]+)%", html)}
        self.assertTrue(all(w > 0 for w in widths))
        self.assertEqual(len(widths), 2)                            # each chart sizes its slots to its own length
        self.assertIn("2 stretches of activity", html)

    def test_a_block_is_never_narrower_than_a_few_pixels(self):
        self.assertEqual(lh._slot_minutes(120), 2)                  # a short session keeps 2 minute slots
        self.assertGreater(lh._slot_minutes(600), 2)                # a long one uses wider slots so blocks stay readable
        self.assertEqual(lh._slot_minutes(10 ** 6), lh.SLOTS[-1])

    def test_the_band_table_survives_missing_numbers(self):
        bands = pd.DataFrame([{"band": "20m", "contacts": 5, "skimmers": 3, "page": float("nan"), "spotted": float("nan"), "listening": 0,
                               "stronger_db": float("nan"), "matches": 0, "thin": False, "note": "", "tone": "neutral", "no_picture": True,
                               "report": float("nan")}])
        html = lh.band_table_html(bands)
        self.assertNotIn("nan", html.lower())
        self.assertIn("no WSPR picture", html)

    def test_a_band_with_one_contact_is_named_under_the_table_not_given_a_row(self):
        row = {"skimmers": 3, "page": 0.8, "spotted": 0.4, "listening": 10, "stronger_db": 2.0, "matches": 9, "thin": False, "note": "",
               "tone": "neutral", "no_picture": False, "report": float("nan")}
        bands = pd.DataFrame([{"band": "20m", "contacts": 40, **row}, {"band": "60m", "contacts": 1, **row}])
        html = lh.band_table_html(bands)
        self.assertEqual(html.count('class="lc-brow"'), 1)
        self.assertIn("Not shown, with fewer than 3 CW contacts: 60m (1 CW).", html)

    def test_the_region_table_tags_dx_and_greys_a_region_with_no_page_figure(self):
        regions = pd.DataFrame([
            {"band": "10m", "region": "Europe", "contacts": 26, "cw": 24, "stations": 25, "on_band": 78, "spotted": 20, "wspr_receivers": 9, "page": 0.79},
            {"band": "10m", "region": "Africa", "contacts": 1, "cw": 1, "stations": 1, "on_band": 13, "spotted": 4, "wspr_receivers": 1, "page": float("nan")},
            {"band": "10m", "region": "US East", "contacts": 30, "cw": 30, "stations": 29, "on_band": 0, "spotted": 0, "wspr_receivers": 0, "page": float("nan")},
            {"band": "20m", "region": "Europe", "contacts": 5, "cw": 5, "stations": 5, "on_band": 3, "spotted": 1, "wspr_receivers": 4, "page": 0.5}])
        html = lh.regions_html(regions, "10m")
        self.assertEqual(html.count('class="lc-rr"'), 3)                    # only this band's regions
        self.assertEqual(html.count("<em>DX</em>"), 2)                      # Europe and Africa, not the US
        self.assertIn("26 <small>(24 CW)</small>", html)                    # all modes, and how many were CW
        self.assertIn("79%", html)
        self.assertIn("greyed", html)                                       # Africa: one WSPR receiver
        self.assertIn("no skimmers on the band", html)                      # US East has none in the data
        self.assertNotIn("nan", html.lower())

    def test_the_band_row_counts_other_modes_it_cannot_compare(self):
        row = {"band": "10m", "contacts": 54, "other": 21, "skimmers": 50, "page": 0.8, "spotted": 0.2, "listening": 90, "stronger_db": 5.0,
               "matches": 20, "thin": False, "note": "", "tone": "neutral", "no_picture": False, "report": 7.0}
        html = lh.band_table_html(pd.DataFrame([row]))
        self.assertIn("CW contacts", html)
        self.assertIn("+21 other modes", html)

    def test_the_four_tiles_are_facts_from_the_log(self):
        s = lc.summary(self.log)
        html = lh.tiles_html(s, 1)
        self.assertIn("bands worked", html)
        self.assertIn("estimated active rate", html)
        self.assertIn("came back on another band", html)
        self.assertNotIn("typical WSPR station", html)                                       # the strength estimate is in the comparison section
        self.assertIn(f'<div class="n" style="color:var(--a)">{len(s["bands"])}', html)
        self.assertIn("is an estimate", html)                                                # the hover note on the rate
        one = dict(s, bands=["20m"])
        self.assertIn(">20m</div>", lh.tiles_html(one, 0))                                   # a single band is named, not a range

    def test_the_notes_name_stations_outside_north_america(self):
        html = lh.followers_html(self.log, lc.summary(self.log))
        self.assertIn("KH6DE", html)
        self.assertIn("W1AAA", html)


class LogCheckReportsAndPlaces(unittest.TestCase):
    """Signal reports in the log, and placing the stations you worked on a map (made-up data, no network)."""

    def log(self):
        rows = [("W1AAA", "20m", "599", "579", "PA"), ("W2BBB", "20m", "559", "599", "NY"), ("W1AAA", "40m", "579", "599", "PA"),
                ("VE3CCC", "20m", "-12", "-08", "ON"), ("W4DDD", "15m", "", "", "FL")]
        return lc.parse_adif("".join(
            f"<CALL:{len(c)}>{c} <QSO_DATE:8>20261118 <TIME_ON:6>20{i:02d}00 <BAND:{len(b)}>{b} <MODE:2>CW <RST_RCVD:{len(r)}>{r} <RST_SENT:{len(t)}>{t} "
            f"<STATE:{len(s)}>{s} <EOR>\n" for i, (c, b, r, t, s) in enumerate(rows)))

    def test_the_s_digit_of_a_report(self):
        self.assertEqual([lc.s_digit(x) for x in ("599", "579", "59", "339")], [9.0, 7.0, 9.0, 3.0])
        for odd in ("", "-12", "+05", "000", "699", "5", "5999", "abc"):
            self.assertTrue(np.isnan(lc.s_digit(odd)), odd)

    def test_reports_are_read_from_the_log_both_ways(self):
        log = self.log()
        self.assertEqual(list(log["rst_rcvd"]), ["599", "559", "579", "-12", ""])  # what they gave you
        self.assertEqual(list(log["rst_sent"]), ["579", "599", "599", "-08", ""])  # what you gave them

    def test_the_report_summary_counts_only_usable_reports(self):
        r = lc.report_summary(self.log())
        self.assertEqual((r["n"], r["s9"]), (3, 1))
        self.assertAlmostEqual(r["received"], (9 + 5 + 7) / 3)
        self.assertAlmostEqual(r["sent"], (7 + 9 + 9) / 3)
        self.assertEqual(r["weakest"], 5.0)

    def test_a_contact_is_shown_at_the_centre_of_its_grid_square_not_at_the_address(self):
        lat, lon, grid = lc.snap_to_grid4(42.0123, -87.8456)
        self.assertEqual(grid, "EN62")
        self.assertEqual((lat, lon), (42.5, -87.0))   # the middle of EN62: 2 degrees wide, 1 high

    def test_a_lookup_that_only_found_the_country_falls_back_to_the_state(self):
        guess = (39.8, -98.6, None, "center of United States (approximate - enter a grid for accuracy)")
        placed = lc.finish_place(guess, "FL", "United States")
        self.assertEqual((placed["level"], placed["source"]), ("state", "centre of FL"))
        self.assertEqual((placed["lat"], placed["lon"]), lc.STATE_CENTRES["FL"])
        self.assertEqual(lc.finish_place(guess, "", "United States")["level"], "country")  # no state to use
        self.assertEqual(lc.finish_place(guess, "FL", "Venezuela")["level"], "country")   # a state code means nothing outside North America
        self.assertIsNone(lc.finish_place(None, "", ""))

    def test_an_exact_lookup_is_snapped_and_named_by_its_source(self):
        placed = lc.finish_place((42.0123, -87.8456, "EN62ab", "FCC (callook.info)"), "IL", "United States")
        self.assertEqual((placed["level"], placed["source"], placed["grid"]), ("grid", "FCC", "EN62"))

    def places(self):
        return pd.DataFrame({"lat": [42.5, 40.5], "lon": [-77.0, -75.0], "level": ["grid", "state"], "source": ["FCC", "centre of NY"]},
                            index=pd.Index(["W1AAA", "W2BBB"], name="call"))

    def test_the_contacts_with_a_place_are_kept_with_their_reports(self):
        worked = lc.where_worked(self.log(), self.places())
        self.assertEqual(sorted(worked["call"]), ["W1AAA", "W1AAA", "W2BBB"])   # VE3CCC and W4DDD could not be placed
        self.assertEqual(list(worked.sort_values("time")["s"]), [9.0, 5.0, 7.0])
        self.assertIn("grid square", worked["place"].iloc[0])

    def test_the_region_table_sets_contacts_beside_skimmers(self):
        worked = lc.where_worked(self.log(), self.places())
        spots = pd.DataFrame({"spotter": ["K1AAA-2", "K1AAA", "K9ZZZ"], "band": "20m", "snr": 10, "time": pd.Timestamp("2026-11-18 20:05")})
        table = lc.region_table(worked, spots, {"K1AAA-2": (40.0, -75.0), "K9ZZZ": (40.0, -100.0)})
        self.assertEqual(table.loc["US East"].to_dict(), {"contacts": 3, "stations": 2, "skimmers": 1})  # K1AAA twice is one skimmer
        self.assertEqual(table.loc["US Central", "contacts"], 0)
        self.assertEqual(table.loc["US Central", "skimmers"], 1)

    def test_placing_contacts_asks_each_call_once_and_remembers_exact_answers(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"RBN_CACHE_DIR": folder}):
            asked = []

            def lookup(call, skimmers=None):
                asked.append(call)
                return {"W1AAA": (42.0, -87.8, "EN62", "FCC (callook.info)"), "W4DDD": (39.8, -98.6, None, "center of United States (approximate)")}.get(call)

            seen = []
            rows = [("W1AAA", "PA", "United States"), ("W4DDD", "FL", "United States"), ("K0NOPE", "", "")]
            with mock.patch.object(ds, "lookup_callsign_location", lookup):
                table = ds.load_contact_places(rows, {}, progress=lambda done, total: seen.append((done, total)), workers=1)
                self.assertEqual(sorted(table.index), ["W1AAA", "W4DDD"])  # K0NOPE could not be placed at all
                self.assertEqual((table.loc["W1AAA", "level"], table.loc["W4DDD", "level"]), ("grid", "state"))
                self.assertEqual(seen[-1], (3, 3))
                asked.clear()
                ds.load_contact_places(rows, {}, workers=1)
            self.assertEqual(sorted(asked), ["K0NOPE", "W4DDD"])  # the exact answer for W1AAA came from the disk, the guesses are asked again

    def adif(self, *records):
        return "<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(records) + "\n"

    def rec(self, call, hhmm, band="20m", date="20261118", extra=""):
        return f"<CALL:{len(call)}>{call} <QSO_DATE:8>{date} <TIME_ON:4>{hhmm} <BAND:{len(band)}>{band} <MODE:2>CW {extra}<EOR>"

    def test_the_rate_counts_only_the_time_on_the_air(self):
        # five contacts a minute apart, then a night off, then five more: the break is not time spent operating slowly
        recs = [self.rec(f"W{i}AA", f"20{i:02d}") for i in range(5)] + [self.rec(f"K{i}BB", f"20{i:02d}", date="20261119") for i in range(5)]
        s = lc.summary(lc.parse_adif(self.adif(*recs)))
        self.assertAlmostEqual(s["per_hour"], 60.0, delta=1.0)                              # a contact a minute
        self.assertAlmostEqual(s["on_air_hours"], 8 / 60, places=3)                         # eight one minute gaps, not 24 hours
        lone = lc.summary(lc.parse_adif(self.adif(self.rec("W1AA", "2000"), self.rec("W2BB", "2200"))))
        self.assertTrue(np.isnan(lone["per_hour"]))                                         # no two contacts close enough to make a rate
        self.assertIn("–", lh.tiles_html(lone, 0))

    def test_the_page_says_how_many_records_it_read_and_why_it_left_some_out(self):
        text = self.adif(self.rec("W1AA", "2000"), "<CALL:4>W2BB <QSO_DATE:8>20261118 <BAND:3>20m <EOR>",
                         "<CALL:4>W3CC <QSO_DATE:8>20261118 <TIME_ON:4>2002 <BAND:3>20m <MODE:2>CW <EOR>",
                         "<CALL:4>W4DD <QSO_DATE:8>20261118 <TIME_ON:4>2003 <BAND:3>zz9 <MODE:2>CW <EOR>")
        log = lc.parse_adif(text)
        self.assertEqual((len(log), log.attrs["records"], log.attrs["no_time"], log.attrs["no_band"]), (2, 4, 1, 1))

    def test_a_log_made_in_two_places_or_under_two_callsigns_is_noticed(self):
        recs = [self.rec("W1AA", "2000", extra="<STATION_CALLSIGN:5>K5OHY <MY_GRIDSQUARE:6>DM81wx "),
                self.rec("W2BB", "2001", extra="<STATION_CALLSIGN:5>K5OHY <MY_GRIDSQUARE:6>DM81wy "),      # the same 4 character square
                self.rec("W3CC", "2002", extra="<STATION_CALLSIGN:7>K5OHY/P <MY_GRIDSQUARE:6>DM91sl ")]
        log = lc.parse_adif(self.adif(*recs))
        self.assertEqual(lc.origin_counts(log, "my_grid"), [("DM81", 2), ("DM91", 1)])
        self.assertEqual(lc.origin_counts(log, "station"), [("K5OHY", 2), ("K5OHY/P", 1)])
        self.assertEqual(lc.origin_counts(lc.parse_adif(self.adif(self.rec("W1AA", "2000"))), "my_grid"), [])   # a log that does not say

    def test_the_log_says_who_and_where_you_were(self):
        text = ("<ADIF_VER:5>3.1.4 <EOH>\n"
                "<CALL:5>W1AAA <QSO_DATE:8>20261118 <TIME_ON:6>200000 <BAND:3>20m <MODE:2>CW <STATION_CALLSIGN:5>K5OHY <MY_GRIDSQUARE:6>DM81wx <EOR>\n"
                "<CALL:5>W2BBB <QSO_DATE:8>20261118 <TIME_ON:6>200100 <BAND:3>20m <MODE:2>CW <STATION_CALLSIGN:5>K5OHY <MY_GRIDSQUARE:6>DM81wx <EOR>\n"
                "<CALL:5>W3CCC <QSO_DATE:8>20261118 <TIME_ON:6>200200 <BAND:3>20m <MODE:2>CW <STATION_CALLSIGN:7>K5OHY/P <MY_GRIDSQUARE:6>DM91sl <EOR>\n")
        self.assertEqual(lc.log_origin(lc.parse_adif(text)), ("K5OHY", "DM81wx"))            # the most common of each
        bare = lc.parse_adif("<CALL:5>W1AAA <QSO_DATE:8>20261118 <TIME_ON:6>200000 <BAND:3>20m <MODE:2>CW <EOR>")
        self.assertEqual(lc.log_origin(bare), ("", ""))                                     # a logger that leaves them out

    def test_contacts_outside_north_america_are_placed_without_a_lookup(self):
        asked = []

        def lookup(call, skimmers=None):
            asked.append(call)
            return (42.0, -87.8, "EN62", "FCC (callook.info)")

        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"RBN_CACHE_DIR": folder}):
            rows = [("W1AAA", "IL", "United States"), ("DL1ABC", "", "Germany"), ("VK2XYZ", "", "Australia")]
            with mock.patch.object(ds, "lookup_callsign_location", lookup):
                table = ds.load_contact_places(rows, {}, workers=1)
        self.assertEqual(asked, ["W1AAA"])                                                  # only the American station was looked up
        self.assertEqual(sorted(table.index), ["DL1ABC", "VK2XYZ", "W1AAA"])
        self.assertEqual((table.loc["DL1ABC", "level"], table.loc["W1AAA", "level"]), ("country", "grid"))

    def cond_log(self, mode="CW", extra_days=False):
        rows = [("W1AAA", "2000", "20m"), ("W2BBB", "2010", "20m"), ("W3CCC", "2040", "20m"), ("W4DDD", "2105", "15m")]
        if extra_days:
            rows.append(("W5EEE", "2005", "20m"))
        text = "".join(f"<CALL:5>{c} <QSO_DATE:8>{'20261119' if (extra_days and c == 'W5EEE') else '20261118'} <TIME_ON:4>{t} <BAND:3>{b} "
                       f"<MODE:{len(mode)}>{mode} <EOR>" + chr(10) for c, t, b in rows)
        return lc.parse_adif(text)

    def cond_wspr(self):
        """WSPR spots near home on 20m: 30 receivers, half strong and half far below the threshold, heard at 20:10 and 20:40 and 21:10."""
        recs = []
        for i in range(30):
            for t in ("2026-11-18 20:10", "2026-11-18 20:40", "2026-11-18 21:10"):
                recs.append({"time": pd.Timestamp(t), "tx": "N5TX", "tx_lat": 31.0, "tx_lon": -102.0, "rx": f"RX{i}", "rx_lat": 35.0 + i * 0.1,
                             "rx_lon": -90.0, "band": "20m", "power": 37.0, "snr": 10.0 if i % 2 == 0 else -30.0})
        return pd.DataFrame(recs)

    def test_the_conditions_mode_is_the_one_most_contacts_were_made_in(self):
        self.assertEqual(lc.condition_mode(self.cond_log("CW")), "CW")
        self.assertEqual(lc.condition_mode(self.cond_log("USB")), "SSB")
        self.assertEqual(lc.condition_mode(self.cond_log("FT8")), "FT8")
        self.assertEqual(lc.condition_mode(self.cond_log("RTTY")), "CW")                    # something the page has no threshold for

    def test_a_pause_of_hours_starts_a_new_conditions_picture(self):
        self.assertEqual(len(lc.condition_panels(self.cond_log())), 1)
        panels = lc.condition_panels(self.cond_log(extra_days=True))
        self.assertEqual(len(panels), 2)                                                    # the 19 Nov contact is a day later
        self.assertEqual(panels[0], (pd.Timestamp("2026-11-18 20:00"), pd.Timestamp("2026-11-18 21:00")))

    def test_the_conditions_grid_counts_receivers_and_contacts_for_each_half_hour(self):
        asked = []
        wspr = self.cond_wspr()

        def wspr_for(a, b):
            asked.append((a, b))
            return wspr[(wspr["time"] > a) & (wspr["time"] <= b)]

        grid = lc.conditions_grid(self.cond_log(), wspr_for, HOME, 100.0)
        self.assertEqual(sorted(grid["band"].unique()), ["15m", "20m"])
        self.assertEqual(list(grid["slot"].unique()), list(pd.date_range("2026-11-18 20:00", "2026-11-18 21:00", freq="30min")))
        g20 = grid[grid["band"] == "20m"].set_index("slot")
        self.assertEqual(int(g20.loc[pd.Timestamp("2026-11-18 20:00"), "contacts"]), 2)    # the 20:00 and the 20:10 contact
        self.assertEqual(int(g20.loc[pd.Timestamp("2026-11-18 20:30"), "contacts"]), 1)
        self.assertEqual(int(g20.loc[pd.Timestamp("2026-11-18 20:00"), "receivers"]), 30)
        self.assertAlmostEqual(g20.loc[pd.Timestamp("2026-11-18 20:30"), "share"], 0.5, delta=0.1)   # half of them are strong enough
        self.assertTrue(grid[grid["band"] == "15m"]["share"].isna().all())                  # no WSPR on 15m: too few to say
        self.assertTrue(all((b - a) <= pd.Timedelta(hours=lc.FETCH_CHUNK_H) for a, b in asked))   # fetched in chunks, never in one huge query

    def test_the_conditions_notes_compare_each_band_with_itself(self):
        slots = pd.date_range("2026-11-18 20:00", periods=6, freq="30min")
        rows = []
        for band, shares, contacts in (("10m", [0.5, 0.6, 0.9, 0.95, 0.97, 0.97], [8, 0, 0, 0, 0, 0]),
                                       ("15m", [0.95, 0.93, 0.95, 0.96, 0.94, 0.95], [0, 6, 0, 0, 0, 0]),
                                       ("20m", [0.42, 0.40, 0.45, 0.44, 0.41, 0.43], [0, 0, 9, 0, 0, 0]),
                                       ("17m", [0.40, 0.45, 0.50, 0.55, 0.50, 0.45], [0, 0, 7, 0, 0, 0]),
                                       ("40m", [0.9, 0.7, 0.6, 0.5, 0.4, 0.3], [0, 0, 0, 0, 0, 0])):
            for slot, share, n in zip(slots, shares, contacts):
                rows.append({"panel": 0, "slot": slot, "band": band, "receivers": 50, "good": int(share * 50), "share": share, "contacts": n})
        notes = lc.conditions_notes(pd.DataFrame(rows))
        text = " ".join(lead + " " + rest for lead, rest in notes)
        self.assertIn("15m stayed above 90% the whole time", text)
        self.assertIn("10m was higher at other times", text)
        self.assertIn("averaged 50%", text)                                                 # what it was during your contacts
        self.assertIn("The receivers heard can change over a session", text)
        self.assertNotIn("looked its best", text)                                           # no verdict on where you operated
        self.assertIn("17m averaged 50% during your contacts. That is 7 contacts. The session peak was 55%.", text)
        self.assertNotIn("On 15m", text)                                                    # already said to be wide open, so no second line
        self.assertIn("20m stayed steady. It sat at about 45% the whole time you were on it (9 contacts)", text)
        self.assertIn("40m was fading", text)
        self.assertNotIn("nan", text.lower())
        self.assertEqual(lc.conditions_notes(pd.DataFrame(columns=["panel", "slot", "band", "receivers", "good", "share", "contacts"])), [])
        one = pd.DataFrame([{"panel": 0, "slot": slots[0], "band": "20m", "receivers": 90, "good": 60, "share": 0.65, "contacts": 5}])
        self.assertEqual(lc.conditions_notes(one), [])                                      # one box is not enough to call a band steady

    def test_the_conditions_picture_shows_percentages_contacts_and_hatches_thin_boxes(self):
        slots = pd.date_range("2026-11-18 20:00", periods=2, freq="30min")
        grid = pd.DataFrame([{"panel": 0, "slot": slots[0], "band": "20m", "receivers": 300, "good": 99, "share": 0.33, "contacts": 12},
                             {"panel": 0, "slot": slots[1], "band": "20m", "receivers": 300, "good": 120, "share": 0.4, "contacts": 0},
                             {"panel": 0, "slot": slots[0], "band": "10m", "receivers": 4, "good": 3, "share": float("nan"), "contacts": 2},
                             {"panel": 0, "slot": slots[1], "band": "10m", "receivers": 30, "good": 29, "share": 0.97, "contacts": 0}])
        html = lh.conditions_html(grid, [("20m looked weak.", "It was at 33%.")], 75.0, "CW", "America/Chicago")
        self.assertIn("How open each band looked", html)
        self.assertIn("33%", html)
        self.assertIn("97%", html)
        self.assertIn("<i></i>12</em>", html)                                               # the 12 contacts of the first half hour
        self.assertEqual(html.count('class="cell few"'), 1)                                 # the box with 4 receivers is hatched
        self.assertIn("14:00 local", html)                                                  # 20:00Z in Chicago
        self.assertIn("20m looked weak.", html)
        self.assertLess(html.index("read across each row"), html.index('class="lc-cg'))        # the instruction comes before the grid
        self.assertNotIn("always", html)
        self.assertNotIn("nan", html.lower())
        self.assertLess(html.index("20m</div>"), html.index("10m</div>"))                   # the bands run in the order of the grid

    def dx_wspr(self):
        """The 20m spots of cond_wspr plus 16 receivers in Europe (more than 3,000 miles from HOME): 10 strong and 6 far below the threshold."""
        recs = []
        for i in range(16):
            for t in ("2026-11-18 20:10", "2026-11-18 20:40"):
                recs.append({"time": pd.Timestamp(t), "tx": "N5TX", "tx_lat": 31.0, "tx_lon": -102.0, "rx": f"DL{i}AAA", "rx_lat": 50.0,
                             "rx_lon": 8.0 + i * 0.1, "band": "20m", "power": 37.0, "snr": 10.0 if i < 10 else -30.0})
        return pd.concat([self.cond_wspr(), pd.DataFrame(recs)], ignore_index=True)

    def dx_grid(self):
        wspr = self.dx_wspr()
        return lc.conditions_grid(self.cond_log(), lambda a, b: wspr[(wspr["time"] > a) & (wspr["time"] <= b)], HOME, 100.0)

    def test_the_conditions_grid_counts_the_distant_receivers_that_would_hear_you(self):
        grid = self.dx_grid()
        g20 = grid[grid["band"] == "20m"].set_index("slot")
        box = g20.loc[pd.Timestamp("2026-11-18 20:30")]
        self.assertEqual(int(box["dx_heard"]), 16)                                          # the 16 receivers in Europe heard WSPR near home
        self.assertEqual(int(box["dx_good"]), 10)                                           # 10 of them are strong enough for 100 W CW
        self.assertEqual(box["dx_regions"], {"Europe": 10})
        self.assertEqual(int(g20.loc[pd.Timestamp("2026-11-18 20:00"), "dx_good"]), 10)     # the hour to 20:30 holds the 20:10 spots
        self.assertEqual(int(grid[grid["band"] == "15m"]["dx_good"].sum()), 0)              # nothing on 15m
        self.assertTrue((grid["rbn_far"] == 0).all())                                       # RBN is added later
        self.assertEqual(int(grid["dx_heard"].max()), 16)                                   # the US receivers at 35 N are not DX

    def test_a_contact_outside_north_america_is_found_by_continent_or_country(self):
        log = lc.parse_adif("<CALL:5>W1AAA <QSO_DATE:8>20261118 <TIME_ON:4>2000 <BAND:3>20m <MODE:2>CW <CONT:2>NA <EOR>"
                            "<CALL:5>DL1AA <QSO_DATE:8>20261118 <TIME_ON:4>2001 <BAND:3>20m <MODE:2>CW <CONT:2>EU <EOR>"
                            "<CALL:5>JA1AA <QSO_DATE:8>20261118 <TIME_ON:4>2002 <BAND:3>20m <MODE:2>CW <COUNTRY:5>Japan <EOR>"
                            "<CALL:5>K1AAA <QSO_DATE:8>20261118 <TIME_ON:4>2003 <BAND:3>20m <MODE:2>CW <COUNTRY:13>United States <EOR>"
                            "<CALL:5>N1AAA <QSO_DATE:8>20261118 <TIME_ON:4>2004 <BAND:3>20m <MODE:2>CW <EOR>")
        self.assertEqual(list(lc.dx_contacts_mask(log)), [False, True, True, False, False])   # no continent and no country counts as home

    def test_skimmers_far_away_that_spotted_you_are_added_to_the_picture(self):
        grid = self.dx_grid()
        spots = pd.DataFrame({"spotter": ["DL1AAA", "DL1AAA-2", "W5XX", "ZZ9ZZ"], "band": ["20m", "20m", "20m", "20m"],
                              "snr": [10.0] * 4, "time": pd.to_datetime(["2026-11-18 20:10"] * 4)})
        locs = {"DL1AAA": (50.0, 8.0), "DL1AAA-2": (50.0, 8.0), "W5XX": (32.0, -101.0)}     # the last has no place, so it is not counted
        out = lc.add_rbn_far(grid, spots, locs, HOME)
        box = out[(out["band"] == "20m") & (out["slot"] == pd.Timestamp("2026-11-18 20:00"))].iloc[0]
        self.assertEqual(int(box["rbn_far"]), 1)                                            # DL1AAA and its -2 are one skimmer; W5XX is near
        self.assertEqual(int(out["rbn_far"].sum()), 1)
        self.assertEqual(int(lc.add_rbn_far(grid, spots.iloc[0:0], locs, HOME)["rbn_far"].sum()), 0)

    def dx_table(self, rows):
        """A DX grid from (band, boxes) where each box is (dx_good, dx_heard, contacts, dx_contacts, rbn_far, regions)."""
        slots = pd.date_range("2026-11-18 20:00", periods=7, freq="30min")
        out = []
        for band, boxes in rows:
            for slot, (good, heard, n, dxn, rbn, regs) in zip(slots, boxes):
                out.append({"panel": 0, "slot": slot, "band": band, "receivers": 100, "good": 50, "share": 0.5, "contacts": n, "dx_heard": heard,
                            "dx_good": good, "dx_regions": regs, "dx_contacts": dxn, "rbn_far": rbn})
        return pd.DataFrame(out)

    def test_the_dx_lines_state_what_each_band_showed(self):
        e = {"Europe": 2}
        rows = [("15m", [(3, 6, 0, 0, 0, e), (2, 3, 12, 1, 1, e), (1, 3, 28, 0, 0, e), (3, 3, 1, 0, 0, e), (3, 3, 0, 0, 0, e), (3, 3, 0, 0, 0, e), (4, 4, 0, 0, 0, e)]),
                ("20m", [(0, 30, 0, 0, 0, {}), (1, 35, 0, 0, 0, {"Asia": 1}), (0, 27, 0, 0, 0, {}), (0, 29, 12, 0, 0, {}), (1, 33, 34, 1, 0, {"Asia": 1}),
                         (1, 29, 19, 0, 0, {"Asia": 1}), (3, 33, 0, 0, 0, {"Asia": 3})]),
                ("12m", [(0, 7, 0, 0, 0, {}), (0, 7, 16, 0, 0, {})] + [(0, 0, 0, 0, 0, {})] * 5),
                ("30m", [(0, 1, 0, 0, 0, {})] * 4 + [(0, 0, 0, 0, 0, {}), (0, 0, 15, 0, 0, {}), (1, 1, 7, 0, 0, {"Africa": 1})])]
        notes = lc.dx_notes(self.dx_table(rows), 75.0)
        text = {lead: rest for lead, rest in notes}
        self.assertEqual([lead.split()[0] for lead, _ in notes], ["15m", "20m", "30m", "12m"])   # most evidence first, then the bands with none
        self.assertIn("15m had DX that would hear 75 W in 7 of 7 half hours.", text)
        self.assertIn("1 to 4 receivers over 3,000 miles away would have heard 75 W, in Europe.", text["15m had DX that would hear 75 W in 7 of 7 half hours."])
        self.assertIn("You made 41 contacts on 15m, all of them in half hours with DX evidence, and 1 was outside North America.",
                      text["15m had DX that would hear 75 W in 7 of 7 half hours."])
        self.assertIn("RBN skimmers over 3,000 miles from you spotted you on it, first in the half hour from 20:30Z.", text["15m had DX that would hear 75 W in 7 of 7 half hours."])
        lead20 = "20m had DX that would hear 75 W in 4 of 7 half hours."
        self.assertIn("27 to 35 receivers over 3,000 miles away heard WSPR on 20m, but most were too weak for 75 W.", text[lead20])   # many heard, few strong
        self.assertIn("in Asia.", text[lead20])
        self.assertIn("Only the half hour from 23:00Z had one", text["30m showed little DX that would hear 75 W."])
        self.assertIn("2 half hours had receivers over 3,000 miles away that heard WSPR, but none strong enough.", text["12m showed no DX that would hear 75 W."])
        self.assertNotIn("missed", " ".join(a + b for a, b in notes).lower())               # facts, not advice
        self.assertEqual(lc.dx_notes(self.dx_table([("40m", [(0, 0, 3, 0, 0, {})] + [(0, 0, 0, 0, 0, {})] * 6)]), 75.0), [])    # a band with 3 contacts and nothing to say
        self.assertEqual(lc.dx_notes(pd.DataFrame(columns=["panel", "slot", "band", "contacts"]), 75.0), [])

    def test_the_dx_picture_shows_counts_markers_and_four_kinds_of_box(self):
        rows = [("15m", [(3, 6, 12, 1, 1, {"Europe": 3}), (1, 2, 0, 0, 0, {"Europe": 1}), (0, 5, 0, 0, 0, {}), (0, 0, 4, 0, 0, {})] + [(0, 0, 0, 0, 0, {})] * 3)]
        grid = self.dx_table(rows)
        html = lh.dx_windows_html(grid, [("15m had DX.", "Some.")], 75.0, "CW", "America/Chicago")
        self.assertIn("Band conditions while you were on the air", html)
        self.assertEqual(html.count('class="cell s3"'), 1)
        self.assertEqual(html.count('class="cell s1"'), 1)
        self.assertEqual(html.count('class="cell few"'), 1)                                 # DX heard WSPR, none strong enough
        self.assertEqual(html.count('class="cell none"'), 4)
        self.assertIn("<i></i>12</em>", html)                                               # contacts
        self.assertIn("&#9733;", html)                                                      # a contact outside North America
        self.assertIn("<u></u></em>", html)                                                 # a skimmer that far away
        self.assertIn("14:00 local", html)                                                  # 20:00Z in Chicago
        self.assertIn("would hear 75 W", html)
        self.assertIn("15m had DX.", html)
        self.assertNotIn("nan", html.lower())
        self.assertNotIn('<em title="a skimmer that far away spotted you">', lh.dx_windows_html(grid.assign(rbn_far=0), [], 75.0, "CW"))

    def test_where_dx_reached_is_a_band_by_region_table(self):
        e = {"Europe": 2, "Asia": 1}
        grid = self.dx_table([("15m", [(3, 6, 12, 1, 1, e), (3, 3, 0, 0, 0, {"Europe": 3}), (0, 0, 0, 0, 0, {})] + [(0, 0, 0, 0, 0, {})] * 4),
                              ("20m", [(0, 9, 5, 0, 0, {})] * 7)])
        html = lh.dx_regions_html(grid)
        self.assertIn("Where DX reached, by band", html)
        self.assertLess(html.index("<th>Europe</th>"), html.index("<th>Asia</th>"))         # the order of the other tables
        self.assertIn("3 <small>20:00&ndash;21:00</small>", html)                           # up to 3 Europe receivers in the first two half hours
        self.assertIn("1 outside North America", html)
        self.assertEqual(lh.dx_regions_html(self.dx_table([("20m", [(0, 9, 5, 0, 0, {})] * 7)])), "")   # nothing reached: no table

    def test_a_day_without_an_rbn_file_says_when_it_will_have_one(self):
        utc = lc.rbn_ready_message(["20261120"])
        self.assertIn("20 Nov will be ready after 00:02 UTC on 21 Nov", utc)
        self.assertNotIn("(", utc)                                                          # no local time when the zone is not known
        here = lc.rbn_ready_message(["20261120"], "America/Chicago")
        self.assertIn("(Fri 20 Nov, 6:02 PM CST)", here)                                     # the evening before, in the visitor's own time
        self.assertIn("21 Nov", lc.rbn_ready_message(["20261119", "20261120"]))              # the latest missing day decides
        self.assertNotIn("(", lc.rbn_ready_message(["20261120"], "Not/AZone"))              # an unknown zone name is ignored

    def test_a_map_can_leave_out_the_dotted_paths_and_frame_the_points_it_is_given(self):
        from maps import build_map
        worked = lc.where_worked(self.log(), self.places())
        none = pd.DataFrame({"spotter": [], "band": [], "snr": [], "freq": [], "time": pd.to_datetime([])})
        with_paths = build_map(none, {}, HOME, "DM81wx", "K5OHY", False, "Street", "mi", None, contacts=worked, show_spots=False).get_root().render()
        without = build_map(none, {}, HOME, "DM81wx", "K5OHY", False, "Street", "mi", None, contacts=worked, show_spots=False,
                            contact_paths=False, view=[(10.0, -60.0), (50.0, 10.0)]).get_root().render()
        self.assertTrue("\"dashArray\": \"2 6\"" in with_paths)                           # the dotted line's dash pattern
        self.assertFalse("\"dashArray\": \"2 6\"" in without)
        self.assertTrue("[10.0, -60.0], [50.0, 10.0]" in without)                          # the map is framed on the points it was given

    def test_the_map_shows_the_stations_you_worked_coloured_by_report(self):
        from maps import build_map
        worked = lc.where_worked(self.log(), self.places())
        spots = pd.DataFrame({"spotter": ["K1AAA"], "band": "20m", "snr": 12.0, "freq": 14050.0, "time": pd.Timestamp("2026-11-18 20:05")})
        html = build_map(spots, {"K1AAA": (40.0, -75.0)}, HOME, "DM81wx", "K5OHY", False, "Street", "mi", None, contacts=worked).get_root().render()
        self.assertIn("Stations you worked", html)
        self.assertIn("W1AAA", html)
        self.assertIn("They gave", html)          # the popup lists the reports
        only = build_map(spots.iloc[0:0], {}, HOME, "DM81wx", "K5OHY", False, "Street", "mi", None, contacts=worked, show_spots=False).get_root().render()
        self.assertNotIn("SNR (dB)", only)         # no skimmer key when only contacts are shown
        self.assertIn("Stations you worked", only)

    def story_log(self, who):
        """A log built from {call: [bands]}, a contact a minute."""
        rows, t = [], 0
        for call, bands in who.items():
            for b in bands:
                rows.append(f"<CALL:{len(call)}>{call} <QSO_DATE:8>20261118 <TIME_ON:6>20{t // 60:02d}{t % 60:02d} <BAND:{len(b)}>{b} <MODE:2>CW <EOR>")
                t += 1
        return lc.parse_adif("\n".join(rows))

    def test_the_followers_headline_counts_stations_by_how_many_bands(self):
        who = {f"A{i}A": ["10m", "15m", "20m"] for i in range(2)}
        who.update({f"B{i}B": ["15m", "20m"] for i in range(3)})
        who["C1C"] = ["40m"]
        rep = lc.repeat_stations(self.story_log(who))
        self.assertEqual(lh.followers_headline(rep), "2 stations worked you on three bands; another 3 on two.")
        self.assertEqual(lh.followers_headline(lc.repeat_stations(self.story_log({"A1A": ["20m", "40m"]}))), "1 station worked you on two bands.")
        self.assertEqual(lh.followers_headline(lc.repeat_stations(self.story_log({"A1A": ["20m"]}))), "Nobody was worked on more than one band.")

    def test_the_ladder_puts_the_most_bands_first_in_callsign_order_and_shows_each_count(self):
        who = {"ZZ9Z": ["10m", "15m", "20m"], "AA1A": ["10m", "15m", "20m"], "MM5M": ["15m", "20m"]}
        rep = lc.repeat_stations(self.story_log(who))
        self.assertEqual(list(rep.index), ["AA1A", "ZZ9Z", "MM5M"])                        # three bands before two; ties in callsign order
        html = lh.ladder_html(rep, lc.bands_top_down(self.story_log(who)))
        self.assertIn('<span class="n" title="worked on 3 bands">3</span>', html)
        self.assertEqual(html.count('class="cl'), 3)

    def test_the_rest_of_a_long_ladder_goes_in_a_show_all_box(self):
        who = {f"K{i:02d}AA": ["20m", "40m"] for i in range(30)}
        log = self.story_log(who)
        self.assertEqual(lh.followers_html(log, lc.summary(log)).count('class="cl'), 12)      # the card shows 12
        rest = lh.ladder_rest_html(log)
        self.assertEqual(rest.count('class="cl'), 18)                                          # the other 18 wait in the box
        self.assertIn("K29AA", rest)
        self.assertIn("K12AA", rest)
        self.assertNotIn("K11AA", rest)
        self.assertIn("station · bands", lh.followers_html(log, lc.summary(log)))              # the number beside each callsign has a label

    def test_the_notes_beside_the_ladder_have_no_warning_and_no_report_average(self):
        log = lc.parse_adif("".join(f"<CALL:5>W{i}AAA <QSO_DATE:8>20261118 <TIME_ON:6>20{i:02d}00 <BAND:3>20m <MODE:2>CW <RST_RCVD:3>599 <RST_SENT:3>579 <EOR>\n"
                                    for i in range(6)))
        html = lh.followers_html(log, lc.summary(log))
        self.assertNotIn("barely spotted", html)
        self.assertNotIn("S9.0", html)
        self.assertIn("Busiest stretch", html)

    def test_a_band_with_only_two_contacts_gets_no_warning(self):
        self.assertEqual(lc._note(2, 0.9, 0.0), ("", "neutral"))                           # two contacts, nobody spotted: too little to say
        self.assertEqual(lc._note(3, 0.9, 0.0), ("Worked, barely spotted", "warn"))        # three is enough

    def test_contacts_are_coloured_by_report_and_ringed_when_they_followed_you(self):
        from maps import build_map
        worked = lc.where_worked(self.log(), self.places())
        worked = worked.assign(bands_worked=worked["call"].map({"W1AAA": 3, "W2BBB": 1}))
        none = pd.DataFrame({"spotter": [], "band": [], "snr": [], "freq": [], "time": pd.to_datetime([])})
        ringed = build_map(none, {}, HOME, "DM81wx", "K5OHY", False, "Street", "mi", None, contacts=worked, show_spots=False,
                           contact_paths=False).get_root().render()
        plain = build_map(none, {}, HOME, "DM81wx", "K5OHY", False, "Street", "mi", None, contacts=worked.drop(columns="bands_worked"),
                          show_spots=False, contact_paths=False).get_root().render()
        self.assertEqual(ringed.count("0 0 0 2.5px #111"), 1)                               # only W1AAA (three bands) has the ring
        self.assertEqual(plain.count("0 0 0 2.5px #111"), 0)                                # no ring when the log does not say
        self.assertIn("#8b0000", ringed)                                                    # the colour is still the report (S9 is dark red)
        self.assertIn("worked on 3 bands", ringed)
