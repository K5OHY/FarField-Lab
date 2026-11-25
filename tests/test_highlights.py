"""The session highlights: when each other continent first answered, the farthest contact on each band, new stations by the hour, and RBN spot timing."""
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

    def test_new_stations_are_counted_once_each_hour_by_hour_with_gaps_kept(self):
        hours = hl.new_by_hour(self.log())
        self.assertEqual(hours["hour"].dt.strftime("%H").tolist(), ["20", "21", "22"])
        self.assertEqual(hours["contacts"].tolist(), [2, 2, 2])
        self.assertEqual(hours["new"].tolist(), [2, 1, 2])                                         # W1AAA's second contact (on 15m) is not a new station
        quiet = log_of(rec("W1AAA", "2000", gridsquare="FN31"), rec("W1BBB", "2250", gridsquare="FN31"))
        gaps = hl.new_by_hour(quiet)
        self.assertEqual(gaps["contacts"].tolist(), [1, 0, 1])
        self.assertTrue(pd.isna(gaps["share"].iloc[1]))                                            # no contacts, so no share, not a zero share

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
        first, far, hours = hl.first_by_continent(p), hl.farthest_by_band(p), hl.new_by_hour(self.log())
        lines = hl.highlight_lines(first, far, hours)
        self.assertTrue(lines[0].startswith("The first contact outside your continent was Europe: DL1AAA on 20m at 21:00 UTC, 1 h into the session."), lines[0])
        for line in lines:
            self.assertEqual(lo.unsupported_claims(line), [], line)
        self.assertEqual(hl.highlight_lines(first.iloc[0:0], far.iloc[0:0], hours.iloc[0:0]), [])

    def test_the_card_shows_the_three_tables_and_is_empty_with_nothing_to_show(self):
        p = self.places()
        first, far, hours = hl.first_by_continent(p), hl.farthest_by_band(p), hl.new_by_hour(self.log())
        html = lh.highlights_html(first, far, hours, hl.highlight_lines(first, far, hours))
        for text in ("Session highlights", "When each other continent first answered", "The farthest contact on each band", "New stations in each hour", "DL1AAA"):
            self.assertIn(text, html)
        self.assertEqual(lh.highlights_html(first.iloc[0:0], far.iloc[0:0], hours.iloc[0:0], []), "")


if __name__ == "__main__":
    unittest.main()
