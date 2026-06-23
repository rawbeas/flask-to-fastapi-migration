# Benchmarking — Flask vs FastAPI

Locust-based load-testing suite that runs the same workflow against both services and produces a side-by-side comparison.

---

## Results (from the actual benchmark run on this machine)

| Metric | Flask | FastAPI |
|---|---|---|
| Total requests | 821 | 1500 |
| Failures | 0 | 0 |
| Avg latency (ms) | 2193.1 | 700.9 |
| P95 latency (ms) | 2600.0 | 2100.0 |
| P99 latency (ms) | 3300.0 | 3300.0 |
| Throughput (req/s) | 14.20 | 25.57 |

20 concurrent simulated users, 30 second run per service, sequential runs.

---

## Prerequisites

1. Both apps must be running:
   - Flask: `python app.py` in `flask-app/` (port 5000)
   - FastAPI: `python -m uvicorn app:app --reload --port 8000` in `fastapi-app/`

2. Rate limiting must be disabled in **both** `.env` files:
   ```
   RATE_LIMIT_ENABLED=false
   ```
   Restart both apps after changing this.

3. Install Locust (from the project root):
   ```bash
   pip install -r benchmarks/requirements.txt
   ```

---

## Run the benchmark

```bash
python benchmarks/run_benchmarks.py
```

This runs Flask first, then FastAPI, and prints a comparison table at the end.

**Custom load:**
```bash
python benchmarks/run_benchmarks.py --users 50 --spawn-rate 10 --duration 60s
```

| Flag | Default | Description |
|---|---|---|
| `--users` | 20 | Concurrent simulated users |
| `--spawn-rate` | 5 | Users added per second |
| `--duration` | 30s | How long each run lasts |

---

## What each simulated user does

1. Uploads a receipt via `POST /upload-receipt` — saves the `receipt_id`
2. Repeatedly calls `GET /health`, `POST /extract`, `POST /validate` using that ID
3. Waits 0.5–2 seconds between actions (think time)
4. Occasionally uploads a new receipt

The same `locustfile.py` runs unchanged against both services — possible because both expose an identical API contract.

---

## Results location

```
benchmarks/results/locust/
├── locust_comparison.md    Flask vs FastAPI table (saved permanently)
├── flask.html              Full Locust HTML report — open in browser
├── fastapi.html
├── flask_stats.csv
└── fastapi_stats.csv
```

The `results/` folder is gitignored — results are regenerated on every run.

---

## Run against one app with live UI

```bash
locust -f benchmarks/locustfile.py --host http://localhost:5000
# open http://localhost:8089 in browser for live charts
```

---

## How the API key is loaded

`locustfile.py` auto-reads `API_KEY` from `flask-app/.env` using dotenv — no manual config needed. If you changed the key from the default `change-me`, the benchmark picks it up automatically.
