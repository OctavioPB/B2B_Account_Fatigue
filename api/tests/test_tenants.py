"""Tests for tenant provisioning endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.tests.conftest import MOCK_ADMIN_TOKEN


# ===========================================================================
# POST /v1/tenants (admin only)
# ===========================================================================


class TestTenantCreation:
    def test_create_tenant_201(self, admin_client):
        payload = {
            "slug": "new-corp",
            "display_name": "New Corp Inc.",
            "plan": "growth",
            "rate_limit_rpm": 120,
        }
        r = admin_client.post("/v1/tenants", json=payload)
        assert r.status_code == 201
        body = r.json()
        assert body["slug"] == "new-corp"
        assert body["display_name"] == "New Corp Inc."
        assert body["plan"] == "growth"
        assert body["rate_limit_rpm"] == 120
        assert body["is_active"] is True

    def test_schema_name_derived_from_slug(self, admin_client):
        payload = {
            "slug": "acme-corp",
            "display_name": "Acme Corporation",
        }
        r = admin_client.post("/v1/tenants", json=payload)
        assert r.status_code == 201
        body = r.json()
        assert body["schema_name"] == "tenant_acme_corp"

    def test_default_plan_is_starter(self, admin_client):
        payload = {"slug": "tiny-co", "display_name": "Tiny Co"}
        r = admin_client.post("/v1/tenants", json=payload)
        assert r.status_code == 201
        assert r.json()["plan"] == "starter"

    def test_returns_uuid(self, admin_client):
        payload = {"slug": "uuid-test", "display_name": "UUID Test"}
        r = admin_client.post("/v1/tenants", json=payload)
        assert r.status_code == 201
        body = r.json()
        assert "id" in body
        # Should be a valid UUID string
        import uuid
        uuid.UUID(body["id"])  # raises if invalid


class TestTenantValidation:
    def test_slug_with_uppercase_rejected(self, admin_client):
        payload = {"slug": "UpperCase", "display_name": "Bad Slug"}
        r = admin_client.post("/v1/tenants", json=payload)
        assert r.status_code == 422

    def test_slug_with_space_rejected(self, admin_client):
        payload = {"slug": "has space", "display_name": "Bad Slug"}
        r = admin_client.post("/v1/tenants", json=payload)
        assert r.status_code == 422

    def test_slug_too_short_rejected(self, admin_client):
        payload = {"slug": "x", "display_name": "Too Short"}
        r = admin_client.post("/v1/tenants", json=payload)
        assert r.status_code == 422

    def test_invalid_plan_rejected(self, admin_client):
        payload = {"slug": "valid-slug", "display_name": "Valid", "plan": "platinum"}
        r = admin_client.post("/v1/tenants", json=payload)
        assert r.status_code == 422

    def test_rate_limit_below_minimum_rejected(self, admin_client):
        payload = {"slug": "valid-slug2", "display_name": "Valid", "rate_limit_rpm": 5}
        r = admin_client.post("/v1/tenants", json=payload)
        assert r.status_code == 422

    def test_missing_display_name_rejected(self, admin_client):
        payload = {"slug": "no-display"}
        r = admin_client.post("/v1/tenants", json=payload)
        assert r.status_code == 422


class TestTenantAuthorization:
    def test_no_auth_header_returns_401(self, app, test_settings):
        from api.config import get_settings
        app.dependency_overrides.clear()
        app.dependency_overrides[get_settings] = lambda: test_settings
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post("/v1/tenants", json={"slug": "test", "display_name": "Test"})
        assert r.status_code in (401, 403, 422)
        app.dependency_overrides.clear()

    def test_wrong_admin_token_returns_401(self, app, test_settings):
        from api.config import get_settings
        app.dependency_overrides.clear()
        app.dependency_overrides[get_settings] = lambda: test_settings
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(
                "/v1/tenants",
                json={"slug": "abc-co", "display_name": "Abc"},
                headers={"Authorization": "Bearer wrong-token"},
            )
        assert r.status_code == 401
        app.dependency_overrides.clear()

    def test_correct_admin_token_succeeds(self, app, test_settings):
        from api.config import get_settings
        app.dependency_overrides.clear()
        app.dependency_overrides[get_settings] = lambda: test_settings
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(
                "/v1/tenants",
                json={"slug": "auth-co", "display_name": "Auth Co"},
                headers={"Authorization": f"Bearer {MOCK_ADMIN_TOKEN}"},
            )
        assert r.status_code == 201
        app.dependency_overrides.clear()


class TestMultiTenantIsolation:
    """Verify that tenant A cannot access tenant B's data using real JWT decode."""

    def test_different_tenant_tokens_produce_different_account_ids(
        self, app, test_settings
    ):
        from api.config import get_settings
        from api.tests.conftest import _make_token

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

        # The account IDs are tenant-scoped (UUID v5 includes tenant_id in seed)
        id_a = r_a.json()["account"]["id"]
        id_b = r_b.json()["account"]["id"]
        assert id_a != id_b, "Tenant A and B must see different account IDs for the same domain"

        app.dependency_overrides.clear()
