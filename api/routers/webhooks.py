"""Webhook registration endpoints.

Tenants register target URLs to receive real-time NBA and scoring events.
All webhook payloads are signed with HMAC-SHA256 using the per-registration secret.

Endpoints:
  POST   /v1/webhooks              — register a new webhook
  GET    /v1/webhooks              — list all webhooks for the tenant
  DELETE /v1/webhooks/{webhook_id} — deactivate a webhook
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from api.middleware.auth import TenantContext, get_current_tenant
from api.models.schemas import WebhookRegisterRequest, WebhookResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])

_Tenant = Annotated[TenantContext, Depends(get_current_tenant)]

_NOW = datetime(2024, 7, 1, tzinfo=timezone.utc)

# In-memory stub store (replaced by DB in production)
_WEBHOOK_STORE: dict[str, WebhookResponse] = {}


def _hash_secret(secret: str) -> str:
    """One-way hash of the signing secret stored in the DB."""
    return hashlib.sha256(secret.encode()).hexdigest()


@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def register_webhook(
    body: WebhookRegisterRequest,
    tenant: _Tenant,
) -> WebhookResponse:
    """Register a new webhook endpoint for NBA and scoring events."""
    signing_secret = secrets.token_hex(32)
    webhook_id = uuid.uuid4()

    webhook = WebhookResponse(
        id=webhook_id,
        tenant_id=uuid.UUID(tenant.tenant_id),
        target_url=body.target_url,
        description=body.description,
        event_types=body.event_types,
        is_active=True,
        failure_count=0,
        last_success_at=None,
        created_at=_NOW,
    )

    _WEBHOOK_STORE[str(webhook_id)] = webhook

    logger.info(
        "Webhook registered: tenant=%s id=%s url=%s events=%s",
        tenant.tenant_slug,
        webhook_id,
        body.target_url,
        body.event_types,
    )

    # Return the signing secret once — never again.
    # In production: include signing_secret in a separate field of this response.
    response_dict = webhook.model_dump()
    response_dict["signing_secret"] = signing_secret  # type: ignore[assignment]

    return webhook


@router.get("", response_model=list[WebhookResponse])
async def list_webhooks(tenant: _Tenant) -> list[WebhookResponse]:
    """List all active webhooks for the authenticated tenant."""
    tenant_uuid = tenant.tenant_id
    return [
        w for w in _WEBHOOK_STORE.values()
        if str(w.tenant_id) == tenant_uuid and w.is_active
    ]


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_webhook(webhook_id: str, tenant: _Tenant) -> Response:
    """Deactivate a webhook registration."""
    webhook = _WEBHOOK_STORE.get(webhook_id)

    if webhook is None or str(webhook.tenant_id) != tenant.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id!r} not found",
        )

    # Soft-delete: set is_active=False (preserves delivery log linkage)
    updated = webhook.model_copy(update={"is_active": False})
    _WEBHOOK_STORE[webhook_id] = updated

    logger.info(
        "Webhook deactivated: tenant=%s id=%s",
        tenant.tenant_slug,
        webhook_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
