"""The session highlights: when each other continent first answered, the farthest contact on each band, the repeat line, and RBN spot timing."""
import unittest

import pandas as pd

import log_check as lc
import log_check_html as lh
import log_highlights as hl
import log_openings as lo

HOME = (31.0, -102.0)
T = pd.Timestamp


def log_of(*records):
    return lc.parse_adif("<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(records) + "\n")


def rec(call, hhmm, band="20m", date="20261118", **fields):
    extra = "".join(f"<{k.upper()}:{len(str(v))}>{v} " for k, v in fields.items())
    return f"<CALL:{len(call)}>{call} <QSO_DATE:8>{date} <TIME_ON:4>{hhmm} <BAND:{len(band)}>{band} <MODE:2>CW {extra}<EOR>"


class Highlights(unittest.TestCase):
    def log(self):
        return log_of(rec("W1AAA", "2000", gridsquare="FN31"), rec("W1BBB", "2010", band="15m", gridsquare="FN31"),
                      rec("DL1AAA", "2100", gridsquare="JN58"), rec("W1AAA", "2105", band="15m", gridsquare="FN31"),
                      rec("JA1ZZZ", "2230", band="15m", gridsquare="PM95"), rec("DL1BBB", "2240", gridsquare="KO02"))

    def places(self):
        return lc.contact_places(self.log(), HOME)

    def test_each_other_continent_is_listed_in_the_order_it_first_answered_and_your_own_is_left_out(self):
        first = hl.first_by_continent(self.places(), "NA")
        self.assertEqual(first["code"].tolist(), ["EU", "AS"])
        eu = first.iloc[0]
        self.assertEqual((eu["call"], eu["band"], eu["stations"]), ("DL1AAA", "20m", 2))
        self.assertAlmostEqual(eu["since"], 60.0)                                                  # an hour after the first contact of the log
        self.assertEqual(hl.first_by_continent(self.places(), "EU")["code"].tolist(), ["NA", "AS"])     # a station in Europe does not list Europe, and does list North America
        self.assertEqual(len(hl.first_by_continent(None)), 0)

    def test_the_farthest_contact_on_each_band_is_found_highest_band_first(self):
        far = hl.farthest_by_band(self.places())
        self.assertEqual(far["band"].tolist(), ["15m", "20m"])
        self.assertEqual(far.set_index("band").loc["15m", "call"], "JA1ZZZ")
        self.assertEqual(far.set_index("band").loc["20m", "call"], "DL1BBB")
        self.assertTrue((far["km"] > 0).all())

    def test_a_repeat_is_a_station_already_worked_on_another_band_or_again_on_the_same_one(self):
        r = hl.repeat_contacts(self.log())
        self.assertEqual((r["total"], r["other_band"], r["same_band"], r["repeats"]), (6, 1, 0, 1))      # W1AAA came back on 15m
        again = log_of(rec("W1AAA", "2000"), rec("W1AAA", "2010"), rec("W1AAA", "2020", band="15m"), rec("W1BBB", "2030"))
        r = hl.repeat_contacts(again)
        self.assertEqual((r["same_band"], r["other_band"], r["repeats"]), (1, 1, 2))                       # the second 20m contact is a repeat, the 15m one is on another band
        self.assertAlmostEqual(r["share"], 0.5)
        self.assertEqual(hl.repeat_contacts(None)["total"], 0)

    def test_the_repeat_line_is_written_only_when_enough_of_the_contacts_were_repeats(self):
        p = self.places()
        first, far = hl.first_by_continent(p), hl.farthest_by_band(p)
        hunters_only = hl.highlight_lines(first, far, hl.repeat_contacts(self.log()))
        self.assertFalse(any("already worked" in line for line in hunters_only))                              # a station back on another band is a hunter, not a repeat
        few = {"total": 100, "same_band": 2, "other_band": 30, "repeats": 32, "share": 0.32}
        self.assertFalse(any("already worked" in line for line in hl.highlight_lines(first, far, few)))        # two in a hundred is not worth a line
        both = {"total": 20, "same_band": 2, "other_band": 3, "repeats": 5, "share": 0.25}
        text = [line for line in hl.highlight_lines(first, far, both) if "already worked" in line][0]
        self.assertEqual(text, "2 of 20 contacts (10%) were with a station already worked on the same band; a further 3 were with stations that came back on another band.")
        alone = {"total": 20, "same_band": 2, "other_band": 0, "repeats": 2, "share": 0.1}
        self.assertEqual([line for line in hl.highlight_lines(first, far, alone) if "already worked" in line],
                         ["2 of 20 contacts (10%) were with a station already worked on the same band."])
        self.assertFalse(any("already worked" in line for line in hl.highlight_lines(first, far)))            # no repeats given, no line
        for line in hl.highlight_lines(first, far, both):
            self.assertEqual(lo.unsupported_claims(line), [], line)

    def test_the_timing_of_the_spots_sits_beside_the_contacts_band_by_band(self):
        spots = pd.DataFrame({"spotter": ["A", "B", "C"], "band": ["20m", "20m", "15m"], "snr": [10.0] * 3,
                              "time": [T("2026-11-18 19:58"), T("2026-11-18 22:41"), T("2026-11-18 20:05")]})
        timing = hl.rbn_timing(self.log(), spots).set_index("band")
        self.assertEqual(timing.loc["20m", "first_spot"], T("2026-11-18 19:58"))
        self.assertEqual(timing.loc["20m", "last_spot"], T("2026-11-18 22:41"))
        self.assertEqual(timing.loc["20m", "first_contact"], T("2026-11-18 20:00"))
        self.assertEqual(timing.loc["15m", "spots"], 1)
        self.assertEqual(len(hl.rbn_timing(self.log(), None)), 0)

    def test_the_sentences_pass_the_wording_guard_and_say_when_things_happened(self):
        p = self.places()
        first, far = hl.first_by_continent(p), hl.farthest_by_band(p)
        lines = hl.highlight_lines(first, far)
        self.assertTrue(lines[0].startswith("The first contact outside your continent was Europe: DL1AAA on 20m at 21:00 UTC, 1 h into the session."), lines[0])
        for line in lines:
            self.assertEqual(lo.unsupported_claims(line), [], line)
        self.assertEqual(hl.highlight_lines(first.iloc[0:0], far.iloc[0:0]), [])

    def test_the_card_shows_the_two_tables_and_is_empty_with_nothing_to_show(self):
        p = self.places()
        first, far = hl.first_by_continent(p), hl.farthest_by_band(p)
        both = {"total": 20, "same_band": 2, "other_band": 3, "repeats": 5, "share": 0.25}
        html = lh.highlights_html(first, far, hl.highlight_lines(first, far, both))
        for text in ("Session highlights", "When each other continent first answered", "The farthest contact on each band", "DL1AAA", "already worked on the same band"):
            self.assertIn(text, html)
        self.assertNotIn("New stations in each hour", html)                                          # the hourly table said little, since nearly every contact is a new station
        self.assertEqual(lh.highlights_html(first.iloc[0:0], far.iloc[0:0], []), "")


class RateAndLink(unittest.TestCase):
    """How fast the contacts came in, and the link to the My spots page for the session."""

    def log(self):
        # 20:00-20:50 a steady run on 20m (one every 5 minutes); then a 90 minute pause; then 22:20-22:35 on 15m
        return log_of(*[rec(f"W1A{i}", f"20{m:02d}", gridsquare="FN31") for i, m in enumerate(range(0, 55, 5))],
                      *[rec(f"W2B{i}", f"22{m:02d}", band="15m", gridsquare="FN31") for i, m in enumerate((20, 24, 28, 32))])

    def test_a_bar_is_ten_minutes_and_its_height_is_the_count_of_contacts(self):
        bars, line = hl.rate_table(self.log())
        first = bars[bars["slot"] == T("2026-11-18 20:00")]
        self.assertEqual(first["band"].tolist(), ["20m"])
        self.assertEqual(int(first["contacts"].iloc[0]), 2)                                     # 20:00 and 20:05
        self.assertEqual(first["rate"].iloc[0], 12.0)                                           # 2 contacts in 10 minutes is a pace of 12 an hour
        self.assertEqual(first["pace"].iloc[0], 12.0)
        self.assertEqual((first["end"].iloc[0] - first["slot"].iloc[0]), pd.Timedelta(minutes=10))
        self.assertEqual(set(bars["band"]), {"20m", "15m"})

    def test_the_pace_of_a_bin_adds_up_every_band_in_it(self):
        mixed = log_of(rec("W1AAA", "2000", band="20m"), rec("W1BBB", "2002", band="15m"), rec("W1CCC", "2004", band="15m"))
        bars, _ = hl.rate_table(mixed)
        self.assertEqual(set(bars["pace"]), {18.0})                                             # three contacts in ten minutes, whichever band each was on

    def test_a_pause_breaks_the_line_and_is_not_a_dip_to_zero(self):
        bars, line = hl.rate_table(self.log())
        self.assertEqual(len(line), 16)                                                         # every ten minutes from 20:00 to 22:30
        inside = line[(line["mid"] > T("2026-11-18 21:00")) & (line["mid"] < T("2026-11-18 22:00"))]
        self.assertTrue(inside["rolling"].isna().all())                                         # inside the 90 minute pause: no value at all
        busy = line[line["slot"] == T("2026-11-18 20:20")].iloc[0]
        self.assertAlmostEqual(busy["rolling"], 13.2)                                           # 11 contacts (20:00 to 20:50) in the 50 minutes on the air within the hour around 20:25
        self.assertEqual(len(hl.rate_table(None)[0]), 0)

    def test_the_busiest_stretch_is_a_pace_not_a_rate(self):
        best = hl.best_stretch(self.log(), 10)
        self.assertEqual(best["contacts"], 3)                                                   # three in any ten minutes of the 5 minute run
        self.assertEqual(best["pace"], 18.0)
        line = hl.rate_line(best)
        self.assertIn("a pace of 18 an hour if it had been kept up", line)
        self.assertEqual(lo.unsupported_claims(line), [])
        self.assertIsNone(hl.best_stretch(log_of(rec("W1AAA", "2000"), rec("W1BBB", "2001")), 10))
        self.assertEqual(hl.rate_line(None), "")

    def test_the_first_contact_on_each_band_is_marked(self):
        marks = hl.band_starts(self.log())
        self.assertEqual(marks["band"].tolist(), ["20m", "15m"])
        self.assertEqual(marks["call"].tolist(), ["W1A0", "W2B0"])

    def test_the_bars_and_the_line_are_two_charts_on_one_time_axis_each_named_for_what_it_shows(self):
        chart = hl.rate_chart(self.log(), {"20m": "#800080", "15m": "#444444"})
        spec = chart.to_dict()
        self.assertEqual(len(spec["vconcat"]), 2)                                               # the bars above, the line below
        self.assertEqual(len(spec["vconcat"][0]["layer"]), 2)                                   # the bars and the band marks
        text = str(spec)
        for part in ("Contacts in each 10 minutes, by band", "Contacts an hour, over the hour around (time on the air only)", "Contacts in 10 minutes",
                     "Contacts on this band", "All bands, at that pace", "#800080"):
            self.assertIn(part, text)
        self.assertNotIn("'stroke': 'white'", text)                                             # no white outline on the bars
        self.assertEqual(spec["resolve"]["scale"]["x"], "shared")
        domain = spec["vconcat"][0]["layer"][0]["encoding"]["y"]["scale"]["domain"]
        tallest = int(hl.rate_table(self.log())[0].groupby("slot")["contacts"].sum().max())
        self.assertGreaterEqual(domain[1], tallest)                                             # the axis reaches the tallest stack, so no bar is cut off
        self.assertIsNone(hl.rate_chart(self.log().iloc[0:0], {}))

    def test_the_link_opens_my_spots_on_the_day_and_the_hours_of_the_session(self):
        link = lc.spots_link("K5OHY", "DM81wx", self.log())
        self.assertTrue(link.startswith("./?"))                                                 # My spots is the main page, at the root: a /spots path would say page not found
        for part in ("call=K5OHY", "src=rbn", "grid=DM81wx", "date=2026-11-18", "t0=19%3A50", "t1=22%3A42", "go=1"):
            self.assertIn(part, link)                                                           # ten minutes either side of the first and last contact
        self.assertNotIn("grid=", lc.spots_link("K5OHY", "", self.log()))
        self.assertIn("call=K5OHY%2FP", lc.spots_link("K5OHY/P", "", self.log()))                # a slash in a callsign is kept safe in the address

    def test_a_log_over_two_days_links_a_date_range_and_no_time_window(self):
        two = log_of(rec("W1AAA", "2300"), rec("W1BBB", "0100", date="20261119"))
        link = lc.spots_link("K5OHY", "", two)
        self.assertIn("date=2026-11-18..2026-11-19", link)
        self.assertNotIn("t0=", link)

    def test_the_window_stays_inside_the_day(self):
        edge = log_of(rec("W1AAA", "0003"), rec("W1BBB", "2358"))
        link = lc.spots_link("K5OHY", "", edge)
        self.assertIn("t0=00%3A00", link)
        self.assertIn("t1=23%3A59", link)


if __name__ == "__main__":
    unittest.main()
