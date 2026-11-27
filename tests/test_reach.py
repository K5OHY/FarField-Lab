"""Where RBN heard you: the skimmers that reported you on each band, counted over the half hours with a logged CW contact, beside the skimmers reporting anyone then."""
import unittest

import pandas as pd

import log_check as lc
import log_check_html as lh
import log_openings as lo
import log_reach as lr

T = pd.Timestamp
HOME = (32.2, -101.5)
COLOURS = {"20m": "#800080", "40m": "#ffa500", "15m": "#444444"}
LOCS = {"W1AW-2": (41.7, -72.7), "W1AW-3": (41.7, -72.7), "DL1AAA": (50.0, 8.0), "K9XYZ": (40.0, -88.0), "VK6ANC": (-32.0, 116.0), "W2ABC": (40.0, -74.0),
        "N0OUT": (40.0, -100.0), "K1ABC": (42.0, -71.0), "W6AAA": (37.0, -122.0), "W0BBB": (39.0, -105.0), "VE3CCC": (43.0, -79.0), "W5DDD": (30.0, -97.0)}


def rec(call, hhmm, band="20m", mode="CW", date="20261118"):
    return f"<CALL:{len(call)}>{call} <QSO_DATE:8>{date} <TIME_ON:4>{hhmm} <BAND:{len(band)}>{band} <MODE:{len(mode)}>{mode} <EOR>"


def log_of(*records):
    return lc.parse_adif("<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(records) + "\n")


def listening(*rows):
    return pd.DataFrame([(b, T(slot), c) for b, slot, c in rows], columns=["band", "slot", "b"])


def spots(*rows):
    return pd.DataFrame([(c, b, T(t), 10.0) for c, b, t in rows], columns=["spotter", "band", "time", "snr"])


class TheCounts(unittest.TestCase):
    def log(self):
        # 20m: two half hours with a CW contact (14:00 and 14:30) and one SSB contact at 15:00; 40m: one half hour (12:00); 15m: one half hour with nobody reporting you
        return log_of(rec("A1AAA", "1405"), rec("A1BBB", "1440"), rec("A1CCC", "1500", mode="SSB"), rec("B1AAA", "1210", band="40m"), rec("C1AAA", "1010", band="15m"))

    def listening(self):
        return listening(("20m", "2026-11-18 14:00", "W1AW"), ("20m", "2026-11-18 14:15", "W1AW"), ("20m", "2026-11-18 14:30", "W1AW"),      # one skimmer, three slots: counted once
                         ("20m", "2026-11-18 14:00", "DL1AAA"), ("20m", "2026-11-18 14:00", "K9XYZ"),
                         ("20m", "2026-11-18 13:00", "N0OUT"), ("20m", "2026-11-18 16:00", "K1ABC"),                                          # active, but not in a half hour with a contact
                         ("40m", "2026-11-18 12:00", "VK6ANC"), ("40m", "2026-11-18 12:15", "W2ABC"),
                         ("15m", "2026-11-18 10:00", "W5DDD"), ("15m", "2026-11-18 10:15", "W0BBB"))

    def spots(self):
        return spots(("W1AW-2", "20m", "2026-11-18 14:10"), ("W1AW-3", "20m", "2026-11-18 14:40"), ("DL1AAA", "20m", "2026-11-18 14:35"),     # W1AW twice, under two suffixes
                     ("K1ABC", "20m", "2026-11-18 16:05"),                                                                                  # a spot outside the half hours
                     ("VK6ANC", "40m", "2026-11-18 12:20"))

    def rows(self, **kw):
        out = lr.reach_by_band(self.log(), self.spots(), self.listening(), LOCS, HOME, **kw)
        return {r["band"]: r for r in out}

    def test_the_half_hours_are_those_with_a_logged_cw_contact_on_the_band(self):
        self.assertEqual(lr.window_starts(self.log(), "20m"), [T("2026-11-18 14:00"), T("2026-11-18 14:30")])         # the SSB contact at 15:00 does not open a half hour
        self.assertEqual(lr.window_starts(self.log(), "40m"), [T("2026-11-18 12:00")])

    def test_a_skimmer_is_counted_once_per_band_and_only_in_those_half_hours(self):
        r = self.rows()["20m"]
        self.assertEqual((r["reporters"], r["active"]), (2, 3))                          # W1AW (two suffixes, two half hours) and DL1AAA; K9XYZ was active and did not report you
        self.assertEqual(r["reports"], 3)                                                # three spots of you in the half hours (the one at 16:05 is outside them)
        self.assertEqual(r["spots_total"], 4)                                            # but the whole log's four spots of you on the band are kept for the first and last spot
        self.assertEqual((r["first_spot"], r["last_spot"]), (T("2026-11-18 14:10"), T("2026-11-18 16:05")))

    def test_the_regions_add_up_to_the_active_skimmers_and_a_skimmer_without_a_place_is_still_counted(self):
        r = self.rows()["20m"]
        self.assertEqual(sum(a for _, a in r["regions"].values()), r["active"])
        self.assertEqual(r["regions"]["Europe"], [1, 1])
        self.assertEqual(r["regions"]["US East"], [1, 1])
        self.assertEqual(r["regions"]["US Central"], [0, 1])
        elsewhere = lr.reach_by_band(self.log(), self.spots(), self.listening().pipe(lambda d: pd.concat([d, listening(("20m", "2026-11-18 14:00", "ZZ9ZZZ"))])), LOCS, HOME)
        again = {r["band"]: r for r in elsewhere}["20m"]
        self.assertEqual(again["regions"][lr.UNKNOWN], [0, 1])                           # a receiver the skimmer list does not know goes under its own heading
        self.assertEqual(sum(a for _, a in again["regions"].values()), again["active"])

    def test_the_farthest_report_is_the_farthest_skimmer_that_reported_you_in_those_half_hours(self):
        km, call, region = self.rows()["20m"]["farthest"]
        self.assertEqual((call, region), ("DL1AAA", "Europe"))
        self.assertGreater(km, 8000)
        self.assertEqual(self.rows()["40m"]["farthest"][1], "VK6ANC")

    def test_contacts_in_other_modes_are_not_counted_but_are_said(self):
        r = self.rows()["20m"]
        self.assertEqual((r["contacts"], r["other_mode"]), (2, 1))

    def test_no_reports_of_you_is_a_result_not_a_missing_file(self):
        r = self.rows()["15m"]
        self.assertEqual((r["state"], r["reporters"], r["active"], r["farthest"]), ("ok", 0, 2, None))               # two skimmers reported others and none reported you

    def test_nobody_reporting_at_all_is_told_apart_from_no_reports_of_you(self):
        quiet = lr.reach_by_band(self.log(), spots(), listening(("40m", "2026-11-18 12:00", "VK6ANC")), LOCS, HOME)
        self.assertEqual({r["band"]: r["state"] for r in quiet}["20m"], "no_activity")

    def test_a_missing_file_or_an_unreadable_list_is_unavailable_not_zero(self):
        gone = self.rows(missing={"20261118"})
        self.assertTrue(all(r["state"] == "unavailable" for r in gone.values()))
        self.assertEqual(gone["20m"]["missing_days"], ["20261118"])
        unreadable = {r["band"]: r for r in lr.reach_by_band(self.log(), self.spots(), None, LOCS, HOME)}
        self.assertTrue(all(r["state"] == "unavailable" for r in unreadable.values()))
        self.assertEqual(unreadable["20m"]["missing_days"], [])
        self.assertEqual(lr.reach_by_band(log_of(rec("A1AAA", "1405", mode="SSB")), self.spots(), self.listening(), LOCS, HOME), [])      # a phone-only log has nothing to count

    def test_a_missing_day_leaves_only_its_own_half_hours_out(self):
        two = log_of(rec("A1AAA", "1405"), rec("A1BBB", "1405", date="20261119"))
        out = lr.reach_by_band(two, spots(("W1AW-2", "20m", "2026-11-18 14:10"), ("W1AW-2", "20m", "2026-11-19 14:10")),
                               listening(("20m", "2026-11-18 14:00", "W1AW"), ("20m", "2026-11-19 14:00", "W1AW"), ("20m", "2026-11-19 14:00", "DL1AAA")), LOCS, HOME, missing={"20261119"})[0]
        self.assertEqual((out["windows"], out["windows_all"], out["reporters"], out["active"], out["missing_days"]), (1, 2, 1, 1, ["20261119"]))

    def test_the_map_and_the_card_read_the_same_spots_over_the_same_half_hours(self):
        """The skimmers on the map are the skimmers in the card: the same half hours, the same spots, and a skimmer with a -# suffix counted once."""
        for band in ("20m", "40m", "15m"):
            inside, half_hours = lr.window_spots(self.log(), self.spots(), band)
            card = self.rows()[band]
            self.assertEqual(lr.reporter_count(inside), card["reporters"], band)
            self.assertEqual(len(inside), card["reports"], band)
            self.assertEqual(half_hours, card["windows"], band)
        inside, _ = lr.window_spots(self.log(), self.spots(), "20m")
        self.assertEqual(inside["spotter"].nunique(), 3)                                  # W1AW-2, W1AW-3 and DL1AAA as written
        self.assertEqual(lr.reporter_count(inside), 2)                                    # W1AW once, and DL1AAA
        none, count = lr.window_spots(log_of(rec("A1AAA", "1405", mode="SSB")), self.spots(), "20m")
        self.assertEqual((len(none), count), (0, 0))                                      # a band with only phone contacts has no half hours
        empty, count = lr.window_spots(self.log(), None, "20m")
        self.assertEqual((len(empty), count), (0, 2))

    def test_the_old_whole_stretch_counts_are_kept_to_show_what_narrowing_changes(self):
        r = self.rows()["20m"]
        self.assertGreaterEqual(r["active_wide"], r["reporters_wide"])
        self.assertIn("reporters_wide", r)


class TheCard(unittest.TestCase):
    def rows(self):
        log = log_of(rec("A1AAA", "1405"), rec("A1BBB", "1440"), rec("B1AAA", "1210", band="40m"), rec("C1AAA", "1010", band="15m"))
        sp = spots(("W1AW-2", "20m", "2026-11-18 14:10"), ("DL1AAA", "20m", "2026-11-18 14:35"), ("VK6ANC", "40m", "2026-11-18 12:20"))
        ls = listening(("20m", "2026-11-18 14:00", "W1AW"), ("20m", "2026-11-18 14:00", "DL1AAA"), ("20m", "2026-11-18 14:00", "K9XYZ"),
                       ("40m", "2026-11-18 12:00", "VK6ANC"), ("40m", "2026-11-18 12:00", "W2ABC"), ("15m", "2026-11-18 10:00", "W5DDD"))
        return lr.reach_by_band(log, sp, ls, LOCS, HOME)

    def text(self, html):
        import re
        return re.sub(r"<[^>]+>", " ", html)

    def test_the_card_leads_with_the_farthest_report_and_opens_only_that_band(self):
        html = lh.reach_html(self.rows(), COLOURS, 3, 3)
        self.assertIn("Where RBN heard you", html)
        self.assertIn("Your farthest RBN report was on 40m: VK6ANC in Oceania, approximately", html)
        self.assertEqual(html.count("<details"), 3)                                      # a folded regional breakdown for each band
        self.assertEqual(html.count("<details class=\"dv-more\" open>"), 1)               # and the band with the farthest report is the one open
        self.assertIn("Regional breakdown", html)
        self.assertIn("First to last logged contact", html)
        self.assertIn("No RBN reports from", html)
        self.assertNotIn("%", self.text(html))                                           # no percentage to read as a score

    def test_each_band_says_how_many_skimmers_reported_you_and_how_many_were_reporting(self):
        text = self.text(lh.reach_html(self.rows(), COLOURS, 3, 3))
        self.assertIn("2 skimmers reported you on 20m", " ".join(text.split()))
        self.assertIn("3 skimmers reported any station on 20m in the 2 half hours with your logged CW contacts, you included", " ".join(text.split()))
        self.assertIn("0 skimmers reported you on 15m", " ".join(text.split()))

    def test_unavailable_data_zero_reports_and_a_quiet_band_are_worded_differently(self):
        log = log_of(rec("A1AAA", "1405"), rec("B1AAA", "1210", band="40m"), rec("C1AAA", "1010", band="15m"))
        sp = spots(("DL1AAA", "20m", "2026-11-18 14:10"))
        gone = " ".join(self.text(lh.reach_html(lr.reach_by_band(log, sp, None, LOCS, HOME), COLOURS)).split())
        self.assertIn("No RBN data for 20m", gone)
        self.assertIn("could not be read", gone)
        nofile = " ".join(self.text(lh.reach_html(lr.reach_by_band(log, sp, listening(("20m", "2026-11-18 14:00", "DL1AAA")), LOCS, HOME, missing={"20261118"}), COLOURS)).split())
        self.assertIn("RBN has no file for 18 Nov yet", nofile)
        quiet = " ".join(self.text(lh.reach_html(lr.reach_by_band(log, sp, listening(("20m", "2026-11-18 14:00", "DL1AAA")), LOCS, HOME), COLOURS)).split())
        self.assertIn("No skimmer reported any station on 40m", quiet)
        self.assertIn("No skimmer reported any station on 15m", quiet)
        self.assertNotIn("0 skimmers reported you on 40m", quiet)                        # a band nobody was reporting on is not a band that has "zero reports of you"

    def test_a_busiest_band_heard_only_in_north_america_says_so(self):
        log = log_of(*[rec(f"A1A{i}", f"14{m:02d}") for i, m in enumerate(range(0, 50, 5))])
        sp = spots(("W1AW-2", "20m", "2026-11-18 14:10"), ("W6AAA", "20m", "2026-11-18 14:11"), ("W0BBB", "20m", "2026-11-18 14:12"), ("VE3CCC", "20m", "2026-11-18 14:13"))
        ls = listening(("20m", "2026-11-18 14:00", "W1AW"), ("20m", "2026-11-18 14:00", "W6AAA"), ("20m", "2026-11-18 14:00", "W0BBB"), ("20m", "2026-11-18 14:00", "VE3CCC"),
                       ("20m", "2026-11-18 14:00", "DL1AAA"))
        rows = lr.reach_by_band(log, sp, ls, LOCS, HOME)
        self.assertIn("Your 20m reports came from North America.", lh.reach_takeaway(rows))
        sp2 = spots(*[(c, "20m", t) for c, t in (("W1AW-2", "2026-11-18 14:10"), ("W6AAA", "2026-11-18 14:11"), ("DL1AAA", "2026-11-18 14:12"))])
        self.assertNotIn("North America", lh.reach_takeaway(lr.reach_by_band(log, sp2, ls, LOCS, HOME)))                 # a report from Europe: no such sentence

    def test_the_words_pass_the_wording_guard(self):
        html = lh.reach_html(self.rows(), COLOURS, 3, 3)
        self.assertEqual(lo.unsupported_claims(self.text(html)), [])
        self.assertEqual(lh.reach_html([], COLOURS), "")

    def test_a_band_worked_on_two_days_names_both_days(self):
        log = log_of(rec("A1AAA", "1405"), rec("A1BBB", "0910", date="20261119"))
        sp = spots(("DL1AAA", "20m", "2026-11-18 14:10"), ("DL1AAA", "20m", "2026-11-19 09:20"))
        ls = listening(("20m", "2026-11-18 14:00", "DL1AAA"), ("20m", "2026-11-19 09:00", "DL1AAA"))
        text = " ".join(self.text(lh.reach_html(lr.reach_by_band(log, sp, ls, LOCS, HOME), COLOURS)).split())
        self.assertIn("18 Nov 14:05 to 19 Nov 09:10 UTC", text)                          # not "14:05 to 09:10", which reads as ending before it began
        self.assertIn("18 Nov 14:10 to 19 Nov 09:20 UTC", text)
        one_day = " ".join(self.text(lh.reach_html(lr.reach_by_band(log_of(rec("A1AAA", "1405"), rec("A1BBB", "1440")), sp.iloc[:1], ls.iloc[:1], LOCS, HOME), COLOURS)).split())
        self.assertIn("14:05–14:40 UTC", one_day)

    def test_distances_are_written_as_approximate(self):
        self.assertEqual(lh._approx_km(16513.0), "16,500")
        self.assertEqual(lh._approx_km(2924.4), "2,900")
        self.assertEqual(lh._approx_km(412.0), "410")


if __name__ == "__main__":
    unittest.main()
