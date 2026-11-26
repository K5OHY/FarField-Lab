"""Run the tests in parallel, so the whole suite takes about a minute instead of five.

    python run_tests.py                  every test, spread over several processes
    python run_tests.py --quick          everything except the slow Compare page tests
    python run_tests.py openings core    only the tests whose name contains one of these words
    python run_tests.py --skip ComparePage --workers 6

How it works: it finds every test, shares them out over several worker processes (each worker runs its share with the ordinary unittest runner) and prints one
summary. It remembers how long each test took (in .test_timings.json, which is not committed) and uses that to share the work out evenly the next time. Each worker
gets its own temporary folder, so tests that write scratch files do not step on each other. A test that fails is listed with its error, and the exit code is 1.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TIMINGS = ROOT / ".test_timings.json"
SLOW_DEFAULT_S, FAST_DEFAULT_S = 1.5, 0.15     # a guess for a test that has not been timed yet: the page tests (test_app) are slow, the rest are not


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item.id()


def discover_ids():
    """Every test id under tests/, found the way `python -m unittest discover` finds them."""
    import logging
    logging.getLogger("streamlit").setLevel(logging.ERROR)          # importing the page tests makes Streamlit chatter about running outside a server
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]            # the tests live in a plain folder, so their names start at the file (test_app.MySpotsPage...)
    suite = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
    return sorted(set(_flatten(suite)))


def share_out(ids, weights, workers):
    """Longest job first onto the emptiest worker, so every worker finishes at about the same time."""
    bins = [[0.0, []] for _ in range(workers)]
    for test_id in sorted(ids, key=lambda i: -weights.get(i, SLOW_DEFAULT_S if "test_app" in i else FAST_DEFAULT_S)):
        smallest = min(bins, key=lambda b: b[0])
        smallest[0] += weights.get(test_id, SLOW_DEFAULT_S if "test_app" in test_id else FAST_DEFAULT_S)
        smallest[1].append(test_id)
    return [b[1] for b in bins if b[1]]


class _TimedResult(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.durations, self._start = {}, 0.0

    def startTest(self, test):
        self._start = time.time()
        super().startTest(test)

    def stopTest(self, test):
        self.durations[test.id()] = time.time() - self._start
        super().stopTest(test)


def worker(ids_file, result_file):
    """Run the tests listed in `ids_file` and write what happened to `result_file` (as JSON)."""
    import io
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
    os.chdir(ROOT)
    ids = json.loads(Path(ids_file).read_text(encoding="utf-8"))
    suite = unittest.TestLoader().loadTestsFromNames(ids)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=0, resultclass=_TimedResult).run(suite)
    bad = [(t.id(), tb) for t, tb in result.failures + result.errors]
    Path(result_file).write_text(json.dumps({"ran": result.testsRun, "skipped": len(result.skipped), "bad": bad, "durations": result.durations}), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run the tests in parallel.")
    parser.add_argument("words", nargs="*", help="run only the tests whose name contains one of these words (case does not matter)")
    parser.add_argument("--quick", action="store_true", help="leave out the slow Compare page tests")
    parser.add_argument("--skip", nargs="*", default=[], help="leave out tests whose name contains one of these words")
    parser.add_argument("--workers", type=int, default=0, help="how many processes (default: most of the cores, at most 10)")
    parser.add_argument("--worker", nargs=2, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(*args.worker)
        return 0

    started = time.time()
    ids = discover_ids()
    words = [w.lower() for w in args.words]
    skips = [s.lower() for s in args.skip] + (["compare"] if args.quick else [])
    if words:
        ids = [i for i in ids if any(w in i.lower() for w in words)]
    if skips:
        ids = [i for i in ids if not any(s in i.lower() for s in skips)]
    if not ids:
        print("No tests match.")
        return 1
    weights = json.loads(TIMINGS.read_text(encoding="utf-8")) if TIMINGS.exists() else {}
    workers = args.workers or max(2, min(10, (os.cpu_count() or 4) - 2))
    shares = share_out(ids, weights, min(workers, len(ids)))
    print(f"{len(ids)} tests on {len(shares)} workers (found in {time.time() - started:.0f} s)...", flush=True)

    scratch = Path(tempfile.mkdtemp(prefix="fftests_"))
    procs = []
    for n, share in enumerate(shares):
        ids_file, result_file, tmp = scratch / f"ids{n}.json", scratch / f"result{n}.json", scratch / f"tmp{n}"
        tmp.mkdir()
        ids_file.write_text(json.dumps(share), encoding="utf-8")
        env = dict(os.environ, TEMP=str(tmp), TMP=str(tmp), TMPDIR=str(tmp), PYTHONIOENCODING="utf-8")
        procs.append((subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", str(ids_file), str(result_file)], cwd=ROOT, env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True), result_file))
    ran = skipped = 0
    bad, durations, crashed = [], {}, []
    for n, (proc, result_file) in enumerate(procs):
        _, err = proc.communicate()
        if proc.returncode != 0 or not result_file.exists():
            crashed.append((n, (err or "").strip()[-1500:]))
            continue
        data = json.loads(result_file.read_text(encoding="utf-8"))
        ran += data["ran"]
        skipped += data["skipped"]
        bad += data["bad"]
        durations.update(data["durations"])
    if durations:
        merged = dict(weights)
        merged.update({k: round(v, 3) for k, v in durations.items()})
        TIMINGS.write_text(json.dumps(merged, indent=0, sort_keys=True), encoding="utf-8")
    took = time.time() - started
    for test_id, tb in bad:
        print("=" * 70 + f"\nFAIL: {test_id}\n{tb}")
    for n, err in crashed:
        print("=" * 70 + f"\nA worker stopped before it finished (share {n}):\n{err}")
    slowest = sorted(durations.items(), key=lambda kv: -kv[1])[:3]
    print("-" * 70)
    print(f"Ran {ran} tests in {took:.0f} s on {len(shares)} workers" + (f" ({skipped} skipped)" if skipped else ""))
    print("slowest: " + ", ".join(f"{k.split('.')[-1]} {v:.1f}s" for k, v in slowest))
    print("OK" if not bad and not crashed else f"FAILED ({len(bad)} failed, {len(crashed)} workers stopped)")
    return 0 if not bad and not crashed else 1


if __name__ == "__main__":
    sys.exit(main())
