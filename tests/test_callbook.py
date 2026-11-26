"""Stations outside North America with no grid in the log: placed by their call area (or their HamQTH home when the app has a key), not at the centre of the country.
Nothing here uses the network: HamQTH's answers are stood in for."""
import os
import tempfile
import unittest
from unittest import mock

import pandas as pd

import callbook as cb
import data_sources as ds
import log_check as lc
import share_card as sc

HOME = (31.0, -102.0)


def log_of(*records):
    return lc.parse_adif("<ADIF_VER:5>3.1.4 <EOH>\n" + "\n".join(records) + "\n")


def rec(call, hhmm="2010", band="20m", **fields):
    extra = "".join(f"<{k.upper()}:{len(str(v))}>{v} " for k, v in fields.items())
    return f"<CALL:{len(call)}>{call} <QSO_DATE:8>20261118 <TIME_ON:4>{hhmm} <BAND:{len(band)}>{band} <MODE:2>CW {extra}<EOR>"


AREAS = {"JA1ABC": ("Japan (Kanto)", 35.7, 139.8), "JH3EUJ": ("Japan (Kinki)", 35.01, 135.77), "JA7XYZ": ("Japan (Tohoku)", 40.82, 140.74)}


class FakeHamQTH:
    """Stands in for requests.get: records every call made and answers like the service does."""

    def __init__(self, key_ok=True):
        self.calls, self.key_ok = [], key_ok

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        resp = mock.Mock()
        resp.content = b"x"
        call = (params or {}).get("callsign") or url.rsplit("/", 1)[-1]
        if "/dxcc" in url:
            area = AREAS.get(call)
            resp.status_code = 200 if area else 404
            resp.json.return_value = {"details": f"{area[0]}, Class A", "lat": area[1], "lon": area[2], "entity": {"name": "Japan", "lat": 35.7, "lon": 139.8}} if area else {}
        else:
            if not self.key_ok:
                resp.status_code, resp.json.return_value = 401, {}
            else:
                resp.status_code = 200
                resp.json.return_value = {"location": {"lat": 34.7, "lon": 135.5, "grid": "PM74QR"}}
        return resp


class TheLookup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"RBN_CACHE_DIR": self.tmp.name}, clear=False)
        self.env.start()
        os.environ.pop("HAMQTH_API_KEY", None)
        self.no_file = mock.patch.object(cb, "_setting", lambda name: os.environ.get(name, ""))     # a key in this computer's own secrets file is not the test's business
        self.no_file.start()
        cb._RECENT.clear()
        cb._KEY_REFUSED = False

    def tearDown(self):
        self.no_file.stop()
        self.env.stop()
        self.tmp.cleanup()
        cb._KEY_REFUSED = False

    def test_only_callsigns_are_ever_sent(self):
        for good in ("JA1ABC", "9A1A", "W1AW/P", "EA8/DF4UE", "KH6/K5OHY"):
            self.assertTrue(cb.plausible(good), good)
        for bad in ("", "x", "a b", "DROP TABLE", "JA1ABC?x=1", "../etc"):
            self.assertFalse(cb.plausible(bad), bad)

    def test_without_a_key_a_station_is_placed_by_its_call_area(self):
        fake = FakeHamQTH()
        with mock.patch("callbook.requests.get", fake):
            got = cb.locate("JH3EUJ")
        self.assertEqual((got["source"], got["where"]), ("area", "Japan (Kinki)"))
        self.assertAlmostEqual(got["lon"], 135.77)
        self.assertTrue(all("/dxcc" in c[0] for c in fake.calls), "the callbook is not asked without a key")
        self.assertTrue(all("Authorization" not in c[2] for c in fake.calls))

    def test_only_the_country_and_region_are_kept_never_a_name_or_a_licence_class(self):
        for details, kept in (("Czech Republic, Petr, Author of the CQRLOG", "Czech Republic"), ("Brazil, Pernambuco (PE), Class A and B", "Brazil, Pernambuco (PE)"),
                              ("Federal Republic of Germany, Full License", "Federal Republic of Germany"), ("Japan (Kinki), Class A", "Japan (Kinki)")):
            resp = mock.Mock(status_code=200, content=b"x")
            resp.json.return_value = {"details": details, "lat": 1.0, "lon": 2.0}
            with mock.patch("callbook.requests.get", return_value=resp):
                self.assertEqual(cb.area_of("DL1ABC")["where"], kept, details)

    def test_an_answer_is_kept_so_a_call_is_asked_once(self):
        fake = FakeHamQTH()
        with mock.patch("callbook.requests.get", fake):
            cb.locate("JA1ABC")
            cb._RECENT.clear()
            cb.locate("JA1ABC")
        self.assertEqual(len(fake.calls), 1)

    def test_a_call_that_is_not_found_is_left_out_and_nothing_raises(self):
        with mock.patch("callbook.requests.get", FakeHamQTH()):
            self.assertEqual(cb.load_places(["JA1ABC", "ZZ9ZZZ"]).keys(), {"JA1ABC"})
        with mock.patch("callbook.requests.get", side_effect=cb.requests.ConnectionError("down")):
            cb._RECENT.clear()
            self.assertEqual(cb.load_places(["JH3EUJ"]), {})

    def test_with_a_key_the_callbook_home_is_used_and_the_key_stays_in_the_header(self):
        fake = FakeHamQTH()
        with mock.patch.dict(os.environ, {"HAMQTH_API_KEY": "hqk_secretvalue"}), mock.patch("callbook.requests.get", fake):
            got = cb.locate("JA1ABC")
        self.assertEqual((got["source"], got["where"]), ("home", "PM74QR"))
        url, params, headers = fake.calls[0]
        self.assertEqual(headers["Authorization"], "Bearer hqk_secretvalue")
        self.assertNotIn("hqk_secretvalue", url + str(params))                                        # never in an address

    def test_a_portable_callsign_is_placed_by_its_area_not_by_a_home_record(self):
        fake = FakeHamQTH()
        with mock.patch.dict(os.environ, {"HAMQTH_API_KEY": "hqk_x"}), mock.patch("callbook.requests.get", fake):
            cb.locate("EA8/DF4UE")
        self.assertTrue(all("/callbook/" not in c[0] for c in fake.calls))

    def test_a_refused_key_is_not_tried_again_and_the_area_is_used(self):
        fake = FakeHamQTH(key_ok=False)
        with mock.patch.dict(os.environ, {"HAMQTH_API_KEY": "hqk_bad"}), mock.patch("callbook.requests.get", fake):
            first = cb.locate("JA1ABC")
            cb._RECENT.clear()
            second = cb.locate("JH3EUJ")
            self.assertFalse(cb.key_in_use())
        self.assertEqual((first["source"], second["source"]), ("area", "area"))
        self.assertEqual(sum("/callbook/" in c[0] for c in fake.calls), 1)                            # asked once, then left alone

    def test_the_secret_is_never_part_of_what_a_lookup_returns(self):
        with mock.patch.dict(os.environ, {"HAMQTH_API_KEY": "hqk_secretvalue"}), mock.patch("callbook.requests.get", FakeHamQTH()):
            got = cb.load_places(["JA1ABC"])
        self.assertNotIn("hqk_secretvalue", repr(got))


class ThePlacement(unittest.TestCase):
    def setUp(self):
        self.log = log_of(rec("JA1ABC"), rec("JH3EUJ", "2011"), rec("DL1GRID", "2012", gridsquare="JN58"), rec("W1STATE", "2013", state="PA"), rec("HA1CTRY", "2014"))

    def test_only_stations_that_need_a_lookup_are_listed(self):
        self.assertEqual(lc.contact_dx_calls(self.log), ["HA1CTRY", "JA1ABC", "JH3EUJ"])            # a grid, or North America, needs none

    def test_a_station_is_placed_by_its_area_and_the_country_centre_is_the_fallback(self):
        before = lc.contact_places(self.log, HOME).set_index("call")
        self.assertEqual(before.loc["JA1ABC", "c_source"], "country")
        self.log.attrs["call_places"] = {c: {"lat": a[1], "lon": a[2], "source": "area", "where": a[0]} for c, a in AREAS.items()}
        after = lc.contact_places(self.log, HOME).set_index("call")
        self.assertEqual((after.loc["JA1ABC", "c_source"], after.loc["JH3EUJ", "c_source"]), ("area", "area"))
        self.assertNotAlmostEqual(after.loc["JA1ABC", "c_lon"], after.loc["JH3EUJ", "c_lon"], places=1)       # not one point for the whole country
        self.assertEqual(after.loc["HA1CTRY", "c_source"], "country")                                 # nobody knew this one
        self.assertEqual(after.loc["DL1GRID", "c_source"], "grid")

    def test_a_grid_in_the_log_still_wins_over_a_lookup(self):
        log = log_of(rec("JA1ABC", gridsquare="PM95"))
        log.attrs["call_places"] = {"JA1ABC": {"lat": 10.0, "lon": 10.0, "source": "area", "where": ""}}
        self.assertEqual(lc.contact_places(log, HOME).iloc[0]["c_source"], "grid")

    def test_a_home_is_shown_only_as_the_centre_of_its_four_character_grid(self):
        log = log_of(rec("JA1ABC"))
        log.attrs["call_places"] = {"JA1ABC": {"lat": 34.7, "lon": 135.5, "source": "home", "where": "PM74QR"}}
        row = lc.contact_places(log, HOME).iloc[0]
        self.assertEqual(row["c_source"], "home")
        self.assertFalse(row["c_approx"])
        self.assertEqual((row["c_lat"], row["c_lon"]), (34.5, 135.0))                                # PM74 is 34-35 N, 134-136 E: its centre, never a street

    def test_an_area_is_rough_and_a_home_is_not_when_the_farthest_contact_is_chosen(self):
        self.assertNotIn("area", lc.PRECISE_SOURCES)
        self.assertIn("home", lc.PRECISE_SOURCES)

    def test_a_far_area_counts_in_a_sector_and_a_near_one_does_not(self):
        log = log_of(rec("JA1ABC"), rec("XE1ABC", "2011"))
        log.attrs["call_places"] = {"JA1ABC": {"lat": 35.7, "lon": 139.8, "source": "area", "where": ""}, "XE1ABC": {"lat": 19.4, "lon": -99.1, "source": "area", "where": ""}}
        rows = lc.contact_places(log, HOME).set_index("call")
        self.assertEqual(rows.loc["JA1ABC", "sector_basis"], "area")
        self.assertTrue(pd.isna(rows.loc["XE1ABC", "sector_whole"]))                                         # about 1,500 km: a region's centre could be in another sector

    def test_the_page_says_how_each_was_placed(self):
        import log_openings as lo
        with open(lo.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"area": "its call area"', src)
        self.assertIn('"home": "its station profile"', src)


class TheMaps(unittest.TestCase):
    def test_the_map_pipeline_uses_the_same_lookup(self):
        dx = {"JH3EUJ": {"lat": 35.01, "lon": 135.77, "source": "area", "where": "Japan (Kinki)"}, "JA1ABC": {"lat": 34.7, "lon": 135.5, "source": "home", "where": "PM74QR"}}
        out = ds.load_contact_places([("JH3EUJ", "", "Japan"), ("JA1ABC", "", "Japan"), ("HA1AB", "", "Hungary")], {}, dx_places=dx)
        self.assertEqual(out.loc["JH3EUJ", "level"], "area")
        self.assertIn("Kinki", out.loc["JH3EUJ", "source"])
        self.assertEqual(out.loc["JA1ABC", "level"], "grid")                                          # a home is drawn as its grid square, as every other home is
        self.assertEqual(out.loc["HA1AB", "level"], "country")                                        # no lookup answer: the country's centre, as before
        self.assertIn("call area", lc.place_note("area", "HamQTH call area, Japan (Kinki)"))

    def test_without_any_lookup_nothing_changes(self):
        out = ds.load_contact_places([("JH3EUJ", "", "Japan")], {})
        self.assertEqual(out.loc["JH3EUJ", "level"], "country")


class TheShareCardMap(unittest.TestCase):
    def facts(self):
        calls = ["JA1ABC", "JH3EUJ", "JA7XYZ"]
        log = log_of(*[rec(c, f"20{i:02d}") for i, c in enumerate(calls)])
        log.attrs["call_places"] = {c: {"lat": a[1], "lon": a[2], "source": "area", "where": a[0]} for c, a in AREAS.items()}
        return sc.map_facts(lc.contact_places(log, HOME), HOME)

    def test_each_place_says_how_many_stations_are_there(self):
        m = self.facts()
        self.assertEqual(sorted(p["stations"] for p in m["points"]), [1, 1, 1])                       # three places, one station each
        self.assertEqual(sum(p["stations"] for p in m["points"]), 3)

    def test_the_map_has_no_country_names_but_still_draws_each_station(self):
        m = self.facts()
        for p in m["points"]:
            p["country"] = "Japan"
        import io
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.figure import Figure
        fig = Figure(figsize=sc.SIZE)
        ax = sc._draw_world(fig, m)
        self.assertEqual([t.get_text() for t in ax.texts], [])                                    # no names over the paths and diamonds
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        self.assertGreater(len(buf.getvalue()), 1000)

    def test_a_few_stations_at_one_place_are_fanned_out_one_diamond_each(self):
        m = self.facts()
        place = {"bands": ["15m", "20m"], "band_n": {"15m": 4, "20m": 1}, "band_calls": {"15m": {"JA1ABC": 2, "JA1XYZ": 1, "JA1QRP": 1}, "20m": {"JA1ABC": 1}}}
        self.assertEqual(sc._fan(place), [("15m", 2), ("15m", 1), ("15m", 1), ("20m", 1)])                 # four stations on bands, four diamonds
        crowd = {"bands": ["20m"], "band_n": {"20m": 90}, "band_calls": {"20m": {f"W{i}AA": 1 for i in range(sc.FAN_MAX + 1)}}}
        self.assertEqual(sc._fan(crowd), [("20m", 90)])                                                  # too many (a state's centre): one for the band, as before
        self.assertEqual(sc._fan({"bands": ["20m"], "band_n": {"20m": 3}, "band_calls": {"20m": {"JA1ABC": 3}}}), [("20m", 3)])
        self.assertEqual(sum(len(p["band_calls"]) for p in m["points"]), 3)

    def test_the_diamonds_are_smaller_and_each_station_of_a_fan_is_drawn(self):
        m = self.facts()
        for p in m["points"]:
            p["country"] = "Japan"
        from matplotlib.figure import Figure
        ax = sc._draw_world(Figure(figsize=sc.SIZE), m)
        sizes = [float(s) for c in ax.collections for s in c.get_sizes()]
        self.assertEqual(sorted(sizes)[:3], [32.0, 32.0, 32.0], sizes)                                    # three diamonds of one contact each (the star and its glow are larger)


if __name__ == "__main__":
    unittest.main()
