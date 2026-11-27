"""The story behind a session's space weather: NASA's DONKI (storms, ejections, flares and the links between them) and the sentences and chart built from it."""
import json
import unittest
from unittest import mock

import pandas as pd

import donki
import log_check as lc
import log_openings as lo
import log_space as ls
import log_space_html as lsh
import log_story as st

T = pd.Timestamp


def log_of(*stamps):
    rec = lambda i, d, hhmm: f"<CALL:5>W1A{i:02d} <QSO_DATE:8>{d} <TIME_ON:4>{hhmm} <BAND:3>20m <MODE:2>CW <EOR>"
    return lc.parse_adif("<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(rec(i, d, h) for i, (d, h) in enumerate(stamps)) + "\n")


GST = [{"gstID": "2024-05-10T15:00:00-GST-001", "startTime": "2024-05-10T15:00Z",
        "allKpIndex": [{"kpIndex": 7.67, "observedTime": "2024-05-10T18:00Z"}, {"kpIndex": 9.0, "observedTime": "2024-05-11T00:00Z"}, {"kpIndex": 8.33, "observedTime": "2024-05-11T06:00Z"}],
        "linkedEvents": [{"activityID": "2024-05-08T22:24:00-CME-001"}, {"activityID": "2024-05-09T09:24:00-CME-001"}, {"activityID": "2024-05-10T16:36:00-IPS-001"}]}]
CME = [{"activityID": "2024-05-08T22:24:00-CME-001", "startTime": "2024-05-08T22:24Z", "sourceLocation": "S20W17", "activeRegionNum": 13664, "note": "x",
        "cmeAnalyses": [{"isMostAccurate": False, "speed": 500.0}, {"isMostAccurate": True, "speed": 1257.0, "enlilList": [{"estimatedShockArrivalTime": "2024-05-10T18:10Z"}]}],
        "linkedEvents": [{"activityID": "2024-05-08T21:08:00-FLR-001"}, {"activityID": "2024-05-10T15:00:00-GST-001"}]},
       {"activityID": "2024-05-09T09:24:00-CME-001", "startTime": "2024-05-09T09:24Z", "sourceLocation": "S20W25", "activeRegionNum": 13664, "note": "",
        "cmeAnalyses": [{"isMostAccurate": True, "speed": 1330.0}], "linkedEvents": [{"activityID": "2024-05-09T08:45:00-FLR-001"}, {"activityID": "2024-05-10T15:00:00-GST-001"}]},
       {"activityID": "2024-05-07T02:12:00-CME-001", "startTime": "2024-05-07T02:12Z", "cmeAnalyses": [], "linkedEvents": []}]
def found(storms=True, cmes=True):
    return {"storms": donki.parse_storms(GST) if storms else [], "cmes": donki.parse_cmes(CME) if cmes else [], "own_key": False, "storms_ok": storms, "cmes_ok": cmes, "complete": storms and cmes}


# NOAA's flare list as the page has it (class, peak and, in the details, the begin time that the IDs NASA links to carry)
FLARES = {"flares": [(T("2024-05-08 21:40"), "X1.0"), (T("2024-05-09 09:13"), "X2.2")],
          "flare_details": {T("2024-05-08 21:40"): {"begin": T("2024-05-08 21:08")}, T("2024-05-09 09:13"): {"begin": T("2024-05-09 08:45")}}}


def kp_series(**peaks):
    """Three-hour Kp steps from 8 May 2024 to 14 May: 2 everywhere except what is given as {'2024-05-10 15:00': 7.67, ...}."""
    base = {t: 2.0 for t in pd.date_range("2024-05-08", "2024-05-14", freq="3h")}
    base.update({T(k.replace("_", " ")): v for k, v in peaks.items()})
    return sorted(base.items())


class TheDonkiReader(unittest.TestCase):
    def setUp(self):
        donki._REFUSED = False
        patch = mock.patch.object(donki, "_setting", return_value="")                       # whatever key this computer has, a test starts without one
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(setattr, donki, "_REFUSED", False)

    def test_storms_and_ejections_are_read_with_their_links(self):
        storm = donki.parse_storms(GST)[0]
        self.assertEqual((storm["start"], storm["max_kp"], storm["max_time"]), (T("2024-05-10 15:00"), 9.0, T("2024-05-11 00:00")))
        self.assertEqual(len(storm["linked"]), 3)
        cmes = {c["id"]: c for c in donki.parse_cmes(CME)}
        fast = cmes["2024-05-08T22:24:00-CME-001"]
        self.assertEqual((fast["speed"], fast["region"], fast["arrivals"]), (1257.0, 13664, [T("2024-05-10 18:10")]))       # the analysis NASA marks most accurate
        self.assertEqual(cmes["2024-05-07T02:12:00-CME-001"]["speed"], None)                                              # one with no analysis still reads

    def test_an_activity_id_carries_its_time(self):
        self.assertEqual(donki.id_time("2024-05-10T16:36:00-IPS-001"), T("2024-05-10 16:36"))
        self.assertIsNone(donki.id_time("nonsense"))
        self.assertIsNone(donki.id_time(None))

    def reply(self, body, status=200):
        return mock.Mock(status_code=status, json=lambda: body, raise_for_status=lambda: None)

    def test_a_past_stretch_is_asked_for_once_and_kept(self):
        with mock.patch.object(donki.requests, "get", return_value=self.reply(GST)) as get, mock.patch("disk_cache.get_bytes", return_value=None), mock.patch("disk_cache.put_bytes") as put:
            raw = donki._fetch("GST", "2024-05-08", "2024-05-14")
        self.assertEqual(raw, GST)
        self.assertEqual(put.call_count, 1)
        params = get.call_args.kwargs["params"]
        self.assertEqual(sorted(params), ["api_key", "endDate", "startDate"])                                          # only dates and the key are sent
        self.assertEqual((params["startDate"], params["endDate"]), ("2024-05-08", "2024-05-14"))
        kept = json.dumps(GST).encode()
        with mock.patch.object(donki.requests, "get", side_effect=AssertionError("asked again")), mock.patch("disk_cache.get_bytes", return_value=kept):
            self.assertEqual(donki._fetch("GST", "2024-05-08", "2024-05-14"), GST)

    def test_a_limit_a_refused_key_or_a_failure_is_none_not_an_error(self):
        with mock.patch("disk_cache.get_bytes", return_value=None):
            for status in (429, 403, 401):
                with mock.patch.object(donki.requests, "get", return_value=self.reply([], status)):
                    self.assertIsNone(donki._fetch("GST", "2024-05-08", "2024-05-14"), status)
            with mock.patch.object(donki.requests, "get", side_effect=RuntimeError("down")):
                self.assertIsNone(donki._fetch("GST", "2024-05-08", "2024-05-14"))
            with mock.patch.object(donki.requests, "get", return_value=self.reply({"error": "x"})):
                self.assertIsNone(donki._fetch("GST", "2024-05-08", "2024-05-14"))

    def test_the_key_comes_from_the_settings_and_falls_back_to_the_shared_demo_key(self):
        self.assertEqual((donki.api_key(), donki.key_in_use()), ("DEMO_KEY", False))
        with mock.patch.object(donki, "_setting", return_value="abc123"):
            self.assertEqual((donki.api_key(), donki.key_in_use()), ("abc123", True))
            with mock.patch.object(donki.requests, "get", return_value=mock.Mock(status_code=403)), mock.patch("disk_cache.get_bytes", return_value=None):
                self.assertIsNone(donki._fetch("GST", "2024-05-08", "2024-05-14"))
            self.assertFalse(donki.key_in_use())                                                                     # a key NASA refuses is not counted as one

    def test_the_events_are_none_only_when_neither_storms_nor_ejections_can_be_read(self):
        def ask(kinds_ok):
            return lambda kind, a, b: {"GST": GST, "CME": CME}[kind] if kind in kinds_ok else None
        with mock.patch.object(donki, "_fetch", side_effect=ask(set())):
            self.assertIsNone(donki.events("2024-05-08", "2024-05-14"))
        with mock.patch.object(donki, "_fetch", side_effect=ask({"GST"})):
            partial = donki.events("2024-05-08", "2024-05-14")
        self.assertEqual((partial["storms_ok"], partial["cmes_ok"], partial["complete"]), (True, False, False))
        with mock.patch.object(donki, "_fetch", side_effect=ask({"GST", "CME"})) as fetch:
            whole = donki.events("2024-05-08", "2024-05-14")
        self.assertTrue(whole["complete"])
        self.assertEqual(fetch.call_args_list[1].args[1], T("2024-05-04"))                                                 # an ejection can leave days before the storm it causes


class TheStory(unittest.TestCase):
    def log(self, date="20240509", times=("1400", "1500")):
        return log_of(*[(date, t) for t in times])

    def test_the_window_is_three_days_before_and_two_after_and_never_too_long(self):
        a, b = st.window(self.log())
        self.assertEqual((a, b), (T("2024-05-06"), T("2024-05-12")))
        long_log = log_of(("20240501", "1000"), ("20240507", "1000"))
        a, b = st.window(long_log)
        self.assertLessEqual((b - a).days, st.MAX_DAYS)
        self.assertEqual(a, T("2024-04-29"))                                                                       # seven days of session leave room for two more, which go before it
        self.assertEqual(b, T("2024-05-08"))
        huge = st.window(log_of(("20240501", "1000"), ("20240515", "1000")))
        self.assertEqual(huge, (T("2024-05-01"), T("2024-05-16")))                                                  # a very long session is never cut, whatever the limit

    def test_a_storm_is_a_run_of_steps_at_kp_five_or_more(self):
        kp = kp_series(**{"2024-05-10_15:00": 7.67, "2024-05-10_18:00": 8.67, "2024-05-11_00:00": 9.0, "2024-05-12_21:00": 6.33})
        storms = st.kp_storms(kp)
        self.assertEqual([(s["start"], s["end"], s["peak_kp"], s["level"]) for s in storms],
                         [(T("2024-05-10 15:00"), T("2024-05-11 03:00"), 9.0, "G5"), (T("2024-05-12 21:00"), T("2024-05-13 00:00"), 6.33, "G2")])      # a dip of three hours inside a disturbance does not end it
        self.assertEqual([st.g_level(k) for k in (5.0, 6.0, 7.33, 8.0, 9.0)], ["G1", "G2", "G3", "G4", "G5"])
        self.assertEqual(st.kp_storms(kp_series()), [])

    def test_donki_links_a_storm_to_its_ejections_the_flare_and_the_shock(self):
        kp = kp_series(**{"2024-05-10_15:00": 7.67, "2024-05-10_18:00": 8.67, "2024-05-11_00:00": 9.0})
        story = st.build(self.log(), dict(FLARES, kp=kp), found())
        storm = story["storms"][0]
        self.assertEqual([c["id"][:16] for c in storm["cmes"]], ["2024-05-08T22:24", "2024-05-09T09:24"])
        self.assertEqual(storm["shock"], T("2024-05-10 16:36"))
        self.assertEqual(storm["flare"]["class"], "X2.2")
        self.assertEqual(story["donki_state"], "ok")
        text = " ".join(story["sentences"])
        for part in ("A geomagnetic storm began at 15:00 UTC on 10 May", "G5, extreme", "NASA's DONKI links it to 2 coronal mass ejections", "between 8 May and 9 May",
                     "from active region 13664", "about 1,330 km/s", "an X2.2 flare that peaked at 09:13 UTC", "reached Earth near 16:36 UTC on 10 May", "before the storm began"):
            self.assertIn(part, text)
        self.assertNotIn("caused", text)                                                                               # NASA's links are reported, no cause of our own is stated

    def test_where_the_session_fell_against_the_storm(self):
        kp = kp_series(**{"2024-05-10_15:00": 7.0, "2024-05-10_18:00": 8.0})
        before = " ".join(st.build(self.log("20240509"), {"kp": kp, "flares": []}, found())["sentences"])
        self.assertIn("Your last contact was about 24 hours before the storm began.", before)
        during = " ".join(st.build(self.log("20240510", ("1600", "1700")), {"kp": kp, "flares": []}, found())["sentences"])
        self.assertIn("You were on the air while the storm was under way: Kp was up to 7 during your session.", during)
        after = " ".join(st.build(self.log("20240511", ("1000", "1100")), {"kp": kp, "flares": []}, found())["sentences"])
        self.assertIn("Your first contact was about 13 hours after the storm ended.", after)

    def test_what_is_missing_from_nasa_is_said_and_never_filled_in(self):
        kp = kp_series(**{"2024-05-10_15:00": 7.0})
        history = {"kp": kp, "flares": []}
        none = st.build(self.log(), history, None)
        self.assertEqual(none["donki_state"], "unavailable")
        self.assertIn("What caused it could not be read from NASA's DONKI just now.", " ".join(none["sentences"]))
        partial = st.build(self.log(), history, found(cmes=False))
        self.assertIn("the ejections linked to it could not be read just now", " ".join(partial["sentences"]))
        self.assertNotIn("links no coronal mass ejection", " ".join(partial["sentences"]))                             # not reading the list is not the same as there being none
        unrecorded = dict(found(), storms=[])
        self.assertIn("has no record of this storm", " ".join(st.build(self.log(), history, unrecorded)["sentences"]))
        unlinked = dict(found(), cmes=[])
        self.assertIn("links no coronal mass ejection to it", " ".join(st.build(self.log(), history, unlinked)["sentences"]))
        self.assertIsNone(st.build(self.log(), {"kp": None, "flares": []}, found()))                                    # no Kp, no story

    def test_a_quiet_stretch_says_so_and_names_the_strongest_flare(self):
        story = st.build(self.log(), {"kp": kp_series(), "flares": [(T("2024-05-09 12:00"), "M2.1"), (T("2024-05-09 13:00"), "C5.0")]}, found())
        self.assertEqual(story["storms"], [])
        text = " ".join(story["sentences"])
        self.assertIn("There was no geomagnetic storm (Kp 5 or more) in these 6 days; Kp peaked at 2.", text)
        self.assertIn("the strongest was an M2.1, peaking at 12:00 UTC on 9 May (R1, minor", text)
        self.assertIn("could not be read for these days", " ".join(st.build(self.log(), {"kp": kp_series(), "flares": None}, found())["sentences"]))

    def test_nasa_is_asked_only_when_there_was_a_storm(self):
        self.assertFalse(st.needs_donki({"kp": kp_series()}, self.log()))
        self.assertTrue(st.needs_donki({"kp": kp_series(**{"2024-05-10_15:00": 7.0})}, self.log()))
        self.assertFalse(st.needs_donki({"kp": None}, self.log()))
        quiet = st.build(self.log(), {"kp": kp_series(), "flares": []}, None, asked=False)
        self.assertEqual(quiet["donki_state"], "not_needed")
        self.assertNotIn("DONKI", " ".join(quiet["sentences"]))                                                         # a quiet stretch says nothing about NASA

    def test_the_words_pass_the_wording_guard(self):
        kp = kp_series(**{"2024-05-10_15:00": 7.67, "2024-05-11_00:00": 9.0})
        for donki_found in (found(), None, found(cmes=False)):
            for sentence in st.build(self.log(), {"kp": kp, "flares": [(T("2024-05-09 09:13"), "X2.2")]}, donki_found)["sentences"]:
                self.assertEqual(lo.unsupported_claims(sentence), [], sentence)


class TheChart(unittest.TestCase):
    def html(self, donki_found, flares=None):
        log = log_of(("20240509", "1400"), ("20240509", "1500"))
        kp = kp_series(**{"2024-05-10_15:00": 7.67, "2024-05-10_18:00": 8.67, "2024-05-11_00:00": 9.0})
        history = {"kp": kp, "flux": [(T("2024-05-09"), 233.0)], "flares": flares if flares is not None else [(T("2024-05-09 09:13"), "X2.2"), (T("2024-05-09 17:44"), "X1.1")]}
        facts = ls.facts(log, history, (32.23, -101.49))
        return lsh.space_html(facts, {}, st.build(log, history, donki_found))

    def test_the_chart_shows_kp_flares_ejections_the_shock_and_the_session(self):
        html = self.html(found())
        for part in ("The days around your session", "Ejections from the Sun", "G5 storm · Kp 9", "shock reaches Earth 16:36", "fastest about 1,330 km/s", "Your session", "sw-sess"):
            self.assertIn(part, html)
        self.assertEqual(html.count('class="sw-arrow"'), 2)                                                              # one arrow from each linked ejection to the shock, once
        self.assertEqual(html.count('class="sw-cme"'), 2)
        self.assertIn("NASA links to a storm", html)
        self.assertIn("The story:</b> three days before your session to two days after", html)
        self.assertIn("shared demo key", html)                                                                           # with no key of its own the page says what limits it

    def test_a_quiet_stretch_has_no_ejection_row_and_says_why_nasa_was_not_asked(self):
        log = log_of(("20240509", "1400"))
        history = {"kp": kp_series(), "flux": [(T("2024-05-09"), 233.0)], "flares": []}
        html = lsh.space_html(ls.facts(log, history, (32.23, -101.49)), {}, st.build(log, history, None, asked=False))
        self.assertIn("The days around your session", html)
        self.assertNotIn("Ejections from the Sun", html)
        self.assertNotIn("Purple diamonds", html)
        self.assertIn("so NASA's DONKI was not asked for a cause", html)

    def test_what_could_not_be_read_is_said_on_the_chart(self):
        html = self.html(None)
        self.assertIn("Ejections could not be read from NASA's DONKI just now.", html)
        self.assertIn("could not be read just now, so the story says what the Kp shows and not why", html)
        self.assertNotIn('class="sw-arrow"', html)
        log = log_of(("20240509", "1400"), ("20240509", "1500"))
        history = {"kp": kp_series(**{"2024-05-10_15:00": 7.67}), "flux": [(T("2024-05-09"), 233.0)], "flares": None}
        self.assertIn("Flare data is not available for these days.", lsh.space_html(ls.facts(log, history, (32.23, -101.49)), {}, st.build(log, history, found())))

    def test_no_chart_without_kp_and_a_card_without_a_story_still_draws(self):
        log = log_of(("20240509", "1400"))
        facts = ls.facts(log, {"kp": [(T("2024-05-09 12:00"), 1.0)], "flux": [], "flares": []}, (32.23, -101.49))
        self.assertNotIn("The days around your session", lsh.space_html(facts, {}, None))
        self.assertIn("Space weather during your session", lsh.space_html(facts, {}, None))


if __name__ == "__main__":
    unittest.main()
