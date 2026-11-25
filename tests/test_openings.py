"""Checks of 'How you used the openings' (log_openings.py and its grid), with made-up data and no network."""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import log_check as lc  # noqa: E402
import log_check_html as lh  # noqa: E402
import log_foundations as lf  # noqa: E402
import log_openings as lo  # noqa: E402

HOME = (31.0, -102.0)
T = pd.Timestamp
DX = lc.DX_KM


def log_of(*records):
    return lc.parse_adif("<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(records) + "\n")


def rec(call, hhmm, band="20m", mode="CW", **fields):
    extra = "".join(f"<{k.upper()}:{len(str(v))}>{v} " for k, v in fields.items())
    return f"<CALL:{len(call)}>{call} <QSO_DATE:8>20261118 <TIME_ON:4>{hhmm} <BAND:{len(band)}>{band} <MODE:{len(mode)}>{mode} {extra}<EOR>"


class Session(unittest.TestCase):
    """A session on 20m. WSPR near you is heard by strong receivers in Germany, weak ones in Japan and a few nearby ones in the US. Your contacts:
    20:10 Germany, 20:40 a US station, nothing at 21:10, and 21:05 Japan."""

    def log(self, mode="CW", extra=""):
        return log_of(rec("DL1AAA", "2010", mode=mode, gridsquare="JN58", **({"my_pota_ref": "US-1234"} if extra == "pota" else {})),
                      rec("W1AAA", "2040", mode=mode, gridsquare="FN31"),
                      rec("JA1ZZZ", "2105", mode=mode, gridsquare="PM95"))

    def wspr(self, transmitters=3, japan_strong=False):
        rows = []
        for t in ("2026-11-18 20:10", "2026-11-18 20:40", "2026-11-18 21:10"):
            for i in range(6):
                rows.append({"time": T(t), "rx": f"DL1R{chr(65 + i)}", "rx_lat": 50.0 + i * 0.1, "rx_lon": 10.0, "snr": 10.0})
                rows.append({"time": T(t), "rx": f"JA1R{chr(65 + i)}", "rx_lat": 36.0 + i * 0.1, "rx_lon": 140.0, "snr": 10.0 if japan_strong else -30.0})
            for i in range(20):
                rows.append({"time": T(t), "rx": f"N{i % 10}A{chr(65 + i // 10)}{chr(65 + i % 10)}", "rx_lat": 35.0 + i * 0.1, "rx_lon": -90.0, "snr": -30.0})
        df = pd.DataFrame(rows)
        df["tx"] = [f"N5T{i % transmitters}" for i in range(len(df))]
        return df.assign(tx_lat=31.0, tx_lon=-102.0, band="20m", power=37.0)

    def grid(self, log=None, wspr=None):
        log = self.log() if log is None else log
        wspr = self.wspr() if wspr is None else wspr
        return lc.conditions_grid(log, lambda a, b: wspr[(wspr["time"] > a) & (wspr["time"] <= b)], HOME, 100.0, radius_km=500)

    def cells(self, dest="EU", view="continent", min_km=DX, spots=None, rbn_ok=True, log=None, wspr=None, metric="good", locs=None):
        log = self.log() if log is None else log
        grid = self.grid(log, wspr)
        places = lc.contact_places(log, HOME)
        return lo.opening_cells(grid, log, places, spots, locs or {}, HOME, view, dest, min_km, metric, rbn_ok), grid, places

    def at(self, cells, hhmm, band="20m"):
        return cells[(cells["band"] == band) & (cells["slot"] == T(f"2026-11-18 {hhmm}"))].iloc[0]


class PathEvidenceByDestination(Session):
    def test_the_shading_counts_only_receivers_in_the_destination(self):
        cells, _, _ = self.cells("EU")
        row = self.at(cells, "20:30")
        self.assertEqual((row["heard"], row["good"], row["state"]), (6, 6, lf.EVIDENCE))          # the six in Germany, not Japan and not the US

    def test_a_destination_that_decoded_but_was_too_weak_is_below_threshold(self):
        cells, _, _ = self.cells("AS")
        row = self.at(cells, "20:30")
        self.assertEqual((row["heard"], row["good"], row["state"]), (6, 0, lf.BELOW))

    def test_a_destination_with_no_receivers_has_no_reports(self):
        cells, _, _ = self.cells("AF")
        self.assertEqual(set(cells["state"]), {lf.NO_REPORTS})

    def test_the_observed_view_counts_who_decoded_not_who_looked_strong_enough(self):
        cells, _, _ = self.cells("AS", metric="heard")
        row = self.at(cells, "20:30")
        self.assertEqual((row["n"], row["state"]), (6, lf.EVIDENCE))

    def test_a_minimum_distance_leaves_out_the_nearer_stations(self):
        near, _, _ = self.cells(None, view="sector", min_km=0.0)
        far, _, _ = self.cells(None, view="sector", min_km=DX)
        self.assertGreater(self.at(near, "20:30")["heard"], self.at(far, "20:30")["heard"])        # the 20 US receivers are not DX
        self.assertEqual(self.at(far, "20:30")["heard"], 12)                                        # Germany and Japan

    def test_a_direction_is_the_compass_sector_seen_from_you(self):
        from geographiclib.geodesic import Geodesic
        sector = lf.sector_of(Geodesic.WGS84.Inverse(HOME[0], HOME[1], 50.0, 10.0)["azi1"] % 360)
        cells, _, _ = self.cells(sector, view="sector")
        self.assertEqual(self.at(cells, "20:30")["state"], lf.EVIDENCE)


class TheFiveConclusions(Session):
    def quiet_log(self):
        """Contacts at 20:10 and 21:05 only, so the 20:30 box has none."""
        return log_of(rec("DL1AAA", "2010", gridsquare="JN58"), rec("W1AAA", "2105", gridsquare="FN31"))

    def test_a_path_and_a_contact_with_it(self):
        cells, _, _ = self.cells("EU")
        row = self.at(cells, "20:00")
        self.assertEqual((row["key"], row["with_dest"], row["active"]), (lo.BOTH, 1, 1))
        self.assertIn("WSPR showed a path to Europe", row["text"])
        self.assertIn("logged 1 contact with stations in Europe", row["text"])

    def test_a_path_and_activity_without_a_contact_with_it(self):
        row = self.at(self.cells("EU")[0], "20:30")
        self.assertEqual((row["key"], row["with_dest"], row["active"]), (lo.PATH_OTHER, 0, 1))

    def test_a_contact_elsewhere_in_the_box_still_counts_as_activity(self):
        row = self.at(self.cells("EU")[0], "21:00")
        self.assertEqual((row["key"], row["active"], row["with_dest"]), (lo.PATH_OTHER, 1, 0))     # the 21:05 contact is with Japan, on 20m

    def test_a_path_and_no_contact_on_the_band(self):
        quiet = self.cells("EU", log=self.quiet_log())[0]
        row = self.at(quiet, "20:30")
        self.assertEqual((row["key"], row["active"]), (lo.PATH_IDLE, 0))                         # nothing logged in that box at all
        self.assertIn("You logged no contact on 20m in this box.", row["text"])

    def test_a_contact_with_no_path_in_the_wspr(self):
        row = self.at(self.cells("AS")[0], "21:00")
        self.assertEqual((row["key"], row["with_dest"]), (lo.CONTACT_NO_PATH, 1))
        self.assertIn("although WSPR showed no path (none of the WSPR stations there looked strong enough)", row["text"])

    def test_no_path_and_no_contact(self):
        row = self.at(self.cells("AS")[0], "20:00")
        self.assertEqual(row["key"], lo.NEITHER)
        self.assertIn("WSPR showed no path to Asia", row["text"])

    def test_all_five_conclusions_are_reachable(self):
        keys = (set(self.cells("EU")[0]["key"]) | set(self.cells("AS")[0]["key"])
                | set(self.cells("EU", log=self.quiet_log())[0]["key"]))
        self.assertEqual(keys, set(lo.CONCLUSIONS))

    def test_too_little_wspr_gives_no_conclusion_and_says_so(self):
        cells, _, _ = self.cells("EU", wspr=self.wspr(transmitters=1))
        row = self.at(cells, "20:30")
        self.assertEqual(row["state"], lf.SPARSE)
        self.assertIsNone(row["key"])
        self.assertTrue(row["text"].startswith("Too little WSPR to say whether there was a path to Europe."))
        self.assertNotIn("no path", row["text"])                                                  # thin data is never read as a closed band
        self.assertIn("You logged 1 contact with stations in Europe.", self.at(cells, "20:00")["text"])

    def test_no_destination_chosen_reads_as_stations_at_the_distance(self):
        row = self.at(self.cells(None, view="sector")[0], "20:00")
        self.assertIn("path to stations at this distance", row["text"])


class RbnOnlyWhereItApplies(Session):
    def spots(self, kind="CQ", hhmm="2012", spotter="DL1SKM"):
        return pd.DataFrame({"spotter": [spotter], "band": ["20m"], "snr": [12.0], "time": [T(f"2026-11-18 {hhmm}")], "mode": [kind], "tx_mode": ["CW"]})

    LOCS = {"DL1SKM": (50.0, 10.0), "JA1SKM": (36.0, 140.0)}

    def test_a_skimmer_in_the_destination_counts_when_you_were_calling_cq(self):
        cells, _, _ = self.cells("EU", spots=self.spots(), locs=self.LOCS)
        self.assertEqual((self.at(cells, "20:00")["rbn_state"], self.at(cells, "20:00")["rbn_n"]), (lf.EVIDENCE, 1))
        self.assertEqual(self.at(cells, "20:30")["rbn_state"], lf.NOT_APPLICABLE)                 # no CQ spot in that box, so it is not known that you were calling

    def test_skimmers_are_counted_as_the_stations_they_are_never_capped_by_the_contacts(self):
        spots = pd.DataFrame({"spotter": ["DL1SKM", "DL1SKM", "DL2SKM", "DL3SKM", "JA1SKM"], "band": ["20m"] * 5, "snr": [12.0] * 5,
                              "time": [T("2026-11-18 20:05"), T("2026-11-18 20:07"), T("2026-11-18 20:08"), T("2026-11-18 20:12"), T("2026-11-18 20:13")],
                              "mode": ["CQ"] * 5, "tx_mode": ["CW"] * 5})
        locs = {"DL1SKM": (50.0, 10.0), "DL2SKM": (51.0, 9.0), "DL3SKM": (48.0, 11.0), "JA1SKM": (36.0, 140.0)}
        cells, _, _ = self.cells("EU", spots=spots, locs=locs)
        box = self.at(cells, "20:00")
        self.assertEqual(box["active"], 1)                                                   # one contact in the box ...
        self.assertEqual(box["rbn_n"], 3)                                                    # ... and still three different skimmers in Europe, the repeat counted once
        cells_asia, _, _ = self.cells("AS", spots=spots, locs=locs)
        self.assertEqual(self.at(cells_asia, "20:00")["rbn_n"], 1)                           # the one in Japan is counted only for Asia

    def test_a_skimmer_elsewhere_is_not_counted_for_this_destination(self):
        cells, _, _ = self.cells("AS", spots=self.spots(), locs=self.LOCS)
        self.assertEqual(self.at(cells, "20:00")["rbn_n"], 0)

    def test_a_box_with_a_cq_spot_but_no_skimmer_in_the_destination_says_none_spotted_you(self):
        cells, _, _ = self.cells("AS", spots=self.spots(), locs=self.LOCS)
        self.assertEqual(self.at(cells, "20:00")["rbn_state"], lf.NO_REPORTS)

    def test_a_spot_that_is_not_a_call_does_not_make_rbn_apply(self):
        cells, _, _ = self.cells("EU", spots=self.spots(kind="BEACON"), locs=self.LOCS)
        self.assertEqual(self.at(cells, "20:00")["rbn_state"], lf.NOT_APPLICABLE)

    def test_an_activation_is_run_by_calling_so_rbn_applies_in_every_box(self):
        cells, _, _ = self.cells("EU", spots=self.spots(), locs=self.LOCS, log=self.log(extra="pota"))
        self.assertEqual(self.at(cells, "20:30")["rbn_state"], lf.NO_REPORTS)                     # applicable, and no skimmer there spotted you

    def test_ssb_is_never_an_rbn_session(self):
        cells, _, _ = self.cells("EU", spots=self.spots(), locs=self.LOCS, log=self.log(mode="SSB", extra="pota"))
        self.assertEqual(set(cells["rbn_state"]), {lf.NOT_APPLICABLE})
        self.assertIn("RBN carries CW and RTTY, not SSB", cells["rbn_why"].iloc[0])

    def test_missing_rbn_spots_are_unavailable_not_zero(self):
        cells, _, _ = self.cells("EU", spots=None, rbn_ok=False, log=self.log(extra="pota"))
        self.assertEqual(set(cells["rbn_state"]), {lf.UNAVAILABLE})
        self.assertEqual(lo.rbn_sentence(lf.UNAVAILABLE, 0, lo.where_forms("continent", "EU")), "RBN spots are not available.")

    def test_the_rbn_sentences_say_little_about_an_absence(self):
        where = lo.where_forms("continent", "EU")
        self.assertEqual(lo.rbn_sentence(lf.EVIDENCE, 2, where), "2 RBN skimmers in Europe spotted you.")
        self.assertIn("this says little", lo.rbn_sentence(lf.NO_REPORTS, 0, where))
        self.assertTrue(lo.rbn_sentence(lf.NOT_APPLICABLE, 0, where).startswith("RBN not applicable or unknown."))


class TheSummary(Session):
    def test_the_summary_is_made_from_the_counts_and_says_active_not_caught(self):
        cells, _, _ = self.cells("EU")
        lines = lo.openings_summary(cells)
        self.assertEqual(len(lines), 2)                                                            # 20m, and RBN
        self.assertTrue(lines[0].startswith("20m: of 3 boxes, you were active in 3 and WSPR showed a path to Europe in 3."))
        self.assertIn("You logged a contact with stations in Europe in 1 of the 3 with a path.", lines[0])
        self.assertTrue(lines[1].startswith("RBN not applicable or unknown for this session."))

    def test_a_contact_without_a_path_is_reported_without_a_judgement(self):
        lines = lo.openings_summary(self.cells("AS")[0])
        self.assertIn("In 1 other box you logged a contact with stations in Asia although WSPR showed no path then.", lines[0])

    def test_thin_boxes_are_said_to_say_nothing_either_way(self):
        lines = lo.openings_summary(self.cells("EU", wspr=self.wspr(transmitters=1))[0])
        self.assertIn("3 boxes had too little WSPR behind it to say either way.", lines[0])

    def test_a_band_you_did_not_work_is_mentioned_only_with_a_path(self):
        log = log_of(rec("DL1AAA", "2010", band="15m", gridsquare="JN58"))
        wspr = self.wspr()
        cells = lo.opening_cells(lc.conditions_grid(log, lambda a, b: wspr[(wspr["time"] > a) & (wspr["time"] <= b)], HOME, 100.0),
                                 log, lc.contact_places(log, HOME), None, {}, HOME, "continent", "EU", DX, "good", True)
        lines = lo.openings_summary(cells)
        self.assertTrue(any(line.startswith("20m: you logged no contact on it.") for line in lines))

    def test_the_guard_catches_claims_the_data_cannot_support(self):
        for text in ("You caught the opening.", "You missed the opening on 20m.", "You should have been on 15m.", "A utilization score of 80%.",
                     "Skimmers were listening then.", "You tried 40m.", "An opportunity was lost."):
            self.assertTrue(lo.unsupported_claims(text), text)
        self.assertEqual(lo.unsupported_claims("You were active in 3 of 5 boxes. WSPR showed a path to Europe in 2."), [])

    def test_every_sentence_the_page_can_write_passes_the_guard(self):
        for dest, view in ((None, "sector"), ("EU", "continent"), ("AS", "continent"), ("NE", "sector")):
            for wspr in (self.wspr(), self.wspr(transmitters=1)):
                cells, _, _ = self.cells(dest, view=view, wspr=wspr)
                for line in lo.openings_summary(cells) + list(cells["text"]):
                    self.assertEqual(lo.unsupported_claims(line), [], line)
                    self.assertNotIn("%", line)                                                    # no score, no percentage

    def test_there_is_no_utilisation_score_anywhere_in_the_cells(self):
        cells, _, _ = self.cells("EU")
        for column in cells.columns:
            self.assertNotIn("score", column.lower())
            self.assertNotIn("util", column.lower())


class TheGridDrawn(Session):
    def test_each_state_has_its_own_look_and_the_marks_are_drawn(self):
        cells, grid, _ = self.cells("EU", spots=RbnOnlyWhereItApplies().spots(), locs=RbnOnlyWhereItApplies.LOCS)
        html = lh.openings_html(cells, grid, None, "estimate")
        self.assertIn("How you used the openings", html)
        self.assertIn('class="cell s3"', html)                                                      # six stations in Europe
        self.assertIn("<em><i></i>1</em>", html)                                                    # active on the band
        self.assertIn("&#9733;", html)                                                              # a contact with the destination
        self.assertIn("<u></u>", html)                                                              # a skimmer there spotted you
        thin, grid2, _ = self.cells("EU", wspr=self.wspr(transmitters=1))
        sparse = lh.openings_html(thin, grid2, None, "estimate")
        self.assertIn('class="cell sparse"', sparse)
        self.assertIn('<span class="p">?</span>', sparse)
        weak, grid3, _ = self.cells("AS")
        self.assertIn('class="cell few"', lh.openings_html(weak, grid3, None, "estimate"))         # decoded, none strong enough
        none, grid4, _ = self.cells("AF")
        self.assertIn('class="cell none"', lh.openings_html(none, grid4, None, "estimate"))        # no reports from there

    def test_the_words_say_what_it_is_and_what_it_is_not(self):
        cells, grid, _ = self.cells("EU")
        html = lh.openings_explain_html(cells, grid, "estimate")
        self.assertIn("evidence about the path, not a score", html)
        self.assertIn("does not say what you should have done", html)
        self.assertIn("in Europe and at least 3,000 miles", html)
        self.assertIn("RBN carries CW and RTTY only", html)
        self.assertIn("The evidence:", html)                                                       # the WSPR reports and transmitters it rests on

    def test_the_card_leads_with_the_answer_and_keeps_the_explanations_out_of_the_way(self):
        cells, grid, _ = self.cells("EU")
        html = lh.openings_html(cells, grid, None, "estimate")
        self.assertLess(html.index("Looking at Europe"), html.index('class="lc-cg'))               # the headline comes before the grid
        for explanation in ("evidence about the path", "How to read it", "The evidence:", "RBN carries CW and RTTY only"):
            self.assertNotIn(explanation, html)                                                    # they are in the folded piece
        self.assertIn("you were active", html)                                                     # but the key to the marks stays beside the grid

    def test_the_observed_view_is_explained_without_a_strength_estimate(self):
        cells, grid, _ = self.cells("EU", metric="heard")
        html = lh.openings_explain_html(cells, grid, "observed")
        self.assertIn("decoded WSPR transmitters near you, in the hour", html)
        self.assertNotIn("looked strong enough to hear", html)

    def test_a_box_tooltip_carries_its_statement(self):
        cells, grid, _ = self.cells("EU")
        self.assertIn("WSPR showed a path to Europe. You were active on 20m and logged 1 contact", lh.openings_html(cells, grid, None, "estimate"))


class TheHeadlineAndTheTable(Session):
    def test_the_headline_counts_the_boxes_of_the_bands_you_worked(self):
        cells, _, _ = self.cells("EU")
        self.assertEqual(lo.openings_headline(cells),
                         "Looking at Europe: WSPR showed a path in 3 of 3 boxes on the bands you worked. You were active in 3 of the 3 and logged a contact with stations in Europe in 1.")

    def test_the_headline_says_none_not_zero_and_follows_the_destination(self):
        text = lo.openings_headline(self.cells("AS")[0])
        self.assertEqual(text, "Looking at Asia: WSPR showed a path in none of 3 boxes on the bands you worked. You were active in 3 of the 3 and "
                               "logged a contact with stations in Asia in 1.")
        self.assertTrue(lo.openings_headline(self.cells(None, view="sector")[0]).startswith("Looking at stations at this distance:"))

    def test_the_headline_is_clean_and_empty_without_cells(self):
        for dest, view in ((None, "sector"), ("EU", "continent"), ("AS", "continent"), ("NE", "sector")):
            self.assertEqual(lo.unsupported_claims(lo.openings_headline(self.cells(dest, view=view)[0])), [])
        self.assertEqual(lo.openings_headline(self.cells("EU")[0].iloc[0:0]), "")

    def test_the_table_has_a_row_for_each_band_with_the_counts(self):
        table = lo.openings_table(self.cells("EU")[0])
        self.assertEqual(list(table.columns), lo.OPENINGS_COLUMNS)
        self.assertEqual(table.iloc[0].tolist(), ["20m", 3, 3, 3, 1, 1, 0])
        thin = lo.openings_table(self.cells("EU", wspr=self.wspr(transmitters=1))[0])
        self.assertEqual(thin.iloc[0]["Too little WSPR"], 3)
        self.assertEqual(thin.iloc[0]["WSPR path"], 0)                                              # thin boxes are not counted as a path, nor as none

    def test_a_band_you_did_not_work_has_a_row_only_with_a_path_and_comes_last(self):
        log = log_of(rec("DL1AAA", "2010", band="15m", gridsquare="JN58"))
        wspr = self.wspr()
        cells = lo.opening_cells(lc.conditions_grid(log, lambda a, b: wspr[(wspr["time"] > a) & (wspr["time"] <= b)], HOME, 100.0),
                                 log, lc.contact_places(log, HOME), None, {}, HOME, "continent", "EU", DX, "good", True)
        table = lo.openings_table(cells)
        self.assertEqual(table["Band"].tolist(), ["15m", "20m (not worked)"])

    def test_the_rbn_line_stands_apart_from_the_bands(self):
        cells, _, _ = self.cells("EU")
        self.assertTrue(lo.rbn_line(cells).startswith("RBN not applicable or unknown for this session."))
        self.assertEqual(lo.rbn_line(cells.iloc[0:0]), "")
        self.assertEqual(lo.openings_summary(cells)[-1], lo.rbn_line(cells))                       # the sentences still end with it


class TheBandTimeline(Session):
    LOCS = {"DL1SKM": (50.0, 10.0), "JA1SKM": (36.0, 140.0)}

    def timeline(self, metric="good", only=None, log=None, wspr=None, spots=None, rbn_ok=True, min_km=DX):
        log = self.log() if log is None else log
        grid = self.grid(log, wspr)
        return lo.band_timeline(grid, log, lc.contact_places(log, HOME), spots, self.LOCS, HOME, min_km, metric, rbn_ok, only), grid

    def card(self, tl, band="20m", panel=0):
        return next(c for c in tl["panels"][panel]["cards"] if c["band"] == band)

    def test_a_card_for_each_band_you_worked_in_a_fixed_order_highest_first(self):
        log = log_of(rec("DL1AAA", "2010", band="15m", gridsquare="JN58"), rec("DL1BBB", "2015", band="20m", gridsquare="JN58"),
                     rec("DL1CCC", "2040", band="10m", gridsquare="JN58"))
        tl, _ = self.timeline(log=log)
        self.assertEqual([c["band"] for c in tl["panels"][0]["cards"]], ["10m", "15m", "20m"])

    def test_the_lanes_are_the_distant_continents_with_a_receiver_by_the_views_metric(self):
        good, _ = self.timeline("good")
        self.assertEqual(set(self.card(good)["lanes"]), {"EU"})                                    # Japan's receivers decoded but were too weak
        self.assertEqual([x["n"] for x in self.card(good)["lanes"]["EU"]], [6, 6, 6])
        heard, _ = self.timeline("heard")
        self.assertEqual(set(self.card(heard)["lanes"]), {"EU", "AS"})
        self.assertEqual(lo.LANES, ("EU", "AF", "AS", "OC", "SA"))

    def test_one_receiver_is_pale_and_two_or_more_are_solid_and_neither_is_called_weak(self):
        wspr = self.wspr()
        one = wspr[~wspr["rx"].str.startswith("DL1R") | (wspr["rx"] == "DL1RA")]
        tl, grid = self.timeline(wspr=one)
        html = lh.band_cards_html(tl)
        self.assertEqual([x["n"] for x in self.card(tl)["lanes"]["EU"]], [1, 1, 1])
        self.assertIn('class="bc-bar p"', html)                                                     # pale: one receiving station
        many, _ = self.timeline()
        self.assertIn('class="bc-bar"', lh.band_cards_html(many))                                  # solid: two or more
        text = html.replace("limited evidence, not a weak signal", "")
        self.assertNotIn("weak", text.lower())                                                      # nowhere else does a thin count become a weak signal
        self.assertIn("one receiving station, which is limited evidence, not a weak signal", html)

    def test_the_legend_says_what_the_bars_are_in_each_view(self):
        observed = lh.band_cards_html(self.timeline("heard")[0])
        estimate = lh.band_cards_html(self.timeline("good")[0])
        self.assertIn("Nothing is assumed about your station", observed)
        self.assertNotIn("looked strong enough", observed)
        self.assertIn("restated to 100 W in CW, looked strong enough to hear you", estimate)

    def test_logged_activity_is_split_at_pauses_and_joined_otherwise(self):
        times = ["2026-11-18 20:00", "2026-11-18 20:10", "2026-11-18 20:24", "2026-11-18 20:50"]
        spans = lo.activity_spans(times)
        self.assertEqual([(a.strftime("%H:%M"), b.strftime("%H:%M"), n) for a, b, n in spans], [("20:00", "20:24", 3), ("20:50", "20:50", 1)])
        self.assertEqual(len(lo.activity_spans(times, gap_min=30)), 1)
        self.assertEqual(lo.activity_spans([]), [])

    def test_the_shading_is_called_logged_activity_and_not_listening(self):
        html = lh.band_cards_html(self.timeline()[0])
        self.assertIn("Logged activity on 20m", html)
        self.assertIn("logged activity on the band", html)
        self.assertIn("not when you were listening or calling", html)
        self.assertNotIn("You were on", html)

    def test_each_card_has_its_own_utc_axis_and_no_callsign_labels_on_the_chart(self):
        html = lh.band_cards_html(self.timeline(log=log_of(rec("DL1AAA", "2010", band="15m", gridsquare="JN58"), rec("DL1BBB", "2015", band="20m", gridsquare="JN58"),
                                                           rec("DL1CCC", "2040", band="20m", gridsquare="JN58")))[0])
        self.assertEqual(html.count(">UTC</div><div class=\"bc-ax\">"), 2)                       # one axis under each of the two cards
        self.assertEqual(html.count('title="DL1AAA, 20:10 UTC, Europe"'), 1)                        # the call is in the dot's tooltip...
        self.assertNotIn('<span class="n"', html)                                                   # ...and nothing is written over the chart
        self.assertIn("Contacts there: DL1AAA (Europe).", html)                                     # ...the calls are listed under the card

    def test_the_time_resolution_is_stated(self):
        self.assertIn("each judged on the hour of WSPR up to its end", lh.band_cards_html(self.timeline()[0]))

    def test_a_bin_with_too_little_wspr_has_no_bar_and_is_marked(self):
        tl, _ = self.timeline(wspr=self.wspr(transmitters=1))
        card = self.card(tl)
        self.assertEqual(len(card["thin"]), 3)
        self.assertEqual(card["lanes"], {})                                                         # nothing is drawn as a path, nor as no path
        html = lh.band_cards_html(tl)
        self.assertIn("Too little WSPR</div>", html)
        self.assertIn('class="bc-thin"', html)

    def test_a_chosen_continent_shows_its_lane_even_when_empty(self):
        tl, _ = self.timeline(only="AF")
        self.assertEqual(list(self.card(tl)["lanes"]), ["AF"])
        self.assertIn("no reports from there", lh.band_cards_html(tl))
        self.assertEqual(list(self.card(self.timeline(only="EU")[0])["lanes"]), ["EU"])

    def test_rbn_is_a_ring_in_the_continents_lane_and_only_where_it_applies(self):
        spots = RbnOnlyWhereItApplies().spots()
        tl, _ = self.timeline(spots=spots)
        lane = self.card(tl)["lanes"]["EU"]
        self.assertEqual(lane[0]["rbn"], ["DL1SKM"])
        self.assertEqual(lane[1]["rbn"], [])
        html = lh.band_cards_html(tl)
        self.assertEqual(html.count('class="bc-ring"'), 1)
        self.assertIn("RBN: DL1SKM in Europe spotted you", html)
        none = lh.band_cards_html(self.timeline(spots=RbnOnlyWhereItApplies().spots(kind="BEACON"))[0])
        self.assertNotIn('class="bc-ring"', none)                                                   # not a call, so RBN does not apply
        ssb = self.timeline(spots=spots, log=self.log(mode="SSB"))[0]
        self.assertNotIn('class="bc-ring"', lh.band_cards_html(ssb))
        self.assertIn("RBN not applicable or unknown", ssb["rbn_line"])

    def test_a_skimmer_in_a_continent_with_no_wspr_still_gets_its_lane(self):
        spots = pd.DataFrame({"spotter": ["JA1SKM"], "band": ["20m"], "snr": [9.0], "time": [T("2026-11-18 20:13")], "mode": ["CQ"], "tx_mode": ["CW"]})
        tl, _ = self.timeline("good", spots=spots)                                                  # Japan's WSPR receivers were too weak, but a skimmer there heard you
        self.assertEqual(set(self.card(tl)["lanes"]), {"EU", "AS"})
        self.assertEqual([x["n"] for x in self.card(tl)["lanes"]["AS"]], [0, 0, 0])
        self.assertEqual(self.card(tl)["lanes"]["AS"][0]["rbn"], ["JA1SKM"])

    def test_a_skimmer_in_a_continent_you_worked_is_added_to_the_finding(self):
        spots = pd.DataFrame({"spotter": ["JA1SKM"], "band": ["20m"], "snr": [9.0], "time": [T("2026-11-18 21:06")], "mode": ["CQ"], "tx_mode": ["CW"]})
        tl, _ = self.timeline("good", spots=spots, log=log_of(rec("JA1ZZZ", "2105", gridsquare="PM95")))
        self.assertEqual(self.card(tl)["finding"], "Worked Asia. No corresponding nearby WSPR reports in the selected window. RBN skimmers in Asia also spotted you. "
                         "Europe paths appeared during your logged activity on 20m; you logged no contact there.")                        # a path to a continent you did not work is still said
        none, _ = self.timeline("good", log=log_of(rec("JA1ZZZ", "2105", gridsquare="PM95")))
        self.assertNotIn("RBN", self.card(none)["finding"])                                         # no spot, no sentence

    def test_missing_rbn_spots_draw_no_ring_and_say_so(self):
        tl, _ = self.timeline(spots=None, rbn_ok=False, log=self.log(extra="pota"))
        self.assertNotIn('class="bc-ring"', lh.band_cards_html(tl))
        self.assertIn("RBN spots were not available", tl["rbn_line"])

    def test_the_finding_for_a_contact_with_no_path_is_short_and_plain(self):
        tl, _ = self.timeline("good", log=log_of(rec("JA1ZZZ", "2105", gridsquare="PM95")))
        self.assertEqual(self.card(tl)["finding"], "Worked Asia. No corresponding nearby WSPR reports in the selected window. "
                                                   "Europe paths appeared during your logged activity on 20m; you logged no contact there.")
        self.assertEqual(self.card(tl)["worked"], [("JA1ZZZ", "AS")])

    def test_the_finding_for_a_path_while_you_were_on_another_band_says_what_the_log_shows(self):
        log = log_of(rec("W1AAA", "2010", band="20m", gridsquare="FN31"), rec("W1BBB", "2015", band="15m", gridsquare="FN31"),
                     rec("W1CCC", "2105", band="20m", gridsquare="FN31"))
        wspr = pd.concat([self.wspr(), self.wspr().assign(band="15m")], ignore_index=True)
        tl, _ = self.timeline(log=log, wspr=wspr)
        self.assertEqual(self.card(tl, "15m")["finding"], "Europe paths appeared 20:30–21:30, outside your logged activity on 15m. Your log shows 20m activity then. "
                                                          "Your log has 1 15m contact, at 20:15 UTC.")

    def test_a_path_during_your_activity_with_no_contact_there_is_said_plainly(self):
        log = log_of(rec("W1AAA", "2010", gridsquare="FN31"), rec("W1BBB", "2040", gridsquare="FN31"), rec("W1CCC", "2105", gridsquare="FN31"))
        tl, _ = self.timeline(log=log)
        self.assertEqual(self.card(tl)["finding"], "Europe paths appeared during your logged activity on 20m; you logged no contact there.")

    def test_no_path_at_all_says_so(self):
        wspr = self.wspr()
        none = wspr[~wspr["rx"].str.startswith(("DL", "JA"))]
        tl, _ = self.timeline(wspr=none, log=log_of(rec("W1AAA", "2010", gridsquare="FN31"), rec("W1BBB", "2105", gridsquare="FN31")))
        self.assertEqual(self.card(tl)["finding"], "No distant-continent paths in the nearby WSPR.")

    def japan(self, contact, path_times=("2026-11-18 20:10", "2026-11-18 20:40", "2026-11-18 21:10"), others=("2010",)):
        """Japan is strong in the WSPR near you only at `path_times` (the US stations near you are heard at all three times, so there is coverage);
        you work a US station at each of `others` and Japan at `contact`."""
        wspr = self.wspr(japan_strong=True)
        wspr = wspr[~wspr["rx"].str.startswith("JA") | wspr["time"].isin([T(t) for t in path_times])]
        log = log_of(*[rec(f"W1A{i}", hhmm, gridsquare="FN31") for i, hhmm in enumerate(others)], rec("JA1ZZZ", contact, gridsquare="PM95"))
        return self.timeline("good", wspr=wspr, log=log)[0]

    def test_a_contact_hours_after_the_path_is_not_described_as_supported_by_it(self):
        text = self.card(self.japan("2205", path_times=("2026-11-18 20:10",), others=("2010", "2150")))["finding"]
        self.assertIn("Worked Asia at 22:05; nearby WSPR showed a path there earlier (", text)
        self.assertNotIn("at the time", text)
        self.assertNotIn("also showed a path", text)

    def test_a_contact_in_the_hour_of_the_path_is_said_to_be_at_the_time(self):
        text = self.card(self.japan("2105"))["finding"]
        self.assertTrue(text.startswith("Worked Asia; nearby WSPR showed a path there at the time."), text)

    def test_a_path_that_came_after_the_contact_is_said_to_be_later(self):
        text = self.card(self.japan("2005", path_times=("2026-11-18 21:10",), others=("2150", "2210")))["finding"]
        self.assertIn("Worked Asia at 20:05; nearby WSPR showed a path there later (", text)

    def test_a_contact_nearer_than_the_distance_rule_is_not_a_distant_contact_in_the_cards(self):
        log = log_of(rec("HK3AAA", "2010", gridsquare="FJ24"), rec("W1AAA", "2040", gridsquare="FN31"))             # Bogota is in South America but about 3,900 km away
        km = lc.contact_places(log, HOME)["c_km"].iloc[0]
        self.assertLess(km, DX)
        near, _ = self.timeline(log=log)
        self.assertEqual(self.card(near)["worked"], [])                                                          # not worked, by the rule the WSPR and the skimmers follow
        self.assertEqual([c["cont"] for c in self.card(near)["contacts"]], ["", ""])
        anywhere, _ = self.timeline(log=log, min_km=0.0)
        self.assertEqual([cont for _, cont in self.card(anywhere)["worked"]], ["SA"])

    def test_each_destination_keeps_its_own_times(self):
        text = lo.band_finding("20m", {"EU": [T("2026-11-18 20:00")], "AF": [T("2026-11-18 21:30")]}, {T("2026-11-18 23:00")}, {}, [], 5, T("2026-11-18 23:00"), pd.Timedelta(minutes=30))
        self.assertIn("Europe paths appeared 20:00–20:30", text)
        self.assertIn("Africa paths appeared 21:30–22:00", text)
        self.assertNotIn("Europe and Africa paths appeared", text)                                           # not one pooled set of times for both

    def test_a_card_with_no_distant_path_says_so_once_under_the_chart_not_inside_it(self):
        wspr = self.wspr()
        none = wspr[~wspr["rx"].str.startswith(("DL", "JA"))]
        tl, _ = self.timeline(wspr=none, log=log_of(rec("W1AAA", "2010", gridsquare="FN31"), rec("W1BBB", "2105", gridsquare="FN31")))
        html = lh.band_cards_html(tl)
        self.assertEqual(html.count("No distant-continent paths in the nearby WSPR"), 1)          # the sentence under the chart
        self.assertNotIn('class="bc-none"', html)                                                   # not a second note inside it, spilling out of the shading

    def test_the_rbn_comparison_card_is_not_also_called_band_by_band(self):
        bands = pd.DataFrame([{"band": "20m", "contacts": 5, "other": 0, "skimmers": 4, "report": 5.0, "page": 0.5, "spotted": 0.5, "listening": 3,
                               "stronger_db": 2.0, "matches": 9, "thin": False, "note": "", "tone": "", "no_picture": False}])
        html = lh.band_table_html(bands)
        self.assertIn("<h4>What RBN skimmers heard on each band</h4>", html)
        self.assertNotIn("<h4>Band by band</h4>", html)                                             # that name belongs to the openings view

    def test_every_finding_passes_the_guard_and_none_scores_or_judges(self):
        for metric in ("good", "heard"):
            for only in (None, "EU", "AS"):
                tl, _ = self.timeline(metric, only)
                for card in tl["panels"][0]["cards"]:
                    self.assertEqual(lo.unsupported_claims(card["finding"]), [], card["finding"])
                    self.assertNotIn("%", card["finding"])

    def test_bands_you_did_not_work_are_named_underneath(self):
        wspr = self.wspr().assign(band="15m")
        both = pd.concat([self.wspr(), wspr], ignore_index=True)
        tl, _ = self.timeline(wspr=both)
        self.assertEqual(tl["idle"], [])                                                       # a band with a path to show gets a card of its own, not a footnote
        card = self.card(tl, "15m")
        self.assertFalse(card["worked_band"])
        self.assertEqual(card["contacts"], [])
        self.assertIn("you logged no contact on 15m.", card["finding"])
        self.assertNotIn("Your log has 0", card["finding"])
        self.assertEqual([c["band"] for c in tl["panels"][0]["cards"]], ["20m", "15m"])        # the bands you worked first
        html = lh.band_cards_html(tl)
        self.assertIn("<small>not worked</small>", html)

    def test_a_band_you_did_not_work_and_with_no_path_stays_in_the_footnote(self):
        weak = self.wspr().assign(band="15m", snr=-30.0)
        tl, _ = self.timeline(wspr=pd.concat([self.wspr(), weak], ignore_index=True))
        self.assertEqual([c["band"] for c in tl["panels"][0]["cards"]], ["20m"])
        self.assertEqual(tl["idle"], [("15m", "none")])
        self.assertIn("15m: you logged no contact; nearby WSPR showed no path to a distant continent.", lh.band_cards_html(tl))

    def test_your_own_continent_is_never_a_destination_but_the_others_are(self):
        self.assertEqual(lo.lane_set("dx", "NA")[0], ("EU", "AF", "AS", "OC", "SA"))
        eu = lo.lane_set("dx", "EU")[0]
        self.assertNotIn("EU", eu)
        self.assertIn("NA", eu)                                                                # a station in Europe has North America to look at
        self.assertEqual(lo.lane_set("regional")[0], lf.SECTORS)

    def test_the_regional_picture_has_a_lane_for_each_direction_and_says_so(self):
        log = log_of(rec("W1AAA", "2010", gridsquare="FN31"), rec("W5BBB", "2040", gridsquare="EM10"))     # one far to the northeast of Texas, one near
        wspr = self.wspr()
        east = wspr[wspr["rx"].str.startswith("N")]
        tl = lo.band_timeline(self.grid(log, east), log, lc.contact_places(log, HOME), None, {}, HOME, DX, "heard", True, None, "regional")
        self.assertEqual(tl["reach"], "regional")
        self.assertEqual(tl["lane_order"], list(lf.SECTORS))
        self.assertEqual(tl["lane_word"], "direction")
        card = tl["panels"][0]["cards"][0]
        self.assertTrue(set(card["lanes"]) <= set(lf.SECTORS))
        self.assertTrue(card["worked"] and card["worked"][0][1] in lf.SECTORS)                 # a contact is placed in a direction, not a continent
        self.assertNotIn("distant continent", tl["headline"])
        self.assertIn("toward the northeast", tl["headline"])
        html = lh.band_cards_html(tl)
        self.assertIn("in that direction", html)

    def test_a_regional_lane_that_never_changes_is_named_in_a_line_not_drawn(self):
        log = log_of(rec("W7AAA", "2010", gridsquare="CN87"), rec("W7BBB", "2040", gridsquare="CN87"), rec("W7CCC", "2105", gridsquare="CN87"))      # all to the northwest
        east = self.wspr()
        east = east[east["rx"].str.startswith("N")]
        tl = lo.band_timeline(self.grid(log, east), log, lc.contact_places(log, HOME), None, {}, HOME, DX, "heard", True, None, "regional")
        card = tl["panels"][0]["cards"][0]
        self.assertTrue(card["steady"], "the receivers are heard in every bin, so some lane stays open throughout")
        self.assertFalse(set(card["steady"]) & set(card["lanes"]))                               # not drawn
        self.assertIn("Paths stayed open the whole time toward", card["finding"])
        in_lane = {c["cont"] for c in card["contacts"] if c["cont"]}
        self.assertFalse(in_lane & set(card["steady"]))                                          # a lane you are in is always drawn, with your contacts in it
        self.assertEqual(lo.unsupported_claims(card["finding"]), [])
        html = lh.band_cards_html(tl)
        self.assertIn('class="bc-dot"', html)                                                    # each contact is a dot in its own lane
        dx = lo.band_timeline(self.grid(log, east), log, lc.contact_places(log, HOME), None, {}, HOME, DX, "heard", True, None, "dx")
        self.assertEqual(dx["panels"][0]["cards"][0]["steady"], [])                              # only the regional picture collapses lanes

    def test_a_regional_contact_is_a_contact_between_500_km_and_the_dx_distance(self):
        log = log_of(rec("W5NEAR", "2010", gridsquare="EM00"), rec("W1FAR", "2020", gridsquare="FN31"), rec("DL1AAA", "2030", gridsquare="JN58"))
        places = lc.contact_places(log, HOME)
        tl = lo.band_timeline(self.grid(log, self.wspr()), log, places, None, {}, HOME, DX, "heard", True, None, "regional")
        dots = [c for c in tl["panels"][0]["cards"][0]["contacts"] if c["cont"]]
        self.assertEqual([c["call"] for c in dots], ["W1FAR"])                                 # not the one next door, not Germany (that is DX)

    def test_a_log_over_several_days_has_a_panel_and_a_date_for_each(self):
        log = log_of(rec("DL1AAA", "2010", gridsquare="JN58"), rec("DL1BBB", "2010", gridsquare="JN58").replace("20261118", "20261120"))
        wspr = self.wspr()
        late = wspr.assign(time=wspr["time"] + pd.Timedelta(days=2))
        tl, _ = self.timeline(log=log, wspr=pd.concat([wspr, late], ignore_index=True))
        self.assertEqual(len(tl["panels"]), 2)
        self.assertIn("Wed 18 Nov", lh.band_cards_html(tl))
        self.assertIn("Fri 20 Nov", lh.band_cards_html(tl))

    def test_the_explanation_carries_the_evidence_and_the_limits(self):
        tl, grid = self.timeline()
        html = lh.band_cards_explain_html(tl, grid)
        self.assertIn("evidence about paths near you, not a score", html)
        self.assertIn("not the time you spent listening", html)
        self.assertIn("The evidence:", html)


class OneBoxInFull(Session):
    LOCS = RbnOnlyWhereItApplies.LOCS

    def evidence(self, hhmm="20:00", dest="EU", view="continent", spots=None):
        log = self.log()
        wspr = self.wspr()
        grid = self.grid(log, wspr)
        places = lc.contact_places(log, HOME)
        return lo.cell_evidence(grid, log, places, spots, self.LOCS, lambda a, b: wspr[(wspr["time"] > a) & (wspr["time"] <= b)], HOME, "20m",
                                T(f"2026-11-18 {hhmm}"), view, dest, DX, spots is not None)

    def test_it_gives_the_exact_window_and_what_stands_behind_it(self):
        ev = self.evidence()
        self.assertEqual(ev["window"], (T("2026-11-18 19:30"), T("2026-11-18 20:30")))
        self.assertEqual(ev["bin"], (T("2026-11-18 20:00"), T("2026-11-18 20:30")))
        self.assertEqual(ev["coverage"]["transmitters"], 3)
        self.assertEqual(ev["coverage"]["receivers"], 32)

    def test_it_lists_the_transmitters_near_you_with_their_distances(self):
        tx = self.evidence()["transmitters"]
        self.assertEqual(set(tx["Transmitter"]), {"N5T0", "N5T1", "N5T2"})
        self.assertTrue((tx["Km from you"] < 1).all())                                              # they are all at home in this fake
        self.assertEqual(list(tx.columns), ["Transmitter", "Km from you", "Reports", "First report", "Last report"])

    def test_it_lists_only_the_receivers_in_the_destination_with_their_times(self):
        rx = self.evidence()["receivers"]
        self.assertEqual(len(rx), 6)
        self.assertTrue(all(r.startswith("DL1R") for r in rx["Receiver"]))
        self.assertEqual(set(rx["Looked strong enough"]), {"yes"})
        self.assertEqual(set(rx["First decode"]), {T("2026-11-18 20:10")})
        self.assertTrue((rx["Km from you"] > 8000).all())

    def test_it_lists_all_your_rbn_spots_in_the_box_and_marks_those_in_the_destination(self):
        spots = pd.DataFrame({"spotter": ["DL1SKM", "JA1SKM", "W5NEAR"], "band": ["20m", "20m", "20m"], "snr": [12.0, 8.0, 25.0],
                              "time": [T("2026-11-18 20:12"), T("2026-11-18 20:13"), T("2026-11-18 20:14")], "mode": ["CQ", "CQ", "CQ"], "tx_mode": ["CW", "CW", "CW"]})
        locs = dict(self.LOCS, W5NEAR=(32.0, -101.0))
        log = self.log()
        wspr = self.wspr()
        grid = self.grid(log, wspr)
        rbn = lo.cell_evidence(grid, log, lc.contact_places(log, HOME), spots, locs, lambda a, b: wspr[(wspr["time"] > a) & (wspr["time"] <= b)], HOME, "20m",
                               T("2026-11-18 20:00"), "continent", "EU", DX, True)["rbn"]
        self.assertEqual(rbn["Skimmer"].tolist(), ["DL1SKM", "JA1SKM", "W5NEAR"])                  # every spot of you in the box, not only the distant ones
        self.assertEqual(rbn["In the destination"].tolist(), ["yes", "no", "no"])
        self.assertEqual(rbn["SNR"].tolist(), [12, 8, 25])
        self.assertLess(rbn["Km from you"].iloc[2], 200)                                              # the near skimmer is listed with its distance

    def test_a_spot_from_a_skimmer_whose_place_is_not_known_is_still_listed(self):
        spots = pd.DataFrame({"spotter": ["XX9UNKNOWN"], "band": ["20m"], "snr": [5.0], "time": [T("2026-11-18 20:12")], "mode": ["CQ"], "tx_mode": ["CW"]})
        log = self.log()
        wspr = self.wspr()
        rbn = lo.cell_evidence(self.grid(log, wspr), log, lc.contact_places(log, HOME), spots, {}, lambda a, b: wspr[(wspr["time"] > a) & (wspr["time"] <= b)], HOME,
                               "20m", T("2026-11-18 20:00"), "continent", "EU", DX, True)["rbn"]
        self.assertEqual(rbn["Skimmer"].tolist(), ["XX9UNKNOWN"])
        self.assertTrue(pd.isna(rbn["Km from you"].iloc[0]))
        self.assertEqual(rbn["In the destination"].tolist(), ["no"])

    def test_it_lists_your_contacts_in_the_box_and_which_were_with_the_destination(self):
        q = self.evidence()["qsos"]
        self.assertEqual(q["Call"].tolist(), ["DL1AAA"])
        self.assertEqual(q["With the destination"].tolist(), ["yes"])
        self.assertEqual(q["Placed by"].tolist(), ["its grid"])
        other = self.evidence("20:30")["qsos"]
        self.assertEqual((other["Call"].tolist(), other["With the destination"].tolist()), (["W1AAA"], ["no"]))

    def test_a_box_with_nothing_in_it_gives_empty_tables_not_errors(self):
        ev = self.evidence("19:00", dest="AF")
        self.assertEqual((len(ev["transmitters"]), len(ev["receivers"]), len(ev["rbn"]), len(ev["qsos"])), (0, 0, 0, 0))
        self.assertEqual(ev["state"], lf.NO_REPORTS)


class TheCardHeadline(Session):
    LOCS = TheBandTimeline.LOCS
    timeline = TheBandTimeline.timeline
    card = TheBandTimeline.card

    def test_the_headline_says_who_you_worked_and_where_paths_appeared_outside_your_activity(self):
        log = log_of(rec("W1AAA", "2010", band="20m", gridsquare="FN31"), rec("W1BBB", "2015", band="15m", gridsquare="FN31"),
                     rec("W1CCC", "2105", band="20m", gridsquare="FN31"), rec("JA1ZZZ", "2106", band="20m", gridsquare="PM95"))
        wspr = pd.concat([self.wspr(), self.wspr().assign(band="15m")], ignore_index=True)
        tl, _ = self.timeline("heard", log=log, wspr=wspr)
        self.assertEqual(tl["headline"], "You worked 1 station in Asia. WSPR near you showed a path to a distant continent on 15m and 20m at times when your log has no contact on that band.")
        self.assertTrue(self.card(tl, "15m")["outside"])
        self.assertTrue(self.card(tl, "20m")["outside"])                                                   # Europe paths on 20m, a continent you did not work there

    def test_the_headline_for_a_session_with_nothing_distant_is_plain(self):
        wspr = self.wspr()
        none = wspr[~wspr["rx"].str.startswith(("DL", "JA"))]
        tl, _ = self.timeline(wspr=none, log=log_of(rec("W1AAA", "2010", gridsquare="FN31"), rec("W1BBB", "2105", gridsquare="FN31")))
        self.assertEqual(tl["headline"], "You logged no contact with a distant continent. WSPR near you showed no path to a distant continent on the bands you worked.")

    def test_the_headline_leads_the_cards_and_passes_the_guard(self):
        tl, _ = self.timeline("heard")
        html = lh.band_cards_html(tl)
        self.assertLess(html.index(tl["headline"][:30]), html.index('class="bc"'))
        self.assertEqual(lo.unsupported_claims(tl["headline"]), [])


class TheDestinationView(Session):
    """The openings one destination at a time: only destinations with something to show get a view, the rest are named."""
    LOCS = {"DL1SKM": (50.0, 10.0), "ZS6SKM": (-26.0, 28.0)}

    def timeline(self, log=None, wspr=None, spots=None, rbn_ok=True):
        log = self.log() if log is None else log
        grid = self.grid(log, wspr)
        return lo.band_timeline(grid, log, lc.contact_places(log, HOME), spots, self.LOCS, HOME, DX, "good", rbn_ok, None, "dx", "NA")

    def test_only_destinations_with_a_path_a_skimmer_or_a_contact_get_a_view(self):
        views, empty = lo.destination_views(self.timeline())
        self.assertEqual([v["code"] for v in views], ["EU", "AS"])                               # Germany: path and contact; Japan: a contact only (its receivers were too weak)
        self.assertEqual(empty, ["Africa", "Oceania", "South America"])                        # nothing at all there
        eu, asia = views
        self.assertEqual((eu["contacts"], eu["paths"], asia["contacts"], asia["paths"]), (1, 1, 1, 0))
        self.assertEqual((lo.destination_badge(eu), lo.destination_badge(asia)), ("1 contact", "1 contact"))
        self.assertEqual(lo.destination_badge({"contacts": 0, "rbn": False}), "paths only")
        self.assertEqual(lo.destination_badge({"contacts": 3, "rbn": True}), "3 contacts \u00b7 RBN")

    def test_the_destinations_you_worked_come_before_those_with_only_paths(self):
        wspr = self.wspr()
        africa = wspr[wspr["rx"].str.startswith("DL")].assign(rx=lambda d: d["rx"].str.replace("DL1R", "ZS6R"), rx_lat=-26.0, rx_lon=28.0)
        views, empty = lo.destination_views(self.timeline(wspr=pd.concat([wspr, africa], ignore_index=True)))
        self.assertEqual([v["code"] for v in views][:2], ["EU", "AS"])                           # worked first
        self.assertIn("AF", [v["code"] for v in views])
        self.assertEqual([v["code"] for v in views][-1], "AF")                                   # paths only, last
        self.assertEqual(lo.destination_badge(views[-1]), "paths only")

    def test_a_view_says_for_this_destination_alone_when_the_path_was_and_what_you_did(self):
        views, _ = lo.destination_views(self.timeline())
        panel = views[0]["panels"][0]
        self.assertEqual(panel["lanes"][0]["band"], "20m")
        self.assertEqual([c["call"] for c in panel["lanes"][0]["contacts"]], ["DL1AAA"])
        band, text = panel["lines"][0]
        self.assertEqual(band, "20m")
        self.assertIn("Worked Europe", text)
        self.assertEqual(lo.unsupported_claims(text), [])
        self.assertNotIn("Asia", text)                                                           # the line is about Europe only

    def test_the_strip_names_the_band_you_were_on_and_leaves_a_gap_where_you_logged_nothing(self):
        log = log_of(rec("W1AAA", "2000", band="20m", gridsquare="FN31"), rec("W1BBB", "2010", band="20m", gridsquare="FN31"),
                     rec("W1CCC", "2100", band="15m", gridsquare="FN31"))
        runs = lo._band_runs([(T("2026-11-18 20:00"), "20m"), (T("2026-11-18 20:10"), "20m"), (T("2026-11-18 21:00"), "15m")], T("2026-11-18 20:00"), T("2026-11-18 21:15"))
        self.assertEqual([(a.strftime("%H:%M"), b.strftime("%H:%M"), band) for a, b, band in runs],
                         [("20:00", "20:15", "20m"), ("20:15", "21:00", None), ("21:00", "21:15", "15m")])
        self.assertEqual(lo._band_runs([], T("2026-11-18 20:00"), T("2026-11-18 20:30")), [(T("2026-11-18 20:00"), T("2026-11-18 20:30"), None)])

    def test_a_skimmer_alone_is_enough_for_a_destination_and_says_so(self):
        spots = pd.DataFrame({"spotter": ["ZS6SKM"], "band": ["20m"], "snr": [9.0], "time": [T("2026-11-18 20:12")], "mode": ["CQ"], "tx_mode": ["CW"]})
        views, empty = lo.destination_views(self.timeline(spots=spots))
        africa = [v for v in views if v["code"] == "AF"]
        self.assertTrue(africa and africa[0]["rbn"])
        self.assertEqual(lo.destination_badge(africa[0]), "RBN")
        line = africa[0]["panels"][0]["lines"][0][1]
        self.assertIn("RBN skimmers in Africa spotted you on 20m", line)
        self.assertEqual(lo.unsupported_claims(line), [])

    def test_a_contact_nearer_than_the_limit_is_explained_not_lost(self):
        log = log_of(rec("HK3AAA", "2010", gridsquare="FJ24", country="Colombia"), rec("W1AAA", "2040", gridsquare="FN31"))
        note = lo.inside_limit_note(lc.contact_places(log, HOME), "NA", DX)
        self.assertEqual(note, "Inside the 3,000 mile limit, so not counted as DX: HK3AAA (Colombia).")            # by callsign, with the country its prefix says
        self.assertEqual(lo.inside_limit_note(lc.contact_places(log, HOME), "NA", 0.0), "")
        self.assertEqual(lo.inside_limit_note(lc.contact_places(self.log(), HOME), "NA", DX), "")

    def test_the_picture_has_the_idea_the_lines_the_strip_the_lanes_and_what_was_left_out(self):
        tl = self.timeline()
        views, empty = lo.destination_views(tl)
        html = lh.destination_html(views[0], tl, {"20m": "#800080", "15m": "#444444"}, empty, "Inside the 3,000 mile limit, so not counted as DX: Aruba.")
        for text in ("Europe: when was it reachable, and where were you?", "Nearby WSPR stations act as test signals", "WORTH A LOOK", "You were on", "DL1AAA",
                     "nearby WSPR showed a path to Europe (pale: one receiving station)", "your contact with Europe", "an RBN skimmer in Europe spotted you",
                     "Not shown: Africa, Oceania and South America (no nearby WSPR path, no RBN skimmer and no contact there).", "not counted as DX: Aruba.", 'id="sec-openings"'):
            self.assertIn(text, html)
        self.assertEqual(lo.unsupported_claims(html), [])

    def test_a_log_over_two_days_has_a_stretch_for_each_and_dated_lines(self):
        log = log_of(rec("DL1AAA", "2010", gridsquare="JN58"), rec("DL1BBB", "2010", gridsquare="JN58").replace("20261118", "20261120"))
        wspr = self.wspr()
        late = wspr.assign(time=wspr["time"] + pd.Timedelta(days=2))
        tl = self.timeline(log=log, wspr=pd.concat([wspr, late], ignore_index=True))
        views, empty = lo.destination_views(tl)
        self.assertEqual(len(views[0]["panels"]), 2)
        html = lh.destination_html(views[0], tl, None, empty)
        self.assertIn("Wed 18 Nov 2026", html)
        self.assertIn("Fri 20 Nov 2026", html)


class TheSignalComparison(unittest.TestCase):
    """The comparison with RBN as a section of its own: what it compares, how wide the results ran, and which receiving stations are behind it."""

    def matches(self):
        rows = [("20m", f"DL{i}SKM", -10.0 + i, -20.0 + i, 10.0 + (i % 3)) for i in range(1, 7)] + [("20m", "DL1SKM", -9.0, -19.0, 11.0), ("15m", "JA1SKM", -12.0, -20.0, 8.0)]
        return pd.DataFrame(rows, columns=["band", "rx", "adj", "obs", "diff"])

    def test_the_table_has_a_row_for_each_band_and_station_with_the_matches_counted(self):
        table = lc.match_table(self.matches())
        self.assertEqual(list(table.columns), lc.MATCH_COLUMNS)
        self.assertEqual(table["Band"].tolist()[0], "15m")                                       # highest band first (15m is above 20m)
        dl1 = table[table["Receiving station"] == "DL1SKM"].iloc[0]
        self.assertEqual(dl1["Matches"], 2)                                                      # one station heard in two stretches is two matches, one row
        self.assertEqual(len(table), 7)
        self.assertEqual(len(lc.match_table(None)), 0)

    def test_the_table_takes_off_the_same_reference_the_bars_do(self):
        match = pd.DataFrame([("20m", "DL1SKM", -10.0, -20.0, 15.0)], columns=["band", "rx", "adj", "obs", "diff"])
        row = lc.match_table(match).iloc[0]
        self.assertEqual(row["Above (+) or below (-) the estimate (dB)"], 15.0 - lc.TYPICAL_OFFSET_DB)

    def test_the_section_says_what_it_compares_and_that_the_reference_is_experimental(self):
        html = lh.signal_intro_html(10.0)
        self.assertIn('id="sec-signal"', html)
        self.assertIn("Signal comparison: RBN skimmers against WSPR stations near you", html)
        self.assertIn("experimental", html)
        self.assertIn("about 10 dB higher", html)
        self.assertEqual(lo.unsupported_claims(html), [])

    def test_the_section_works_the_arithmetic_through_with_the_power_and_says_what_the_mode_does(self):
        import conditions as cond
        html = lh.signal_intro_html(10.0, 100.0, "CW", None, cond.MODES)
        self.assertIn("How a bar is worked out", html)
        self.assertIn("10 × log₁₀(your watts ÷ its watts)", html)
        self.assertIn("-20 + (50 − 37) = -7 dB for your 100 W (50 dBm)", html)           # a 5 W transmitter heard at -20 dB, restated to 100 W
        self.assertIn("only thing added or taken off by hand", html)                          # the 10 dB is the one fixed correction and is not tied to power or mode
        self.assertIn("<b>Power.</b> You entered 100 W", html)
        self.assertIn("the estimates are the ones a 100 W station would get", html)
        self.assertIn("doubling it adds 3 dB", html)
        self.assertIn("<b>Mode.</b> The bars do not use it", html)
        self.assertIn("CW -5 dB", html)                                                       # the threshold the mode does set, in the openings
        self.assertIn("SSB +8 dB", html)
        half = lh.signal_intro_html(10.0, 50.0, "CW", None, cond.MODES)
        self.assertIn("every estimate is -3.0 dB from what a 100 W station would get", half)
        self.assertIn("-20 + (47 − 37) = -10 dB for your 50 W (47 dBm)", half)
        self.assertEqual(lo.unsupported_claims(html), [])

    def test_a_real_match_is_worked_through_when_one_matched_once(self):
        table = lc.match_table(pd.DataFrame([("20m", "K1HTV-4", -10.0, -20.0, 15.0), ("20m", "K3GMQ", -9.0, -19.0, 14.0), ("20m", "K3GMQ", -9.0, -19.0, 14.0)],
                                            columns=["band", "rx", "adj", "obs", "diff"]))
        ex = lh.signal_example(table)
        self.assertEqual(ex["rx"], "K1HTV-4")                                                  # a station matched once, so the numbers add up exactly
        self.assertEqual((ex["obs"], ex["est"], ex["diff"], ex["after"]), (-20.0, -10.0, -10.0, -20.0))
        html = lh.signal_intro_html(10.0, 100.0, "CW", ex, None)
        self.assertIn("K1HTV-4 on 20m", html)
        self.assertIn("-20 − (-10) = -10.0 dB", html)
        self.assertIn("leaves <b>-20.0 dB</b>", html)
        self.assertIsNone(lh.signal_example(table[table["Matches"] > 1]))
        self.assertIsNone(lh.signal_example(None))

    def test_a_band_with_enough_matches_shows_how_far_the_middle_half_ran(self):
        row = {"band": "20m", "contacts": 5, "other": 0, "skimmers": 4, "report": 5.0, "page": 0.5, "spotted": 0.5, "listening": 3, "stronger_db": 2.0, "matches": 9,
               "match_rx": 6, "q1": -1.0, "q3": 5.0, "thin": False, "note": "", "tone": "", "no_picture": False}
        html = lh.band_table_html(pd.DataFrame([row]))
        self.assertIn("The middle half of the matches ran from -1.0 to +5.0 dB", html)
        self.assertIn("6 different receiving stations", html)
        row.update(stronger_db=float("nan"), q1=float("nan"), q3=float("nan"))
        self.assertNotIn("middle half", lh.band_table_html(pd.DataFrame([row])))


class TheGlanceRow(unittest.TestCase):
    """The row of short findings under the tiles, each a link to its section."""

    def test_an_id_goes_on_the_first_card_or_hero_and_nothing_else_changes(self):
        self.assertEqual(lh.with_id('<div class="lc"><div class="lc-card"><h4>x</h4></div></div>', "sec-a"), '<div class="lc"><div class="lc-card" id="sec-a"><h4>x</h4></div></div>')
        self.assertEqual(lh.with_id('<div class="lc"><div class="lc-hero"><h3>x</h3></div></div>', "sec-b"), '<div class="lc"><div class="lc-hero" id="sec-b"><h3>x</h3></div></div>')
        self.assertEqual(lh.with_id("<p>no card</p>", "sec-c"), "<p>no card</p>")

    def test_each_finding_is_a_link_to_its_section_and_an_empty_one_is_left_out(self):
        html = lh.glance_html([("Park", "46th of 468.", "sec-park"), ("RBN", "", "sec-session"), ("Openings", "A <path> showed.", "sec-openings")])
        self.assertIn('href="#sec-park"', html)
        self.assertNotIn("sec-session", html)                                                  # no sentence yet, so no card
        self.assertIn("A &lt;path&gt; showed.", html)                                         # text is escaped
        self.assertEqual(lh.glance_html([("RBN", "", "sec-session")]), "")

    def test_the_page_builds_the_row_from_what_is_known_so_far(self):
        from views.log_view import _glance
        log = log_of(rec("DL1AAA", "2010", band="20m"), rec("DL1AAA", "2020", band="15m"), rec("W1AAA", "2030", band="20m"))
        rep = lc.repeat_stations(log)
        early = _glance([], rep, None, {}, HOME, "", None)
        self.assertIn("sec-hunters", early)
        self.assertNotIn("sec-session", early)                                                 # RBN not read yet
        spots = pd.DataFrame({"spotter": ["DL1SKM", "JA1SKM"], "band": ["20m", "15m"], "snr": [12.0, 8.0], "time": [T("2026-11-18 20:12"), T("2026-11-18 20:22")]})
        later = _glance([], rep, spots, {"DL1SKM": (50.0, 10.0), "JA1SKM": (36.0, 140.0)}, HOME, "Looking at Europe: WSPR showed a path in 2 of 4 boxes.", None)
        self.assertIn("2 RBN skimmers spotted you, on 20m, 15m.", later.replace("15m, 20m", "20m, 15m"))
        self.assertIn("The farthest was JA1SKM", later)
        self.assertIn("sec-openings", later)


class TheShareCardMap(unittest.TestCase):
    def places(self, *records):
        return lc.contact_places(log_of(*records), HOME)

    def test_the_map_holds_a_point_for_each_place_with_the_bands_worked_there(self):
        import share_card as sc
        m = sc.map_facts(self.places(
            rec("DL1AAA", "2010", gridsquare="JN58", rst_rcvd="579"), rec("DL1AAA", "2011", band="15m", gridsquare="JN58", rst_rcvd="599"),
            rec("DL1AAA", "2012", band="15m", gridsquare="JN58"), rec("W1AAA", "2013", gridsquare="FN31", rst_rcvd="55")), HOME)
        self.assertEqual(m["placed"], 4)
        self.assertEqual(m["home"], HOME)
        by_call = {p["call"]: p for p in m["points"]}
        self.assertEqual(len(m["points"]), 2)
        self.assertEqual(by_call["DL1AAA"]["n"], 3)
        self.assertEqual(by_call["DL1AAA"]["bands"], ["15m", "20m"])                                 # busiest band first
        self.assertEqual(by_call["DL1AAA"]["band_n"], {"15m": 2, "20m": 1})
        self.assertEqual(by_call["W1AAA"]["bands"], ["20m"])
        self.assertEqual(by_call["DL1AAA"]["country"], "Germany")                                      # named from the callsign, in plain words
        self.assertNotIn("s", by_call["DL1AAA"])                                                       # the colour is the band, not the report
        self.assertEqual(len(m["contacts"]), 4)

    def test_the_farthest_contact_is_named(self):
        import share_card as sc
        m = sc.map_facts(self.places(rec("JA1ZZZ", "2010", band="15m", gridsquare="PM95"), rec("W1AAA", "2012", gridsquare="FN31")), HOME)
        self.assertEqual((m["farthest"]["call"], m["farthest"]["band"]), ("JA1ZZZ", "15m"))
        self.assertGreater(m["farthest"]["km"], 9000)

    def test_no_places_means_no_map(self):
        import share_card as sc
        self.assertIsNone(sc.map_facts(None, HOME))
        self.assertIsNone(sc.map_facts(self.places(rec("W5AAA", "2010", gridsquare="DM82")), None))
        nowhere = self.places(rec("W5AAA", "2010")).assign(c_source="", c_lat=float("nan"), c_lon=float("nan"))
        self.assertIsNone(sc.map_facts(nowhere, HOME))

    def test_a_path_to_asia_runs_on_across_the_pacific_and_the_map_still_holds_it(self):
        import share_card as sc
        m = sc.map_facts(self.places(rec("JA1ZZZ", "2010", gridsquare="PM95"), rec("W1AAA", "2012", gridsquare="FN31")), HOME)
        lines, ends, (west, east, south, north) = sc._paths(m)
        self.assertLess(west, -180)                                                                    # unwrapped: the way a path really goes
        x0, x1, y0, y1 = sc._extent((west, east, south, north), (0.31, 0.97, 0.10, 0.90))
        self.assertLessEqual(x0, west)
        self.assertGreaterEqual(x1, east)
        self.assertAlmostEqual((x1 - x0) / (y1 - y0), sc.SIZE[0] / sc.SIZE[1], places=6)              # one scale in both directions
        lat, lon = ends[(m["points"][0]["lat"], m["points"][0]["lon"], "20m")]
        self.assertTrue(-90 <= lat <= 90)                                                              # a path's end is (latitude, longitude), and the diamond goes there

    def test_a_local_session_still_gets_a_map_not_a_zoom_to_nothing(self):
        import share_card as sc
        m = sc.map_facts(self.places(rec("W5AAA", "2010", gridsquare="DM82")), HOME)
        lines, ends, bounds = sc._paths(m)
        x0, x1, y0, y1 = sc._extent(bounds, (0.31, 0.97, 0.10, 0.90))
        self.assertGreaterEqual((x1 - x0) * 0.66, sc.MIN_LON_SPAN - 1e-6)

    def test_the_card_counts_the_contacts_on_each_band_highest_band_first(self):
        import share_card as sc
        log = log_of(rec("W1AAA", "2010", band="20m"), rec("W1BBB", "2011", band="20m"), rec("W1CCC", "2012", band="15m"), rec("W1DDD", "2013", band="10m"))
        facts = sc.share_facts(log, lc.summary(log), lc.worked_summary(log), "K5OHY", None, lc.repeat_stations(log))
        self.assertEqual(facts["bands"], [("10m", 1), ("15m", 1), ("20m", 2)])

    def test_the_top_hunter_is_the_station_worked_on_the_most_bands(self):
        import share_card as sc
        log = log_of(rec("W1HUNT", "2010", band="20m"), rec("W1HUNT", "2011", band="15m"), rec("W1HUNT", "2012", band="10m"), rec("W1HUNT", "2013", band="17m"),
                     rec("W2TWO", "2014", band="20m"), rec("W2TWO", "2015", band="15m"), rec("W3ONE", "2016", band="20m"))
        facts = sc.share_facts(log, lc.summary(log), lc.worked_summary(log), "K5OHY", None, lc.repeat_stations(log))
        self.assertEqual(facts["hunters"], {"n": 2, "top": "W1HUNT", "k": 4, "bands": ["10m", "15m", "17m", "20m"]})
        self.assertIn("stations worked on 2 or more bands", " ".join(facts["lines"]))                 # the text for a post still says it
        none = sc.share_facts(log_of(rec("W1AAA", "2010")), lc.summary(log_of(rec("W1AAA", "2010"))), lc.worked_summary(log_of(rec("W1AAA", "2010"))), "K5OHY", None, None)
        self.assertIsNone(none["hunters"])

    def test_the_picture_draws_with_the_bands_and_the_hunters_and_without_them(self):
        import share_card as sc
        log = log_of(rec("W1HUNT", "2010", band="20m", gridsquare="FN31"), rec("W1HUNT", "2011", band="15m", gridsquare="FN31"),
                     rec("DL1AAA", "2012", band="17m", gridsquare="JN58"))
        places = lc.contact_places(log, HOME)
        full = sc.share_facts(log, lc.summary(log), lc.worked_summary(log), "K5OHY", None, lc.repeat_stations(log), places, HOME)
        bare = dict(full, hunters=None, bands=[])
        a, b = sc.share_png(full), sc.share_png(bare)
        self.assertTrue(a.startswith(b"\x89PNG") and b.startswith(b"\x89PNG"))
        self.assertNotEqual(a, b)
        many = dict(full, bands=[(f"{n}m", 5) for n in (160, 80, 60, 40, 30, 20, 17, 15, 12, 10, 6)],
                    hunters=dict(full["hunters"], k=11, bands=[f"{n}m" for n in (160, 80, 60, 40, 30, 20, 17, 15, 12, 10, 6)]))
        self.assertTrue(sc.share_png(many).startswith(b"\x89PNG"))                                    # eleven bands fit, in two columns

    def test_the_picture_is_sharp_and_the_map_changes_it(self):
        import share_card as sc
        log = log_of(rec("DL1AAA", "2010", gridsquare="JN58"), rec("W1AAA", "2012", gridsquare="FN31"), rec("JA1ZZZ", "2015", gridsquare="PM95"))
        places = lc.contact_places(log, HOME)
        with_map = sc.share_facts(log, lc.summary(log), lc.worked_summary(log), "K5OHY", None, None, places, HOME)
        without = sc.share_facts(log, lc.summary(log), lc.worked_summary(log), "K5OHY", None, None)
        self.assertIsNotNone(with_map["map"])
        self.assertIsNone(without["map"])
        a, b = sc.share_png(with_map), sc.share_png(without)
        for png in (a, b):
            self.assertEqual((int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")), (2400, 1260))
        self.assertNotEqual(a, b)
        long = dict(with_map, title="A very long park name " * 8, subtitle="and a very long line " * 20, lines=["x" * 400, "y" * 400, "z" * 400])
        self.assertTrue(sc.share_png(long).startswith(b"\x89PNG"))                                    # long text is cut, never an error

    def test_long_text_is_cut_with_an_ellipsis_and_short_text_is_left_alone(self):
        import share_card as sc
        self.assertEqual(sc._wrap("short", 30, 2), ["short"])
        self.assertEqual(sc._wrap("", 30, 2), [""])
        cut = sc._wrap("The most QSOs of any activation listed at the park, and among the top few percent of all POTA activations this year", 56, 2)
        self.assertEqual(len(cut), 2)
        self.assertTrue(cut[-1].endswith("\u2026"))
        self.assertNotIn("\u2026\u2026", cut[-1])

    def test_the_text_for_sharing_is_unchanged_by_the_map(self):
        import share_card as sc
        log = log_of(rec("DL1AAA", "2010", gridsquare="JN58"))
        places = lc.contact_places(log, HOME)
        a = sc.share_text(sc.share_facts(log, lc.summary(log), lc.worked_summary(log), "K5OHY", None, None, places, HOME))
        b = sc.share_text(sc.share_facts(log, lc.summary(log), lc.worked_summary(log), "K5OHY", None, None))
        self.assertEqual(a, b)


class TheShareCardShapes(unittest.TestCase):
    """The picture for each place it is posted: landscape, square, portrait and story."""

    def facts(self, with_map=True):
        import share_card as sc
        log = log_of(rec("W1HUNT", "2010", band="20m", gridsquare="FN31"), rec("W1HUNT", "2011", band="15m", gridsquare="FN31"),
                     rec("DL1AAA", "2012", band="17m", gridsquare="JN58"), rec("JA1ZZZ", "2013", band="10m", gridsquare="PM95"))
        places = lc.contact_places(log, HOME) if with_map else None
        return sc.share_facts(log, lc.summary(log), lc.worked_summary(log), "K5OHY", None, lc.repeat_stations(log), places, HOME if with_map else None)

    def size_of(self, data):
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")

    def test_there_is_a_shape_for_each_place_it_is_posted(self):
        import share_card as sc
        self.assertEqual(list(sc.FORMATS), ["landscape", "square", "portrait", "story"])
        self.assertEqual(sc.DEFAULT_FORMAT, "landscape")
        for spec in sc.FORMATS.values():
            self.assertTrue(spec["label"] and spec["where"])

    def test_each_shape_is_the_size_and_ratio_the_sites_want_at_twice_the_pixels(self):
        import share_card as sc
        facts = self.facts()
        expect = {"landscape": (2400, 1260), "square": (2160, 2160), "portrait": (2160, 2700), "story": (2160, 3840)}
        for fmt, size in expect.items():
            data = sc.share_png(facts, fmt)
            self.assertTrue(data.startswith(b"\x89PNG"))
            self.assertEqual(self.size_of(data), size, fmt)
        w, h = expect["portrait"]
        self.assertEqual(w / h, 4 / 5)                                                                 # Instagram's portrait post
        w, h = expect["story"]
        self.assertAlmostEqual(w / h, 9 / 16, places=6)                                                # a story

    def test_the_default_is_the_landscape_picture_as_before(self):
        import share_card as sc
        facts = self.facts()
        self.assertEqual(sc.share_png(facts), sc.share_png(facts, "landscape"))

    def test_a_jpeg_is_the_same_size_and_smaller(self):
        import io
        from PIL import Image
        import share_card as sc
        facts = self.facts()
        for fmt in sc.FORMATS:
            jpg, png = sc.share_jpg(facts, fmt), sc.share_png(facts, fmt)
            self.assertTrue(jpg.startswith(b"\xff\xd8"))
            self.assertEqual(Image.open(io.BytesIO(jpg)).size, Image.open(io.BytesIO(png)).size)
            self.assertLess(len(jpg), len(png) * 1.3)

    def test_a_story_keeps_the_top_and_the_bottom_clear_for_the_apps_buttons(self):
        import io
        from PIL import Image
        import share_card as sc
        spec = sc.FORMATS["story"]
        img = Image.open(io.BytesIO(sc.share_png(self.facts(), "story"))).convert("RGB")
        w, h = img.size
        top, bottom = round(spec["safe_top"] * sc.DPI), round(spec["safe_bottom"] * sc.DPI)
        self.assertEqual(img.crop((20, 0, w - 20, top - 4)).getcolors(), [((w - 40) * (top - 4), (14, 17, 23))])        # one flat colour: nothing drawn
        self.assertEqual(img.crop((20, h - bottom + 4, w - 20, h - 20)).getcolors(), [((w - 40) * (bottom - 24), (11, 17, 25))])

    def test_the_other_shapes_have_content_to_their_edges(self):
        import io
        from PIL import Image
        import share_card as sc
        img = Image.open(io.BytesIO(sc.share_png(self.facts(), "portrait"))).convert("RGB")
        self.assertGreater(len(img.crop((0, 0, img.size[0], 300)).getcolors(maxcolors=100000)), 5)                    # the map reaches the top of a post

    def test_every_shape_draws_without_a_map_with_long_text_and_with_many_bands(self):
        import share_card as sc
        for fmt in sc.FORMATS:
            self.assertTrue(sc.share_png(self.facts(with_map=False), fmt).startswith(b"\x89PNG"), fmt)
            full = self.facts()
            long = dict(full, title="A very long park name " * 8, subtitle="and a very long line " * 20, lines=["x" * 400, "y" * 400, "z" * 400])
            self.assertTrue(sc.share_png(long, fmt).startswith(b"\x89PNG"), fmt)
            many = dict(full, bands=[(f"{n}m", 5) for n in (160, 80, 60, 40, 30, 20, 17, 15, 12, 10, 6)],
                        hunters=dict(full["hunters"], k=11, bands=[f"{n}m" for n in (160, 80, 60, 40, 30, 20, 17, 15, 12, 10, 6)]))
            self.assertTrue(sc.share_png(many, fmt).startswith(b"\x89PNG"), fmt)

    def test_a_world_map_is_never_stretched_taller_than_the_world(self):
        import share_card as sc
        m = self.facts()["map"]
        bounds = sc._paths(m)[2]
        W = sc.FORMATS["story"]["size"][0]
        per_inch = max(bounds[1] - bounds[0], sc.MIN_LON_SPAN) / (0.9 * W)
        self.assertLessEqual(165.0 / per_inch, 8)                                                      # a wide spread of contacts gives a short map, not a tall one


class TheShareCardOnAirTime(unittest.TestCase):
    """The time on the air and the contacts an hour on the share picture."""

    def facts_of(self, *records):
        import share_card as sc
        log = log_of(*records)
        return sc.share_facts(log, lc.summary(log), lc.worked_summary(log), "K5OHY", None, lc.repeat_stations(log), lc.contact_places(log, HOME), HOME)

    def test_a_length_of_time_is_written_in_plain_words(self):
        import share_card as sc
        self.assertEqual([sc._hm(m) for m in (47, 59, 60, 112, 150)], ["47 min", "59 min", "1 h", "1 h 52 m", "2 h 30 m"])
        self.assertEqual([sc._compact(m) for m in (47, 60, 112, 150)], ["47m", "1h", "1h 52m", "2h 30m"])

    def test_one_contact_has_no_time_on_the_air(self):
        import share_card as sc
        facts = self.facts_of(rec("W1AAA", "2010", gridsquare="FN31"))
        self.assertIsNone(facts["on_air"])
        self.assertEqual(len(sc.card_numbers(facts)), len(facts["numbers"]))
        self.assertNotIn("on the air", sc.share_text(facts))

    def test_a_steady_session_shows_the_time_and_the_rate_without_a_span(self):
        import share_card as sc
        facts = self.facts_of(*[rec(f"W{i}AAA", f"20{m:02d}", gridsquare="FN31") for i, m in enumerate(range(0, 60, 5), 1)])
        oa = facts["on_air"]
        self.assertEqual(oa["elapsed"], "")
        self.assertTrue(oa["text"].endswith(("min", "m")))
        numbers = sc.card_numbers(facts)
        self.assertEqual(len(numbers), len(facts["numbers"]) + 2)
        self.assertEqual(numbers[-2][1], "on the air")
        self.assertEqual(numbers[-1][1], "contacts / hour")
        self.assertIn("on the air", sc.share_text(facts))
        self.assertNotIn("between the first and last", sc.share_text(facts))

    def test_a_long_break_is_not_counted_and_the_span_is_shown(self):
        import share_card as sc
        recs = [rec(f"W{i}AAA", f"20{m:02d}", gridsquare="FN31") for i, m in enumerate(range(0, 30, 5), 1)] + \
               [rec(f"K{i}AAA", f"23{m:02d}", gridsquare="FN31") for i, m in enumerate(range(0, 30, 5), 1)]
        oa = self.facts_of(*recs)["on_air"]
        self.assertLess(oa["minutes"], 90)                                                  # the three hours off the air are not counted
        self.assertEqual(oa["elapsed"], "3 h 25 m")
        facts = self.facts_of(*recs)
        self.assertEqual(sc.card_numbers(facts)[-2][1], "on air of 3 h 25 m")
        self.assertIn("between the first and last contact", sc.share_text(facts))

    def test_every_shape_draws_with_and_without_the_two_extra_tiles(self):
        import share_card as sc
        facts = self.facts_of(*[rec(f"W{i}AAA", f"20{m:02d}", gridsquare="FN31") for i, m in enumerate(range(0, 60, 5), 1)])
        self.assertIsNotNone(facts["on_air"])
        for fmt in sc.FORMATS:
            self.assertTrue(sc.share_png(facts, fmt).startswith(b"\x89PNG"), fmt)
            self.assertTrue(sc.share_png(dict(facts, on_air=None), fmt).startswith(b"\x89PNG"), fmt)


class ContactMapsWithoutRbn(unittest.TestCase):
    def test_the_placing_of_contacts_does_not_need_any_rbn_data(self):
        places = lc.contact_places(log_of(rec("DL1AAA", "2010", gridsquare="JN58"), rec("W1AAA", "2040", state="NY", country="United States")), HOME)
        self.assertEqual(places["c_source"].tolist(), ["grid", "state"])                            # the right-hand map's data comes from the log alone


if __name__ == "__main__":
    unittest.main()
