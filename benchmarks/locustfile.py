"""
benchmarks/locustfile.py — Load test for the Receipt Verification Service.

Works against EITHER the Flask app (port 5000) or the FastAPI app (port 8000)
unchanged — that's the whole point of building both to the same contract
(same endpoints, same request/response shapes, same auth).

Run manually (one target at a time)
------------------------------------
  locust -f locustfile.py --host http://localhost:5000   # Flask, web UI at :8089
  locust -f locustfile.py --host http://localhost:8000   # FastAPI

Run both automatically (one command)
-------------------------------------
  python run_benchmarks.py

Config via environment variables
---------------------------------
  API_KEY  — must match the target app's API_KEY (default "change-me")
"""

import io
import os

from locust import HttpUser, between, task

API_KEY = os.getenv("API_KEY", "change-me")
AUTH_HEADERS = {"X-API-Key": API_KEY}
JSON_HEADERS = {**AUTH_HEADERS, "Content-Type": "application/json"}

# Minimal valid JPEG header + padding — small enough to keep upload latency
# dominated by the app/DB, not network transfer of a big file.
SAMPLE_JPEG = bytes.fromhex("ffd8ffe000104a46494600010101006000600000") + b"\x00" * 2048


class ReceiptUser(HttpUser):
    """
    Simulates a client of the receipt verification API.

    on_start uploads one receipt to get a real receipt_id, then extract/
    validate/health are exercised repeatedly using that id — mirroring a
    realistic usage pattern (upload once, query status/details many times).
    """

    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.receipt_id = None
        self._upload_one()

    def _upload_one(self):
        files = {"file": ("receipt.jpg", io.BytesIO(SAMPLE_JPEG), "image/jpeg")}
        with self.client.post(
            "/upload-receipt", headers=AUTH_HEADERS, files=files,
            name="/upload-receipt", catch_response=True,
        ) as resp:
            if resp.status_code == 201:
                self.receipt_id = resp.json().get("receipt_id")
                resp.success()
            else:
                resp.failure(f"upload failed: {resp.status_code} {resp.text}")

    @task(4)
    def health(self):
        self.client.get("/health", name="/health")

    @task(3)
    def extract(self):
        if not self.receipt_id:
            return
        self.client.post(
            "/extract", headers=JSON_HEADERS,
            json={"receipt_id": self.receipt_id}, name="/extract",
        )

    @task(3)
    def validate(self):
        if not self.receipt_id:
            return
        self.client.post(
            "/validate", headers=JSON_HEADERS,
            json={"receipt_id": self.receipt_id}, name="/validate",
        )

    @task(1)
    def upload(self):
        self._upload_one()