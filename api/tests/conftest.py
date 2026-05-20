"""pytest fixtures for the harmoni API test suite.

All tests use a TestClient wired to a mock tenant so no real database,
Redis, or external services are required.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import jwt
import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app
from api.middleware.auth import TenantContext, get_current_tenant, require_admin

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOCK_TENANT_ID = "11111111-1111-1111-1111-111111111111"
MOCK_TENANT_SLUG = "test-corp"
MOCK_SCHEMA = "tenant_test_corp"
MOCK_ADMIN_TOKEN = "test-admin-secret"
JWT_SECRET = "test-jwt-secret-32-chars-minimum!"
JWT_ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# Settings override
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings(
        database_url="postgresql://test:test@localhost:5432/harmoni_test",
        api_secret_key=JWT_SECRET,
        jwt_algorithm=JWT_ALGORITHM,
        harmoni_admin_token=MOCK_ADMIN_TOKEN,
        redis_url="redis://localhost:6379/15",
        rate_limit_enabled=False,
        log_json=False,
        log_level="WARNING",
    )


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _make_token(
    tenant_id: str = MOCK_TENANT_ID,
    slug: str = MOCK_TENANT_SLUG,
    schema: str = MOCK_SCHEMA,
    plan: str = "growth",
    rpm: int = 60,
    expired: bool = False,
) -> str:
    now = datetime.now(tz=timezone.utc)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
    payload = {
        "sub": tenant_id,
        "slug": slug,
        "schema": schema,
        "plan": plan,
        "rpm": rpm,
        "iat": now,
        "exp": exp,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@pytest.fixture
def valid_token() -> str:
    return _make_token()


@pytest.fixture
def expired_token() -> str:
    return _make_token(expired=True)


@pytest.fixture
def other_tenant_token() -> str:
    return _make_token(
        tenant_id="22222222-2222-2222-2222-222222222222",
        slug="other-corp",
        schema="tenant_other_corp",
    )


# ---------------------------------------------------------------------------
# Mock tenant context
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_tenant() -> TenantContext:
    return TenantContext(
        tenant_id=MOCK_TENANT_ID,
        tenant_slug=MOCK_TENANT_SLUG,
        schema_name=MOCK_SCHEMA,
        plan="growth",
        rate_limit_rpm=60,
    )


# ---------------------------------------------------------------------------
# Test app and client
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def app(test_settings):
    return create_app(settings=test_settings)


@pytest.fixture
def client(app, mock_tenant, test_settings) -> TestClient:
    """TestClient with auth dependency overridden to return mock_tenant."""
    app.dependency_overrides[get_current_tenant] = lambda: mock_tenant
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def authed_client(client, valid_token) -> TestClient:
    """TestClient that sends a real JWT (dependency NOT overridden)."""
    return client


@pytest.fixture
def admin_client(app, test_settings) -> TestClient:
    """TestClient with admin dependency overridden."""
    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_settings] = lambda: test_settings
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()
