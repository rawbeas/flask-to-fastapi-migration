"""
benchmarks/run_ab.py - Apache Bench comparison runner for Flask vs FastAPI.

Apache Bench (ab) is a simple, single-threaded HTTP load tool - great for
measuring raw latency and RPS with no overhead. Unlike Locust it can't
simulate user think-time or chain requests, but it gives clean,
reproducible numbers for individual endpoints.

Limitation: ab doesn't support multipart/form-data file uploads, so
/upload-receipt is skipped here. Use:
  - locust  (run_benchmarks.py) for full workflow including file upload
  - JMeter  (jmeter_plan.jmx)  for full workflow with richer reporting

Endpoints tested here:
  GET  /health          (no auth)
  POST /extract         (JSON body, X-API-Key)
  POST /validate        (JSON body, X-API-Key)

Results saved to:
  benchmarks/results/ab_flask.txt
  benchmarks/results/ab_fastapi.txt
  benchmarks/results/ab_comparison.md   <- the table you want to keep

Prerequisites - getting ab on Windows
--------------------------------------
  Option A (easiest): XAMPP
    1. Install XAMPP from https://www.apachefriends.org
    2. Add C:\\xampp\\apache\\bin to PATH
    3. Open a new terminal and run: ab -V

  Option B: Apache Lounge (standalone, no installer)
    1. Go to https://www.apachelounge.com/download/
    2. Download httpd-*-win64-VS17.zip
    3. Extract, add the bin/ folder to PATH
    4. Run: ab -V

  macOS:
    brew install httpd
    ab -V

  Ubuntu/Debian:
    sudo apt install apache2-utils
    ab -V

Prerequisites - getting ab on PATH (Windows quick check)
---------------------------------------------------------
  Open PowerShell and run:
    where.exe ab
  If nothing shows, ab is not on PATH yet.

Usage
-----
  python run_ab.py
  python run_ab.py --requests 500 --concurrency 20

  # Use a specific receipt_id for /extract and /validate:
  RECEIPT_ID=your-uuid python run_ab.py      (macOS/Linux)
  $env:RECEIPT_ID="your-uuid"; python run_ab.py   (PowerShell)
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

RESULTS_DIR = pathlib.Path(__file__).parent / "results" / "ab"

TARGETS = {
    "flask":   "http://localhost:5000",
    "fastapi": "http://localhost:8000",
}

# Read API_KEY - auto-loads from flask-app/.env if not set in environment
_env_file = pathlib.Path(__file__).parent.parent / "flask-app" / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        pass

API_KEY = os.getenv("API_KEY", "change-me")

# Optional: pre-existing receipt_id to test /extract and /validate.
# If blank, those endpoints are skipped (upload a receipt first via Postman/Swagger).
RECEIPT_ID = os.getenv("RECEIPT_ID", "")

ROWS = [
    ("Requests/sec (RPS)", "rps",     "{:.1f}"),
    ("Avg latency (ms)",   "avg_ms",  "{:.1f}"),
    ("P50 latency (ms)",   "p50_ms",  "{:.0f}"),
    ("P95 latency (ms)",   "p95_ms",  "{:.0f}"),
    ("P99 latency (ms)",   "p99_ms",  "{:.0f}"),
    ("Failed requests",    "failures","{:.0f}"),
]


# ─── Pre-flight ───────────────────────────────────────────────────────────────

def check_ab() -> bool:
    try:
        r = subprocess.run(["ab", "-V"], capture_output=True, check=False)
        return True
    except FileNotFoundError:
        return False


def check_health(name: str, host: str) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/health", timeout=3) as r:
            if r.status == 200:
                print(f"  OK      {name:8s} -> {host}")
                return True
    except Exception as e:
        print(f"  FAIL    {name:8s} -> {host}  ({e})")
    return False


# ─── ab helpers ───────────────────────────────────────────────────────────────

def _parse_ab_output(output: str) -> dict:
    """Parse key metrics from ab's stdout."""
    parsed: dict = {"raw": output, "rps": 0.0, "avg_ms": 0.0,
                    "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "failures": 0}
    in_percentiles = False
    for line in output.splitlines():
        line = line.strip()
        if "Requests per second" in line:
            try: parsed["rps"] = float(line.split()[3])
            except (IndexError, ValueError): pass
        elif line.startswith("Time per request") and "mean" not in line and "across" not in line:
            try: parsed["avg_ms"] = float(line.split()[3])
            except (IndexError, ValueError): pass
        elif "Failed requests" in line:
            try: parsed["failures"] = int(line.split()[2])
            except (IndexError, ValueError): pass
        elif "Percentage of the requests" in line:
            in_percentiles = True
        elif in_percentiles:
            parts = line.split()
            if len(parts) >= 2 and parts[0].endswith("%"):
                pct = parts[0].rstrip("%")
                try:
                    val = float(parts[1])
                    if pct == "50":  parsed["p50_ms"] = val
                    elif pct == "95": parsed["p95_ms"] = val
                    elif pct == "99": parsed["p99_ms"] = val
                except ValueError:
                    pass
    return parsed


def _run_ab(cmd: list[str]) -> dict:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return _parse_ab_output(result.stdout + result.stderr)
    except FileNotFoundError:
        print("  ERROR: 'ab' not found in PATH")
        return {}


def ab_get(url: str, n: int, c: int) -> dict:
    return _run_ab(["ab", "-n", str(n), "-c", str(c),
                    "-H", f"X-API-Key: {API_KEY}", url])


def ab_post_json(url: str, body: dict, n: int, c: int) -> dict:
    data = json.dumps(body).encode()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="wb") as f:
        f.write(data)
        tmp = f.name
    result = _run_ab(["ab", "-n", str(n), "-c", str(c),
                      "-H", f"X-API-Key: {API_KEY}",
                      "-H", "Content-Type: application/json",
                      "-p", tmp, "-T", "application/json", url])
    os.unlink(tmp)
    return result


# ─── Per-target run ───────────────────────────────────────────────────────────

def run_ab_against(name: str, host: str, n: int, c: int) -> dict[str, dict]:
    print(f"\n  Running ab against {name} ({host}) -- {n} requests, {c} concurrent")
    results: dict[str, dict] = {}

    print(f"    GET  /health ...")
    results["health"] = ab_get(f"{host}/health", n, c)
    print(f"         RPS={results['health'].get('rps', 0):.1f}  avg={results['health'].get('avg_ms', 0):.1f}ms")

    if RECEIPT_ID:
        body = {"receipt_id": RECEIPT_ID}
        print(f"    POST /extract ...")
        results["extract"] = ab_post_json(f"{host}/extract", body, n, c)
        print(f"         RPS={results['extract'].get('rps', 0):.1f}  avg={results['extract'].get('avg_ms', 0):.1f}ms")

        print(f"    POST /validate ...")
        results["validate"] = ab_post_json(f"{host}/validate", body, n, c)
        print(f"         RPS={results['validate'].get('rps', 0):.1f}  avg={results['validate'].get('avg_ms', 0):.1f}ms")
    else:
        print(f"    POST /extract  -- SKIPPED (set RECEIPT_ID env var to enable)")
        print(f"    POST /validate -- SKIPPED")

    # Save raw output
    RESULTS_DIR.mkdir(exist_ok=True)
    raw_path = RESULTS_DIR / f"ab_{name}.txt"
    with open(raw_path, "w") as f:
        for endpoint, data in results.items():
            f.write(f"\n{'='*50}\n{endpoint}\n{'='*50}\n")
            f.write(data.get("raw", "no output"))
    return results


# ─── Comparison table ─────────────────────────────────────────────────────────

def print_and_save_comparison(all_results: dict[str, dict[str, dict]]) -> None:
    endpoints = list(next(iter(all_results.values())).keys()) if all_results else []

    print(f"\n{'='*60}\nApache Bench Comparison\n{'='*60}")

    md_lines = ["# Apache Bench: Flask vs FastAPI\n"]

    for ep in endpoints:
        print(f"\n  /{ep}")
        hdr = f"  {'Metric':<24} {'Flask':>12} {'FastAPI':>12}"
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))

        md_lines.append(f"## /{ep}\n")
        md_lines.append(f"| {'Metric':<24} | {'Flask':>12} | {'FastAPI':>12} |")
        md_lines.append(f"|{'-'*26}|{'-'*14}|{'-'*14}|")

        for label, key, fmt in ROWS:
            f_val  = fmt.format(all_results["flask"].get(ep, {}).get(key, 0))   if "flask"   in all_results else "-"
            fa_val = fmt.format(all_results["fastapi"].get(ep, {}).get(key, 0)) if "fastapi" in all_results else "-"
            print(f"  {label:<24} {f_val:>12} {fa_val:>12}")
            md_lines.append(f"| {label:<24} | {f_val:>12} | {fa_val:>12} |")
        md_lines.append("")

    md_lines.append("\n> /upload-receipt not tested by ab (no multipart support).")
    md_lines.append("> Use run_benchmarks.py (Locust) or jmeter_plan.jmx for full coverage.")

    out_path = RESULTS_DIR / "ab_comparison.md"
    with open(out_path, "w") as f:
        f.write("\n".join(md_lines))
    print(f"\nComparison saved -> {out_path}")
    print(f"Raw ab output    -> {RESULTS_DIR}/ab_flask.txt  and  ab_fastapi.txt")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Apache Bench: Flask vs FastAPI")
    parser.add_argument("--requests",    default="300", help="Requests per endpoint (default: 300)")
    parser.add_argument("--concurrency", default="10",  help="Concurrent requests (default: 10)")
    args = parser.parse_args()

    n, c = int(args.requests), int(args.concurrency)

    print("Checking 'ab' is available...")
    if not check_ab():
        print("\n  ERROR: 'ab' not found in PATH.")
        print("  Windows: download from https://www.apachelounge.com/download/")
        print("           extract and add bin/ to PATH, then reopen terminal")
        print("  macOS:   brew install httpd")
        print("  Ubuntu:  sudo apt install apache2-utils")
        sys.exit(1)
    print("  ab found OK")

    print("\nChecking apps are running...")
    reachable = {name: check_health(name, host) for name, host in TARGETS.items()}
    if not any(reachable.values()):
        print("\nNeither app is reachable. Start them first.")
        sys.exit(1)

    if not RECEIPT_ID:
        print("\nNOTE: RECEIPT_ID not set - /extract and /validate will be skipped.")
        print("  Upload a receipt via Postman or Swagger, copy the receipt_id, then:")
        print("  PowerShell: $env:RECEIPT_ID=\"paste-id-here\"; python run_ab.py")
        print("  macOS/Linux: RECEIPT_ID=paste-id-here python run_ab.py")

    RESULTS_DIR.mkdir(exist_ok=True)

    all_results: dict[str, dict[str, dict]] = {}
    for name, host in TARGETS.items():
        if not reachable[name]:
            print(f"\nSkipping {name} -- not reachable")
            continue
        all_results[name] = run_ab_against(name, host, n, c)

    if all_results:
        print_and_save_comparison(all_results)


if __name__ == "__main__":
    main()