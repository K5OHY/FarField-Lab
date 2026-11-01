"""Builds OpenHFTA on this machine and compares it with reference outputs (no Streamlit needed)."""
import io, json, os, platform, subprocess, sys, tempfile, time, urllib.request, zipfile
from pathlib import Path

import numpy as np

COMMIT = "7d62e863f1d27372c97df3ac6ef53092fb58bd50"
HERE = Path(__file__).resolve().parent


def machine_info():
    info = {"machine": platform.machine(), "python": sys.version.split()[0], "platform": platform.platform()}
    try:
        cpu = Path("/proc/cpuinfo").read_text()
        info["cpu"] = next((l.split(":", 1)[1].strip() for l in cpu.splitlines() if l.startswith(("model name", "Model"))), "?")
        info["cpus"] = cpu.count("processor\t:")
    except OSError:
        pass
    for tool in ("gfortran", "make"):
        try:
            info[tool] = subprocess.run([tool, "--version"], capture_output=True, text=True).stdout.splitlines()[0]
        except Exception as e:
            info[tool] = f"missing ({e.__class__.__name__})"
    return info


def build(workdir):
    src = Path(workdir) / "openhfta"
    local = os.environ.get("OPENHFTA_SRC")
    if local:  # for testing off Streamlit with an existing checkout
        import shutil
        shutil.copytree(local, src, ignore=shutil.ignore_patterns("*.so", "*.o", "*.mod", ".git"))
    else:
        url = f"https://codeload.github.com/RioDXGroup/openhfta/zip/{COMMIT}"
        data = urllib.request.urlopen(url, timeout=60).read()
        zipfile.ZipFile(io.BytesIO(data)).extractall(workdir)
        next(Path(workdir).glob("openhfta-*")).rename(src)
    t = time.time()
    r = subprocess.run(["make"], cwd=src, capture_output=True, text=True)
    return src, r.returncode, round(time.time() - t, 1), (r.stdout + r.stderr)[-3000:]


def compare(src):
    sys.path.insert(0, str(src))
    import hfta
    rows, worst = [], 0.0
    for c in json.loads((HERE / "ref.json").read_text()):
        ang, g = hfta.analyze(str(src / "test" / "pro" / c["profile"]), c["mhz"], c["heights"], c["phases"],
                              c["epsr"], c["sigma"], lib_path=str(src / "libopenytwcore.so"),
                              antenna_pattern_type=c["type"])
        d = float(np.max(np.abs(np.asarray(g, float) - np.asarray(c["gain"]))))
        worst = max(worst, d)
        rows.append({"case": f'{c["profile"]} {c["mhz"]} MHz {c["heights"]} type {c["type"]} soil {c["epsr"]}/{c["sigma"]}',
                     "peak_dBi": round(float(np.max(g)), 3), "max_diff_dB": round(d, 4)})
    return rows, worst


if __name__ == "__main__":
    print(json.dumps(machine_info(), indent=1))
    with tempfile.TemporaryDirectory() as w:
        src, rc, secs, log = build(w)
        print("make exit", rc, "in", secs, "s")
        if rc:
            print(log); sys.exit(1)
        rows, worst = compare(src)
        print(json.dumps(rows, indent=1), "\nworst diff dB:", worst)
