"""A listening test for the Reverse Beacon Network's live feed: connect, listen for a set time, and report how many spots arrive.

This is a prototype to measure the real rate and size before deciding how to collect today's spots. It is not part of the app and
nothing in the app imports it. It needs only Python 3.9 or newer, no extra packages.

    python collector/rbn_listen.py --call YOURCALL --minutes 60

The feed asks for a callsign when you connect (it is how RBN knows who is listening), so the callsign is given on the command line.
It writes, in the folder given by --out (default: collector/out):
    spots.db       every spot received, in a small SQLite database
    progress.log   one line a minute while it runs
    summary.json   the totals when it finishes (also written if you stop it with Ctrl+C)
"""
import argparse
import gzip
import json
import re
import socket
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HOST = "telnet.reversebeacon.net"
PORTS = {"cw": 7000, "ft": 7001}      # 7000: CW, RTTY and other keyed modes; 7001: FT8 and FT4

# DX de KM3T-#:    14033.0  K5OHY          CW    22 dB  24 WPM  CQ      1234Z
LINE = re.compile(
    r"^DX de\s+(?P<spotter>[A-Z0-9/\-#]+):\s+(?P<freq>[\d.]+)\s+(?P<dx>[A-Z0-9/]+)\s+(?P<mode>\S+)\s+(?P<snr>-?\d+)\s*dB\s+"
    r"(?P<speed>\d+)\s*(?P<unit>WPM|BPS)\s+(?P<kind>.*?)\s+(?P<hhmm>\d{4})Z\s*$")


def parse(line):
    """One spot line as a dict, or None for anything else (the welcome text, the prompt, other kinds of line)."""
    m = LINE.match(line.strip())
    if not m:
        return None
    d = m.groupdict()
    return {"spotter": d["spotter"].rstrip("#").rstrip("-"), "freq": float(d["freq"]), "dx": d["dx"], "mode": d["mode"], "snr": int(d["snr"]),
            "speed": int(d["speed"]), "kind": d["kind"].strip(), "hhmm": d["hhmm"]}


def now():
    return datetime.now(timezone.utc)


class Listener:
    def __init__(self, host, port, call, out, minutes):
        self.host, self.port, self.call, self.minutes = host, port, call, minutes
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.out / "spots.db")
        self.db.execute("create table if not exists spots (got text, spotter text, freq real, dx text, mode text, snr int, speed int, kind text, hhmm text)")
        self.log = open(self.out / "progress.log", "a", encoding="utf-8")
        self.per_minute, self.modes, self.spotters, self.dxcalls = Counter(), Counter(), set(), set()
        self.total = self.unparsed = self.disconnects = self.bytes = 0
        self.first = self.last = None
        self.unparsed_examples = []

    def note(self, text):
        line = f"{now():%H:%M:%S}Z {text}"
        print(line, flush=True)
        self.log.write(line + "\n")
        self.log.flush()

    def connect(self):
        sock = socket.create_connection((self.host, self.port), timeout=30)
        sock.settimeout(20)
        seen = b""
        while b"call" not in seen.lower():              # the feed asks "Please enter your call:" and waits
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("closed before asking for a callsign")
            seen += chunk
            if len(seen) > 20000:
                break
        sock.sendall(self.call.encode() + b"\r\n")
        self.note(f"connected to {self.host}:{self.port} and sent the callsign")
        return sock

    def handle(self, line):
        spot = parse(line)
        if spot is None:
            if line.strip() and len(self.unparsed_examples) < 8 and "DX de" in line:
                self.unparsed_examples.append(line.strip())
            if "DX de" in line:
                self.unparsed += 1
            return
        stamp = now()
        self.total += 1
        self.first = self.first or stamp
        self.last = stamp
        self.per_minute[f"{stamp:%H:%M}"] += 1
        self.modes[spot["mode"]] += 1
        self.spotters.add(spot["spotter"])
        self.dxcalls.add(spot["dx"])
        self.db.execute("insert into spots values (?,?,?,?,?,?,?,?,?)",
                        (f"{stamp:%Y-%m-%d %H:%M:%S}", spot["spotter"], spot["freq"], spot["dx"], spot["mode"], spot["snr"], spot["speed"], spot["kind"], spot["hhmm"]))

    def run(self):
        end = time.time() + self.minutes * 60
        next_report, pending, sock = time.time() + 60, b"", None
        try:
            while time.time() < end:
                if sock is None:
                    try:
                        sock = self.connect()
                    except OSError as exc:
                        self.note(f"could not connect: {exc}; trying again in 15 seconds")
                        time.sleep(15)
                        continue
                try:
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise ConnectionError("the feed closed the connection")
                except socket.timeout:
                    chunk = b""
                except OSError as exc:
                    self.disconnects += 1
                    self.note(f"disconnected: {exc}")
                    sock.close()
                    sock, pending = None, b""
                    continue
                self.bytes += len(chunk)
                pending += chunk
                *lines, pending = pending.split(b"\n")
                for raw in lines:
                    self.handle(raw.decode("ascii", "replace"))
                if time.time() >= next_report:
                    self.db.commit()
                    self.note(f"{self.total:,} spots so far; last minute {self.per_minute.get(f'{(now()):%H:%M}', 0)} (this minute so far)")
                    next_report += 60
        except KeyboardInterrupt:
            self.note("stopped with Ctrl+C")
        finally:
            if sock:
                sock.close()
            self.db.commit()
        return self.summary()

    def summary(self):
        seconds = (self.last - self.first).total_seconds() if self.first and self.last else 0
        full = [n for minute, n in sorted(self.per_minute.items())][1:-1] or list(self.per_minute.values())     # leave out the partial first and last minute
        csv = "\n".join(f"{s},{f},{d},{m},{n},{k},{h}" for s, f, d, m, n, k, h in self.db.execute("select spotter, freq, dx, mode, snr, kind, hhmm from spots"))
        gz = len(gzip.compress(csv.encode())) if csv else 0
        spots_per_minute = (sum(full) / len(full)) if full else 0
        result = {
            "port": self.port, "spots": self.total, "minutes_listened": round(seconds / 60, 1), "spots_per_minute_average": round(spots_per_minute, 1),
            "spots_per_second_average": round(spots_per_minute / 60, 2), "busiest_minute": max(self.per_minute.values(), default=0),
            "quietest_full_minute": min(full, default=0), "different_skimmers": len(self.spotters), "different_stations_heard": len(self.dxcalls),
            "by_mode": dict(self.modes.most_common()), "lines_that_looked_like_spots_but_did_not_parse": self.unparsed,
            "unparsed_examples": self.unparsed_examples, "disconnects": self.disconnects, "bytes_received": self.bytes,
            "database_bytes": (self.out / "spots.db").stat().st_size, "gzipped_csv_bytes_for_this_run": gz,
            "a_day_would_be_roughly": {"spots": round(spots_per_minute * 1440), "database_MB": round((self.out / "spots.db").stat().st_size / max(self.total, 1) * spots_per_minute * 1440 / 1e6, 1),
                                       "gzipped_csv_MB": round(gz / max(self.total, 1) * spots_per_minute * 1440 / 1e6, 1)},
        }
        (self.out / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        self.note("finished; totals are in summary.json")
        print(json.dumps(result, indent=2))
        return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Listen to the Reverse Beacon Network's live feed for a while and report how many spots arrive.")
    p.add_argument("--call", required=True, help="the callsign to log in with (the feed asks for one)")
    p.add_argument("--minutes", type=float, default=60)
    p.add_argument("--feed", choices=list(PORTS), default="cw", help="cw: CW and RTTY (port 7000); ft: FT8 and FT4 (port 7001)")
    p.add_argument("--host", default=HOST)
    p.add_argument("--port", type=int, help="overrides --feed; for testing against a local fake feed")
    p.add_argument("--out", default=str(Path(__file__).parent / "out"))
    a = p.parse_args(argv)
    Listener(a.host, a.port or PORTS[a.feed], a.call.upper().strip(), a.out, a.minutes).run()


if __name__ == "__main__":
    sys.exit(main())
