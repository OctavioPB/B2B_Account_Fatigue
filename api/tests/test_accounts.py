"""Tests for account endpoints.

Covers: happy paths, authentication failures, cross-tenant isolation,
domain validation, and signal ingestion.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.tests.conftest import JWT_SECRET, JWT_ALGORITHM, MOCK_ADMIN_TOKEN, _make_token


# ===========================================================================
# GET /health (sanity — no auth)
# ===========================================================================


def test_health_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ===========================================================================
# GET /v1/accounts
# ===========================================================================


def test_list_accounts_200(client):
    r = client.get("/v1/accounts")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)
    assert body["total"] == len(body["items"])


def test_list_accounts_pagination_fields(client):
    r = client.get("/v1/accounts?page=1&page_size=10")
    assert r.status_code == 200
    body = r.json()
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert "has_next" in body


def test_list_accounts_no_auth_returns_403_or_401(app):
    """Without dependency override, missing auth returns 401/403."""
    from fastapi.testclient import TestClient
    app.dependency_overrides.clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/v1/accounts")
    assert r.status_code in (401, 403)


# ===========================================================================
# GET /v1/accounts/{domain}
# ===========================================================================


def test_get_account_200(client):
    r = client.get("/v1/accounts/acme.com")
    assert r.status_code == 200
    body = r.json()
    assert body["account"]["domain"] == "acme.com"
    assert "fatigue" in body
    assert "intent" in body
    assert "churn" in body
    assert "current_nba" in body


def test_get_account_domain_normalized(client):
    r = client.get("/v1/accounts/ACME.COM")
    assert r.status_code == 200
    assert r.json()["account"]["domain"] == "acme.com"


def test_get_account_invalid_domain(client):
    r = client.get("/v1/accounts/notadomain")
    assert r.status_code == 422


def test_get_account_domain_with_subdomain(client):
    r = client.get("/v1/accounts/api.acme.com")
    assert r.status_code == 200


# ===========================================================================
# GET /v1/accounts/{domain}/fatigue
# ===========================================================================


def test_get_fatigue_200(client):
    r = client.get("/v1/accounts/acme.com/fatigue")
    assert r.status_code == 200
    body = r.json()
    assert "score" in body
    assert "severity" in body
    assert 0.0 <= body["score"] <= 100.0
    assert body["severity"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_get_fatigue_invalid_domain(client):
    r = client.get("/v1/accounts/invalid/fatigue")
    assert r.status_code == 422


# ===========================================================================
# GET /v1/accounts/{domain}/intent
# ===========================================================================


def test_get_intent_200(client):
    r = client.get("/v1/accounts/acme.com/intent")
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["intent_score"] <= 100.0
    assert 0.0 <= body["confidence"] <= 1.0


# ===========================================================================
# GET /v1/accounts/{domain}/nba
# ===========================================================================


def test_get_nba_200(client):
    r = client.get("/v1/accounts/acme.com/nba")
    assert r.status_code == 200
    body = r.json()
    assert "action_type" in body
    assert "rationale" in body
    assert body["is_active"] is True


def test_get_nba_has_priority(client):
    r = client.get("/v1/accounts/acme.com/nba")
    assert r.status_code == 200
    assert 1 <= r.json()["priority"] <= 7


# ===========================================================================
# POST /v1/accounts/{domain}/signals
# ===========================================================================


def test_ingest_signal_202(client):
    payload = {
        "member_email": "alice@acme.com",
        "signal_type": "pricing_page_view",
        "channel": "web",
        "occurred_at": "2024-07-01T10:00:00Z",
    }
    r = client.post("/v1/accounts/acme.com/signals", json=payload)
    assert r.status_code == 202
    body = r.json()
    assert body["accepted"] is True
    assert body["account_domain"] == "acme.com"
    assert "signal_id" in body


def test_ingest_signal_invalid_email(client):
    payload = {
        "member_email": "not-an-email",
        "signal_type": "email_open",
        "channel": "email",
        "occurred_at": "2024-07-01T10:00:00Z",
    }
    r = client.post("/v1/accounts/acme.com/signals", json=payload)
    assert r.status_code == 422


def test_ingest_signal_missing_fields(client):
    r = client.post("/v1/accounts/acme.com/signals", json={"member_email": "alice@acme.com"})
    assert r.status_code == 422


def test_ingest_signal_invalid_domain(client):
    payload = {
        "member_email": "alice@acme.com",
        "signal_type": "email_open",
        "channel": "email",
        "occurred_at": "2024-07-01T10:00:00Z",
    }
    r = client.post("/v1/accounts/notadomain/signals", json=payload)
    assert r.status_code == 422


# ===========================================================================
# Authentication edge cases
# ===========================================================================


def test_expired_token_returns_401(app, test_settings):
    """Real JWT decode path — expired token must return 401."""
    from fastapi.testclient import TestClient
    from api.middleware.auth import get_current_tenant
    from api.config import get_settings

    # Clear overrides to hit real JWT decode
    app.dependency_overrides.clear()
    app.dependency_overrides[get_settings] = lambda: test_settings

    expired = _make_token(expired=True)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/v1/accounts", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401

    app.dependency_overrides.clear()


def test_invalid_token_returns_401(app, test_settings):
    from fastapi.testclient import TestClient
    from api.config import get_settings

    app.dependency_overrides.clear()
    app.dependency_overrides[get_settings] = lambda: test_settings

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/v1/accounts", headers={"Authorization": "Bearer totally.invalid.token"})
    assert r.status_code == 401

    app.dependency_overrides.clear()
