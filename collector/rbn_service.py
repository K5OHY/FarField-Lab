"""The live RBN collector: listens to the Reverse Beacon Network's live feed all day, keeps the last two days of spots in a small database,
and answers one question over the web: "the spots of this callsign on this day". FarField Lab uses it for today, which RBN's daily file
does not cover until the UTC day is over.

It is one program with no extra packages (Python 3.9 or newer). It is meant to run all the time on a small always-on machine; see
collector/SETUP.md.

    python collector/rbn_service.py --call YOURCALL --db spots.db --port 8080

The feed asks for a callsign when you connect, so --call is the callsign to log in with.

Web addresses (JSON):
    GET /health                           is it connected, the newest spot, how many spots are held
    GET /spots?call=K5OHY&date=2026-11-22   the spots of that callsign on that UTC day (today or yesterday only), with which part of the
                                          day was actually collected, so the app can say when spots may be missing
If RBN_SERVICE_KEY is set, /spots needs the same value in an X-Api-Key header.
"""
import argparse
import gzip
import json
import os
import re
import socket
import sqlite3
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rbn_listen import HOST, PORTS, parse  # noqa: E402

COLUMNS = ["callsign", "freq", "band", "dx", "mode", "db", "date", "speed", "tx_mode"]     # the same names as RBN's daily file
BANDS = [("160m", 1800, 2000), ("80m", 3500, 4000), ("60m", 5300, 5500), ("40m", 7000, 7300), ("30m", 10100, 10150), ("20m", 14000, 14350),
         ("17m", 18068, 18168), ("15m", 21000, 21450), ("12m", 24890, 24990), ("10m", 28000, 29700), ("6m", 50000, 54000)]
KEEP_HOURS = 48
HEARTBEAT = 15            # seconds between "still connected" marks, which is how the gaps are found
GAP_SECONDS = 90          # a break shorter than this is not reported as a gap
IDLE_LIMIT = 180          # seconds with nothing from the feed before it is treated as dead and reconnected
MAX_ROWS = 100_000
CALL_RE = re.compile(r"^[A-Z0-9]{1,4}(/[A-Z0-9]{1,4})?[A-Z0-9]*(/[A-Z0-9]{1,4})?$")
CACHE_SECONDS = 20


def band_of(freq):
    for name, lo, hi in BANDS:
        if lo <= freq <= hi:
            return name
    return "unknown"


def utc_now():
    return int(time.time())


def stamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def day_bounds(day):
    """The first second of a UTC day and the first second after it, as epoch seconds."""
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


class Store:
    """The spots and the record of when the collector was connected. One writer (the collector); readers open their own connection."""

    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.Lock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.db.execute("pragma journal_mode=wal")
        self.db.execute("pragma synchronous=normal")
        self.db.execute("create table if not exists spots (ts integer, spotter text, freq real, band text, dx text, kind text, snr integer, speed integer, mode text)")
        self.db.execute("create index if not exists spots_dx on spots (dx, ts)")
        self.db.execute("create index if not exists spots_ts on spots (ts)")
        self.db.execute("create table if not exists sessions (start integer, end integer)")
        self.db.commit()

    def add(self, rows):
        if rows:
            with self.lock:
                self.db.executemany("insert into spots values (?,?,?,?,?,?,?,?,?)", rows)
                self.db.commit()

    def open_session(self):
        with self.lock:
            cur = self.db.execute("insert into sessions values (?, ?)", (utc_now(), utc_now()))
            self.db.commit()
            return cur.lastrowid

    def beat(self, session):
        with self.lock:
            self.db.execute("update sessions set end=? where rowid=?", (utc_now(), session))
            self.db.commit()

    def prune(self, keep_hours=KEEP_HOURS):
        cut = utc_now() - keep_hours * 3600
        with self.lock:
            self.db.execute("delete from spots where ts < ?", (cut,))
            self.db.execute("delete from sessions where end < ?", (cut,))
            self.db.commit()

    def reader(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = None
        return db


class Collector(threading.Thread):
    """Holds the connection to the live feed, reconnecting when it drops, and writes what arrives."""

    def __init__(self, store, call, host=HOST, port=PORTS["cw"]):
        super().__init__(daemon=True, name="collector")
        self.store, self.call, self.host, self.port = store, call, host, port
        self.stop = threading.Event()
        self.connected, self.reconnects, self.total = False, 0, 0
        self.started, self.last_spot, self.last_error = utc_now(), None, ""

    def log(self, text):
        print(f"{stamp(utc_now())}Z {text}", flush=True)

    def run(self):
        wait = 5
        while not self.stop.is_set():
            try:
                self.session()
                wait = 5
            except Exception as exc:                                  # a dropped connection, a refused one, a timeout: try again
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.log(f"feed problem: {self.last_error}")
            self.connected = False
            if self.stop.wait(wait):
                break
            self.reconnects += 1
            wait = min(wait * 2, 120)

    def session(self):
        sock = socket.create_connection((self.host, self.port), timeout=30)
        sock.settimeout(1)                                           # wake once a second to save what has arrived and to notice a silent feed
        try:
            seen = b""
            while b"call" not in seen.lower():
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("the feed closed before asking for a callsign")
                seen += chunk
                if len(seen) > 20000:
                    break
            sock.sendall(self.call.encode() + b"\r\n")
            session = self.store.open_session()
            self.connected = True
            self.log(f"connected to {self.host}:{self.port}")
            pending, batch = b"", []
            last_data = last_beat = last_flush = last_prune = time.time()
            while not self.stop.is_set():
                try:
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise ConnectionError("the feed closed the connection")
                    last_data = time.time()
                    pending += chunk
                except socket.timeout:
                    chunk = b""
                if time.time() - last_data > IDLE_LIMIT:
                    raise TimeoutError(f"nothing from the feed for {IDLE_LIMIT} seconds")
                *lines, pending = pending.split(b"\n")
                got = utc_now()
                for raw in lines:
                    spot = parse(raw.decode("ascii", "replace"))
                    if spot:
                        batch.append((got, spot["spotter"], spot["freq"], band_of(spot["freq"]), spot["dx"], spot["kind"], spot["snr"], spot["speed"], spot["mode"]))
                now = time.time()
                if batch and now - last_flush >= 1:
                    self.store.add(batch)
                    self.total += len(batch)
                    self.last_spot = got
                    batch, last_flush = [], now
                if now - last_beat >= HEARTBEAT:
                    self.store.beat(session)
                    last_beat = now
                if now - last_prune >= 3600:
                    self.store.prune()
                    last_prune = now
            self.store.add(batch)
            self.store.beat(session)
        finally:
            self.connected = False
            sock.close()


def coverage(db, day_start, day_end, now):
    """What part of a UTC day the collector was connected for: (anything collected that day at all, the time it began collecting that day, the
    gaps after that). A day that was collected from its first second has no start to report."""
    cap = min(now, day_end)
    segments = [(max(s, day_start), min(e, cap)) for s, e in
                db.execute("select start, end from sessions where end >= ? and start <= ? order by start", (day_start, day_end)) if min(e, cap) >= max(s, day_start)]
    if not segments:
        return False, None, []
    gaps = [(a[1], b[0]) for a, b in zip(segments, segments[1:]) if b[0] - a[1] > GAP_SECONDS]
    if cap - segments[-1][1] > GAP_SECONDS:
        gaps.append((segments[-1][1], cap))
    first = segments[0][0]
    return True, (None if first - day_start <= GAP_SECONDS else first), gaps


def spots_answer(store, call, day, now=None):
    """The JSON-ready answer for one callsign on one UTC day."""
    now = now or utc_now()
    start, end = day_bounds(day)
    db = store.reader()
    try:
        rows = db.execute("select ts, spotter, freq, band, dx, kind, snr, speed, mode from spots where dx = ? and ts >= ? and ts < ? order by ts limit ?",
                          (call, start, end, MAX_ROWS)).fetchall()
        newest = db.execute("select max(ts) from spots").fetchone()[0]
        any_collected, began, gaps = coverage(db, start, end, now)
    finally:
        db.close()
    return {"call": call, "date": f"{day:%Y-%m-%d}", "columns": COLUMNS,
            "rows": [[spotter, freq, band, dx, kind, snr, stamp(ts), speed, mode] for ts, spotter, freq, band, dx, kind, snr, speed, mode in rows],
            "collected_from": stamp(began) if began else None, "gaps": [[stamp(a), stamp(b)] for a, b in gaps],
            "covered": any_collected,
            "newest_spot": stamp(newest) if newest else None, "now": stamp(now)}


class RateLimit:
    def __init__(self, per_minute):
        self.per_minute, self.hits, self.lock = per_minute, defaultdict(deque), threading.Lock()

    def allow(self, who):
        now = time.time()
        with self.lock:
            q = self.hits[who]
            while q and q[0] < now - 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            if len(self.hits) > 5000:                                  # forget callers not seen for a minute
                for key in [k for k, v in self.hits.items() if not v or v[-1] < now - 60]:
                    self.hits.pop(key, None)
            return True


def make_handler(store, collector, key, limiter):
    cache, cache_lock = {}, threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "rbn-service"

        def log_message(self, fmt, *args):                              # the standard one logs every request line; keep the log short
            pass

        def send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, separators=(",", ":")).encode()
            gz = "gzip" in self.headers.get("Accept-Encoding", "") and len(data) > 1000
            if gz:
                data = gzip.compress(data, 6)
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            if gz:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def who(self):
            peer = self.client_address[0]
            forwarded = self.headers.get("X-Forwarded-For", "")
            return forwarded.split(",")[0].strip() if forwarded and peer in ("127.0.0.1", "::1") else peer

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/health":
                return self.send(200, self.health())
            if url.path != "/spots":
                return self.send(404, {"error": "not found"})
            if key and self.headers.get("X-Api-Key", "") != key:
                return self.send(401, {"error": "a key is needed"})
            if not limiter.allow(self.who()):
                return self.send(429, {"error": "too many requests; wait a minute"})
            q = parse_qs(url.query)
            call = (q.get("call", [""])[0]).strip().upper()
            if not call or not CALL_RE.match(call) or len(call) > 14:
                return self.send(400, {"error": "give a callsign, for example call=K5OHY"})
            try:
                day = datetime.strptime(q.get("date", [f"{datetime.now(timezone.utc):%Y-%m-%d}"])[0], "%Y-%m-%d").date()
            except ValueError:
                return self.send(400, {"error": "date must look like 2026-11-22"})
            today = datetime.now(timezone.utc).date()
            if day > today or day < today - timedelta(days=1):
                return self.send(400, {"error": "only today and yesterday (UTC) are held; use RBN's daily file for older days"})
            ckey, now = (call, day), time.time()
            with cache_lock:
                hit = cache.get(ckey)
            if hit and now - hit[0] < CACHE_SECONDS:
                return self.send(200, hit[1])
            body = json.dumps(spots_answer(store, call, day), separators=(",", ":")).encode()
            with cache_lock:
                if len(cache) > 500:
                    cache.clear()
                cache[ckey] = (now, body)
            self.send(200, body)

        def health(self):
            db = store.reader()
            try:
                count, oldest, newest = db.execute("select count(*), min(ts), max(ts) from spots").fetchone()
            finally:
                db.close()
            return {"ok": True, "connected": collector.connected, "spots_held": count, "oldest_spot": stamp(oldest) if oldest else None,
                    "newest_spot": stamp(newest) if newest else None, "spots_since_start": collector.total, "reconnects": collector.reconnects,
                    "running_since": stamp(collector.started), "last_problem": collector.last_error, "now": stamp(utc_now())}

    return Handler


def serve(store, collector, host, port, key=None, per_minute=120):
    server = ThreadingHTTPServer((host, port), make_handler(store, collector, key, RateLimit(per_minute)))
    server.daemon_threads = True
    return server


def main(argv=None):
    p = argparse.ArgumentParser(description="Collect RBN's live spots and serve them by callsign.")
    p.add_argument("--call", required=True, help="the callsign to log in to the feed with")
    p.add_argument("--db", default="spots.db")
    p.add_argument("--bind", default="127.0.0.1", help="the address to listen on (127.0.0.1 when a web server such as Caddy sits in front)")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--feed-host", default=HOST)
    p.add_argument("--feed-port", type=int, default=PORTS["cw"])
    a = p.parse_args(argv)
    store = Store(a.db)
    store.prune()
    collector = Collector(store, a.call.upper().strip(), a.feed_host, a.feed_port)
    collector.start()
    server = serve(store, collector, a.bind, a.port, os.environ.get("RBN_SERVICE_KEY") or None)
    print(f"{stamp(utc_now())}Z serving on {a.bind}:{a.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        collector.stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
