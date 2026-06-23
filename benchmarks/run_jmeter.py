"""
benchmarks/run_jmeter.py - JMeter comparison runner for Flask vs FastAPI.

Reads API_KEY from flask-app/.env automatically (same pattern as run_ab.py
and run_benchmarks.py) — no manual copy-paste needed.

Runs jmeter_plan.jmx against Flask (port 5000) then FastAPI (port 8000),
saving each run's HTML dashboard to results/jmeter/flask_report/ and
results/jmeter/fastapi_report/.

Prerequisites
-------------
  Install JMeter 5.6+ from https://jmeter.apache.org/download_jmeter.cgi
    - Extract the zip anywhere (e.g. C:\\jmeter)
    - Java 8+ required: java -version
    - Add bin/ to PATH so 'jmeter' works from any terminal
      Windows: C:\\jmeter\\bin  -> System Environment Variables -> PATH
      macOS:   export PATH="$PATH:/opt/jmeter/bin"
    - Verify: jmeter --version

Usage
-----
  python run_jmeter.py
  python run_jmeter.py --threads 50 --ramp-up 10 --duration 120

Results saved to:
  benchmarks/results/jmeter/flask_report/index.html    <- open in browser
  benchmarks/results/jmeter/fastapi_report/index.html
  benchmarks/results/jmeter/flask.jtl                  <- raw data
  benchmarks/results/jmeter/fastapi.jtl
"""

import argparse
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

BENCHMARK_DIR = pathlib.Path(__file__).parent
RESULTS_DIR   = BENCHMARK_DIR / "results" / "jmeter"
PLAN          = BENCHMARK_DIR / "jmeter_plan.jmx"

TARGETS = {
    "flask":   {"host": "localhost", "port": "5000"},
    "fastapi": {"host": "localhost", "port": "8000"},
}

# ── Read API_KEY from flask-app/.env automatically ───────────────────────────
_env_file = BENCHMARK_DIR.parent / "flask-app" / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        pass

API_KEY = os.getenv("API_KEY", "change-me")


# ─── Pre-flight ───────────────────────────────────────────────────────────────

def check_jmeter() -> bool:
    try:
        subprocess.run(["jmeter", "--version"], capture_output=True, check=False)
        return True
    except FileNotFoundError:
        return False


def check_health(name: str, host: str, port: str) -> bool:
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            if r.status == 200:
                print(f"  OK      {name:8s} -> {url}")
                return True
    except Exception as e:
        print(f"  FAIL    {name:8s} -> {url}  ({e})")
    return False


# ─── Run JMeter ───────────────────────────────────────────────────────────────

def run_jmeter(name: str, host: str, port: str,
               threads: str, ramp_up: str, duration: str) -> None:

    jtl_path    = RESULTS_DIR / f"{name}.jtl"
    report_path = RESULTS_DIR / f"{name}_report"

    # JMeter refuses to write HTML report if the folder already exists
    if report_path.exists():
        import shutil
        shutil.rmtree(report_path)

    print(f"\n{'='*60}")
    print(f"  JMeter -> {name}  ({host}:{port})")
    print(f"  Threads={threads}  Ramp={ramp_up}s  Duration={duration}s")
    print(f"{'='*60}")

    cmd = [
        "jmeter", "-n",
        "-t", str(PLAN),
        f"-JHOST={host}",
        f"-JPORT={port}",
        f"-JAPI_KEY={API_KEY}",
        f"-JTHREADS={threads}",
        f"-JRAMP_UP={ramp_up}",
        f"-JDURATION={duration}",
        f"-JSAMPLE_FILE={BENCHMARK_DIR / 'sample_receipt.jpg'}",
        "-l", str(jtl_path),
        "-e", "-o", str(report_path),
    ]

    # check=False — JMeter exits non-zero if any assertion fails,
    # which is normal during load tests; we still want the HTML report.
    result = subprocess.run(cmd, check=False)

    if report_path.exists():
        print(f"\n  HTML report -> {report_path / 'index.html'}")
    else:
        print(f"\n  WARNING: HTML report not generated (JMeter may have failed to start).")
        print(f"  Check JMeter is on PATH: jmeter --version")

    if result.returncode not in (0, 1):
        print(f"  WARNING: JMeter exited with code {result.returncode}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="JMeter: Flask vs FastAPI")
    parser.add_argument("--threads",  default="20",  help="Concurrent users (default: 20)")
    parser.add_argument("--ramp-up",  default="5",   help="Ramp-up seconds (default: 5)")
    parser.add_argument("--duration", default="60",  help="Duration in seconds (default: 60)")
    args = parser.parse_args()

    print("Checking JMeter is available...")
    if not check_jmeter():
        print("\n  ERROR: 'jmeter' not found in PATH.")
        print("  Download: https://jmeter.apache.org/download_jmeter.cgi")
        print("  Extract zip, add bin/ to PATH, then reopen terminal.")
        sys.exit(1)
    print("  jmeter found OK")

    print(f"\n  API_KEY loaded: '{API_KEY}'")
    print(f"  (auto-read from flask-app/.env -- change there if needed)")

    print("\nChecking apps are running...")
    reachable = {
        name: check_health(name, cfg["host"], cfg["port"])
        for name, cfg in TARGETS.items()
    }
    if not any(reachable.values()):
        print("\nNeither app is reachable. Start them first.")
        sys.exit(1)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    for name, cfg in TARGETS.items():
        if not reachable[name]:
            print(f"\nSkipping {name} -- not reachable")
            continue
        run_jmeter(name, cfg["host"], cfg["port"],
                   args.threads, args.ramp_up, args.duration)

    print(f"\n{'='*60}")
    print("Done. Open these in your browser to compare:")
    for name in TARGETS:
        report = RESULTS_DIR / f"{name}_report" / "index.html"
        if report.exists():
            print(f"  {name:8s}: {report}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()