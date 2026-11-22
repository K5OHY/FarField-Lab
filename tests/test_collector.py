"""Checks of the live RBN collector (collector/rbn_service.py): reading the feed's lines, remembering what was collected and when, and answering
by callsign. No network: the feed is a small fake one on this computer.

    python -m unittest tests.test_collector -v
"""
import gzip
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "collector"))

import rbn_listen  # noqa: E402
import rbn_service as svc  # noqa: E402

LINES = [
    "DX de KM3T-#:    14033.0  K5OHY          CW    22 dB  24 WPM  CQ      1234Z",
    "DX de W3LPL-#:    7022.3  K3RA           CW    19 dB  30 WPM  CQ      1234Z",
    "DX de K5TR-1:    28217.6  WA1LAD/B       CW    11 dB  14 WPM  BEACON  1234Z",
    "DX de N8AI-#:    14070.2  W1AW           RTTY  14 dB  45 BPS  CQ      1234Z",
    "DX de OH6BG-#:   14100.0  DL0IGI         CW     9 dB  12 WPM  NCDXF B 1234Z",
    "DX de DK9IP-#:   14033.1  K5OHY          CW     7 dB  21 WPM  DX      1235Z",
]


class FakeFeed:
    """A stand-in for RBN's feed: asks for a callsign, then sends the spot lines, one cut in two as a network sometimes does."""

    def __init__(self, repeat=1):
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(2)
        self.port = self.srv.getsockname()[1]
        self.repeat, self.logins, self.drop_first = repeat, [], False
        self.connections = 0
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self.serve, args=(conn, self.connections), daemon=True).start()

    def serve(self, conn, number):
        try:
            conn.sendall(b"Please enter your call: ")
            got = b""
            while b"\n" not in got:
                got += conn.recv(100)
            self.logins.append(got.strip().decode())
            conn.sendall(b"Welcome\r\n\r\n")
            if self.drop_first and number == 1:
                time.sleep(0.3)
                conn.close()
                return
            for _ in range(self.repeat):
                for line in LINES:
                    conn.sendall((line + "\r\n").encode())
                half = LINES[0].encode()
                conn.sendall(half[:30])
                time.sleep(0.05)
                conn.sendall(half[30:] + b"\r\n")
            time.sleep(30)
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self.srv.close()


def get(url, headers=None):
    """(status, parsed JSON) for a web address, whether or not it answers with an error."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        with e:
            return e.code, json.loads(e.read())


class Lines(unittest.TestCase):
    def test_a_spot_line_is_read_into_its_parts(self):
        s = rbn_listen.parse(LINES[0])
        self.assertEqual((s["spotter"], s["freq"], s["dx"], s["mode"], s["snr"], s["speed"], s["kind"], s["hhmm"]), ("KM3T", 14033.0, "K5OHY", "CW", 22, 24, "CQ", "1234"))
        self.assertEqual(rbn_listen.parse(LINES[2])["spotter"], "K5TR-1")                  # a skimmer's own number stays, the feed's -# goes
        self.assertEqual(rbn_listen.parse(LINES[2])["dx"], "WA1LAD/B")
        self.assertEqual((rbn_listen.parse(LINES[3])["mode"], rbn_listen.parse(LINES[3])["speed"]), ("RTTY", 45))
        self.assertEqual(rbn_listen.parse(LINES[4])["kind"], "NCDXF B")
        self.assertEqual(rbn_listen.parse("DX de KM3T-#:   14033.0  K5OHY  CW  -3 dB  24 WPM  CQ  1234Z")["snr"], -3)

    def test_other_lines_are_not_spots(self):
        for text in ("Please enter your call:", "Welcome K5OHY", "", "DX de WEIRD:  something odd here", "WWV de VE7CC <18>: SFI=100"):
            self.assertIsNone(rbn_listen.parse(text), text)

    def test_bands(self):
        self.assertEqual([svc.band_of(f) for f in (14033.0, 7022.3, 1821.5, 28217.6, 99999)], ["20m", "40m", "160m", "10m", "unknown"])


class Coverage(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = svc.Store(os.path.join(self.dir.name, "s.db"))
        self.day = date(2026, 11, 22)
        self.start, self.end = svc.day_bounds(self.day)

    def tearDown(self):
        self.store.db.close()
        self.dir.cleanup()

    def sessions(self, *spans):
        for a, b in spans:
            self.store.db.execute("insert into sessions values (?,?)", (a, b))
        self.store.db.commit()

    def cover(self, now):
        db = self.store.reader()
        try:
            return svc.coverage(db, self.start, self.end, now)
        finally:
            db.close()

    def test_a_day_connected_from_its_first_second_has_nothing_to_report(self):
        self.sessions((self.start - 3600, self.start + 7200 + 5))
        self.assertEqual(self.cover(self.start + 7200 + 10), (True, None, []))

    def test_a_day_that_was_started_part_way_says_when_collecting_began(self):
        self.sessions((self.start + 3600 * 5, self.start + 3600 * 7))
        any_, began, gaps = self.cover(self.start + 3600 * 7 + 20)
        self.assertEqual((any_, began, gaps), (True, self.start + 3600 * 5, []))

    def test_a_break_is_a_gap_and_a_short_hiccup_is_not(self):
        self.sessions((self.start, self.start + 1000), (self.start + 1030, self.start + 5000), (self.start + 6000, self.start + 7000))
        any_, began, gaps = self.cover(self.start + 7010)
        self.assertEqual((began, gaps), (None, [(self.start + 5000, self.start + 6000)]))

    def test_a_collector_that_stopped_leaves_a_gap_up_to_now(self):
        self.sessions((self.start, self.start + 1000))
        _, _, gaps = self.cover(self.start + 4000)
        self.assertEqual(gaps, [(self.start + 1000, self.start + 4000)])

    def test_a_day_with_nothing_collected_says_so(self):
        self.sessions((self.start - 90000, self.start - 80000))
        self.assertEqual(self.cover(self.start + 100), (False, None, []))


class ServiceEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.feed = FakeFeed(repeat=3)
        cls.store = svc.Store(os.path.join(cls.dir.name, "s.db"))
        cls.collector = svc.Collector(cls.store, "K5OHY", "127.0.0.1", cls.feed.port)
        cls.collector.start()
        cls.server = svc.serve(cls.store, cls.collector, "127.0.0.1", 0, key=None, per_minute=1000)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        deadline = time.time() + 15
        while cls.collector.total < 3 * (len(LINES) + 1) and time.time() < deadline:
            time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.collector.stop.set()
        cls.server.shutdown()
        cls.server.server_close()
        cls.feed.close()
        time.sleep(0.3)
        cls.store.db.close()
        try:
            cls.dir.cleanup()
        except OSError:
            pass

    def test_it_logs_in_with_the_callsign_it_was_given_and_collects_every_spot(self):
        self.assertEqual(self.feed.logins[0], "K5OHY")
        self.assertEqual(self.collector.total, 3 * (len(LINES) + 1))               # three rounds, each with the cut-in-two line put back together
        self.assertTrue(self.collector.connected)

    def test_health_says_it_is_connected_and_how_much_it_holds(self):
        status, body = get(self.base + "/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"] and body["connected"])
        self.assertGreaterEqual(body["spots_held"], 3 * (len(LINES) + 1))

    def test_one_callsigns_spots_come_back_in_the_dailys_columns(self):
        status, body = get(self.base + "/spots?call=k5ohy")
        self.assertEqual(status, 200)
        self.assertEqual(body["columns"], ["callsign", "freq", "band", "dx", "mode", "db", "date", "speed", "tx_mode"])
        self.assertEqual(len(body["rows"]), 3 * 3)                                  # LINES[0] twice (the cut one too) and LINES[5], three rounds
        row = body["rows"][0]
        self.assertEqual((row[0], row[1], row[2], row[3], row[4], row[5], row[7], row[8]), ("KM3T", 14033.0, "20m", "K5OHY", "CQ", 22, 24, "CW"))
        self.assertEqual(body["date"], f"{datetime.now(timezone.utc):%Y-%m-%d}")
        self.assertTrue(body["covered"])
        self.assertEqual(get(self.base + "/spots?call=NOBODY")[1]["rows"], [])

    def test_a_portable_callsign_with_a_slash_is_asked_for_as_it_is(self):
        status, body = get(self.base + "/spots?call=WA1LAD/B")
        self.assertEqual((status, len(body["rows"])), (200, 3))

    def test_bad_requests_get_a_plain_answer(self):
        today = datetime.now(timezone.utc).date()
        self.assertEqual(get(self.base + "/spots")[0], 400)
        self.assertEqual(get(self.base + "/spots?call=K5OHY;drop")[0], 400)
        self.assertEqual(get(self.base + "/spots?call=K5OHY&date=banana")[0], 400)
        self.assertEqual(get(self.base + f"/spots?call=K5OHY&date={today - timedelta(days=5)}")[0], 400)
        self.assertEqual(get(self.base + f"/spots?call=K5OHY&date={today + timedelta(days=1)}")[0], 400)
        self.assertEqual(get(self.base + f"/spots?call=K5OHY&date={today - timedelta(days=1)}")[0], 200)   # yesterday is held too
        self.assertEqual(get(self.base + "/nothing")[0], 404)

    def test_a_long_answer_is_compressed_when_the_caller_accepts_it(self):
        self.store.add([(svc.utc_now(), "S%d" % i, 14033.0, "20m", "BIG", "CQ", 10, 20, "CW") for i in range(400)])
        req = urllib.request.Request(self.base + "/spots?call=BIG", headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertEqual(r.headers["Content-Encoding"], "gzip")
            self.assertEqual(len(json.loads(gzip.decompress(r.read()))["rows"]), 400)


class KeyAndLimit(unittest.TestCase):
    def test_a_key_is_needed_when_one_is_set_and_callers_are_limited(self):
        with tempfile.TemporaryDirectory() as folder:
            store = svc.Store(os.path.join(folder, "s.db"))

            class Idle:
                connected, total, reconnects, started, last_error = False, 0, 0, svc.utc_now(), ""

            server = svc.serve(store, Idle(), "127.0.0.1", 0, key="secret", per_minute=3)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                self.assertEqual(get(base + "/spots?call=K5OHY")[0], 401)
                self.assertEqual(get(base + "/spots?call=K5OHY", {"X-Api-Key": "wrong"})[0], 401)
                self.assertEqual(get(base + "/health")[0], 200)                       # health needs no key
                codes = [get(base + "/spots?call=K5OHY", {"X-Api-Key": "secret"})[0] for _ in range(5)]
                self.assertEqual(codes, [200, 200, 200, 429, 429])
            finally:
                server.shutdown()
                server.server_close()
                store.db.close()


class Reconnect(unittest.TestCase):
    def test_a_dropped_connection_is_picked_up_again_and_leaves_a_gap_record(self):
        with tempfile.TemporaryDirectory() as folder:
            feed = FakeFeed(repeat=1)
            feed.drop_first = True
            store = svc.Store(os.path.join(folder, "s.db"))
            collector = svc.Collector(store, "K5OHY", "127.0.0.1", feed.port)
            orig = collector.stop.wait
            collector.stop.wait = lambda seconds: orig(0.2)                            # do not wait the real 5 seconds in a test
            collector.start()
            try:
                deadline = time.time() + 15
                while collector.total < len(LINES) + 1 and time.time() < deadline:
                    time.sleep(0.1)
                self.assertEqual(collector.total, len(LINES) + 1)
                self.assertGreaterEqual(collector.reconnects, 1)
                self.assertEqual(len(feed.logins), 2)
                self.assertEqual(store.db.execute("select count(*) from sessions").fetchone()[0], 2)
            finally:
                collector.stop.set()
                feed.close()
                time.sleep(0.3)
                store.db.close()


if __name__ == "__main__":
    unittest.main()
