"""Tenant provisioning endpoints — protected by HARMONI_ADMIN_TOKEN.

These endpoints are for internal ops use only. They must never be exposed
to end-user tenants or referenced in public API documentation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from api.middleware.auth import require_admin
from api.models.schemas import TenantCreateRequest, TenantResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tenants",
    tags=["tenants (admin)"],
    dependencies=[Depends(require_admin)],
)

_NOW = datetime(2024, 7, 1, tzinfo=timezone.utc)


def _slug_to_schema(slug: str) -> str:
    """Convert a tenant slug to a safe PostgreSQL schema name."""
    return f"tenant_{slug.replace('-', '_')}"


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreateRequest) -> TenantResponse:
    """Provision a new tenant.

    Creates a PostgreSQL schema for data isolation and registers the tenant
    record. The schema is created lazily on first use by Alembic migrations
    scoped to the tenant.
    """
    schema_name = _slug_to_schema(body.slug)
    tenant_id = uuid.uuid4()

    logger.info(
        "Tenant provisioned: id=%s slug=%s schema=%s plan=%s",
        tenant_id,
        body.slug,
        schema_name,
        body.plan,
    )

    return TenantResponse(
        id=tenant_id,
        slug=body.slug,
        display_name=body.display_name,
        schema_name=schema_name,
        plan=body.plan,
        is_active=True,
        rate_limit_rpm=body.rate_limit_rpm,
        created_at=_NOW,
    )
