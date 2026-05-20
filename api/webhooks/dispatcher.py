"""Outbound webhook dispatcher.

Signs each payload with HMAC-SHA256 and delivers it via async httpx POST.
Retries up to max_retries times with exponential back-off (capped at 30s).
One dispatcher failure does not affect sibling webhooks for the same event.

Signing header: X-Harmoni-Signature: sha256=<hex_digest>
Payload shape:
  {
    "event": "<event_type>",
    "tenant_id": "<uuid>",
    "occurred_at": "<iso8601>",
    "data": { ... }
  }
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SIGNATURE_HEADER = "X-Harmoni-Signature"
_TIMEOUT = 5.0  # seconds


@dataclass(frozen=True)
class WebhookTarget:
    """Minimal descriptor for a registered webhook."""

    webhook_id: str
    target_url: str
    secret: str          # unhashed HMAC secret (loaded from secure store at dispatch time)
    event_types: list[str]


@dataclass
class DeliveryResult:
    webhook_id: str
    target_url: str
    success: bool
    http_status: int | None = None
    attempt_count: int = 0
    error: str | None = None


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Return sha256=<hex> HMAC signature for payload_bytes."""
    sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _build_payload(event_type: str, tenant_id: str, data: dict[str, Any]) -> bytes:
    envelope = {
        "event": event_type,
        "tenant_id": tenant_id,
        "occurred_at": datetime.now(tz=timezone.utc).isoformat(),
        "data": data,
    }
    return json.dumps(envelope, default=str).encode()


async def _deliver_once(
    client: httpx.AsyncClient,
    target: WebhookTarget,
    payload_bytes: bytes,
    signature: str,
) -> tuple[bool, int | None, str | None]:
    """Single delivery attempt. Returns (success, http_status, error_detail)."""
    try:
        response = await client.post(
            target.target_url,
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                _SIGNATURE_HEADER: signature,
            },
            timeout=_TIMEOUT,
        )
        success = 200 <= response.status_code < 300
        return success, response.status_code, None if success else response.text[:500]
    except httpx.TimeoutException:
        return False, None, "Delivery timeout"
    except httpx.RequestError as exc:
        return False, None, str(exc)


async def dispatch_event(
    target: WebhookTarget,
    event_type: str,
    tenant_id: str,
    data: dict[str, Any],
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> DeliveryResult:
    """Deliver one event to one webhook target with retry.

    Back-off: delay = min(base_delay * 2^attempt, 30) seconds.
    """
    payload_bytes = _build_payload(event_type, tenant_id, data)
    signature = _sign_payload(payload_bytes, target.secret)

    attempt = 0
    async with httpx.AsyncClient() as client:
        while attempt < max_retries:
            attempt += 1
            success, http_status, error = await _deliver_once(
                client, target, payload_bytes, signature
            )

            if success:
                logger.info(
                    "Webhook delivered: id=%s url=%s event=%s attempt=%d status=%d",
                    target.webhook_id,
                    target.target_url,
                    event_type,
                    attempt,
                    http_status,
                )
                return DeliveryResult(
                    webhook_id=target.webhook_id,
                    target_url=target.target_url,
                    success=True,
                    http_status=http_status,
                    attempt_count=attempt,
                )

            delay = min(base_delay * (2 ** (attempt - 1)), 30.0)
            logger.warning(
                "Webhook delivery failed: id=%s attempt=%d/%d status=%s error=%s — retrying in %.1fs",
                target.webhook_id,
                attempt,
                max_retries,
                http_status,
                error,
                delay,
            )
            if attempt < max_retries:
                await asyncio.sleep(delay)

    logger.error(
        "Webhook delivery exhausted: id=%s url=%s event=%s attempts=%d",
        target.webhook_id,
        target.target_url,
        event_type,
        attempt,
    )
    return DeliveryResult(
        webhook_id=target.webhook_id,
        target_url=target.target_url,
        success=False,
        http_status=http_status,
        attempt_count=attempt,
        error=error,
    )


async def fan_out(
    targets: list[WebhookTarget],
    event_type: str,
    tenant_id: str,
    data: dict[str, Any],
    max_retries: int = 3,
) -> list[DeliveryResult]:
    """Deliver one event to all matching webhook targets concurrently.

    Targets that don't subscribe to event_type are skipped.
    One failure does not block others.
    """
    subscribed = [t for t in targets if event_type in t.event_types]
    if not subscribed:
        return []

    tasks = [
        dispatch_event(t, event_type, tenant_id, data, max_retries=max_retries)
        for t in subscribed
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final: list[DeliveryResult] = []
    for target, result in zip(subscribed, results):
        if isinstance(result, BaseException):
            logger.error("Unexpected error dispatching to %s: %s", target.target_url, result)
            final.append(
                DeliveryResult(
                    webhook_id=target.webhook_id,
                    target_url=target.target_url,
                    success=False,
                    error=str(result),
                    attempt_count=0,
                )
            )
        else:
            final.append(result)

    return final
