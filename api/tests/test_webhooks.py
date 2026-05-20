"""Tests for webhook registration endpoints and dispatcher.

Covers: registration, listing, deactivation, delivery signing,
fan-out, and failure isolation.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx

from api.webhooks.dispatcher import (
    DeliveryResult,
    WebhookTarget,
    _sign_payload,
    _build_payload,
    dispatch_event,
    fan_out,
)


# ===========================================================================
# POST /v1/webhooks
# ===========================================================================


class TestWebhookRegistration:
    def test_register_webhook_201(self, client):
        payload = {
            "target_url": "https://hooks.example.com/harmoni",
            "description": "Test hook",
            "event_types": ["nba.created", "fatigue.critical"],
        }
        r = client.post("/v1/webhooks", json=payload)
        assert r.status_code == 201
        body = r.json()
        assert body["target_url"] == "https://hooks.example.com/harmoni"
        assert set(body["event_types"]) == {"nba.created", "fatigue.critical"}
        assert body["is_active"] is True
        assert "id" in body

    def test_register_requires_https(self, client):
        payload = {
            "target_url": "http://insecure.example.com/hook",
            "event_types": ["nba.created"],
        }
        r = client.post("/v1/webhooks", json=payload)
        assert r.status_code == 422

    def test_register_invalid_event_type_rejected(self, client):
        payload = {
            "target_url": "https://hooks.example.com/hook",
            "event_types": ["not.a.real.event"],
        }
        r = client.post("/v1/webhooks", json=payload)
        assert r.status_code == 422

    def test_register_empty_event_types_rejected(self, client):
        payload = {
            "target_url": "https://hooks.example.com/hook",
            "event_types": [],
        }
        r = client.post("/v1/webhooks", json=payload)
        assert r.status_code == 422

    def test_register_deduplicates_event_types(self, client):
        payload = {
            "target_url": "https://hooks.example.com/dedup",
            "event_types": ["nba.created", "nba.created", "fatigue.high"],
        }
        r = client.post("/v1/webhooks", json=payload)
        assert r.status_code == 201
        event_types = r.json()["event_types"]
        assert len(event_types) == len(set(event_types))


# ===========================================================================
# GET /v1/webhooks
# ===========================================================================


class TestListWebhooks:
    def test_list_webhooks_200(self, client):
        # Register first
        client.post(
            "/v1/webhooks",
            json={"target_url": "https://list-test.example.com/h", "event_types": ["nba.created"]},
        )
        r = client.get("/v1/webhooks")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_returns_only_active(self, client):
        # Register and then delete
        reg = client.post(
            "/v1/webhooks",
            json={"target_url": "https://todelete.example.com/h", "event_types": ["nba.created"]},
        ).json()
        client.delete(f"/v1/webhooks/{reg['id']}")

        r = client.get("/v1/webhooks")
        assert r.status_code == 200
        ids = [w["id"] for w in r.json()]
        assert reg["id"] not in ids


# ===========================================================================
# DELETE /v1/webhooks/{webhook_id}
# ===========================================================================


class TestDeleteWebhook:
    def test_delete_webhook_204(self, client):
        reg = client.post(
            "/v1/webhooks",
            json={"target_url": "https://delete-me.example.com/h", "event_types": ["churn.high"]},
        ).json()
        r = client.delete(f"/v1/webhooks/{reg['id']}")
        assert r.status_code == 204

    def test_delete_nonexistent_returns_404(self, client):
        r = client.delete("/v1/webhooks/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_delete_wrong_tenant_returns_404(self, client, app, test_settings, mock_tenant):
        """A webhook owned by tenant A is not visible to tenant B."""
        from api.middleware.auth import TenantContext, get_current_tenant
        from api.config import get_settings

        # Register as original tenant
        app.dependency_overrides[get_current_tenant] = lambda: mock_tenant
        app.dependency_overrides[get_settings] = lambda: test_settings
        with httpx.Client(app=app, base_url="http://test") as c:
            pass  # just confirm setup is OK

        reg = client.post(
            "/v1/webhooks",
            json={"target_url": "https://tenant-a.example.com/h", "event_types": ["nba.created"]},
        ).json()
        webhook_id = reg["id"]

        # Now try to delete as a different tenant
        other = TenantContext(
            tenant_id="99999999-9999-9999-9999-999999999999",
            tenant_slug="other",
            schema_name="tenant_other",
            plan="starter",
            rate_limit_rpm=60,
        )
        app.dependency_overrides[get_current_tenant] = lambda: other
        with httpx.Client(app=app, base_url="http://test") as c2:
            r2 = c2.delete(f"/v1/webhooks/{webhook_id}")
        assert r2.status_code == 404


# ===========================================================================
# WebhookDispatcher unit tests
# ===========================================================================


class TestPayloadSigning:
    def test_sign_payload_format(self):
        sig = _sign_payload(b"hello", "secret")
        assert sig.startswith("sha256=")
        assert len(sig) == len("sha256=") + 64  # hex-encoded SHA-256

    def test_sign_payload_deterministic(self):
        assert _sign_payload(b"data", "key") == _sign_payload(b"data", "key")

    def test_sign_payload_different_secret_produces_different_sig(self):
        assert _sign_payload(b"data", "key1") != _sign_payload(b"data", "key2")

    def test_build_payload_contains_event_and_tenant(self):
        raw = _build_payload("nba.created", "tenant-uuid-123", {"action": "NURTURE"})
        payload = json.loads(raw)
        assert payload["event"] == "nba.created"
        assert payload["tenant_id"] == "tenant-uuid-123"
        assert payload["data"]["action"] == "NURTURE"
        assert "occurred_at" in payload


class TestDispatchEvent:
    @pytest.mark.asyncio
    async def test_successful_delivery(self):
        target = WebhookTarget(
            webhook_id="wh-1",
            target_url="https://hooks.example.com/test",
            secret="mysecret",
            event_types=["nba.created"],
        )

        with respx.mock:
            respx.post("https://hooks.example.com/test").mock(
                return_value=httpx.Response(200, text="ok")
            )
            result = await dispatch_event(target, "nba.created", "t-1", {"action": "NURTURE"})

        assert result.success is True
        assert result.http_status == 200
        assert result.attempt_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self):
        target = WebhookTarget(
            webhook_id="wh-2",
            target_url="https://retry.example.com/hook",
            secret="s",
            event_types=["nba.created"],
        )

        call_count = 0

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(503, text="unavailable")
            return httpx.Response(200, text="ok")

        with respx.mock:
            respx.post("https://retry.example.com/hook").mock(side_effect=side_effect)
            result = await dispatch_event(
                target, "nba.created", "t-1", {}, max_retries=3, base_delay=0.0
            )

        assert result.success is True
        assert result.attempt_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries_returns_failure(self):
        target = WebhookTarget(
            webhook_id="wh-3",
            target_url="https://always-fails.example.com/hook",
            secret="s",
            event_types=["nba.created"],
        )

        with respx.mock:
            respx.post("https://always-fails.example.com/hook").mock(
                return_value=httpx.Response(500, text="error")
            )
            result = await dispatch_event(
                target, "nba.created", "t-1", {}, max_retries=2, base_delay=0.0
            )

        assert result.success is False
        assert result.attempt_count == 2

    @pytest.mark.asyncio
    async def test_timeout_returns_failure(self):
        target = WebhookTarget(
            webhook_id="wh-4",
            target_url="https://slow.example.com/hook",
            secret="s",
            event_types=["nba.created"],
        )

        with respx.mock:
            respx.post("https://slow.example.com/hook").mock(
                side_effect=httpx.TimeoutException("timed out")
            )
            result = await dispatch_event(
                target, "nba.created", "t-1", {}, max_retries=1, base_delay=0.0
            )

        assert result.success is False
        assert "timeout" in (result.error or "").lower()


class TestFanOut:
    @pytest.mark.asyncio
    async def test_fan_out_delivers_to_subscribed_targets(self):
        t1 = WebhookTarget("wh-a", "https://a.example.com/h", "s1", ["nba.created"])
        t2 = WebhookTarget("wh-b", "https://b.example.com/h", "s2", ["nba.created"])
        t3 = WebhookTarget("wh-c", "https://c.example.com/h", "s3", ["fatigue.critical"])

        with respx.mock:
            respx.post("https://a.example.com/h").mock(return_value=httpx.Response(200))
            respx.post("https://b.example.com/h").mock(return_value=httpx.Response(200))
            results = await fan_out([t1, t2, t3], "nba.created", "tenant", {})

        # t3 is not subscribed to nba.created — only t1 and t2
        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_fan_out_no_subscribed_targets_returns_empty(self):
        t1 = WebhookTarget("wh-x", "https://x.example.com/h", "s", ["fatigue.high"])
        results = await fan_out([t1], "nba.created", "tenant", {})
        assert results == []

    @pytest.mark.asyncio
    async def test_fan_out_one_failure_does_not_block_others(self):
        t1 = WebhookTarget("wh-fail", "https://fail.example.com/h", "s1", ["nba.created"])
        t2 = WebhookTarget("wh-ok", "https://ok.example.com/h", "s2", ["nba.created"])

        with respx.mock:
            respx.post("https://fail.example.com/h").mock(
                side_effect=httpx.NetworkError("connection refused")
            )
            respx.post("https://ok.example.com/h").mock(return_value=httpx.Response(200))
            results = await fan_out([t1, t2], "nba.created", "tenant", {}, max_retries=1)

        assert len(results) == 2
        fail_r = next(r for r in results if r.webhook_id == "wh-fail")
        ok_r = next(r for r in results if r.webhook_id == "wh-ok")
        assert fail_r.success is False
        assert ok_r.success is True

    @pytest.mark.asyncio
    async def test_delivery_within_timeout_budget(self):
        """All successful deliveries must complete within 5 seconds (DoD requirement)."""
        import time
        targets = [
            WebhookTarget(f"wh-{i}", f"https://fast{i}.example.com/h", "s", ["nba.created"])
            for i in range(3)
        ]

        with respx.mock:
            for t in targets:
                respx.post(t.target_url).mock(return_value=httpx.Response(200))

            start = time.perf_counter()
            results = await fan_out(targets, "nba.created", "tenant", {})
            elapsed = time.perf_counter() - start

        assert all(r.success for r in results)
        assert elapsed < 5.0, f"fan_out took {elapsed:.2f}s — must complete in < 5s"
