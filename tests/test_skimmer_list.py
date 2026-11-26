"""The skimmer list: RBN's own node list, with HamQTH's copy of it as a second source, so a skimmer added since the saved list was made is still placed when RBN's page cannot be
read. Nothing here uses the network or the real list file."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

import rbn_data as rd


def hamqth_answer(n=60, extra=None):
    skimmers = [{"node": f"K{i:02d}ABC", "call": f"K{i:02d}ABC", "grid": "EM10", "lastSeen": "2026-11-26T04:30:00Z"} for i in range(n)]
    skimmers += extra or []
    resp = mock.Mock(status_code=200)
    resp.raise_for_status = lambda: None
    resp.json.return_value = {"updated": "2026-11-26T04:30:00Z", "skimmers": skimmers}
    return resp


NEW = [{"node": "K3FEF", "call": "K3FEF", "grid": "FN21MH", "lastSeen": "2026-11-26T04:30:00Z"}, {"node": "K1HTV-4", "call": "K1HTV", "grid": "FM18AP", "lastSeen": "2026-11-26T04:30:00Z"},
       {"node": "BADGRID", "call": "BADGRID", "grid": "zz", "lastSeen": "2026-11-26T04:30:00Z"}]


class TheHamQthList(unittest.TestCase):
    def test_it_is_read_as_callsign_and_place_and_a_bad_grid_is_left_out(self):
        with mock.patch.object(rd.requests, "get", return_value=hamqth_answer(extra=NEW)):
            df = rd.fetch_hamqth_skimmers()
        self.assertEqual(list(df.columns), ["callsign", "latitude", "longitude"])
        got = df.set_index("callsign")
        self.assertIn("K3FEF", got.index)
        self.assertIn("K1HTV-4", got.index)                                                        # a node keeps its number
        self.assertNotIn("BADGRID", got.index)
        self.assertAlmostEqual(got.loc["K3FEF", "latitude"], 41.3125, places=3)                    # the centre of FN21MH

    def test_a_list_that_is_far_too_short_is_not_trusted(self):
        with mock.patch.object(rd.requests, "get", return_value=hamqth_answer(n=3)):
            with self.assertRaises(RuntimeError):
                rd.fetch_hamqth_skimmers()

    def test_only_the_list_is_asked_for_with_a_named_client(self):
        with mock.patch.object(rd.requests, "get", return_value=hamqth_answer()) as get:
            rd.fetch_hamqth_skimmers()
        url = get.call_args[0][0]
        self.assertEqual(url, "https://www.hamqth.com/api/v2/rbn/skimmers")
        self.assertIn("FarField-Lab", get.call_args[1]["headers"]["User-Agent"])


class TheRefresh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.cache, self.marker = base / "spotter_coords.csv", base / ".refreshed"
        pd.DataFrame([("W1OLD", 40.0, -75.0)], columns=["callsign", "latitude", "longitude"]).to_csv(self.cache, index=False)
        self.patches = [mock.patch.object(rd, "CACHE_FILE", self.cache), mock.patch.object(rd, "REFRESH_MARKER", self.marker)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def rbn(self, **rows):
        return pd.DataFrame([(k, lat, lon) for k, (lat, lon) in rows.items()], columns=["callsign", "latitude", "longitude"])

    def test_when_rbns_page_cannot_be_read_hamqths_list_fills_in_the_new_skimmers(self):
        with mock.patch.object(rd, "fetch_skimmers", side_effect=RuntimeError("blocked")), mock.patch.object(rd.requests, "get", return_value=hamqth_answer(extra=NEW)):
            ok, msg = rd.refresh_skimmer_cache(force=True)
        self.assertTrue(ok)
        self.assertIn("RBN: blocked", msg)
        locs = rd.load_skimmers()
        self.assertIn("K3FEF", locs)
        self.assertIn("K1HTV-4", locs)
        self.assertIn("W1OLD", locs)                                                               # a skimmer that dropped off is still kept
        self.assertTrue(self.marker.exists())

    def test_rbns_own_place_wins_when_both_have_a_skimmer(self):
        with mock.patch.object(rd, "fetch_skimmers", return_value=self.rbn(K3FEF=(10.0, 20.0))), mock.patch.object(rd.requests, "get", return_value=hamqth_answer(extra=NEW)):
            rd.refresh_skimmer_cache(force=True)
        locs = rd.load_skimmers()
        self.assertEqual(tuple(locs["K3FEF"]), (10.0, 20.0))                                       # RBN's, not HamQTH's FN21MH
        self.assertIn("K1HTV-4", locs)                                                             # only HamQTH had this one

    def test_if_neither_can_be_read_the_saved_list_stays_and_nothing_raises(self):
        with mock.patch.object(rd, "fetch_skimmers", side_effect=RuntimeError("blocked")), mock.patch.object(rd.requests, "get", side_effect=rd.requests.ConnectionError("down")):
            ok, msg = rd.refresh_skimmer_cache(force=True)
        self.assertFalse(ok)
        self.assertIn("using cached copy", msg)
        self.assertEqual(list(rd.load_skimmers()), ["W1OLD"])
        self.assertFalse(self.marker.exists())                                                     # so it is tried again next time

    def test_a_fresh_stamp_over_a_list_that_has_been_put_back_does_not_count_as_up_to_date(self):
        """The hosted app's trap: a redeploy puts the saved list back while the stamp (ignored by git) stays, so 'refreshed an hour ago' sat over a September list."""
        with mock.patch.object(rd, "fetch_skimmers", return_value=self.rbn(K3FEF=(10.0, 20.0))), mock.patch.object(rd.requests, "get", side_effect=rd.requests.ConnectionError("down")):
            self.assertTrue(rd.refresh_skimmer_cache(force=True)[0])
            ok, msg = rd.refresh_skimmer_cache()                                                   # straight after: genuinely fresh, nothing is fetched
            self.assertFalse(ok)
            self.assertIn("up to date", msg)
        pd.DataFrame([("W1OLD", 40.0, -75.0)], columns=["callsign", "latitude", "longitude"]).to_csv(self.cache, index=False)      # the old saved copy comes back; the stamp stays
        self.assertTrue(self.marker.exists())
        with mock.patch.object(rd, "fetch_skimmers", return_value=self.rbn(K3FEF=(10.0, 20.0), N3VLF=(30.0, 40.0))) as fetch,                 mock.patch.object(rd.requests, "get", side_effect=rd.requests.ConnectionError("down")):
            ok, msg = rd.refresh_skimmer_cache()
        fetch.assert_called_once()                                                                 # so it refreshes instead of trusting the stamp
        self.assertTrue(ok)
        self.assertIn("N3VLF", rd.load_skimmers())

    def test_a_stamp_written_before_it_carried_a_fingerprint_is_refreshed_once(self):
        self.marker.touch()                                                                        # the old kind: empty
        with mock.patch.object(rd, "fetch_skimmers", return_value=self.rbn(K3FEF=(10.0, 20.0))) as fetch, mock.patch.object(rd.requests, "get", side_effect=rd.requests.ConnectionError("down")):
            ok, _ = rd.refresh_skimmer_cache()
        fetch.assert_called_once()
        self.assertTrue(ok)
        self.assertNotEqual(self.marker.read_text().strip(), "")                                   # and the stamp now has one

    def test_a_skimmer_that_was_missing_is_placed_afterwards_by_the_pages_own_lookup(self):
        from compare_stats import locate
        with mock.patch.object(rd, "fetch_skimmers", side_effect=RuntimeError("blocked")), mock.patch.object(rd.requests, "get", return_value=hamqth_answer(extra=NEW)):
            rd.refresh_skimmer_cache(force=True)
        locs = rd.load_skimmers()
        self.assertIsNotNone(locate("K3FEF", locs))
        self.assertIsNotNone(locate("K1HTV-4", locs))
        self.assertIsNone(locate("ZZ9ZZZ", locs))


if __name__ == "__main__":
    unittest.main()
