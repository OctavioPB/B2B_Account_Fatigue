"""Tests for orchestrator.actions.dispatcher — ActionDispatcher stubs."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orchestrator.actions.dispatcher import (
    ActionDispatcher,
    CompositeDispatcher,
    DispatchResult,
    HubSpotDispatcher,
    SalesloftDispatcher,
    SlackDispatcher,
)
from orchestrator.models import ActionType, DispatchResult as ModelDispatchResult, NextBestAction

_NOW = datetime(2024, 7, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_action(action_type: ActionType = ActionType.NURTURE, **kwargs) -> NextBestAction:
    defaults = dict(
        account_id="test-account-uuid",
        account_domain="acme.com",
        action_type=action_type,
        rationale="Unit test action",
        fatigue_score=30.0,
        intent_score=55.0,
        churn_probability=0.15,
        created_at=_NOW,
    )
    defaults.update(kwargs)
    return NextBestAction(**defaults)


# ===========================================================================
# ActionDispatcher ABC
# ===========================================================================


class TestActionDispatcherInterface:
    def test_dispatcher_is_abstract(self):
        with pytest.raises(TypeError):
            ActionDispatcher()  # type: ignore[abstract]

    def test_all_stubs_subclass_dispatcher(self):
        for cls in (HubSpotDispatcher, SalesloftDispatcher, SlackDispatcher):
            assert issubclass(cls, ActionDispatcher)

    def test_stubs_implement_all_abstract_methods(self):
        for cls in (HubSpotDispatcher, SalesloftDispatcher, SlackDispatcher):
            d = cls()
            assert hasattr(d, "dispatch")
            assert hasattr(d, "cancel")
            assert hasattr(d, "platform_name")


# ===========================================================================
# HubSpotDispatcher
# ===========================================================================


class TestHubSpotDispatcher:
    def setup_method(self):
        self.d = HubSpotDispatcher()

    def test_platform_name(self):
        assert self.d.platform_name == "hubspot"

    @pytest.mark.parametrize("action_type", list(ActionType))
    def test_dispatch_succeeds_for_all_action_types(self, action_type):
        result = self.d.dispatch(_make_action(action_type))
        assert result.success is True

    def test_dispatch_returns_dispatch_result(self):
        result = self.d.dispatch(_make_action())
        assert isinstance(result, DispatchResult)

    def test_dispatch_returns_external_id(self):
        result = self.d.dispatch(_make_action(ActionType.EXEC_ESCALATION))
        assert result.external_id is not None
        assert result.external_id.startswith("hs-task-")

    def test_dispatch_platform_name_in_result(self):
        result = self.d.dispatch(_make_action())
        assert result.platform == "hubspot"

    def test_cancel_returns_true(self):
        assert self.d.cancel("some-action-id") is True

    def test_dispatch_cooldown_action(self):
        result = self.d.dispatch(_make_action(ActionType.COOLDOWN))
        assert result.success is True


# ===========================================================================
# SalesloftDispatcher
# ===========================================================================


class TestSalesloftDispatcher:
    def setup_method(self):
        self.d = SalesloftDispatcher()

    def test_platform_name(self):
        assert self.d.platform_name == "salesloft"

    def test_cooldown_is_skipped_not_cadenced(self):
        result = self.d.dispatch(_make_action(ActionType.COOLDOWN))
        assert result.success is True
        assert result.external_id is None
        assert "skipped" in result.message.lower() or "cooldown" in result.message.lower()

    @pytest.mark.parametrize("action_type", [
        ActionType.DEAL_REVIEW,
        ActionType.EXEC_ESCALATION,
        ActionType.PRICING_TRIGGER,
        ActionType.ACCELERATE,
        ActionType.RE_ENGAGE,
        ActionType.NURTURE,
    ])
    def test_non_cooldown_returns_enrollment_id(self, action_type):
        result = self.d.dispatch(_make_action(action_type))
        assert result.success is True
        assert result.external_id is not None
        assert result.external_id.startswith("sl-enroll-")

    def test_dispatch_platform_name_in_result(self):
        result = self.d.dispatch(_make_action(ActionType.RE_ENGAGE))
        assert result.platform == "salesloft"

    def test_cancel_returns_true(self):
        assert self.d.cancel("some-action-id") is True


# ===========================================================================
# SlackDispatcher
# ===========================================================================


class TestSlackDispatcher:
    def setup_method(self):
        self.d = SlackDispatcher()

    def test_platform_name(self):
        assert self.d.platform_name == "slack"

    @pytest.mark.parametrize("action_type", list(ActionType))
    def test_dispatch_succeeds_for_all_action_types(self, action_type):
        result = self.d.dispatch(_make_action(action_type))
        assert result.success is True

    def test_dispatch_returns_message_timestamp(self):
        result = self.d.dispatch(_make_action(ActionType.COOLDOWN))
        assert result.external_id is not None

    def test_cancel_returns_false(self):
        # Slack messages are informational — not cancelled
        assert self.d.cancel("some-action-id") is False

    def test_dispatch_platform_name_in_result(self):
        result = self.d.dispatch(_make_action())
        assert result.platform == "slack"


# ===========================================================================
# CompositeDispatcher
# ===========================================================================


class TestCompositeDispatcher:
    def setup_method(self):
        self.composite = CompositeDispatcher([
            HubSpotDispatcher(),
            SalesloftDispatcher(),
            SlackDispatcher(),
        ])

    def test_dispatch_all_returns_three_results(self):
        results = self.composite.dispatch_all(_make_action())
        assert len(results) == 3

    def test_all_results_are_successful(self):
        results = self.composite.dispatch_all(_make_action(ActionType.ACCELERATE))
        assert all(r.success for r in results)

    def test_platforms_in_results(self):
        results = self.composite.dispatch_all(_make_action())
        platforms = {r.platform for r in results}
        assert platforms == {"hubspot", "salesloft", "slack"}

    def test_one_dispatcher_failure_does_not_block_others(self):
        class FailingDispatcher(ActionDispatcher):
            @property
            def platform_name(self):
                return "failing"
            def dispatch(self, action):
                raise RuntimeError("Simulated failure")
            def cancel(self, action_id):
                return False

        composite = CompositeDispatcher([
            FailingDispatcher(),
            SlackDispatcher(),
        ])
        results = composite.dispatch_all(_make_action())
        assert len(results) == 2
        failing_result = next(r for r in results if r.platform == "failing")
        slack_result   = next(r for r in results if r.platform == "slack")
        assert failing_result.success is False
        assert slack_result.success is True

    def test_cancel_all_returns_dict_keyed_by_platform(self):
        result = self.composite.cancel_all("some-action-id")
        assert set(result.keys()) == {"hubspot", "salesloft", "slack"}

    def test_empty_dispatcher_list_returns_empty(self):
        composite = CompositeDispatcher([])
        results = composite.dispatch_all(_make_action())
        assert results == []

    def test_cooldown_action_dispatched_to_all_platforms(self):
        results = self.composite.dispatch_all(_make_action(ActionType.COOLDOWN))
        assert len(results) == 3
        # HubSpot creates a task, Salesloft skips, Slack posts
        hs     = next(r for r in results if r.platform == "hubspot")
        sl     = next(r for r in results if r.platform == "salesloft")
        slack  = next(r for r in results if r.platform == "slack")
        assert hs.success and sl.success and slack.success
        assert sl.external_id is None  # Salesloft skips COOLDOWN
        assert hs.external_id is not None
