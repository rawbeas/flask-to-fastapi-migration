"""
benchmarks/run_benchmarks.py — Single-command benchmark runner for Flask vs FastAPI.

What it does
------------
  1. Checks that both apps are reachable (GET /health)
  2. Runs Locust headless against the Flask app  (http://localhost:5000)
  3. Runs Locust headless against the FastAPI app (http://localhost:8000)
  4. Saves a CSV + HTML report per app under benchmarks/results/
  5. Prints a side-by-side comparison table (avg / p95 latency, RPS, failures)

Why sequential, not parallel
-----------------------------
This is "one command" for convenience, but the two runs happen one after
another — not concurrently. Running both load tests at the same time would
have them compete for CPU/network on your machine, skewing both results.
Running them back-to-back (same load profile, same machine, one after the
other) is the standard approach for a fair apples-to-apples comparison —
matching how you'd do it in production-grade benchmarking too.

Prerequisites
-------------
  1. Both apps running and reachable:
       - via docker-compose (recommended):  docker compose up --build -d
       - or manually in two terminals:
           flask-app:   python app.py            (port 5000)
           fastapi-app: uvicorn app:app --port 8000  (port 8000)

  2. Install benchmark dependencies:
       pip install -r benchmarks/requirements.txt

Usage
-----
  python run_benchmarks.py
  python run_benchmarks.py --users 50 --spawn-rate 10 --duration 60s
"""

import argparse
import csv
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

BENCHMARK_DIR = Path(__file__).parent
RESULTS_DIR   = BENCHMARK_DIR / "results" / "locust"
LOCUSTFILE    = BENCHMARK_DIR / "locustfile.py"

TARGETS = {
    "flask":   "http://localhost:5000",
    "fastapi": "http://localhost:8000",
}


# ─── Pre-flight check ─────────────────────────────────────────────────────────

def check_health(name: str, host: str) -> bool:
    url = f"{host}/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            if resp.status == 200:
                print(f"  ✅  {name:8s} reachable at {url}")
                return True
            print(f"  ❌  {name:8s} returned HTTP {resp.status} at {url}")
            return False
    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
        print(f"  ❌  {name:8s} not reachable at {url}  ({exc})")
        return False


# ─── Run a single Locust load test ────────────────────────────────────────────

def run_locust(name: str, host: str, users: str, spawn_rate: str, duration: str) -> None:
    print(f"\n{'='*60}\nBenchmarking {name} -> {host}\n{'='*60}")
    prefix = RESULTS_DIR / name

    cmd = [
        sys.executable, "-m", "locust",
        "-f", str(LOCUSTFILE),
        "--headless",
        "--users", users,
        "--spawn-rate", spawn_rate,
        "--run-time", duration,
        "--host", host,
        "--csv", str(prefix),
        "--html", str(prefix) + ".html",
    ]
    # check=False — Locust exits with code 1 when ANY request fails, which is
    # normal during a load test (e.g. a handful of 5xx under high concurrency).
    # Using check=True would crash the whole runner the moment one upload gets
    # a 429 or 401, aborting the FastAPI run before it even starts.
    result = subprocess.run(cmd, check=False)
    if result.returncode not in (0, 1):
        print(f"WARNING: Locust exited with unexpected code {result.returncode} for {name}")


# ─── Summarise + compare results ──────────────────────────────────────────────

def summarize(name: str) -> dict | None:
    """Read the 'Aggregated' row from <name>_stats.csv."""
    stats_file = RESULTS_DIR / f"{name}_stats.csv"
    if not stats_file.exists():
        return None

    with open(stats_file, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("Name") == "Aggregated":
                return {
                    "requests":  int(row["Request Count"]),
                    "failures":  int(row["Failure Count"]),
                    "avg_ms":    float(row["Average Response Time"]),
                    "p95_ms":    float(row["95%"]),
                    "p99_ms":    float(row["99%"]),
                    "rps":       float(row["Requests/s"]),
                }
    return None


def print_comparison(results: dict[str, dict]) -> None:
    print(f"\n{'='*60}\nComparison\n{'='*60}")
    header = f"{'Metric':<22} {'Flask':>15} {'FastAPI':>15}"
    print(header)
    print("-" * len(header))

    rows = [
        ("Total requests",   "requests",  "{:.0f}"),
        ("Failures",         "failures",  "{:.0f}"),
        ("Avg latency (ms)", "avg_ms",    "{:.1f}"),
        ("P95 latency (ms)", "p95_ms",    "{:.1f}"),
        ("P99 latency (ms)", "p99_ms",    "{:.1f}"),
        ("Throughput (RPS)", "rps",       "{:.2f}"),
    ]
    for label, key, fmt in rows:
        flask_val   = fmt.format(results["flask"][key])   if results.get("flask")   else "-"
        fastapi_val = fmt.format(results["fastapi"][key]) if results.get("fastapi") else "-"
        print(f"{label:<22} {flask_val:>15} {fastapi_val:>15}")

    print(f"\nFull HTML reports: {RESULTS_DIR}/flask.html  and  {RESULTS_DIR}/fastapi.html")

    # ── Save comparison table to file ─────────────────────────────────────────
    out_path = RESULTS_DIR / "locust_comparison.md"
    with open(out_path, "w") as f:
        f.write("# Locust Benchmark: Flask vs FastAPI\n\n")
        f.write(f"| {'Metric':<22} | {'Flask':>12} | {'FastAPI':>12} |\n")
        f.write(f"|{'-'*24}|{'-'*14}|{'-'*14}|\n")
        for label, key, fmt in rows:
            flask_val   = fmt.format(results["flask"][key])   if results.get("flask")   else "-"
            fastapi_val = fmt.format(results["fastapi"][key]) if results.get("fastapi") else "-"
            f.write(f"| {label:<22} | {flask_val:>12} | {fastapi_val:>12} |\n")
        f.write(f"\nHTML reports: flask.html and fastapi.html in this folder\n")
    print(f"\nComparison table saved -> {out_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Flask vs FastAPI receipt service")
    parser.add_argument("--users", default="20", help="Concurrent simulated users (default: 20)")
    parser.add_argument("--spawn-rate", default="5", help="Users spawned per second (default: 5)")
    parser.add_argument("--duration", default="30s", help="Test duration, e.g. 30s, 2m (default: 30s)")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)

    print("\nPre-flight checklist")
    print("  1. RATE_LIMIT_ENABLED=false must be set in BOTH apps' .env files,")
    print("     then both apps restarted. With 50 users from one IP sharing a")
    print("     30 req/min limit, uploads will get 429s immediately.")
    print("  2. API_KEY in .env must match what this script sends.")
    print("     Auto-loaded from flask-app/.env — current value:", os.getenv("API_KEY", "change-me"))
    print()

    print("Checking that both apps are running...")
    reachable = {name: check_health(name, host) for name, host in TARGETS.items()}

    if not any(reachable.values()):
        print("\nNeither app is reachable. Start them first — see the docstring "
              "at the top of this file for startup commands.")
        sys.exit(1)

    results = {}
    for name, host in TARGETS.items():
        if not reachable[name]:
            print(f"\nSkipping {name} — not reachable.")
            continue
        run_locust(name, host, args.users, args.spawn_rate, args.duration)
        summary = summarize(name)
        if summary:
            results[name] = summary

    if results:
        print_comparison(results)
    else:
        print("\nNo results to compare — both benchmark runs failed to produce stats.")


if __name__ == "__main__":
    main()