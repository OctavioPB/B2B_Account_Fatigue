"""Locust load test for the harmoni FastAPI.

Sprint 10 acceptance gate:
  - 500 concurrent users
  - p99 latency < 200ms for all endpoints under sustained load
  - Zero 5xx errors during the run

Run:
    locust -f infra/load_tests/locustfile.py \
           --host=http://localhost:8000 \
           --users=500 --spawn-rate=50 \
           --run-time=5m --headless \
           --html=infra/load_tests/report.html

Environment variables:
    HARMONI_LOAD_TOKEN   — valid JWT for the load-test tenant
    HARMONI_LOAD_DOMAINS — comma-separated domains to test (default: acme.com,globex.com)
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, task


_TOKEN   = os.getenv("HARMONI_LOAD_TOKEN", "load-test-jwt-placeholder")
_DOMAINS = os.getenv("HARMONI_LOAD_DOMAINS", "acme.com,globex.com,initech.com").split(",")
_HEADERS = {"Authorization": f"Bearer {_TOKEN}", "Content-Type": "application/json"}


class HarmoniApiUser(HttpUser):
    """Simulates a RevOps dashboard user browsing accounts and checking scores."""

    wait_time = between(0.1, 0.5)  # 100–500ms think time between requests

    # ---------------------------------------------------------------------------
    # Read-heavy tasks — weighted to reflect real dashboard usage pattern
    # ---------------------------------------------------------------------------

    @task(10)
    def get_account_summary(self):
        domain = random.choice(_DOMAINS)
        with self.client.get(
            f"/v1/accounts/{domain}",
            headers=_HEADERS,
            name="/v1/accounts/[domain]",
            catch_response=True,
        ) as r:
            if r.status_code == 200:
                r.success()
            elif r.status_code in (401, 403, 404):
                r.failure(f"Unexpected {r.status_code} on {domain}")
            else:
                r.failure(f"Server error {r.status_code}")

    @task(8)
    def get_fatigue_score(self):
        domain = random.choice(_DOMAINS)
        with self.client.get(
            f"/v1/accounts/{domain}/fatigue",
            headers=_HEADERS,
            name="/v1/accounts/[domain]/fatigue",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"{r.status_code}")

    @task(8)
    def get_intent_score(self):
        domain = random.choice(_DOMAINS)
        with self.client.get(
            f"/v1/accounts/{domain}/intent",
            headers=_HEADERS,
            name="/v1/accounts/[domain]/intent",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"{r.status_code}")

    @task(6)
    def get_nba(self):
        domain = random.choice(_DOMAINS)
        with self.client.get(
            f"/v1/accounts/{domain}/nba",
            headers=_HEADERS,
            name="/v1/accounts/[domain]/nba",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"{r.status_code}")

    @task(4)
    def list_accounts(self):
        with self.client.get(
            "/v1/accounts?page=1&page_size=50",
            headers=_HEADERS,
            name="/v1/accounts",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"{r.status_code}")

    @task(2)
    def list_webhooks(self):
        with self.client.get(
            "/v1/webhooks",
            headers=_HEADERS,
            name="/v1/webhooks",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"{r.status_code}")

    # ---------------------------------------------------------------------------
    # Write tasks — lower weight, but must stay < 200ms p99
    # ---------------------------------------------------------------------------

    @task(2)
    def ingest_signal(self):
        domain = random.choice(_DOMAINS)
        with self.client.post(
            f"/v1/accounts/{domain}/signals",
            json={
                "member_email": f"load-test-{random.randint(1, 100)}@{domain}",
                "signal_type": random.choice(["email_open", "page_view", "pricing_page_view"]),
                "channel": random.choice(["email", "web"]),
                "occurred_at": "2024-07-01T10:00:00Z",
            },
            headers=_HEADERS,
            name="/v1/accounts/[domain]/signals",
            catch_response=True,
        ) as r:
            if r.status_code not in (200, 202):
                r.failure(f"{r.status_code}: {r.text[:200]}")

    # ---------------------------------------------------------------------------
    # Health check — always fast, validates liveness under load
    # ---------------------------------------------------------------------------

    @task(1)
    def health_check(self):
        with self.client.get("/health", name="/health", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"Health check failed: {r.status_code}")
            elif r.json().get("status") != "ok":
                r.failure("Health check returned non-ok status")
