"""Security tests — OWASP header compliance and tenant isolation.

Covers:
  - OWASP ZAP HIGH/CRITICAL header requirements
  - Cross-tenant data access prevention (penetration test)
  - Missing auth / malformed token responses
  - SQL injection attempt (422, not 500)
  - Circuit breaker state exposure on /health
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.tests.conftest import MOCK_ADMIN_TOKEN, _make_token, MOCK_TENANT_ID


# ===========================================================================
# OWASP Security Headers
# ===========================================================================

class TestOWASPHeaders:
    """Verify every response carries the headers required by OWASP ASVS v4.0.

    These tests mirror what OWASP ZAP checks for HIGH/CRITICAL findings.
    All must pass before beta launch (Sprint 10 DoD).
    """

    def test_hsts_present(self, client):
        r = client.get("/health")
        assert "strict-transport-security" in r.headers
        assert "max-age=" in r.headers["strict-transport-security"]

    def test_hsts_includes_subdomains(self, client):
        r = client.get("/health")
        assert "includeSubDomains" in r.headers.get("strict-transport-security", "")

    def test_x_content_type_options_nosniff(self, client):
        r = client.get("/health")
        assert r.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options_deny(self, client):
        r = client.get("/health")
        assert r.headers.get("x-frame-options") == "DENY"

    def test_csp_present(self, client):
        r = client.get("/health")
        assert "content-security-policy" in r.headers

    def test_csp_api_denies_frame_ancestors(self, client):
        r = client.get("/v1/accounts")
        csp = r.headers.get("content-security-policy", "")
        assert "frame-ancestors 'none'" in csp

    def test_cache_control_no_store(self, client):
        r = client.get("/v1/accounts")
        assert "no-store" in r.headers.get("cache-control", "")

    def test_referrer_policy_present(self, client):
        r = client.get("/health")
        assert "referrer-policy" in r.headers

    def test_permissions_policy_present(self, client):
        r = client.get("/health")
        assert "permissions-policy" in r.headers

    def test_server_header_absent(self, client):
        r = client.get("/health")
        assert "server" not in r.headers

    def test_x_powered_by_absent(self, client):
        r = client.get("/health")
        assert "x-powered-by" not in r.headers

    def test_all_endpoints_have_security_headers(self, client):
        endpoints = [
            "/health",
            "/v1/accounts",
            "/v1/accounts/acme.com",
            "/v1/accounts/acme.com/fatigue",
            "/v1/accounts/acme.com/nba",
        ]
        for path in endpoints:
            r = client.get(path)
            assert "x-content-type-options" in r.headers, f"Missing on {path}"
            assert "strict-transport-security" in r.headers, f"Missing on {path}"


# ===========================================================================
# Cross-Tenant Isolation (Penetration Test)
# ===========================================================================

class TestTenantIsolation:
    """Verify that tenant A cannot read or write tenant B's data.

    These are the checks from the Sprint 10 penetration test requirement:
    'Confirm tenant isolation with penetration test (cross-tenant data access attempt)'
    """

    def test_different_tenants_see_different_account_ids(self, app, test_settings):
        from api.config import get_settings
        app.dependency_overrides.clear()
        app.dependency_overrides[get_settings] = lambda: test_settings

        token_a = _make_token(
            tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            slug="tenant-a",
            schema="tenant_a",
        )
        token_b = _make_token(
            tenant_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            slug="tenant-b",
            schema="tenant_b",
        )

        with TestClient(app, raise_server_exceptions=False) as c:
            r_a = c.get("/v1/accounts/acme.com", headers={"Authorization": f"Bearer {token_a}"})
            r_b = c.get("/v1/accounts/acme.com", headers={"Authorization": f"Bearer {token_b}"})

        assert r_a.status_code == 200
        assert r_b.status_code == 200
        assert r_a.json()["account"]["id"] != r_b.json()["account"]["id"]

        app.dependency_overrides.clear()

    def test_no_token_returns_401_not_data(self, app, test_settings):
        from api.config import get_settings
        app.dependency_overrides.clear()
        app.dependency_overrides[get_settings] = lambda: test_settings

        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/v1/accounts/acme.com")

        assert r.status_code in (401, 403)
        assert "account" not in r.text

        app.dependency_overrides.clear()

    def test_expired_token_returns_401_not_data(self, app, test_settings):
        from api.config import get_settings
        app.dependency_overrides.clear()
        app.dependency_overrides[get_settings] = lambda: test_settings

        expired = _make_token(expired=True)
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/v1/accounts/acme.com", headers={"Authorization": f"Bearer {expired}"})

        assert r.status_code == 401
        assert "account" not in r.text

        app.dependency_overrides.clear()

    def test_tampered_token_returns_401(self, app, test_settings):
        from api.config import get_settings
        app.dependency_overrides.clear()
        app.dependency_overrides[get_settings] = lambda: test_settings

        valid = _make_token()
        parts = valid.split(".")
        # Modify the payload to claim a different tenant_id
        import base64, json
        fake_payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "hacked-tenant", "slug": "evil", "schema": "evil", "plan": "enterprise", "rpm": 9999}).encode()
        ).rstrip(b"=").decode()
        tampered = f"{parts[0]}.{fake_payload}.fakesig"

        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/v1/accounts/acme.com", headers={"Authorization": f"Bearer {tampered}"})

        assert r.status_code == 401

        app.dependency_overrides.clear()

    def test_webhook_delete_by_wrong_tenant_returns_404(self, client, app, test_settings):
        """Attempting to delete another tenant's webhook must return 404, not 403.

        Returning 404 prevents tenant enumeration — the attacker can't even tell
        whether the webhook exists.
        """
        from api.middleware.auth import TenantContext, get_current_tenant
        from api.config import get_settings

        # Register webhook as tenant A (mock_tenant fixture)
        reg = client.post(
            "/v1/webhooks",
            json={"target_url": "https://secure.example.com/h", "event_types": ["nba.created"]},
        ).json()
        webhook_id = reg["id"]

        # Try to delete as tenant B
        other = TenantContext(
            tenant_id="deadbeef-dead-dead-dead-deaddeadbeef",
            tenant_slug="evil-tenant",
            schema_name="tenant_evil",
            plan="starter",
            rate_limit_rpm=60,
        )
        app.dependency_overrides[get_current_tenant] = lambda: other
        app.dependency_overrides[get_settings] = lambda: test_settings

        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.delete(f"/v1/webhooks/{webhook_id}")

        assert r.status_code == 404

        app.dependency_overrides.clear()


# ===========================================================================
# Injection attack surface
# ===========================================================================

class TestInjectionPrevention:
    """Domain parameter is normalised before any DB lookup — SQLi must return 422."""

    def test_sql_injection_in_domain_returns_422(self, client):
        r = client.get("/v1/accounts/'; DROP TABLE accounts; --")
        # Either 422 (invalid domain) or 404 — never 500
        assert r.status_code in (422, 404)

    def test_script_injection_in_domain_returns_non_500(self, client):
        r = client.get("/v1/accounts/<script>alert(1)</script>.com")
        assert r.status_code != 500

    def test_path_traversal_attempt(self, client):
        r = client.get("/v1/accounts/../../etc/passwd")
        assert r.status_code in (404, 422)

    def test_null_byte_in_domain(self, client):
        r = client.get("/v1/accounts/acme\x00.com")
        assert r.status_code != 500

    def test_signal_body_rejects_xss_in_email_field(self, client):
        payload = {
            "member_email": "<script>alert(1)</script>@acme.com",
            "signal_type": "email_open",
            "channel": "email",
            "occurred_at": "2024-07-01T10:00:00Z",
        }
        r = client.post("/v1/accounts/acme.com/signals", json=payload)
        assert r.status_code == 422


# ===========================================================================
# Circuit breaker health surface
# ===========================================================================

class TestCircuitBreakerIntegration:
    def test_health_endpoint_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_returns_ok_status(self, client):
        r = client.get("/health")
        assert r.json().get("status") == "ok"


# ===========================================================================
# Admin endpoint protection
# ===========================================================================

class TestAdminEndpointProtection:
    def test_tenant_create_with_wrong_token_returns_401(self, app, test_settings):
        from api.config import get_settings
        app.dependency_overrides.clear()
        app.dependency_overrides[get_settings] = lambda: test_settings

        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(
                "/v1/tenants",
                json={"slug": "attacker", "display_name": "Attacker"},
                headers={"Authorization": "Bearer wrong-token"},
            )
        assert r.status_code == 401
        app.dependency_overrides.clear()

    def test_tenant_create_without_auth_returns_401(self, app, test_settings):
        from api.config import get_settings
        app.dependency_overrides.clear()
        app.dependency_overrides[get_settings] = lambda: test_settings

        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post("/v1/tenants", json={"slug": "anon", "display_name": "Anon"})
        assert r.status_code in (401, 403, 422)
        app.dependency_overrides.clear()

    def test_correct_admin_token_creates_tenant(self, app, test_settings):
        from api.config import get_settings
        app.dependency_overrides.clear()
        app.dependency_overrides[get_settings] = lambda: test_settings

        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(
                "/v1/tenants",
                json={"slug": "legit-co", "display_name": "Legit Co"},
                headers={"Authorization": f"Bearer {MOCK_ADMIN_TOKEN}"},
            )
        assert r.status_code == 201
        app.dependency_overrides.clear()
